"""
Tracking Jobs Module
Background jobs for shipment tracking system
"""
from datetime import datetime, timedelta, date
from typing import List, Dict, Any
import logging
import os
from flask import current_app
from extensions import db
from models import Order, ShipmentStatusHistory
from tracking_service import TrackingService

logger = logging.getLogger(__name__)


class TrackingJobs:
    """Background jobs for tracking system"""
    
    @staticmethod
    def sync_active_shipments() -> Dict[str, Any]:
        """
        Poll courier APIs for all active shipments
        Runs every 4 hours
        
        Returns:
            Dict with sync results including success count, failure count, and errors
        """
        logger.info("Starting sync_active_shipments job")
        
        try:
            # Query all orders with active shipments (not delivered, cancelled, or returned)
            active_statuses = ['packed', 'shipped', 'in_transit', 'out_for_delivery']
            active_orders = Order.query.filter(
                Order.shipment_status.in_(active_statuses),
                Order.tracking_number.isnot(None),
                Order.courier_name.isnot(None)
            ).all()
            
            logger.info(f"Found {len(active_orders)} active shipments to sync")
            
            success_count = 0
            failure_count = 0
            errors = []
            
            # Batch process orders to respect rate limits
            batch_size = 10
            for i in range(0, len(active_orders), batch_size):
                batch = active_orders[i:i + batch_size]
                
                for order in batch:
                    try:
                        # Fetch current status from courier API
                        status_data = TrackingService.get_shipment_status(
                            order.tracking_number,
                            order.courier_name
                        )
                        
                        if status_data.get('success'):
                            # Update order with latest status
                            courier_data = status_data.get('courier_data', {})
                            new_status = courier_data.get('status')
                            
                            if new_status and new_status != order.shipment_status:
                                # Status has changed, update order
                                old_status = order.shipment_status
                                order.shipment_status = new_status
                                order.last_api_sync = datetime.utcnow()
                                order.api_sync_status = 'synced'
                                
                                # Update estimated delivery date if provided
                                if courier_data.get('estimated_delivery'):
                                    order.estimated_delivery_date = courier_data.get('estimated_delivery')
                                
                                # Create shipment status history entry
                                history_entry = ShipmentStatusHistory(
                                    order_id=order.id,
                                    tracking_number=order.tracking_number,
                                    old_status=old_status,
                                    new_status=new_status,
                                    status_description=courier_data.get('status_description', f'Status updated to {new_status}'),
                                    location=courier_data.get('location'),
                                    updated_by_source='polling',
                                    courier_timestamp=courier_data.get('timestamp', datetime.utcnow())
                                )
                                db.session.add(history_entry)
                                
                                # Update order status if delivered
                                if new_status == 'delivered':
                                    # Check seller KYC status before allowing delivery completion
                                    from kyc_service import KYCService
                                    if KYCService.is_seller_verified(order.farmer_id):
                                        order.status = 'delivered'
                                        order.delivered_at = datetime.utcnow()
                                        order.actual_delivery_date = datetime.utcnow()
                                    else:
                                        logger.warning(f"Order {order.id} delivery blocked in sync job: Seller {order.farmer_id} KYC not verified")
                                        order.delivery_failure_reason = 'Payment on hold pending seller KYC verification'
                                
                                logger.info(f"Updated order {order.id} status from {old_status} to {new_status}")
                            else:
                                # No status change, just update sync timestamp
                                order.last_api_sync = datetime.utcnow()
                                order.api_sync_status = 'synced'
                            
                            success_count += 1
                        else:
                            # API call failed
                            order.api_sync_status = 'failed'
                            failure_count += 1
                            error_msg = f"Order {order.id}: {status_data.get('error', 'Unknown error')}"
                            errors.append(error_msg)
                            logger.warning(error_msg)
                    
                    except Exception as e:
                        failure_count += 1
                        error_msg = f"Order {order.id}: {str(e)}"
                        errors.append(error_msg)
                        logger.error(f"Error syncing order {order.id}: {str(e)}", exc_info=True)
                        
                        # Mark sync as failed
                        order.api_sync_status = 'failed'
                
                # Commit batch
                try:
                    db.session.commit()
                    logger.info(f"Committed batch {i // batch_size + 1}")
                except Exception as e:
                    db.session.rollback()
                    logger.error(f"Error committing batch: {str(e)}", exc_info=True)
            
            result = {
                'success': True,
                'total_orders': len(active_orders),
                'success_count': success_count,
                'failure_count': failure_count,
                'errors': errors[:10],  # Limit to first 10 errors
                'completed_at': datetime.utcnow()
            }
            
            logger.info(f"Completed sync_active_shipments job: {success_count} succeeded, {failure_count} failed")
            return result
            
        except Exception as e:
            logger.error(f"Fatal error in sync_active_shipments job: {str(e)}", exc_info=True)
            return {
                'success': False,
                'error': str(e),
                'completed_at': datetime.utcnow()
            }

    @staticmethod
    def auto_confirm_deliveries() -> Dict[str, Any]:
        """
        Auto-confirm deliveries after 7 days
        Runs daily at midnight
        
        Returns:
            Dict with confirmation results
        """
        from app import app
        
        with app.app_context():
            logger.info("Starting auto_confirm_deliveries job")
            
            try:
                # Calculate cutoff date (7 days ago)
                cutoff_date = datetime.utcnow() - timedelta(days=7)
                
                # Query orders that are delivered but not confirmed by buyer
                # and were delivered more than 7 days ago
                orders_to_confirm = Order.query.filter(
                    Order.shipment_status == 'delivered',
                    Order.delivery_confirmed_by_buyer == False,
                    Order.delivery_confirmation_date.is_(None),
                    Order.delivered_at.isnot(None),
                    Order.delivered_at < cutoff_date
                ).all()
                
                logger.info(f"Found {len(orders_to_confirm)} orders to auto-confirm")
                
                confirmed_count = 0
                
                for order in orders_to_confirm:
                    try:
                        # Auto-confirm delivery
                        order.delivery_confirmed_by_buyer = True
                        order.delivery_confirmation_date = datetime.utcnow()
                        
                        # Create shipment status history entry
                        history_entry = ShipmentStatusHistory(
                            order_id=order.id,
                            tracking_number=order.tracking_number,
                            old_status='delivered',
                            new_status='delivered',
                            status_description='Delivery auto-confirmed after 7 days',
                            location=None,
                            updated_by_source='system',
                            courier_timestamp=datetime.utcnow()
                        )
                        db.session.add(history_entry)
                        
                        confirmed_count += 1
                        logger.info(f"Auto-confirmed delivery for order {order.id}")
                        
                    except Exception as e:
                        logger.error(f"Error auto-confirming order {order.id}: {str(e)}", exc_info=True)
                
                # Commit all changes
                try:
                    db.session.commit()
                    logger.info(f"Committed {confirmed_count} auto-confirmations")
                except Exception as e:
                    db.session.rollback()
                    logger.error(f"Error committing auto-confirmations: {str(e)}", exc_info=True)
                    raise
                
                result = {
                    'success': True,
                    'total_confirmed': confirmed_count,
                    'completed_at': datetime.utcnow()
                }
                
                logger.info(f"Completed auto_confirm_deliveries job: {confirmed_count} orders confirmed")
                return result
                
            except Exception as e:
                logger.error(f"Fatal error in auto_confirm_deliveries job: {str(e)}", exc_info=True)
                return {
                    'success': False,
                'error': str(e),
                'completed_at': datetime.utcnow()
            }
    
    @staticmethod
    def send_delivery_reminders() -> Dict[str, Any]:
        """
        Send reminders for pending delivery confirmations
        Runs daily at 9 AM
        
        Returns:
            Dict with reminder results
        """
        logger.info("Starting send_delivery_reminders job")
        
        try:
            # Calculate date range for reminders (delivered 3-6 days ago)
            # This gives buyers time to receive but reminds them before auto-confirmation
            min_date = datetime.utcnow() - timedelta(days=6)
            max_date = datetime.utcnow() - timedelta(days=3)
            
            # Query orders that need confirmation reminders
            orders_needing_reminder = Order.query.filter(
                Order.shipment_status == 'delivered',
                Order.delivery_confirmed_by_buyer == False,
                Order.delivery_confirmation_date.is_(None),
                Order.delivered_at.isnot(None),
                Order.delivered_at.between(min_date, max_date)
            ).all()
            
            logger.info(f"Found {len(orders_needing_reminder)} orders needing delivery confirmation reminders")
            
            reminder_sent_count = 0
            reminder_failed_count = 0
            
            for order in orders_needing_reminder:
                try:
                    # Import email service
                    from email_service import EmailService
                    email_service = EmailService()
                    
                    # Calculate days since delivery
                    days_since_delivery = (datetime.utcnow() - order.delivered_at).days
                    days_until_auto_confirm = 7 - days_since_delivery
                    
                    # Send reminder email to buyer
                    buyer = order.buyer
                    subject = f"Confirm Delivery - Order #{order.id}"
                    
                    html_content = f"""
                    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                        <div style="background: #17a2b8; padding: 20px; text-align: center;">
                            <h1 style="color: white; margin: 0;">📦 Delivery Confirmation Reminder</h1>
                        </div>
                        
                        <div style="padding: 30px;">
                            <h2>Hello {buyer.full_name or buyer.username},</h2>
                            
                            <p>Your order was delivered {days_since_delivery} days ago. Please confirm that you received it.</p>
                            
                            <div style="background: #f8f9fa; padding: 20px; border-radius: 10px; margin: 20px 0;">
                                <h3 style="color: #17a2b8;">Order Details:</h3>
                                <p><strong>Order ID:</strong> #{order.id}</p>
                                <p><strong>Crop:</strong> {order.crop.name}</p>
                                <p><strong>Quantity:</strong> {order.quantity_requested} {order.crop.unit}</p>
                                <p><strong>Delivered On:</strong> {order.delivered_at.strftime('%B %d, %Y')}</p>
                                <p><strong>Tracking Number:</strong> {order.tracking_number}</p>
                            </div>
                            
                            <div style="background: #fff3cd; border: 1px solid #ffeaa7; padding: 15px; border-radius: 5px; margin: 20px 0;">
                                <p style="margin: 0;"><strong>Note:</strong> If you don't confirm within {days_until_auto_confirm} days, the delivery will be automatically confirmed.</p>
                            </div>
                            
                            <div style="text-align: center; margin: 30px 0;">
                                <a href="{os.environ.get('BASE_URL', 'http://localhost:5000')}/orders/{order.id}/confirm-delivery" 
                                   style="background: #28a745; color: white; padding: 15px 30px; text-decoration: none; border-radius: 5px; display: inline-block; margin: 5px;">
                                    Confirm Delivery
                                </a>
                                <a href="{os.environ.get('BASE_URL', 'http://localhost:5000')}/orders/{order.id}" 
                                   style="background: #17a2b8; color: white; padding: 15px 30px; text-decoration: none; border-radius: 5px; display: inline-block; margin: 5px;">
                                    View Order
                                </a>
                            </div>
                            
                            <p>If you have any issues with your order, please contact the farmer or our support team.</p>
                            
                            <p>Thank you for using FarmLink AI!<br>The FarmLink AI Team</p>
                        </div>
                        
                        <div style="background: #343a40; color: white; padding: 20px; text-align: center;">
                            <p style="margin: 0;">© 2024 FarmLink AI. Connecting Agriculture, Powering Growth.</p>
                        </div>
                    </div>
                    """
                    
                    result = email_service.send_email(buyer.email, subject, html_content)
                    
                    if result.get('success'):
                        reminder_sent_count += 1
                        logger.info(f"Sent delivery confirmation reminder for order {order.id}")
                    else:
                        reminder_failed_count += 1
                        logger.warning(f"Failed to send reminder for order {order.id}: {result.get('error')}")
                    
                except Exception as e:
                    reminder_failed_count += 1
                    logger.error(f"Error sending reminder for order {order.id}: {str(e)}", exc_info=True)
            
            result = {
                'success': True,
                'total_orders': len(orders_needing_reminder),
                'reminders_sent': reminder_sent_count,
                'reminders_failed': reminder_failed_count,
                'completed_at': datetime.utcnow()
            }
            
            logger.info(f"Completed send_delivery_reminders job: {reminder_sent_count} sent, {reminder_failed_count} failed")
            return result
            
        except Exception as e:
            logger.error(f"Fatal error in send_delivery_reminders job: {str(e)}", exc_info=True)
            return {
                'success': False,
                'error': str(e),
                'completed_at': datetime.utcnow()
            }
    
    @staticmethod
    def cleanup_old_tracking_data() -> Dict[str, Any]:
        """
        Archive tracking data older than 1 year
        Runs monthly
        
        Returns:
            Dict with cleanup results
        """
        logger.info("Starting cleanup_old_tracking_data job")
        
        try:
            # Calculate cutoff date (1 year ago)
            cutoff_date = datetime.utcnow() - timedelta(days=365)
            
            # Query old shipment status history entries
            old_history_entries = ShipmentStatusHistory.query.filter(
                ShipmentStatusHistory.created_at < cutoff_date
            ).all()
            
            logger.info(f"Found {len(old_history_entries)} old tracking history entries to archive")
            
            # For now, we'll just log the count
            # In a production system, you might want to:
            # 1. Export to archive storage (S3, etc.)
            # 2. Create compressed backup
            # 3. Then delete from active database
            
            # Example: Delete old entries (uncomment if you want to actually delete)
            # deleted_count = 0
            # for entry in old_history_entries:
            #     try:
            #         db.session.delete(entry)
            #         deleted_count += 1
            #     except Exception as e:
            #         logger.error(f"Error deleting history entry {entry.id}: {str(e)}")
            # 
            # db.session.commit()
            # logger.info(f"Deleted {deleted_count} old tracking history entries")
            
            # For now, just mark as archived (you could add an 'archived' flag to the model)
            archived_count = len(old_history_entries)
            
            result = {
                'success': True,
                'entries_found': archived_count,
                'entries_archived': 0,  # Set to archived_count if actually archiving
                'cutoff_date': cutoff_date,
                'completed_at': datetime.utcnow(),
                'note': 'Cleanup job identified old entries but did not delete them. Implement archival strategy as needed.'
            }
            
            logger.info(f"Completed cleanup_old_tracking_data job: {archived_count} entries identified for archival")
            return result
            
        except Exception as e:
            logger.error(f"Fatal error in cleanup_old_tracking_data job: {str(e)}", exc_info=True)
            return {
                'success': False,
                'error': str(e),
                'completed_at': datetime.utcnow()
            }
