"""
Tracking Notification Service
Handles tracking-related notifications via email and SMS
"""
import os
import logging
from datetime import datetime
from typing import Optional
from models import Order

logger = logging.getLogger(__name__)


class TrackingNotificationService:
    """Handle tracking notifications"""
    
    @staticmethod
    def send_shipment_created_notification(order: Order):
        """
        Send notification when shipment is created
        
        Args:
            order: Order object
        """
        try:
            from email_service import EmailService
            
            email_service = EmailService()
            buyer = order.buyer
            
            subject = f"Shipment Created - Order #{order.id}"
            
            # Format estimated delivery date
            estimated_delivery = "Not available"
            if order.estimated_delivery_date:
                estimated_delivery = order.estimated_delivery_date.strftime('%B %d, %Y')
            
            html_content = f"""
            <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                <div style="background: #28a745; padding: 20px; text-align: center;">
                    <h1 style="color: white; margin: 0;">📦 Your Order Has Been Shipped!</h1>
                </div>
                
                <div style="padding: 30px;">
                    <h2>Hello {buyer.full_name or buyer.username},</h2>
                    
                    <p>Great news! Your order has been shipped and is on its way to you.</p>
                    
                    <div style="background: #f8f9fa; padding: 20px; border-radius: 10px; margin: 20px 0;">
                        <h3 style="color: #28a745;">Shipment Details:</h3>
                        <p><strong>Order ID:</strong> #{order.id}</p>
                        <p><strong>Tracking Number:</strong> {order.tracking_number}</p>
                        <p><strong>Courier:</strong> {order.courier_name.title() if order.courier_name else 'N/A'}</p>
                        <p><strong>Estimated Delivery:</strong> {estimated_delivery}</p>
                        <p><strong>Crop:</strong> {order.crop.name}</p>
                        <p><strong>Quantity:</strong> {order.quantity_requested} {order.crop.unit}</p>
                    </div>
                    
                    <div style="text-align: center; margin: 30px 0;">
                        <a href="{os.environ.get('BASE_URL', 'http://localhost:5000')}/orders/{order.id}/track" 
                           style="background: #28a745; color: white; padding: 15px 30px; text-decoration: none; border-radius: 5px; display: inline-block; margin: 5px;">
                            Track Your Order
                        </a>
                        {f'''<a href="{order.courier_tracking_url}" 
                           style="background: #17a2b8; color: white; padding: 15px 30px; text-decoration: none; border-radius: 5px; display: inline-block; margin: 5px;">
                            Track on Courier Website
                        </a>''' if order.courier_tracking_url else ''}
                    </div>
                    
                    <p>You can track your order in real-time using the tracking number above.</p>
                    
                    <p>Thank you for choosing FarmLink AI!<br>The FarmLink AI Team</p>
                </div>
                
                <div style="background: #343a40; color: white; padding: 20px; text-align: center;">
                    <p style="margin: 0;">© 2024 FarmLink AI. Connecting Agriculture, Powering Growth.</p>
                </div>
            </div>
            """
            
            result = email_service.send_email(buyer.email, subject, html_content)
            
            if result.get('success'):
                logger.info(f"Sent shipment created notification for order {order.id} to {buyer.email}")
            else:
                logger.error(f"Failed to send shipment created notification for order {order.id}: {result.get('error')}")
            
            return result
            
        except Exception as e:
            logger.error(f"Error sending shipment created notification for order {order.id}: {str(e)}", exc_info=True)
            return {'success': False, 'error': str(e)}
    
    @staticmethod
    def send_status_update_notification(order: Order, old_status: str, new_status: str):
        """
        Send notification when status changes (email and SMS for out_for_delivery)
        
        Args:
            order: Order object
            old_status: Previous status
            new_status: New status
        """
        try:
            from email_service import EmailService
            from datetime import timedelta
            
            email_service = EmailService()
            buyer = order.buyer
            
            # Status display names
            status_names = {
                'packed': 'Packed',
                'shipped': 'Shipped',
                'in_transit': 'In Transit',
                'out_for_delivery': 'Out for Delivery',
                'delivered': 'Delivered',
                'failed': 'Delivery Failed',
                'returned': 'Returned',
                'cancelled': 'Cancelled'
            }
            
            status_display = status_names.get(new_status, new_status.title())
            
            subject = f"Order Status Update - {status_display}"
            
            # Status-specific messages
            status_messages = {
                'in_transit': 'Your order is currently in transit and moving towards you.',
                'out_for_delivery': 'Your order is out for delivery and will reach you soon!',
            }
            
            status_message = status_messages.get(new_status, f'Your order status has been updated to {status_display}.')
            
            # Calculate expected delivery time for out_for_delivery status
            expected_delivery_time = ""
            if new_status == 'out_for_delivery':
                if order.estimated_delivery_date:
                    expected_delivery_time = f"<p><strong>Expected Delivery:</strong> {order.estimated_delivery_date.strftime('%B %d, %Y')}</p>"
                else:
                    # Estimate delivery within 24 hours if no date is set
                    expected_delivery_time = "<p><strong>Expected Delivery:</strong> Today</p>"
            
            html_content = f"""
            <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                <div style="background: #17a2b8; padding: 20px; text-align: center;">
                    <h1 style="color: white; margin: 0;">📍 Order Status Update</h1>
                </div>
                
                <div style="padding: 30px;">
                    <h2>Hello {buyer.full_name or buyer.username},</h2>
                    
                    <p>{status_message}</p>
                    
                    <div style="background: #f8f9fa; padding: 20px; border-radius: 10px; margin: 20px 0;">
                        <h3 style="color: #17a2b8;">Current Status:</h3>
                        <p style="font-size: 24px; font-weight: bold; color: #28a745; margin: 10px 0;">{status_display}</p>
                        <p><strong>Order ID:</strong> #{order.id}</p>
                        <p><strong>Tracking Number:</strong> {order.tracking_number}</p>
                        <p><strong>Courier:</strong> {order.courier_name.title() if order.courier_name else 'N/A'}</p>
                        {expected_delivery_time}
                    </div>
                    
                    <div style="text-align: center; margin: 30px 0;">
                        <a href="{os.environ.get('BASE_URL', 'http://localhost:5000')}/orders/{order.id}/track" 
                           style="background: #28a745; color: white; padding: 15px 30px; text-decoration: none; border-radius: 5px; display: inline-block;">
                            Track Your Order
                        </a>
                    </div>
                    
                    <p>Thank you for your patience!<br>The FarmLink AI Team</p>
                </div>
                
                <div style="background: #343a40; color: white; padding: 20px; text-align: center;">
                    <p style="margin: 0;">© 2024 FarmLink AI. Connecting Agriculture, Powering Growth.</p>
                </div>
            </div>
            """
            
            result = email_service.send_email(buyer.email, subject, html_content)
            
            # Send SMS for "Out for Delivery" status
            sms_result = None
            if new_status == 'out_for_delivery' and TrackingNotificationService._should_send_sms(buyer):
                # Format expected delivery time for SMS
                delivery_time_text = "today"
                if order.estimated_delivery_date:
                    delivery_time_text = order.estimated_delivery_date.strftime('%b %d')
                
                sms_message = f"Your order #{order.id} is out for delivery! Expected delivery: {delivery_time_text}. Track: {os.environ.get('BASE_URL', 'http://localhost:5000')}/orders/{order.id}/track"
                sms_result = TrackingNotificationService.send_sms_notification(buyer.phone, sms_message)
            
            if result.get('success'):
                logger.info(f"Sent status update notification for order {order.id} to {buyer.email}")
            else:
                logger.error(f"Failed to send status update notification for order {order.id}: {result.get('error')}")
            
            return {
                'success': result.get('success'),
                'email_result': result,
                'sms_result': sms_result
            }
            
        except Exception as e:
            logger.error(f"Error sending status update notification for order {order.id}: {str(e)}", exc_info=True)
            return {'success': False, 'error': str(e)}
    
    @staticmethod
    def send_delivery_notification(order: Order):
        """
        Send notification when delivered (email and SMS)
        
        Args:
            order: Order object
        """
        try:
            from email_service import EmailService
            
            email_service = EmailService()
            
            # Send to buyer
            buyer = order.buyer
            buyer_subject = f"Order Delivered - Order #{order.id}"
            
            buyer_html = f"""
            <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                <div style="background: #28a745; padding: 20px; text-align: center;">
                    <h1 style="color: white; margin: 0;">✅ Order Delivered!</h1>
                </div>
                
                <div style="padding: 30px;">
                    <h2>Hello {buyer.full_name or buyer.username},</h2>
                    
                    <p>Great news! Your order has been successfully delivered.</p>
                    
                    <div style="background: #f8f9fa; padding: 20px; border-radius: 10px; margin: 20px 0;">
                        <h3 style="color: #28a745;">Delivery Confirmation:</h3>
                        <p><strong>Order ID:</strong> #{order.id}</p>
                        <p><strong>Tracking Number:</strong> {order.tracking_number}</p>
                        <p><strong>Delivered At:</strong> {order.actual_delivery_date.strftime('%B %d, %Y %I:%M %p') if order.actual_delivery_date else 'Just now'}</p>
                        <p><strong>Crop:</strong> {order.crop.name}</p>
                        <p><strong>Quantity:</strong> {order.quantity_requested} {order.crop.unit}</p>
                    </div>
                    
                    <div style="background: #fff3cd; padding: 15px; border-radius: 5px; margin: 20px 0;">
                        <p style="margin: 0;"><strong>Please confirm delivery:</strong> Click the button below to confirm you received your order in good condition.</p>
                    </div>
                    
                    <div style="text-align: center; margin: 30px 0;">
                        <a href="{os.environ.get('BASE_URL', 'http://localhost:5000')}/orders/{order.id}/confirm-delivery" 
                           style="background: #28a745; color: white; padding: 15px 30px; text-decoration: none; border-radius: 5px; display: inline-block; margin: 5px;">
                            Confirm Delivery
                        </a>
                        <a href="{os.environ.get('BASE_URL', 'http://localhost:5000')}/orders/{order.id}" 
                           style="background: #17a2b8; color: white; padding: 15px 30px; text-decoration: none; border-radius: 5px; display: inline-block; margin: 5px;">
                            View Order Details
                        </a>
                    </div>
                    
                    <p>If you didn't receive your order or have any issues, please contact us immediately.</p>
                    
                    <p>Thank you for choosing FarmLink AI!<br>The FarmLink AI Team</p>
                </div>
                
                <div style="background: #343a40; color: white; padding: 20px; text-align: center;">
                    <p style="margin: 0;">© 2024 FarmLink AI. Connecting Agriculture, Powering Growth.</p>
                </div>
            </div>
            """
            
            buyer_result = email_service.send_email(buyer.email, buyer_subject, buyer_html)
            
            # Send SMS to buyer if phone number is available
            sms_result = None
            if TrackingNotificationService._should_send_sms(buyer):
                sms_message = f"Your order #{order.id} has been delivered! Please confirm delivery at {os.environ.get('BASE_URL', 'http://localhost:5000')}/orders/{order.id}/confirm-delivery"
                sms_result = TrackingNotificationService.send_sms_notification(buyer.phone, sms_message)
            
            # Send to farmer
            farmer = order.farmer_user
            farmer_subject = f"Order Delivered - Order #{order.id}"
            
            farmer_html = f"""
            <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                <div style="background: #28a745; padding: 20px; text-align: center;">
                    <h1 style="color: white; margin: 0;">✅ Order Delivered Successfully!</h1>
                </div>
                
                <div style="padding: 30px;">
                    <h2>Hello {farmer.full_name or farmer.username},</h2>
                    
                    <p>Your order has been successfully delivered to the buyer.</p>
                    
                    <div style="background: #f8f9fa; padding: 20px; border-radius: 10px; margin: 20px 0;">
                        <h3 style="color: #28a745;">Delivery Details:</h3>
                        <p><strong>Order ID:</strong> #{order.id}</p>
                        <p><strong>Tracking Number:</strong> {order.tracking_number}</p>
                        <p><strong>Buyer:</strong> {buyer.full_name or buyer.username}</p>
                        <p><strong>Delivered At:</strong> {order.actual_delivery_date.strftime('%B %d, %Y %I:%M %p') if order.actual_delivery_date else 'Just now'}</p>
                        <p><strong>Total Amount:</strong> ₹{order.total_amount}</p>
                    </div>
                    
                    <div style="text-align: center; margin: 30px 0;">
                        <a href="{os.environ.get('BASE_URL', 'http://localhost:5000')}/orders/{order.id}" 
                           style="background: #28a745; color: white; padding: 15px 30px; text-decoration: none; border-radius: 5px; display: inline-block;">
                            View Order Details
                        </a>
                    </div>
                    
                    <p>The payment will be processed according to our payment terms.</p>
                    
                    <p>Thank you for using FarmLink AI!<br>The FarmLink AI Team</p>
                </div>
                
                <div style="background: #343a40; color: white; padding: 20px; text-align: center;">
                    <p style="margin: 0;">© 2024 FarmLink AI. Connecting Agriculture, Powering Growth.</p>
                </div>
            </div>
            """
            
            farmer_result = email_service.send_email(farmer.email, farmer_subject, farmer_html)
            
            if buyer_result.get('success') and farmer_result.get('success'):
                logger.info(f"Sent delivery notifications for order {order.id}")
            else:
                logger.error(f"Failed to send some delivery notifications for order {order.id}")
            
            return {
                'success': buyer_result.get('success') and farmer_result.get('success'),
                'buyer_result': buyer_result,
                'farmer_result': farmer_result,
                'sms_result': sms_result
            }
            
        except Exception as e:
            logger.error(f"Error sending delivery notification for order {order.id}: {str(e)}", exc_info=True)
            return {'success': False, 'error': str(e)}
    
    @staticmethod
    def send_failed_delivery_notification(order: Order, failure_reason: str):
        """
        Send notification when delivery fails
        
        Args:
            order: Order object
            failure_reason: Reason for delivery failure
        """
        try:
            from email_service import EmailService
            
            email_service = EmailService()
            
            # Send to buyer
            buyer = order.buyer
            buyer_subject = f"Delivery Failed - Order #{order.id}"
            
            buyer_html = f"""
            <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                <div style="background: #dc3545; padding: 20px; text-align: center;">
                    <h1 style="color: white; margin: 0;">⚠️ Delivery Attempt Failed</h1>
                </div>
                
                <div style="padding: 30px;">
                    <h2>Hello {buyer.full_name or buyer.username},</h2>
                    
                    <p>We're sorry to inform you that the delivery attempt for your order has failed.</p>
                    
                    <div style="background: #f8f9fa; padding: 20px; border-radius: 10px; margin: 20px 0;">
                        <h3 style="color: #dc3545;">Delivery Information:</h3>
                        <p><strong>Order ID:</strong> #{order.id}</p>
                        <p><strong>Tracking Number:</strong> {order.tracking_number}</p>
                        <p><strong>Failure Reason:</strong> {failure_reason}</p>
                        <p><strong>Delivery Attempts:</strong> {order.delivery_attempts}</p>
                    </div>
                    
                    <div style="background: #fff3cd; padding: 15px; border-radius: 5px; margin: 20px 0;">
                        <p style="margin: 0;"><strong>What's Next?</strong> The courier will attempt redelivery. Please ensure someone is available to receive the package.</p>
                    </div>
                    
                    <div style="text-align: center; margin: 30px 0;">
                        <a href="{os.environ.get('BASE_URL', 'http://localhost:5000')}/orders/{order.id}/track" 
                           style="background: #28a745; color: white; padding: 15px 30px; text-decoration: none; border-radius: 5px; display: inline-block; margin: 5px;">
                            Track Your Order
                        </a>
                        <a href="{os.environ.get('BASE_URL', 'http://localhost:5000')}/contact" 
                           style="background: #17a2b8; color: white; padding: 15px 30px; text-decoration: none; border-radius: 5px; display: inline-block; margin: 5px;">
                            Contact Support
                        </a>
                    </div>
                    
                    <p>If you have any questions or need to reschedule delivery, please contact us.</p>
                    
                    <p>Best regards,<br>The FarmLink AI Team</p>
                </div>
                
                <div style="background: #343a40; color: white; padding: 20px; text-align: center;">
                    <p style="margin: 0;">© 2024 FarmLink AI. Connecting Agriculture, Powering Growth.</p>
                </div>
            </div>
            """
            
            buyer_result = email_service.send_email(buyer.email, buyer_subject, buyer_html)
            
            # Send to farmer
            farmer = order.farmer_user
            farmer_subject = f"Delivery Failed - Order #{order.id}"
            
            farmer_html = f"""
            <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                <div style="background: #dc3545; padding: 20px; text-align: center;">
                    <h1 style="color: white; margin: 0;">⚠️ Delivery Attempt Failed</h1>
                </div>
                
                <div style="padding: 30px;">
                    <h2>Hello {farmer.full_name or farmer.username},</h2>
                    
                    <p>The delivery attempt for your order has failed.</p>
                    
                    <div style="background: #f8f9fa; padding: 20px; border-radius: 10px; margin: 20px 0;">
                        <h3 style="color: #dc3545;">Delivery Information:</h3>
                        <p><strong>Order ID:</strong> #{order.id}</p>
                        <p><strong>Tracking Number:</strong> {order.tracking_number}</p>
                        <p><strong>Buyer:</strong> {buyer.full_name or buyer.username}</p>
                        <p><strong>Failure Reason:</strong> {failure_reason}</p>
                        <p><strong>Delivery Attempts:</strong> {order.delivery_attempts}</p>
                    </div>
                    
                    <div style="text-align: center; margin: 30px 0;">
                        <a href="{os.environ.get('BASE_URL', 'http://localhost:5000')}/orders/{order.id}" 
                           style="background: #28a745; color: white; padding: 15px 30px; text-decoration: none; border-radius: 5px; display: inline-block;">
                            View Order Details
                        </a>
                    </div>
                    
                    <p>The courier will attempt redelivery. We'll keep you updated on the status.</p>
                    
                    <p>Best regards,<br>The FarmLink AI Team</p>
                </div>
                
                <div style="background: #343a40; color: white; padding: 20px; text-align: center;">
                    <p style="margin: 0;">© 2024 FarmLink AI. Connecting Agriculture, Powering Growth.</p>
                </div>
            </div>
            """
            
            farmer_result = email_service.send_email(farmer.email, farmer_subject, farmer_html)
            
            if buyer_result.get('success') and farmer_result.get('success'):
                logger.info(f"Sent failed delivery notifications for order {order.id}")
            else:
                logger.error(f"Failed to send some failed delivery notifications for order {order.id}")
            
            return {
                'success': buyer_result.get('success') and farmer_result.get('success'),
                'buyer_result': buyer_result,
                'farmer_result': farmer_result
            }
            
        except Exception as e:
            logger.error(f"Error sending failed delivery notification for order {order.id}: {str(e)}", exc_info=True)
            return {'success': False, 'error': str(e)}
    
    @staticmethod
    def send_delivery_confirmation_notification(order: Order):
        """
        Send notification to farmer when buyer confirms delivery
        
        Args:
            order: Order object
        """
        try:
            from email_service import EmailService
            
            email_service = EmailService()
            farmer = order.farmer_user
            buyer = order.buyer
            
            subject = f"Delivery Confirmed - Order #{order.id}"
            
            html_content = f"""
            <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                <div style="background: #28a745; padding: 20px; text-align: center;">
                    <h1 style="color: white; margin: 0;">✅ Delivery Confirmed by Buyer!</h1>
                </div>
                
                <div style="padding: 30px;">
                    <h2>Hello {farmer.full_name or farmer.username},</h2>
                    
                    <p>Great news! The buyer has confirmed receipt of the order.</p>
                    
                    <div style="background: #f8f9fa; padding: 20px; border-radius: 10px; margin: 20px 0;">
                        <h3 style="color: #28a745;">Confirmation Details:</h3>
                        <p><strong>Order ID:</strong> #{order.id}</p>
                        <p><strong>Tracking Number:</strong> {order.tracking_number}</p>
                        <p><strong>Buyer:</strong> {buyer.full_name or buyer.username}</p>
                        <p><strong>Confirmed At:</strong> {order.delivery_confirmation_date.strftime('%B %d, %Y %I:%M %p') if order.delivery_confirmation_date else 'Just now'}</p>
                        <p><strong>Total Amount:</strong> ₹{order.total_amount}</p>
                    </div>
                    
                    <div style="text-align: center; margin: 30px 0;">
                        <a href="{os.environ.get('BASE_URL', 'http://localhost:5000')}/orders/{order.id}" 
                           style="background: #28a745; color: white; padding: 15px 30px; text-decoration: none; border-radius: 5px; display: inline-block;">
                            View Order Details
                        </a>
                    </div>
                    
                    <p>The order is now complete. Payment processing will proceed according to our terms.</p>
                    
                    <p>Thank you for using FarmLink AI!<br>The FarmLink AI Team</p>
                </div>
                
                <div style="background: #343a40; color: white; padding: 20px; text-align: center;">
                    <p style="margin: 0;">© 2024 FarmLink AI. Connecting Agriculture, Powering Growth.</p>
                </div>
            </div>
            """
            
            result = email_service.send_email(farmer.email, subject, html_content)
            
            if result.get('success'):
                logger.info(f"Sent delivery confirmation notification for order {order.id} to {farmer.email}")
            else:
                logger.error(f"Failed to send delivery confirmation notification for order {order.id}: {result.get('error')}")
            
            return result
            
        except Exception as e:
            logger.error(f"Error sending delivery confirmation notification for order {order.id}: {str(e)}", exc_info=True)
            return {'success': False, 'error': str(e)}
    
    @staticmethod
    def _should_send_sms(user) -> bool:
        """
        Check if SMS notifications should be sent to user
        
        Args:
            user: User object
            
        Returns:
            True if SMS should be sent, False otherwise
        """
        # Check if user has a phone number
        if not user.phone:
            return False
        
        # Check if user has opted out of SMS notifications
        # For now, we assume users want SMS if they have a phone number
        # In the future, this can be extended to check a user preference field
        # Example: if hasattr(user, 'sms_notifications_enabled') and not user.sms_notifications_enabled:
        #     return False
        
        return True
    
    @staticmethod
    def _validate_phone_number(phone: str) -> Optional[str]:
        """
        Validate and format phone number
        
        Args:
            phone: Phone number string
            
        Returns:
            Formatted phone number with country code, or None if invalid
        """
        if not phone:
            return None
        
        # Remove spaces, dashes, and parentheses
        phone = phone.replace(' ', '').replace('-', '').replace('(', '').replace(')', '')
        
        # Check if phone already has country code
        if phone.startswith('+'):
            # Validate length (minimum 10 digits after +)
            if len(phone) >= 11:
                return phone
            else:
                logger.warning(f"Invalid phone number format: {phone}")
                return None
        
        # Assume Indian number if no country code
        # Remove leading 0 if present
        if phone.startswith('0'):
            phone = phone[1:]
        
        # Validate Indian mobile number (10 digits)
        if len(phone) == 10 and phone.isdigit():
            return f'+91{phone}'
        else:
            logger.warning(f"Invalid Indian phone number format: {phone}")
            return None
    
    @staticmethod
    def send_sms_notification(phone: str, message: str) -> dict:
        """
        Send SMS via Twilio with phone number validation
        
        Args:
            phone: Phone number (with or without country code)
            message: SMS message text
            
        Returns:
            Dict with success status
        """
        try:
            # Check if Twilio is configured
            twilio_sid = os.environ.get('TWILIO_ACCOUNT_SID')
            twilio_token = os.environ.get('TWILIO_AUTH_TOKEN')
            twilio_phone = os.environ.get('TWILIO_PHONE_NUMBER')
            
            if not all([twilio_sid, twilio_token, twilio_phone]):
                logger.warning("Twilio not configured, skipping SMS notification")
                return {'success': False, 'error': 'Twilio not configured'}
            
            # Validate and format phone number
            formatted_phone = TrackingNotificationService._validate_phone_number(phone)
            if not formatted_phone:
                logger.error(f"Invalid phone number: {phone}")
                return {'success': False, 'error': 'Invalid phone number format'}
            
            # Import Twilio client
            from twilio.rest import Client
            
            # Create Twilio client
            client = Client(twilio_sid, twilio_token)
            
            # Send SMS
            sms = client.messages.create(
                body=message,
                from_=twilio_phone,
                to=formatted_phone
            )
            
            logger.info(f"Sent SMS to {formatted_phone}: {sms.sid}")
            
            return {
                'success': True,
                'sid': sms.sid,
                'status': sms.status
            }
            
        except ImportError:
            logger.error("Twilio library not installed")
            return {'success': False, 'error': 'Twilio library not installed'}
        
        except Exception as e:
            logger.error(f"Error sending SMS to {phone}: {str(e)}", exc_info=True)
            return {'success': False, 'error': str(e)}
