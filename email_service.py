"""
FarmLink AI - Email Service Module
Handles email notifications, OTP verification, and password reset
"""

import os
import random
import string
from datetime import datetime, timedelta
from flask_mail import Message
from app import db, mail
from models import User
import secrets
import logging
from logging_config import log_notification_operation

class EmailService:
    """Email service using Flask-Mail"""
    
    def __init__(self):
        self.from_email = os.environ.get('MAIL_USERNAME', 'farmlink76@gmail.com')
    
    def send_email(self, to_email, subject, html_content, text_content=None, max_retries=3):
        """Send email using Flask-Mail with retry logic for connection issues"""
        import time
        
        log_notification_operation(
            logging.getLogger(__name__),
            'send_attempt',
            notification_type=subject,
            recipient_email=to_email,
            success=None
        )
        
        msg = Message(
            subject=subject,
            sender=self.from_email,
            recipients=[to_email]
        )
        msg.html = html_content
        if text_content:
            msg.body = text_content
        
        last_error = None
        for attempt in range(max_retries):
            try:
                # Create a fresh connection for each send to avoid connection reuse issues
                with mail.connect() as conn:
                    conn.send(msg)
                
                log_notification_operation(
                    logging.getLogger(__name__),
                    'send_success',
                    notification_type=subject,
                    recipient_email=to_email,
                    success=True
                )
                
                return {"success": True, "status_code": 200, "message": "Email sent successfully"}
            except Exception as e:
                last_error = e
                error_str = str(e)
                
                # Check if it's a connection-related error that's worth retrying
                is_connection_error = any(err in error_str.lower() for err in [
                    'connection', 'disconnected', 'aborted', 'connect() first',
                    'timed out', 'reset by peer', 'broken pipe'
                ])
                
                if is_connection_error and attempt < max_retries - 1:
                    wait_time = (attempt + 1) * 2  # Exponential backoff: 2s, 4s, 6s
                    logging.warning(f"Email send attempt {attempt + 1} failed, retrying in {wait_time}s: {error_str}")
                    time.sleep(wait_time)
                    continue
                else:
                    break
        
        # All retries failed
        error_msg = f"Failed to send email to {to_email}: {str(last_error)}"
        
        log_notification_operation(
            logging.getLogger(__name__),
            'send_failure',
            notification_type=subject,
            recipient_email=to_email,
            success=False,
            error=error_msg
        )
        
        logging.exception("Detailed error traceback:")
        return {"success": False, "error": error_msg, "status_code": 500}
    
    def send_login_alert(self, user, ip_address, user_agent, location=None):
        """Send login activity alert"""
        subject = "New Login Activity Detected - FarmLink AI"
        
        html_content = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <div style="background: #f8f9fa; padding: 20px; border-radius: 5px;">
                <h2 style="color: #28a745;">New Login Activity</h2>
                <p>Hello {user.full_name or user.username},</p>
                <p>We detected a new login to your FarmLink AI account:</p>
                
                <div style="background: white; padding: 15px; border-radius: 5px; margin: 15px 0;">
                    <p><strong>Time:</strong> {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC</p>
                    <p><strong>IP Address:</strong> {ip_address}</p>
                    <p><strong>Device:</strong> {user_agent}</p>
                    {f'<p><strong>Location:</strong> {location}</p>' if location else ''}
                </div>
                
                <p>If this wasn't you, please secure your account immediately:</p>
                <div style="text-align: center; margin: 20px 0;">
                    <a href="{os.environ.get('BASE_URL', 'http://localhost:5000')}/change-password" 
                       style="background: #dc3545; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px;">
                        Change Password
                    </a>
                </div>
            </div>
        </div>
        """
        
        return self.send_email(user.email, subject, html_content)

    def send_welcome_email(self, user):
        """Send welcome email to new users"""
        subject = f"Welcome to FarmLink AI, {user.full_name or user.username}!"
        
        html_content = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <div style="background: linear-gradient(135deg, #28a745 0%, #20c997 100%); padding: 30px; text-align: center;">
                <h1 style="color: white; margin: 0;">Welcome to FarmLink AI!</h1>
            </div>
            
            <div style="padding: 30px; background-color: #f8f9fa;">
                <h2 style="color: #28a745;">Hello {user.full_name or user.username},</h2>
                
                <p>Welcome to FarmLink AI - India's smartest agricultural marketplace! We're excited to have you join our community of farmers, buyers, and agricultural experts.</p>
                
                <div style="background: white; padding: 20px; border-radius: 10px; margin: 20px 0;">
                    <h3 style="color: #28a745;">Your Account Details:</h3>
                    <p><strong>Role:</strong> {user.role.title()}</p>
                    <p><strong>Email:</strong> {user.email}</p>
                    <p><strong>Username:</strong> {user.username}</p>
                </div>
                
                <h3 style="color: #28a745;">Get Started:</h3>
                <ul>
                    <li>Complete your profile with location and contact details</li>
                    <li>{"Explore our marketplace to find the best crops" if user.role == "buyer" else "List your crops and connect with buyers"}</li>
                    <li>Use our AI-powered features for smart farming insights</li>
                    <li>Join our expert community for tips and advice</li>
                </ul>
                
                <div style="text-align: center; margin: 30px 0;">
                    <a href="{os.environ.get('BASE_URL', 'http://localhost:5000')}/dashboard" 
                       style="background: #28a745; color: white; padding: 15px 30px; text-decoration: none; border-radius: 5px; display: inline-block;">
                        Go to Dashboard
                    </a>
                </div>
                
                <p>If you have any questions, feel free to contact our support team.</p>
                
                <p>Happy farming!<br>
                The FarmLink AI Team</p>
            </div>
            
            <div style="background: #343a40; color: white; padding: 20px; text-align: center;">
                <p style="margin: 0;">© 2024 FarmLink AI. Connecting Agriculture, Powering Growth.</p>
            </div>
        </div>
        """
        
        return self.send_email(user.email, subject, html_content)
    
    def send_order_notification(self, order, notification_type="new"):
        """Send order-related notifications"""
        if notification_type == "new":
            # Notify farmer about new order
            subject = f"New Order Received - {order.crop.name}"
            recipient = order.farmer_user
            
            html_content = f"""
            <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                <div style="background: #28a745; padding: 20px; text-align: center;">
                    <h1 style="color: white; margin: 0;">New Order Received!</h1>
                </div>
                
                <div style="padding: 30px;">
                    <h2>Hello {recipient.full_name or recipient.username},</h2>
                    
                    <p>Great news! You've received a new order for your crop.</p>
                    
                    <div style="background: #f8f9fa; padding: 20px; border-radius: 10px; margin: 20px 0;">
                        <h3 style="color: #28a745;">Order Details:</h3>
                        <p><strong>Crop:</strong> {order.crop.name}</p>
                        <p><strong>Quantity:</strong> {order.quantity_requested} {order.crop.unit}</p>
                        <p><strong>Price:</strong> ₹{order.price_per_unit} per {order.crop.unit}</p>
                        <p><strong>Total Amount:</strong> ₹{order.total_amount}</p>
                        <p><strong>Buyer:</strong> {order.buyer.full_name or order.buyer.username}</p>
                        <p><strong>Delivery Address:</strong> {order.delivery_address}</p>
                        {f"<p><strong>Notes:</strong> {order.notes}</p>" if order.notes else ""}
                    </div>
                    
                    <div style="text-align: center; margin: 30px 0;">
                        <a href="{os.environ.get('BASE_URL', 'http://localhost:5000')}/orders/my" 
                           style="background: #28a745; color: white; padding: 15px 30px; text-decoration: none; border-radius: 5px; display: inline-block; margin: 5px;">
                            View Order
                        </a>
                        <a href="{os.environ.get('BASE_URL', 'http://localhost:5000')}/order/update/{order.id}/accepted" 
                           style="background: #17a2b8; color: white; padding: 15px 30px; text-decoration: none; border-radius: 5px; display: inline-block; margin: 5px;">
                            Accept Order
                        </a>
                    </div>
                    
                    <p>Please review the order details and respond promptly to maintain customer satisfaction.</p>
                </div>
            </div>
            """
        
        elif notification_type == "status_update":
            # Notify buyer about order status change
            subject = f"Order Status Update - {order.crop.name}"
            recipient = order.buyer
            
            status_colors = {
                "accepted": "#28a745",
                "rejected": "#dc3545",
                "completed": "#17a2b8"
            }
            
            html_content = f"""
            <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                <div style="background: {status_colors.get(order.status, '#6c757d')}; padding: 20px; text-align: center;">
                    <h1 style="color: white; margin: 0;">Order {order.status.title()}</h1>
                </div>
                
                <div style="padding: 30px;">
                    <h2>Hello {recipient.full_name or recipient.username},</h2>
                    
                    <p>Your order status has been updated to <strong>{order.status.title()}</strong>.</p>
                    
                    <div style="background: #f8f9fa; padding: 20px; border-radius: 10px; margin: 20px 0;">
                        <h3>Order Details:</h3>
                        <p><strong>Order ID:</strong> #{order.id}</p>
                        <p><strong>Crop:</strong> {order.crop.name}</p>
                        <p><strong>Quantity:</strong> {order.quantity_requested} {order.crop.unit}</p>
                        <p><strong>Total Amount:</strong> ₹{order.total_amount}</p>
                        <p><strong>Farmer:</strong> {order.farmer_user.full_name or order.farmer_user.username}</p>
                    </div>
                    
                    <div style="text-align: center; margin: 30px 0;">
                        <a href="{os.environ.get('BASE_URL', 'http://localhost:5000')}/orders/my" 
                           style="background: #28a745; color: white; padding: 15px 30px; text-decoration: none; border-radius: 5px; display: inline-block;">
                            View Order Details
                        </a>
                    </div>
                </div>
            </div>
            """
        
        return self.send_email(recipient.email, subject, html_content)
    
    def send_reset_otp_email(self, user, otp):
        """Send password reset OTP email"""
        subject = "Password Reset Code - FarmLink AI"
        
        html_content = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <div style="background: #28a745; padding: 20px; text-align: center;">
                <h1 style="color: white; margin: 0;">Password Reset Code</h1>
            </div>
            
            <div style="padding: 30px;">
                <h2>Hello {user.full_name or user.username},</h2>
                
                <p>Here's your password reset verification code:</p>
                
                <div style="background: #f8f9fa; border: 2px dashed #28a745; padding: 30px; margin: 30px 0; text-align: center; border-radius: 10px;">
                    <h1 style="color: #28a745; font-size: 3em; margin: 0; letter-spacing: 10px;">{otp}</h1>
                </div>
                
                <p>This code will expire in 10 minutes.</p>
                
                <p style="color: #6c757d; margin-top: 20px;">If you didn't request this password reset, please ignore this email.</p>
            </div>
        </div>
        """
        
        return self.send_email(user.email, subject, html_content)

    def send_password_reset_email(self, user, reset_token):
        """Send password reset email"""
        subject = "Password Reset Request - FarmLink AI"
        
        html_content = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <div style="background: #28a745; padding: 20px; text-align: center;">
                <h1 style="color: white; margin: 0;">Password Reset Request</h1>
            </div>
            
            <div style="padding: 30px;">
                <h2>Hello {user.full_name or user.username},</h2>
                
                <p>We received a request to reset your password for your FarmLink AI account.</p>
                
                <div style="background: #fff3cd; border: 1px solid #ffeaa7; padding: 15px; border-radius: 5px; margin: 20px 0;">
                    <p style="margin: 0;"><strong>Important:</strong> If you didn't request this password reset, please ignore this email. Your password will remain unchanged.</p>
                </div>
                
                <div style="text-align: center; margin: 30px 0;">
                    <a href="{os.environ.get('BASE_URL', 'http://localhost:5000')}/reset-password/{reset_token}" 
                       style="background: #28a745; color: white; padding: 15px 30px; text-decoration: none; border-radius: 5px; display: inline-block;">
                        Reset Password
                    </a>
                </div>
                
                <p>This link will expire in 1 hour for security reasons.</p>
                
                <p>If you're having trouble clicking the button, copy and paste this URL into your browser:</p>
                <p style="word-break: break-all; background: #f8f9fa; padding: 10px; border-radius: 5px;">
                    {os.environ.get('BASE_URL', 'http://localhost:5000')}/reset-password/{reset_token}
                </p>
            </div>
        </div>
        """
        
        return self.send_email(user.email, subject, html_content)

    def send_security_notification(self, user, event_type, details=None):
        """Send security-related notifications"""
        subject_map = {
            "login_attempt": "Unusual Login Attempt Detected",
            "password_changed": "Password Changed Successfully",
            "profile_update": "Profile Information Updated",
            "device_login": "New Device Login",
            "account_locked": "Account Security Alert"
        }
        
        subject = subject_map.get(event_type, "Security Notification")
        
        html_content = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <div style="background: #dc3545; padding: 20px; text-align: center;">
                <h1 style="color: white; margin: 0;">Security Alert</h1>
            </div>
            
            <div style="padding: 30px;">
                <h2>Hello {user.full_name or user.username},</h2>
                
                <div style="background: #fff3cd; padding: 20px; border-radius: 10px; margin: 20px 0;">
                    <h3 style="color: #856404; margin-top: 0;">Security Event Detected</h3>
                    <p><strong>Event Type:</strong> {event_type.replace('_', ' ').title()}</p>
                    {f'<p><strong>Details:</strong> {details}</p>' if details else ''}
                    <p><strong>Time:</strong> {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC</p>
                </div>
                
                <p>If you did not perform this action, please take immediate action:</p>
                <ol>
                    <li>Change your password immediately</li>
                    <li>Review your recent account activity</li>
                    <li>Contact our support team</li>
                </ol>
                
                <div style="text-align: center; margin: 30px 0;">
                    <a href="{os.environ.get('BASE_URL', 'http://localhost:5000')}/profile/security" 
                       style="background: #28a745; color: white; padding: 15px 30px; text-decoration: none; border-radius: 5px; display: inline-block;">
                        Review Account Security
                    </a>
                </div>
            </div>
        </div>
        """
        
        return self.send_email(user.email, subject, html_content)

    def send_crop_notification(self, user, crop, notification_type, details=None):
        """Send crop-related notifications"""
        subject_map = {
            "price_alert": f"Price Alert - {crop.name}",
            "stock_update": f"Stock Update - {crop.name}",
            "quality_check": f"Quality Check Required - {crop.name}",
            "expiry_alert": f"Expiry Alert - {crop.name}",
            "demand_alert": f"High Demand Alert - {crop.name}",
            "crop_added": f"New Crop Listed - {crop.name}",
            "crop_updated": f"Crop Update - {crop.name}",
            "crop_deleted": f"Crop Listing Removed - {crop.name}",
            "crop_approved": f"Crop Approved - {crop.name}",
            "crop_rejected": f"Crop Rejected - {crop.name}",
            "new_order": f"New Order Received - {crop.name}",
            "order_placed": f"Order Confirmation - {crop.name}"
        }
        
        subject = subject_map.get(notification_type, f"Crop Update - {crop.name}")
        
        html_content = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <div style="background: #17a2b8; padding: 20px; text-align: center;">
                <h1 style="color: white; margin: 0;">Crop Update</h1>
            </div>
            
            <div style="padding: 30px;">
                <h2>Hello {user.full_name or user.username},</h2>
                
                <div style="background: #f8f9fa; padding: 20px; border-radius: 10px; margin: 20px 0;">
                    <h3 style="color: #17a2b8; margin-top: 0;">{notification_type.replace('_', ' ').title()}</h3>
                    <p><strong>Crop:</strong> {crop.name}</p>
                    {f'<p><strong>Details:</strong> {details}</p>' if details else ''}
                    <p><strong>Current Stock:</strong> {crop.quantity} {crop.unit}</p>
                    <p><strong>Price:</strong> ₹{crop.price_per_unit}/{crop.unit}</p>
                </div>
                
                <div style="text-align: center; margin: 30px 0;">
                    <a href="{os.environ.get('BASE_URL', 'http://localhost:5000')}/crops/{crop.id}" 
                       style="background: #28a745; color: white; padding: 15px 30px; text-decoration: none; border-radius: 5px; display: inline-block;">
                        View Crop Details
                    </a>
                </div>
            </div>
        </div>
        """
        
        return self.send_email(user.email, subject, html_content)

    def send_system_notification(self, user, notification_type, message, action_url=None, action_text=None):
        """Send system-wide notifications"""
        subject_map = {
            "maintenance": "System Maintenance Notice",
            "feature_update": "New Features Available",
            "service_disruption": "Service Disruption Alert",
            "account_status": "Account Status Update",
            "promotion": "Special Offer Available"
        }
        
        subject = subject_map.get(notification_type, "System Notification")
        
        html_content = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <div style="background: #6c757d; padding: 20px; text-align: center;">
                <h1 style="color: white; margin: 0;">System Notification</h1>
            </div>
            
            <div style="padding: 30px;">
                <h2>Hello {user.full_name or user.username},</h2>
                
                <div style="background: #f8f9fa; padding: 20px; border-radius: 10px; margin: 20px 0;">
                    <h3 style="color: #6c757d; margin-top: 0;">{notification_type.replace('_', ' ').title()}</h3>
                    <p>{message}</p>
                </div>
                
                {f'''
                <div style="text-align: center; margin: 30px 0;">
                    <a href="{action_url}" 
                       style="background: #28a745; color: white; padding: 15px 30px; text-decoration: none; border-radius: 5px; display: inline-block;">
                        {action_text}
                    </a>
                </div>
                ''' if action_url and action_text else ''}
            </div>
        </div>
        """
        
        return self.send_email(user.email, subject, html_content)
    
    def send_order_placed_notification(self, order):
        """Send notification when order is placed (to farmer)"""
        try:
            log_notification_operation(
                logging.getLogger(__name__),
                'prepare',
                notification_type='order_placed',
                order_id=order.id,
                recipient_email=order.farmer_user.email,
                success=None
            )
            
            farmer = order.farmer_user
            buyer = order.buyer
            crop = order.crop
            
            subject = f"New Order Received - {crop.name}"
            
            html_content = f"""
            <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                <div style="background: #28a745; padding: 20px; text-align: center;">
                    <h1 style="color: white; margin: 0;">🎉 New Order Received!</h1>
                </div>
                
                <div style="padding: 30px;">
                    <h2>Hello {farmer.full_name or farmer.username},</h2>
                    
                    <p>Great news! You've received a new order for your crop.</p>
                    
                    <div style="background: #f8f9fa; padding: 20px; border-radius: 10px; margin: 20px 0;">
                        <h3 style="color: #28a745;">Order Details:</h3>
                        <p><strong>Order ID:</strong> #{order.id}</p>
                        <p><strong>Crop:</strong> {crop.name}</p>
                        <p><strong>Quantity:</strong> {order.quantity_requested} {crop.unit}</p>
                        <p><strong>Price:</strong> ₹{order.price_per_unit} per {crop.unit}</p>
                        <p><strong>Total Amount:</strong> ₹{order.total_amount}</p>
                        <p><strong>Buyer:</strong> {buyer.full_name or buyer.username}</p>
                        <p><strong>Delivery Address:</strong> {order.delivery_address}</p>
                        <p><strong>Delivery Method:</strong> {order.delivery_method.title()}</p>
                        {f"<p><strong>Notes:</strong> {order.notes}</p>" if order.notes else ""}
                    </div>
                    
                    <div style="text-align: center; margin: 30px 0;">
                        <a href="{os.environ.get('BASE_URL', 'http://localhost:5000')}/orders/my" 
                           style="background: #28a745; color: white; padding: 15px 30px; text-decoration: none; border-radius: 5px; display: inline-block; margin: 5px;">
                            View Order
                        </a>
                    </div>
                    
                    <p>Please review the order details and respond promptly to maintain customer satisfaction.</p>
                    
                    <p>Best regards,<br>The FarmLink AI Team</p>
                </div>
                
                <div style="background: #343a40; color: white; padding: 20px; text-align: center;">
                    <p style="margin: 0;">© 2024 FarmLink AI. Connecting Agriculture, Powering Growth.</p>
                </div>
            </div>
            """
            
            result = self.send_email(farmer.email, subject, html_content)
            
            log_notification_operation(
                logging.getLogger(__name__),
                'send_complete',
                notification_type='order_placed',
                order_id=order.id,
                recipient_email=farmer.email,
                success=result.get('success', False),
                error=result.get('error')
            )
            
            return result
        except Exception as e:
            log_notification_operation(
                logging.getLogger(__name__),
                'send_error',
                notification_type='order_placed',
                order_id=order.id,
                recipient_email=order.farmer_user.email if order.farmer_user else None,
                success=False,
                error=str(e)
            )
            logging.error(f"Failed to send order placed notification: {str(e)}")
            return {"success": False, "error": str(e)}
    
    def send_payment_confirmed_notification(self, order):
        """Send notification when payment is confirmed (to both buyer and farmer)"""
        try:
            buyer = order.buyer
            farmer = order.farmer_user
            crop = order.crop
            
            # Send to buyer
            buyer_subject = f"Payment Confirmed - Order #{order.id}"
            buyer_html = f"""
            <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                <div style="background: #28a745; padding: 20px; text-align: center;">
                    <h1 style="color: white; margin: 0;">✅ Payment Confirmed!</h1>
                </div>
                
                <div style="padding: 30px;">
                    <h2>Hello {buyer.full_name or buyer.username},</h2>
                    
                    <p>Your payment has been successfully confirmed. Your order is now being processed.</p>
                    
                    <div style="background: #f8f9fa; padding: 20px; border-radius: 10px; margin: 20px 0;">
                        <h3 style="color: #28a745;">Order Summary:</h3>
                        <p><strong>Order ID:</strong> #{order.id}</p>
                        <p><strong>Crop:</strong> {crop.name}</p>
                        <p><strong>Quantity:</strong> {order.quantity_requested} {crop.unit}</p>
                        <p><strong>Total Amount:</strong> ₹{order.total_amount}</p>
                        <p><strong>Payment Status:</strong> {order.payment_status.title()}</p>
                        <p><strong>Farmer:</strong> {farmer.full_name or farmer.username}</p>
                    </div>
                    
                    <div style="text-align: center; margin: 30px 0;">
                        <a href="{os.environ.get('BASE_URL', 'http://localhost:5000')}/orders/my" 
                           style="background: #28a745; color: white; padding: 15px 30px; text-decoration: none; border-radius: 5px; display: inline-block;">
                            Track Your Order
                        </a>
                    </div>
                    
                    <p>You will receive updates as your order progresses.</p>
                    
                    <p>Thank you for choosing FarmLink AI!<br>The FarmLink AI Team</p>
                </div>
                
                <div style="background: #343a40; color: white; padding: 20px; text-align: center;">
                    <p style="margin: 0;">© 2024 FarmLink AI. Connecting Agriculture, Powering Growth.</p>
                </div>
            </div>
            """
            
            # Send to farmer
            farmer_subject = f"Payment Received - Order #{order.id}"
            farmer_html = f"""
            <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                <div style="background: #28a745; padding: 20px; text-align: center;">
                    <h1 style="color: white; margin: 0;">💰 Payment Received!</h1>
                </div>
                
                <div style="padding: 30px;">
                    <h2>Hello {farmer.full_name or farmer.username},</h2>
                    
                    <p>Payment has been confirmed for your order. You can now proceed with processing.</p>
                    
                    <div style="background: #f8f9fa; padding: 20px; border-radius: 10px; margin: 20px 0;">
                        <h3 style="color: #28a745;">Order Details:</h3>
                        <p><strong>Order ID:</strong> #{order.id}</p>
                        <p><strong>Crop:</strong> {crop.name}</p>
                        <p><strong>Quantity:</strong> {order.quantity_requested} {crop.unit}</p>
                        <p><strong>Amount Received:</strong> ₹{order.total_amount}</p>
                        <p><strong>Buyer:</strong> {buyer.full_name or buyer.username}</p>
                    </div>
                    
                    <div style="text-align: center; margin: 30px 0;">
                        <a href="{os.environ.get('BASE_URL', 'http://localhost:5000')}/orders/my" 
                           style="background: #28a745; color: white; padding: 15px 30px; text-decoration: none; border-radius: 5px; display: inline-block;">
                            Process Order
                        </a>
                    </div>
                    
                    <p>Please update the order status as you progress with fulfillment.</p>
                    
                    <p>Best regards,<br>The FarmLink AI Team</p>
                </div>
                
                <div style="background: #343a40; color: white; padding: 20px; text-align: center;">
                    <p style="margin: 0;">© 2024 FarmLink AI. Connecting Agriculture, Powering Growth.</p>
                </div>
            </div>
            """
            
            # Send both emails
            buyer_result = self.send_email(buyer.email, buyer_subject, buyer_html)
            farmer_result = self.send_email(farmer.email, farmer_subject, farmer_html)
            
            return {
                "success": buyer_result.get("success") and farmer_result.get("success"),
                "buyer_result": buyer_result,
                "farmer_result": farmer_result
            }
        except Exception as e:
            logging.error(f"Failed to send payment confirmed notification: {str(e)}")
            return {"success": False, "error": str(e)}
    
    def send_order_status_update_notification(self, order, old_status=None):
        """Send notification when order status is updated (to buyer)"""
        try:
            buyer = order.buyer
            farmer = order.farmer_user
            crop = order.crop
            
            status_messages = {
                "confirmed": "Your order has been confirmed and is awaiting farmer acceptance.",
                "processing": "Your order is being processed by the farmer.",
                "shipped": "Your order has been shipped and is on its way!",
                "delivered": "Your order has been delivered successfully.",
                "rejected": "Unfortunately, your order has been rejected by the farmer.",
                "cancelled": "Your order has been cancelled."
            }
            
            status_colors = {
                "confirmed": "#28a745",
                "processing": "#17a2b8",
                "shipped": "#007bff",
                "delivered": "#28a745",
                "rejected": "#dc3545",
                "cancelled": "#6c757d"
            }
            
            subject = f"Order Status Update - {order.status.title()}"
            color = status_colors.get(order.status, "#6c757d")
            message = status_messages.get(order.status, f"Your order status has been updated to {order.status}.")
            
            html_content = f"""
            <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                <div style="background: {color}; padding: 20px; text-align: center;">
                    <h1 style="color: white; margin: 0;">Order Status Update</h1>
                </div>
                
                <div style="padding: 30px;">
                    <h2>Hello {buyer.full_name or buyer.username},</h2>
                    
                    <p>{message}</p>
                    
                    <div style="background: #f8f9fa; padding: 20px; border-radius: 10px; margin: 20px 0;">
                        <h3 style="color: {color};">Order Details:</h3>
                        <p><strong>Order ID:</strong> #{order.id}</p>
                        <p><strong>Crop:</strong> {crop.name}</p>
                        <p><strong>Quantity:</strong> {order.quantity_requested} {crop.unit}</p>
                        <p><strong>Total Amount:</strong> ₹{order.total_amount}</p>
                        {f'<p><strong>Previous Status:</strong> {old_status.title()}</p>' if old_status else ''}
                        <p><strong>Current Status:</strong> {order.status.title()}</p>
                        <p><strong>Farmer:</strong> {farmer.full_name or farmer.username}</p>
                    </div>
                    
                    <div style="text-align: center; margin: 30px 0;">
                        <a href="{os.environ.get('BASE_URL', 'http://localhost:5000')}/orders/my" 
                           style="background: {color}; color: white; padding: 15px 30px; text-decoration: none; border-radius: 5px; display: inline-block;">
                            View Order Details
                        </a>
                    </div>
                    
                    <p>Thank you for using FarmLink AI!<br>The FarmLink AI Team</p>
                </div>
                
                <div style="background: #343a40; color: white; padding: 20px; text-align: center;">
                    <p style="margin: 0;">© 2024 FarmLink AI. Connecting Agriculture, Powering Growth.</p>
                </div>
            </div>
            """
            
            return self.send_email(buyer.email, subject, html_content)
        except Exception as e:
            logging.error(f"Failed to send order status update notification: {str(e)}")
            return {"success": False, "error": str(e)}
    
    def send_order_shipped_notification(self, order):
        """Send notification when order is shipped with tracking info (to buyer)"""
        try:
            buyer = order.buyer
            farmer = order.farmer_user
            crop = order.crop
            
            # Calculate estimated delivery date based on delivery method
            estimated_delivery = None
            if order.shipped_at:
                if order.delivery_method == 'express':
                    # Express delivery: 2-3 days
                    estimated_delivery = order.shipped_at + timedelta(days=3)
                else:
                    # Standard delivery: 5-7 days
                    estimated_delivery = order.shipped_at + timedelta(days=7)
            
            subject = f"Order Shipped - #{order.id}"
            
            html_content = f"""
            <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                <div style="background: #007bff; padding: 20px; text-align: center;">
                    <h1 style="color: white; margin: 0;">📦 Order Shipped!</h1>
                </div>
                
                <div style="padding: 30px;">
                    <h2>Hello {buyer.full_name or buyer.username},</h2>
                    
                    <p>Great news! Your order has been shipped and is on its way to you.</p>
                    
                    <div style="background: #f8f9fa; padding: 20px; border-radius: 10px; margin: 20px 0;">
                        <h3 style="color: #007bff;">Shipping Details:</h3>
                        <p><strong>Order ID:</strong> #{order.id}</p>
                        <p><strong>Crop:</strong> {crop.name}</p>
                        <p><strong>Quantity:</strong> {order.quantity_requested} {crop.unit}</p>
                        {f'<p><strong>Tracking Number:</strong> {order.tracking_number}</p>' if order.tracking_number else ''}
                        {f'<p><strong>Shipped At:</strong> {order.shipped_at.strftime("%Y-%m-%d %H:%M")}</p>' if order.shipped_at else ''}
                        {f'<p><strong>Estimated Delivery:</strong> {estimated_delivery.strftime("%Y-%m-%d")}</p>' if estimated_delivery else ''}
                        <p><strong>Delivery Method:</strong> {order.delivery_method.title()}</p>
                        <p><strong>Delivery Address:</strong> {order.delivery_address}</p>
                        <p><strong>Farmer:</strong> {farmer.full_name or farmer.username}</p>
                    </div>
                    
                    <div style="text-align: center; margin: 30px 0;">
                        <a href="{os.environ.get('BASE_URL', 'http://localhost:5000')}/orders/my" 
                           style="background: #007bff; color: white; padding: 15px 30px; text-decoration: none; border-radius: 5px; display: inline-block;">
                            Track Your Order
                        </a>
                    </div>
                    
                    <p>You will receive another notification once your order is delivered.</p>
                    
                    <p>Thank you for choosing FarmLink AI!<br>The FarmLink AI Team</p>
                </div>
                
                <div style="background: #343a40; color: white; padding: 20px; text-align: center;">
                    <p style="margin: 0;">© 2024 FarmLink AI. Connecting Agriculture, Powering Growth.</p>
                </div>
            </div>
            """
            
            return self.send_email(buyer.email, subject, html_content)
        except Exception as e:
            logging.error(f"Failed to send order shipped notification: {str(e)}")
            return {"success": False, "error": str(e)}
    
    def send_order_delivered_notification(self, order):
        """Send notification when order is delivered (to buyer)"""
        try:
            buyer = order.buyer
            farmer = order.farmer_user
            crop = order.crop
            
            subject = f"Order Delivered - #{order.id}"
            
            html_content = f"""
            <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                <div style="background: #28a745; padding: 20px; text-align: center;">
                    <h1 style="color: white; margin: 0;">🎉 Order Delivered!</h1>
                </div>
                
                <div style="padding: 30px;">
                    <h2>Hello {buyer.full_name or buyer.username},</h2>
                    
                    <p>Your order has been successfully delivered! We hope you're satisfied with your purchase.</p>
                    
                    <div style="background: #f8f9fa; padding: 20px; border-radius: 10px; margin: 20px 0;">
                        <h3 style="color: #28a745;">Order Summary:</h3>
                        <p><strong>Order ID:</strong> #{order.id}</p>
                        <p><strong>Crop:</strong> {crop.name}</p>
                        <p><strong>Quantity:</strong> {order.quantity_requested} {crop.unit}</p>
                        <p><strong>Total Amount:</strong> ₹{order.total_amount}</p>
                        {f'<p><strong>Delivered At:</strong> {order.delivered_at.strftime("%Y-%m-%d %H:%M")}</p>' if order.delivered_at else ''}
                        <p><strong>Farmer:</strong> {farmer.full_name or farmer.username}</p>
                    </div>
                    
                    <div style="background: #fff3cd; border-left: 4px solid #ffc107; padding: 15px; margin: 20px 0;">
                        <p style="margin: 0;"><strong>📝 Rate Your Experience:</strong> Help other buyers by rating this farmer and sharing your experience!</p>
                    </div>
                    
                    <div style="text-align: center; margin: 30px 0;">
                        <a href="{os.environ.get('BASE_URL', 'http://localhost:5000')}/orders/my" 
                           style="background: #28a745; color: white; padding: 15px 30px; text-decoration: none; border-radius: 5px; display: inline-block; margin: 5px;">
                            View Order
                        </a>
                        <a href="{os.environ.get('BASE_URL', 'http://localhost:5000')}/rate/farmer/{farmer.id}" 
                           style="background: #ffc107; color: #333; padding: 15px 30px; text-decoration: none; border-radius: 5px; display: inline-block; margin: 5px;">
                            Rate Farmer
                        </a>
                    </div>
                    
                    <p>Thank you for choosing FarmLink AI! We look forward to serving you again.</p>
                    
                    <p>Best regards,<br>The FarmLink AI Team</p>
                </div>
                
                <div style="background: #343a40; color: white; padding: 20px; text-align: center;">
                    <p style="margin: 0;">© 2024 FarmLink AI. Connecting Agriculture, Powering Growth.</p>
                </div>
            </div>
            """
            
            return self.send_email(buyer.email, subject, html_content)
        except Exception as e:
            logging.error(f"Failed to send order delivered notification: {str(e)}")
            return {"success": False, "error": str(e)}
    
    def send_order_cancelled_notification(self, order):
        """Send notification when order is cancelled (to both buyer and farmer)"""
        try:
            buyer = order.buyer
            farmer = order.farmer_user
            crop = order.crop
            
            # Send to buyer
            buyer_subject = f"Order Cancelled - #{order.id}"
            buyer_html = f"""
            <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                <div style="background: #6c757d; padding: 20px; text-align: center;">
                    <h1 style="color: white; margin: 0;">Order Cancelled</h1>
                </div>
                
                <div style="padding: 30px;">
                    <h2>Hello {buyer.full_name or buyer.username},</h2>
                    
                    <p>Your order has been cancelled as requested.</p>
                    
                    <div style="background: #f8f9fa; padding: 20px; border-radius: 10px; margin: 20px 0;">
                        <h3 style="color: #6c757d;">Order Details:</h3>
                        <p><strong>Order ID:</strong> #{order.id}</p>
                        <p><strong>Crop:</strong> {crop.name}</p>
                        <p><strong>Quantity:</strong> {order.quantity_requested} {crop.unit}</p>
                        <p><strong>Total Amount:</strong> ₹{order.total_amount}</p>
                        {f'<p><strong>Cancellation Reason:</strong> {order.cancellation_reason}</p>' if order.cancellation_reason else ''}
                        {f'<p><strong>Cancelled At:</strong> {order.cancelled_at.strftime("%Y-%m-%d %H:%M")}</p>' if order.cancelled_at else ''}
                    </div>
                    
                    {f'''
                    <div style="background: #d1ecf1; border-left: 4px solid #17a2b8; padding: 15px; margin: 20px 0;">
                        <p style="margin: 0;"><strong>💰 Refund Information:</strong> If payment was completed, your refund will be processed within 5-7 business days.</p>
                    </div>
                    ''' if order.payment_status == 'paid' else ''}
                    
                    <div style="text-align: center; margin: 30px 0;">
                        <a href="{os.environ.get('BASE_URL', 'http://localhost:5000')}/marketplace/browse" 
                           style="background: #28a745; color: white; padding: 15px 30px; text-decoration: none; border-radius: 5px; display: inline-block;">
                            Browse Marketplace
                        </a>
                    </div>
                    
                    <p>We hope to serve you again soon!</p>
                    
                    <p>Best regards,<br>The FarmLink AI Team</p>
                </div>
                
                <div style="background: #343a40; color: white; padding: 20px; text-align: center;">
                    <p style="margin: 0;">© 2024 FarmLink AI. Connecting Agriculture, Powering Growth.</p>
                </div>
            </div>
            """
            
            # Send to farmer
            farmer_subject = f"Order Cancelled - #{order.id}"
            farmer_html = f"""
            <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                <div style="background: #6c757d; padding: 20px; text-align: center;">
                    <h1 style="color: white; margin: 0;">Order Cancelled</h1>
                </div>
                
                <div style="padding: 30px;">
                    <h2>Hello {farmer.full_name or farmer.username},</h2>
                    
                    <p>An order for your crop has been cancelled.</p>
                    
                    <div style="background: #f8f9fa; padding: 20px; border-radius: 10px; margin: 20px 0;">
                        <h3 style="color: #6c757d;">Order Details:</h3>
                        <p><strong>Order ID:</strong> #{order.id}</p>
                        <p><strong>Crop:</strong> {crop.name}</p>
                        <p><strong>Quantity:</strong> {order.quantity_requested} {crop.unit}</p>
                        <p><strong>Buyer:</strong> {buyer.full_name or buyer.username}</p>
                        {f'<p><strong>Cancellation Reason:</strong> {order.cancellation_reason}</p>' if order.cancellation_reason else ''}
                    </div>
                    
                    <div style="background: #d1ecf1; border-left: 4px solid #17a2b8; padding: 15px; margin: 20px 0;">
                        <p style="margin: 0;"><strong>📦 Inventory Update:</strong> The crop quantity has been restored to your inventory.</p>
                    </div>
                    
                    <div style="text-align: center; margin: 30px 0;">
                        <a href="{os.environ.get('BASE_URL', 'http://localhost:5000')}/orders/my" 
                           style="background: #6c757d; color: white; padding: 15px 30px; text-decoration: none; border-radius: 5px; display: inline-block;">
                            View Orders
                        </a>
                    </div>
                    
                    <p>Best regards,<br>The FarmLink AI Team</p>
                </div>
                
                <div style="background: #343a40; color: white; padding: 20px; text-align: center;">
                    <p style="margin: 0;">© 2024 FarmLink AI. Connecting Agriculture, Powering Growth.</p>
                </div>
            </div>
            """
            
            # Send both emails
            buyer_result = self.send_email(buyer.email, buyer_subject, buyer_html)
            farmer_result = self.send_email(farmer.email, farmer_subject, farmer_html)
            
            return {
                "success": buyer_result.get("success") and farmer_result.get("success"),
                "buyer_result": buyer_result,
                "farmer_result": farmer_result
            }
        except Exception as e:
            logging.error(f"Failed to send order cancelled notification: {str(e)}")
            return {"success": False, "error": str(e)}
    
    def send_kyc_submission_confirmation(self, user):
        """Send KYC submission confirmation email"""
        try:
            log_notification_operation(
                logging.getLogger(__name__),
                'prepare',
                notification_type='kyc_submission',
                recipient_email=user.email,
                success=None
            )
            
            subject = "KYC Verification Submitted - FarmLink AI"
            
            html_content = f"""
            <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                <div style="background: #17a2b8; padding: 20px; text-align: center;">
                    <h1 style="color: white; margin: 0;">📋 KYC Verification Submitted</h1>
                </div>
                
                <div style="padding: 30px;">
                    <h2>Hello {user.full_name or user.username},</h2>
                    
                    <p>Thank you for submitting your KYC (Know Your Customer) verification documents. We have received your application and it is now under review.</p>
                    
                    <div style="background: #d1ecf1; border-left: 4px solid #17a2b8; padding: 20px; margin: 20px 0;">
                        <h3 style="color: #0c5460; margin-top: 0;">What Happens Next?</h3>
                        <ul style="color: #0c5460; margin: 10px 0; padding-left: 20px;">
                            <li>Our team will review your documents within <strong>2-3 business days</strong></li>
                            <li>You will receive an email notification once your KYC is verified</li>
                            <li>After verification, you can start listing crops and selling on FarmLink AI</li>
                        </ul>
                    </div>
                    
                    <div style="background: #f8f9fa; padding: 20px; border-radius: 10px; margin: 20px 0;">
                        <h3 style="color: #17a2b8; margin-top: 0;">Submission Details:</h3>
                        <p><strong>Submitted At:</strong> {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC</p>
                        <p><strong>Status:</strong> Pending Review</p>
                        <p><strong>Estimated Review Time:</strong> 2-3 business days</p>
                    </div>
                    
                    <div style="text-align: center; margin: 30px 0;">
                        <a href="{os.environ.get('BASE_URL', 'http://localhost:5000')}/kyc-status" 
                           style="background: #17a2b8; color: white; padding: 15px 30px; text-decoration: none; border-radius: 5px; display: inline-block;">
                            Check KYC Status
                        </a>
                    </div>
                    
                    <div style="background: #fff3cd; border-left: 4px solid #ffc107; padding: 15px; margin: 20px 0;">
                        <p style="margin: 0; color: #856404;"><strong>⚠️ Important:</strong> Please ensure your contact information is up to date. We may reach out if we need additional information.</p>
                    </div>
                    
                    <p>If you have any questions about the verification process, please contact our support team.</p>
                    
                    <p>Best regards,<br>The FarmLink AI Team</p>
                </div>
                
                <div style="background: #343a40; color: white; padding: 20px; text-align: center;">
                    <p style="margin: 0;">© 2024 FarmLink AI. Connecting Agriculture, Powering Growth.</p>
                </div>
            </div>
            """
            
            result = self.send_email(user.email, subject, html_content)
            
            log_notification_operation(
                logging.getLogger(__name__),
                'send_complete',
                notification_type='kyc_submission',
                recipient_email=user.email,
                success=result.get('success', False),
                error=result.get('error')
            )
            
            return result
        except Exception as e:
            log_notification_operation(
                logging.getLogger(__name__),
                'send_error',
                notification_type='kyc_submission',
                recipient_email=user.email if user else None,
                success=False,
                error=str(e)
            )
            logging.error(f"Failed to send KYC submission confirmation: {str(e)}")
            return {"success": False, "error": str(e)}
    
    def send_kyc_approval_notification(self, user):
        """Send KYC approval notification email"""
        try:
            log_notification_operation(
                logging.getLogger(__name__),
                'prepare',
                notification_type='kyc_approval',
                recipient_email=user.email,
                success=None
            )
            
            subject = "KYC Verified - You Can Now Start Selling!"
            
            html_content = f"""
            <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                <div style="background: #28a745; padding: 20px; text-align: center;">
                    <h1 style="color: white; margin: 0;">✅ KYC Verified Successfully!</h1>
                </div>
                
                <div style="padding: 30px;">
                    <h2>Congratulations {user.full_name or user.username}!</h2>
                    
                    <p>Great news! Your KYC (Know Your Customer) verification has been approved. You are now a verified seller on FarmLink AI and can access all selling features.</p>
                    
                    <div style="background: #d4edda; border-left: 4px solid #28a745; padding: 20px; margin: 20px 0;">
                        <h3 style="color: #155724; margin-top: 0;">🎉 What You Can Do Now:</h3>
                        <ul style="color: #155724; margin: 10px 0; padding-left: 20px;">
                            <li><strong>List Your Crops:</strong> Add your products to the marketplace</li>
                            <li><strong>Receive Orders:</strong> Start accepting orders from buyers</li>
                            <li><strong>Get Paid:</strong> Receive payments directly to your verified bank account</li>
                            <li><strong>Build Trust:</strong> Display your verified badge to attract more buyers</li>
                        </ul>
                    </div>
                    
                    <div style="background: #f8f9fa; padding: 20px; border-radius: 10px; margin: 20px 0;">
                        <h3 style="color: #28a745; margin-top: 0;">Verification Details:</h3>
                        <p><strong>Status:</strong> ✅ Verified</p>
                        <p><strong>Verified At:</strong> {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC</p>
                        <p><strong>Verification Badge:</strong> Active on all your listings</p>
                    </div>
                    
                    <div style="text-align: center; margin: 30px 0;">
                        <a href="{os.environ.get('BASE_URL', 'http://localhost:5000')}/crops/add" 
                           style="background: #28a745; color: white; padding: 15px 30px; text-decoration: none; border-radius: 5px; display: inline-block; margin: 5px;">
                            List Your First Crop
                        </a>
                        <a href="{os.environ.get('BASE_URL', 'http://localhost:5000')}/dashboard" 
                           style="background: #17a2b8; color: white; padding: 15px 30px; text-decoration: none; border-radius: 5px; display: inline-block; margin: 5px;">
                            Go to Dashboard
                        </a>
                    </div>
                    
                    <div style="background: #d1ecf1; border-left: 4px solid #17a2b8; padding: 15px; margin: 20px 0;">
                        <p style="margin: 0; color: #0c5460;"><strong>💡 Pro Tip:</strong> Verified sellers get more visibility in search results and build buyer trust faster. Make sure to keep your listings updated!</p>
                    </div>
                    
                    <p>Thank you for choosing FarmLink AI. We're excited to have you as a verified seller on our platform!</p>
                    
                    <p>Best regards,<br>The FarmLink AI Team</p>
                </div>
                
                <div style="background: #343a40; color: white; padding: 20px; text-align: center;">
                    <p style="margin: 0;">© 2024 FarmLink AI. Connecting Agriculture, Powering Growth.</p>
                </div>
            </div>
            """
            
            result = self.send_email(user.email, subject, html_content)
            
            log_notification_operation(
                logging.getLogger(__name__),
                'send_complete',
                notification_type='kyc_approval',
                recipient_email=user.email,
                success=result.get('success', False),
                error=result.get('error')
            )
            
            return result
        except Exception as e:
            log_notification_operation(
                logging.getLogger(__name__),
                'send_error',
                notification_type='kyc_approval',
                recipient_email=user.email if user else None,
                success=False,
                error=str(e)
            )
            logging.error(f"Failed to send KYC approval notification: {str(e)}")
            return {"success": False, "error": str(e)}
    
    def send_kyc_rejection_notification(self, user, rejection_reason):
        """Send KYC rejection notification email with reason"""
        try:
            log_notification_operation(
                logging.getLogger(__name__),
                'prepare',
                notification_type='kyc_rejection',
                recipient_email=user.email,
                success=None
            )
            
            subject = "KYC Verification Requires Attention"
            
            html_content = f"""
            <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                <div style="background: #ffc107; padding: 20px; text-align: center;">
                    <h1 style="color: #333; margin: 0;">⚠️ KYC Verification Requires Attention</h1>
                </div>
                
                <div style="padding: 30px;">
                    <h2>Hello {user.full_name or user.username},</h2>
                    
                    <p>Thank you for submitting your KYC verification documents. Unfortunately, we were unable to verify your documents at this time.</p>
                    
                    <div style="background: #fff3cd; border-left: 4px solid #ffc107; padding: 20px; margin: 20px 0;">
                        <h3 style="color: #856404; margin-top: 0;">Rejection Reason:</h3>
                        <p style="color: #856404; margin: 0; font-size: 16px;">{rejection_reason}</p>
                    </div>
                    
                    <div style="background: #f8f9fa; padding: 20px; border-radius: 10px; margin: 20px 0;">
                        <h3 style="color: #ffc107; margin-top: 0;">What You Need to Do:</h3>
                        <ol style="color: #333; margin: 10px 0; padding-left: 20px;">
                            <li>Review the rejection reason carefully</li>
                            <li>Prepare corrected or updated documents</li>
                            <li>Resubmit your KYC application with the correct information</li>
                        </ol>
                    </div>
                    
                    <div style="background: #d1ecf1; border-left: 4px solid #17a2b8; padding: 15px; margin: 20px 0;">
                        <p style="margin: 0; color: #0c5460;"><strong>📝 Common Issues:</strong></p>
                        <ul style="color: #0c5460; margin: 10px 0; padding-left: 20px;">
                            <li>Blurry or unclear document images</li>
                            <li>Mismatched information between documents</li>
                            <li>Expired or invalid documents</li>
                            <li>Incomplete information</li>
                        </ul>
                    </div>
                    
                    <div style="text-align: center; margin: 30px 0;">
                        <a href="{os.environ.get('BASE_URL', 'http://localhost:5000')}/kyc-resubmit" 
                           style="background: #ffc107; color: #333; padding: 15px 30px; text-decoration: none; border-radius: 5px; display: inline-block; font-weight: bold;">
                            Resubmit KYC Documents
                        </a>
                    </div>
                    
                    <div style="background: #d4edda; border-left: 4px solid #28a745; padding: 15px; margin: 20px 0;">
                        <p style="margin: 0; color: #155724;"><strong>💡 Tips for Successful Verification:</strong></p>
                        <ul style="color: #155724; margin: 10px 0; padding-left: 20px;">
                            <li>Ensure all documents are clear and readable</li>
                            <li>Verify that all information matches across documents</li>
                            <li>Use valid, non-expired documents</li>
                            <li>Double-check all entered information for accuracy</li>
                        </ul>
                    </div>
                    
                    <p>If you have any questions or need assistance with the resubmission process, please don't hesitate to contact our support team.</p>
                    
                    <p>We look forward to verifying your account soon!</p>
                    
                    <p>Best regards,<br>The FarmLink AI Team</p>
                </div>
                
                <div style="background: #343a40; color: white; padding: 20px; text-align: center;">
                    <p style="margin: 0;">© 2024 FarmLink AI. Connecting Agriculture, Powering Growth.</p>
                    <p style="margin: 10px 0 0 0; font-size: 12px;">Need help? <a href="mailto:farmlink76@gmail.com" style="color: #28a745; text-decoration: none;">Contact Support</a></p>
                </div>
            </div>
            """
            
            result = self.send_email(user.email, subject, html_content)
            
            log_notification_operation(
                logging.getLogger(__name__),
                'send_complete',
                notification_type='kyc_rejection',
                recipient_email=user.email,
                success=result.get('success', False),
                error=result.get('error')
            )
            
            return result
        except Exception as e:
            log_notification_operation(
                logging.getLogger(__name__),
                'send_error',
                notification_type='kyc_rejection',
                recipient_email=user.email if user else None,
                success=False,
                error=str(e)
            )
            logging.error(f"Failed to send KYC rejection notification: {str(e)}")
            return {"success": False, "error": str(e)}

class OTPService:
    """OTP verification service"""
    
    @staticmethod
    def generate_otp(length=6):
        """Generate random OTP"""
        return ''.join(random.choices(string.digits, k=length))
    
    @staticmethod
    def send_verification_otp(user):
        """Send OTP for email verification"""
        otp = OTPService.generate_otp()
        
        # Store OTP in user session or database (you might want to create an OTP table)
        # For now, we'll use a simple approach with user model
        user.verification_otp = otp
        user.otp_generated_at = datetime.utcnow()
        db.session.commit()
        
        email_service = EmailService()
        subject = "Verify Your Email - FarmLink AI"
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
        </head>
        <body style="margin: 0; padding: 0; font-family: Arial, sans-serif; background-color: #f4f4f4;">
            <table width="100%" cellpadding="0" cellspacing="0" style="background-color: #f4f4f4; padding: 20px;">
                <tr>
                    <td align="center">
                        <table width="600" cellpadding="0" cellspacing="0" style="background-color: white; border-radius: 10px; overflow: hidden; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
                            <!-- Header -->
                            <tr>
                                <td style="background: linear-gradient(135deg, #28a745 0%, #20c997 100%); padding: 40px; text-align: center;">
                                    <h1 style="color: white; margin: 0; font-size: 28px;">🌾 FarmLink AI</h1>
                                    <p style="color: white; margin: 10px 0 0 0; font-size: 16px;">Email Verification</p>
                                </td>
                            </tr>
                            
                            <!-- Body -->
                            <tr>
                                <td style="padding: 40px;">
                                    <h2 style="color: #333; margin: 0 0 20px 0;">Hello {user.full_name or user.username}!</h2>
                                    
                                    <p style="color: #666; font-size: 16px; line-height: 1.6; margin: 0 0 20px 0;">
                                        Thank you for registering with FarmLink AI. To complete your registration and start using our platform, please verify your email address.
                                    </p>
                                    
                                    <p style="color: #666; font-size: 16px; line-height: 1.6; margin: 0 0 30px 0;">
                                        Enter this verification code on the verification page:
                                    </p>
                                    
                                    <!-- OTP Box -->
                                    <table width="100%" cellpadding="0" cellspacing="0">
                                        <tr>
                                            <td align="center">
                                                <div style="background: #f8f9fa; border: 3px dashed #28a745; padding: 30px; border-radius: 10px; display: inline-block;">
                                                    <h1 style="color: #28a745; font-size: 48px; margin: 0; letter-spacing: 15px; font-weight: bold;">{otp}</h1>
                                                </div>
                                            </td>
                                        </tr>
                                    </table>
                                    
                                    <p style="color: #999; font-size: 14px; text-align: center; margin: 20px 0 30px 0;">
                                        ⏰ This code will expire in <strong>10 minutes</strong>
                                    </p>
                                    
                                    <!-- Security Notice -->
                                    <div style="background: #fff3cd; border-left: 4px solid #ffc107; padding: 15px; margin: 30px 0;">
                                        <p style="color: #856404; margin: 0; font-size: 14px;">
                                            <strong>🔒 Security Tip:</strong> Never share this code with anyone. FarmLink AI will never ask for your verification code via phone or email.
                                        </p>
                                    </div>
                                    
                                    <p style="color: #999; font-size: 13px; line-height: 1.6; margin: 20px 0 0 0;">
                                        If you didn't create an account with FarmLink AI, please ignore this email or contact our support team if you have concerns.
                                    </p>
                                </td>
                            </tr>
                            
                            <!-- Footer -->
                            <tr>
                                <td style="background: #f8f9fa; padding: 30px; text-align: center; border-top: 1px solid #e9ecef;">
                                    <p style="color: #6c757d; font-size: 14px; margin: 0 0 10px 0;">
                                        Need help? <a href="mailto:farmlink76@gmail.com" style="color: #28a745; text-decoration: none;">Contact Support</a>
                                    </p>
                                    <p style="color: #999; font-size: 12px; margin: 0;">
                                        © 2024 FarmLink AI. Connecting Agriculture, Powering Growth.
                                    </p>
                                </td>
                            </tr>
                        </table>
                    </td>
                </tr>
            </table>
        </body>
        </html>
        """
        
        text_content = f"""
        FarmLink AI - Email Verification
        
        Hello {user.full_name or user.username}!
        
        Thank you for registering with FarmLink AI. Please use the following verification code to complete your registration:
        
        Verification Code: {otp}
        
        This code will expire in 10 minutes.
        
        If you didn't create an account with FarmLink AI, please ignore this email.
        
        Need help? Contact us at farmlink76@gmail.com
        
        © 2024 FarmLink AI
        """
        
        return email_service.send_email(user.email, subject, html_content, text_content)
    
    @staticmethod
    def verify_otp(user, provided_otp):
        """Verify provided OTP"""
        if not hasattr(user, 'verification_otp') or not user.verification_otp:
            return False
        
        # Check if OTP is expired (10 minutes)
        if user.otp_generated_at and datetime.utcnow() - user.otp_generated_at > timedelta(minutes=10):
            return False
        
        return user.verification_otp == provided_otp

# Initialize email service as a singleton
email_service = EmailService()

# Export the instance for other modules to use
__all__ = ['email_service']
