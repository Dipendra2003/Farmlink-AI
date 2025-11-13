"""
Tracking Webhooks Module
Handles incoming webhook callbacks from courier APIs
"""
import os
import hmac
import hashlib
import logging
from datetime import datetime
from typing import Dict, Any, Optional
from flask import request
from extensions import db
from models import Order, ShipmentStatusHistory, CourierAPILog

logger = logging.getLogger(__name__)


class WebhookHandler:
    """Handle courier API webhooks"""
    
    # Rate limiting tracking (in-memory for simplicity, use Redis in production)
    _rate_limit_tracker = {}
    _rate_limit_window = 60  # seconds
    _rate_limit_max_requests = 100  # requests per window
    
    # Status mapping from courier codes to system status values
    STATUS_MAPPING = {
        # Shiprocket status codes
        'NEW': 'packed',
        'PICKUP_SCHEDULED': 'packed',
        'PICKUP_COMPLETE': 'shipped',
        'IN_TRANSIT': 'in_transit',
        'OUT_FOR_DELIVERY': 'out_for_delivery',
        'DELIVERED': 'delivered',
        'FAILED': 'failed',
        'RTO': 'returned',
        'CANCELLED': 'cancelled',
        
        # India Post status codes
        'BOOKED': 'packed',
        'DISPATCHED': 'shipped',
        'IN TRANSIT': 'in_transit',
        'OUT FOR DELIVERY': 'out_for_delivery',
        'DELIVERED': 'delivered',
        'DELIVERY FAILED': 'failed',
        'RETURNED': 'returned',
        
        # Generic status codes
        'packed': 'packed',
        'shipped': 'shipped',
        'in_transit': 'in_transit',
        'out_for_delivery': 'out_for_delivery',
        'delivered': 'delivered',
        'failed': 'failed',
        'returned': 'returned',
        'cancelled': 'cancelled'
    }
    
    @staticmethod
    def validate_signature(payload: bytes, signature: str, secret: str) -> bool:
        """
        Validate webhook signature using HMAC-SHA256
        
        Args:
            payload: Raw request body as bytes
            signature: Signature from request header
            secret: Webhook secret from environment
            
        Returns:
            True if signature is valid, False otherwise
        """
        if not signature or not secret:
            logger.warning("Missing signature or secret for webhook validation")
            return False
        
        try:
            # Compute HMAC-SHA256 signature
            computed_signature = hmac.new(
                secret.encode('utf-8'),
                payload,
                hashlib.sha256
            ).hexdigest()
            
            # Compare signatures (constant-time comparison to prevent timing attacks)
            is_valid = hmac.compare_digest(computed_signature, signature)
            
            if is_valid:
                logger.info("Webhook signature validated successfully")
            else:
                logger.warning(f"Invalid webhook signature. Expected: {computed_signature}, Got: {signature}")
            
            return is_valid
            
        except Exception as e:
            logger.error(f"Error validating webhook signature: {str(e)}", exc_info=True)
            return False
    
    @staticmethod
    def check_rate_limit(ip_address: str) -> bool:
        """
        Check if IP address has exceeded rate limit
        
        Args:
            ip_address: Client IP address
            
        Returns:
            True if within rate limit, False if exceeded
        """
        current_time = datetime.utcnow().timestamp()
        
        # Clean up old entries
        WebhookHandler._cleanup_rate_limit_tracker(current_time)
        
        # Get or initialize tracker for this IP
        if ip_address not in WebhookHandler._rate_limit_tracker:
            WebhookHandler._rate_limit_tracker[ip_address] = []
        
        # Get requests in current window
        requests_in_window = [
            req_time for req_time in WebhookHandler._rate_limit_tracker[ip_address]
            if current_time - req_time < WebhookHandler._rate_limit_window
        ]
        
        # Check if limit exceeded
        if len(requests_in_window) >= WebhookHandler._rate_limit_max_requests:
            logger.warning(f"Rate limit exceeded for IP {ip_address}: {len(requests_in_window)} requests in {WebhookHandler._rate_limit_window}s")
            return False
        
        # Add current request
        WebhookHandler._rate_limit_tracker[ip_address] = requests_in_window + [current_time]
        
        return True
    
    @staticmethod
    def _cleanup_rate_limit_tracker(current_time: float):
        """
        Clean up old entries from rate limit tracker
        
        Args:
            current_time: Current timestamp
        """
        # Remove IPs with no recent requests
        ips_to_remove = []
        for ip_address, requests in WebhookHandler._rate_limit_tracker.items():
            recent_requests = [
                req_time for req_time in requests
                if current_time - req_time < WebhookHandler._rate_limit_window * 2
            ]
            if not recent_requests:
                ips_to_remove.append(ip_address)
            else:
                WebhookHandler._rate_limit_tracker[ip_address] = recent_requests
        
        for ip_address in ips_to_remove:
            del WebhookHandler._rate_limit_tracker[ip_address]
    
    @staticmethod
    def log_webhook_attempt(courier_name: str, payload: Dict, success: bool, 
                           error: Optional[str] = None, order_id: Optional[int] = None):
        """
        Log webhook attempt including failed validations
        
        Args:
            courier_name: Name of courier service
            payload: Webhook payload
            success: Whether webhook processing was successful
            error: Error message if failed
            order_id: Order ID if available
        """
        try:
            # Get client IP from request
            ip_address = request.remote_addr if request else 'unknown'
            
            log_entry = CourierAPILog(
                order_id=order_id,
                courier_name=courier_name,
                api_endpoint='webhook',
                http_method='POST',
                request_payload=str(payload),
                response_status_code=200 if success else 400,
                response_payload='Webhook processed successfully' if success else error,
                error_message=error if not success else None,
                created_at=datetime.utcnow()
            )
            
            db.session.add(log_entry)
            db.session.commit()
            
            logger.info(f"Logged webhook attempt from {courier_name} (IP: {ip_address}, Success: {success})")
            
        except Exception as e:
            logger.error(f"Failed to log webhook attempt: {str(e)}", exc_info=True)
            # Don't raise exception - logging failure shouldn't break webhook processing
    
    @staticmethod
    def process_shiprocket_webhook(payload: Dict) -> Dict[str, Any]:
        """
        Process Shiprocket webhook payload
        
        Args:
            payload: Webhook JSON payload from Shiprocket
            
        Returns:
            Dict with processing result
        """
        try:
            logger.info(f"Processing Shiprocket webhook: {payload}")
            
            # Extract tracking information from Shiprocket payload
            # Shiprocket webhook structure (example):
            # {
            #     "order_id": "12345",
            #     "awb": "AWB123456",
            #     "current_status": "IN_TRANSIT",
            #     "shipment_status": "IN_TRANSIT",
            #     "status_code": "6",
            #     "status": "In Transit",
            #     "location": "Mumbai Hub",
            #     "timestamp": "2024-11-11 14:30:00",
            #     "remarks": "Package in transit"
            # }
            
            # Get order by courier_order_id or AWB code
            courier_order_id = payload.get('order_id') or payload.get('shipment_id')
            awb_code = payload.get('awb') or payload.get('awb_code')
            
            order = None
            if courier_order_id:
                order = Order.query.filter_by(courier_order_id=str(courier_order_id)).first()
            
            if not order and awb_code:
                order = Order.query.filter_by(awb_code=awb_code).first()
            
            if not order:
                error_msg = f"Order not found for Shiprocket webhook (order_id: {courier_order_id}, awb: {awb_code})"
                logger.warning(error_msg)
                WebhookHandler.log_webhook_attempt('shiprocket', payload, False, error_msg)
                return {
                    'success': False,
                    'error': error_msg
                }
            
            # Extract status information
            courier_status = (payload.get('current_status') or 
                            payload.get('shipment_status') or 
                            payload.get('status', '')).upper()
            
            # Map courier status to system status
            system_status = WebhookHandler.STATUS_MAPPING.get(courier_status)
            
            if not system_status:
                logger.warning(f"Unknown Shiprocket status code: {courier_status}")
                system_status = order.shipment_status or 'in_transit'
            
            # Extract additional details
            status_description = payload.get('remarks') or payload.get('status') or courier_status
            location = payload.get('location') or payload.get('current_location')
            
            # Parse timestamp
            courier_timestamp = None
            timestamp_str = payload.get('timestamp') or payload.get('updated_at')
            if timestamp_str:
                try:
                    # Try multiple timestamp formats
                    for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M:%S.%fZ']:
                        try:
                            courier_timestamp = datetime.strptime(timestamp_str, fmt)
                            break
                        except ValueError:
                            continue
                except Exception as e:
                    logger.warning(f"Failed to parse timestamp '{timestamp_str}': {str(e)}")
            
            # Update order status
            status_details = {
                'status': system_status,
                'description': status_description,
                'location': location,
                'courier_timestamp': courier_timestamp,
                'courier_data': payload
            }
            
            result = WebhookHandler.update_order_status(
                order.tracking_number,
                system_status,
                status_details
            )
            
            if result:
                WebhookHandler.log_webhook_attempt('shiprocket', payload, True, None, order.id)
                logger.info(f"Successfully processed Shiprocket webhook for order {order.id}")
                return {
                    'success': True,
                    'order_id': order.id,
                    'tracking_number': order.tracking_number,
                    'new_status': system_status
                }
            else:
                error_msg = "Failed to update order status"
                WebhookHandler.log_webhook_attempt('shiprocket', payload, False, error_msg, order.id)
                return {
                    'success': False,
                    'error': error_msg
                }
                
        except Exception as e:
            error_msg = f"Error processing Shiprocket webhook: {str(e)}"
            logger.error(error_msg, exc_info=True)
            WebhookHandler.log_webhook_attempt('shiprocket', payload, False, error_msg)
            return {
                'success': False,
                'error': error_msg
            }

    @staticmethod
    def process_indiapost_webhook(payload: Dict) -> Dict[str, Any]:
        """
        Process India Post webhook payload
        
        Args:
            payload: Webhook JSON payload from India Post
            
        Returns:
            Dict with processing result
        """
        try:
            logger.info(f"Processing India Post webhook: {payload}")
            
            # Extract tracking information from India Post payload
            # India Post webhook structure (example):
            # {
            #     "consignment_number": "EP123456789IN",
            #     "status": "IN TRANSIT",
            #     "status_code": "IT",
            #     "location": "Delhi GPO",
            #     "timestamp": "2024-11-11T14:30:00Z",
            #     "description": "Item in transit",
            #     "event_type": "status_update"
            # }
            
            # Get order by AWB code or tracking number
            consignment_number = payload.get('consignment_number') or payload.get('tracking_number')
            
            order = None
            if consignment_number:
                # Try to find by AWB code first
                order = Order.query.filter_by(awb_code=consignment_number).first()
                
                # If not found, try by tracking number
                if not order:
                    order = Order.query.filter_by(tracking_number=consignment_number).first()
            
            if not order:
                error_msg = f"Order not found for India Post webhook (consignment: {consignment_number})"
                logger.warning(error_msg)
                WebhookHandler.log_webhook_attempt('india_post', payload, False, error_msg)
                return {
                    'success': False,
                    'error': error_msg
                }
            
            # Extract status information
            courier_status = (payload.get('status') or payload.get('event_type', '')).upper()
            
            # Map courier status to system status
            system_status = WebhookHandler.STATUS_MAPPING.get(courier_status)
            
            if not system_status:
                logger.warning(f"Unknown India Post status code: {courier_status}")
                system_status = order.shipment_status or 'in_transit'
            
            # Extract additional details
            status_description = payload.get('description') or payload.get('status') or courier_status
            location = payload.get('location') or payload.get('office')
            
            # Parse timestamp
            courier_timestamp = None
            timestamp_str = payload.get('timestamp') or payload.get('event_time')
            if timestamp_str:
                try:
                    # Try multiple timestamp formats
                    for fmt in ['%Y-%m-%dT%H:%M:%SZ', '%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S']:
                        try:
                            courier_timestamp = datetime.strptime(timestamp_str, fmt)
                            break
                        except ValueError:
                            continue
                except Exception as e:
                    logger.warning(f"Failed to parse timestamp '{timestamp_str}': {str(e)}")
            
            # Update order status
            status_details = {
                'status': system_status,
                'description': status_description,
                'location': location,
                'courier_timestamp': courier_timestamp,
                'courier_data': payload
            }
            
            result = WebhookHandler.update_order_status(
                order.tracking_number,
                system_status,
                status_details
            )
            
            if result:
                WebhookHandler.log_webhook_attempt('india_post', payload, True, None, order.id)
                logger.info(f"Successfully processed India Post webhook for order {order.id}")
                return {
                    'success': True,
                    'order_id': order.id,
                    'tracking_number': order.tracking_number,
                    'new_status': system_status
                }
            else:
                error_msg = "Failed to update order status"
                WebhookHandler.log_webhook_attempt('india_post', payload, False, error_msg, order.id)
                return {
                    'success': False,
                    'error': error_msg
                }
                
        except Exception as e:
            error_msg = f"Error processing India Post webhook: {str(e)}"
            logger.error(error_msg, exc_info=True)
            WebhookHandler.log_webhook_attempt('india_post', payload, False, error_msg)
            return {
                'success': False,
                'error': error_msg
            }
    
    @staticmethod
    def update_order_status(tracking_number: str, new_status: str, 
                          status_details: Dict[str, Any]) -> bool:
        """
        Update order status and create ShipmentStatusHistory entry
        
        Args:
            tracking_number: Tracking number
            new_status: New shipment status
            status_details: Additional status information including:
                - description: Status description
                - location: Current location
                - courier_timestamp: Timestamp from courier
                - courier_data: Raw courier data
            
        Returns:
            True if update successful, False otherwise
        """
        try:
            # Find order by tracking number
            order = Order.query.filter_by(tracking_number=tracking_number).first()
            
            if not order:
                logger.error(f"Order not found with tracking number: {tracking_number}")
                return False
            
            # Get old status
            old_status = order.shipment_status
            
            # Check if status actually changed
            if old_status == new_status:
                logger.info(f"Status unchanged for order {order.id}: {new_status}")
                # Still create history entry for tracking purposes
            else:
                logger.info(f"Updating order {order.id} status from '{old_status}' to '{new_status}'")
            
            # Update order shipment status
            order.shipment_status = new_status
            order.last_api_sync = datetime.utcnow()
            order.api_sync_status = 'synced'
            
            # Update specific fields based on status
            if new_status == 'shipped' and not order.shipped_at:
                order.shipped_at = datetime.utcnow()
                # Also update order status if still pending/confirmed
                if order.status in ['pending', 'confirmed', 'processing']:
                    order.status = 'shipped'
            
            elif new_status == 'delivered':
                # Check seller KYC status before allowing delivery completion (payment release)
                from kyc_service import KYCService
                if not KYCService.is_seller_verified(order.farmer_id):
                    logger.warning(f"Order {order.id} delivery blocked: Seller {order.farmer_id} KYC not verified")
                    # Don't update to delivered status, keep current status
                    # Add note to shipment history about KYC requirement
                    order.delivery_failure_reason = 'Payment on hold pending seller KYC verification'
                else:
                    order.actual_delivery_date = datetime.utcnow()
                    order.status = 'delivered'
                    order.delivered_at = datetime.utcnow()
            
            elif new_status == 'failed':
                order.delivery_failure_reason = status_details.get('description', 'Delivery failed')
                order.delivery_attempts += 1
            
            elif new_status == 'returned':
                order.status = 'cancelled'
                order.cancellation_reason = 'Shipment returned to sender'
            
            # Create shipment status history entry
            history_entry = ShipmentStatusHistory(
                order_id=order.id,
                tracking_number=tracking_number,
                old_status=old_status,
                new_status=new_status,
                status_description=status_details.get('description'),
                location=status_details.get('location'),
                updated_by_source='webhook',
                courier_timestamp=status_details.get('courier_timestamp'),
                created_at=datetime.utcnow()
            )
            
            db.session.add(history_entry)
            
            # Commit changes
            db.session.commit()
            
            logger.info(f"Successfully updated order {order.id} to status '{new_status}'")
            
            # Trigger notification service for important status changes
            WebhookHandler._trigger_notifications(order, old_status, new_status)
            
            return True
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error updating order status for {tracking_number}: {str(e)}", exc_info=True)
            return False
    
    @staticmethod
    def _trigger_notifications(order: Order, old_status: str, new_status: str):
        """
        Trigger notification service when status changes
        
        Args:
            order: Order object
            old_status: Previous status
            new_status: New status
        """
        try:
            # Import notification service
            from tracking_notifications import TrackingNotificationService
            
            # Send notifications for specific status changes
            if new_status == 'shipped' and old_status != 'shipped':
                TrackingNotificationService.send_shipment_created_notification(order)
            
            elif new_status == 'in_transit' and old_status != 'in_transit':
                TrackingNotificationService.send_status_update_notification(order, old_status, new_status)
            
            elif new_status == 'out_for_delivery' and old_status != 'out_for_delivery':
                TrackingNotificationService.send_status_update_notification(order, old_status, new_status)
                # Also send SMS for out for delivery
                if order.buyer.phone:
                    message = f"Your order #{order.id} is out for delivery. Track: {order.courier_tracking_url}"
                    TrackingNotificationService.send_sms_notification(order.buyer.phone, message)
            
            elif new_status == 'delivered' and old_status != 'delivered':
                TrackingNotificationService.send_delivery_notification(order)
            
            elif new_status == 'failed' and old_status != 'failed':
                failure_reason = order.delivery_failure_reason or 'Unknown reason'
                TrackingNotificationService.send_failed_delivery_notification(order, failure_reason)
            
            logger.info(f"Triggered notifications for order {order.id} status change: {old_status} -> {new_status}")
            
        except ImportError:
            logger.warning("Notification service not available, skipping notifications")
        except Exception as e:
            logger.error(f"Error triggering notifications for order {order.id}: {str(e)}", exc_info=True)
            # Don't raise exception - notification failure shouldn't break webhook processing
