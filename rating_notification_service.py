"""
Rating Notification Service - Handle rating-related notifications
"""
from datetime import datetime
from email_service import EmailService
from models import ProductRating, SellerResponse, User, RatingHelpfulVote, RatingNotificationPreference
from extensions import db
import logging
import os

logger = logging.getLogger(__name__)


class RatingNotificationService:
    """Handle rating-related notifications"""
    
    def __init__(self):
        self.email_service = EmailService()
        self.base_url = os.environ.get('BASE_URL', 'http://localhost:5000')
    
    def notify_seller_new_rating(self, rating_id):
        """
        Notify seller of new rating on their product
        Requirement 10.1: Send email to seller within 10 minutes of new rating
        
        Args:
            rating_id: ID of the newly created rating
            
        Returns:
            dict: Result of email send operation
        """
        try:
            # Get rating with related data
            rating = ProductRating.query.get(rating_id)
            if not rating:
                logger.error(f"Rating {rating_id} not found")
                return {"success": False, "error": "Rating not found"}
            
            # Get seller (product owner)
            seller = rating.product.farmer
            if not seller:
                logger.error(f"Seller not found for product {rating.product_id}")
                return {"success": False, "error": "Seller not found"}
            
            # Check notification preferences
            if not self._should_send_notification(seller.id, 'new_rating'):
                logger.info(f"Seller {seller.id} has disabled new rating notifications")
                return {"success": True, "message": "Notification disabled by user preference"}
            
            # Prepare email content
            subject = f"New {rating.rating}-Star Rating Received - {rating.product.name}"
            
            # Star visualization
            stars_html = self._generate_stars_html(rating.rating)
            
            html_content = f"""
            <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                <div style="background: linear-gradient(135deg, #28a745 0%, #20c997 100%); padding: 30px; text-align: center;">
                    <h1 style="color: white; margin: 0;">New Rating Received!</h1>
                </div>
                
                <div style="padding: 30px; background-color: #f8f9fa;">
                    <h2 style="color: #28a745;">Hello {seller.full_name or seller.username},</h2>
                    
                    <p>Great news! You've received a new rating for your product.</p>
                    
                    <div style="background: white; padding: 25px; border-radius: 10px; margin: 20px 0; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                        <h3 style="color: #28a745; margin-top: 0;">Rating Details</h3>
                        
                        <div style="text-align: center; margin: 20px 0;">
                            {stars_html}
                            <p style="font-size: 24px; font-weight: bold; color: #28a745; margin: 10px 0;">
                                {rating.rating} out of 5 stars
                            </p>
                        </div>
                        
                        <p><strong>Product:</strong> {rating.product.name}</p>
                        <p><strong>Buyer:</strong> {rating.buyer.full_name or rating.buyer.username}</p>
                        <p><strong>Date:</strong> {rating.created_at.strftime('%B %d, %Y at %I:%M %p')}</p>
                        
                        {f'''
                        <div style="background: #f8f9fa; padding: 15px; border-radius: 5px; margin-top: 15px;">
                            <p style="margin: 0;"><strong>Review:</strong></p>
                            <p style="margin: 10px 0 0 0; font-style: italic;">"{rating.review_text}"</p>
                        </div>
                        ''' if rating.review_text else ''}
                    </div>
                    
                    <div style="background: #fff3cd; border-left: 4px solid #ffc107; padding: 15px; border-radius: 5px; margin: 20px 0;">
                        <p style="margin: 0;"><strong>💡 Tip:</strong> Responding to ratings shows customers you care and can improve your reputation!</p>
                    </div>
                    
                    <div style="text-align: center; margin: 30px 0;">
                        <a href="{self.base_url}/ratings/rating/{rating.id}/respond" 
                           style="background: #28a745; color: white; padding: 15px 30px; text-decoration: none; border-radius: 5px; display: inline-block; margin: 5px;">
                            Respond to Rating
                        </a>
                        <a href="{self.base_url}/ratings/product/{rating.product_id}/ratings" 
                           style="background: #17a2b8; color: white; padding: 15px 30px; text-decoration: none; border-radius: 5px; display: inline-block; margin: 5px;">
                            View All Ratings
                        </a>
                    </div>
                    
                    <p style="color: #6c757d; font-size: 14px; margin-top: 30px;">
                        This is an automated notification. You can manage your notification preferences in your account settings.
                    </p>
                </div>
                
                <div style="background: #343a40; color: white; padding: 20px; text-align: center;">
                    <p style="margin: 0;">© 2024 FarmLink AI. Connecting Agriculture, Powering Growth.</p>
                </div>
            </div>
            """
            
            # Send email
            result = self.email_service.send_email(
                to_email=seller.email,
                subject=subject,
                html_content=html_content
            )
            
            if result.get('success'):
                logger.info(f"New rating notification sent to seller {seller.id} for rating {rating_id}")
            else:
                logger.error(f"Failed to send new rating notification: {result.get('error')}")
            
            return result
            
        except Exception as e:
            logger.error(f"Error sending new rating notification: {str(e)}")
            return {"success": False, "error": str(e)}
    
    def notify_buyer_seller_response(self, rating_id):
        """
        Notify buyer when seller responds to their rating
        Requirement 4.5, 10.1: Send email to buyer within 10 minutes of seller response
        
        Args:
            rating_id: ID of the rating that received a response
            
        Returns:
            dict: Result of email send operation
        """
        try:
            # Get rating with seller response
            rating = ProductRating.query.get(rating_id)
            if not rating:
                logger.error(f"Rating {rating_id} not found")
                return {"success": False, "error": "Rating not found"}
            
            if not rating.seller_response:
                logger.error(f"No seller response found for rating {rating_id}")
                return {"success": False, "error": "Seller response not found"}
            
            # Get buyer
            buyer = rating.buyer
            if not buyer:
                logger.error(f"Buyer not found for rating {rating_id}")
                return {"success": False, "error": "Buyer not found"}
            
            # Check notification preferences
            if not self._should_send_notification(buyer.id, 'seller_response'):
                logger.info(f"Buyer {buyer.id} has disabled seller response notifications")
                return {"success": True, "message": "Notification disabled by user preference"}
            
            seller_response = rating.seller_response
            seller = seller_response.seller
            
            # Prepare email content
            subject = f"Seller Responded to Your Rating - {rating.product.name}"
            
            stars_html = self._generate_stars_html(rating.rating)
            
            html_content = f"""
            <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                <div style="background: linear-gradient(135deg, #17a2b8 0%, #138496 100%); padding: 30px; text-align: center;">
                    <h1 style="color: white; margin: 0;">Seller Responded to Your Rating</h1>
                </div>
                
                <div style="padding: 30px; background-color: #f8f9fa;">
                    <h2 style="color: #17a2b8;">Hello {buyer.full_name or buyer.username},</h2>
                    
                    <p>The seller has responded to your rating!</p>
                    
                    <div style="background: white; padding: 25px; border-radius: 10px; margin: 20px 0; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                        <h3 style="color: #17a2b8; margin-top: 0;">Your Rating</h3>
                        
                        <div style="text-align: center; margin: 15px 0;">
                            {stars_html}
                        </div>
                        
                        <p><strong>Product:</strong> {rating.product.name}</p>
                        <p><strong>Your Rating Date:</strong> {rating.created_at.strftime('%B %d, %Y')}</p>
                        
                        {f'''
                        <div style="background: #f8f9fa; padding: 15px; border-radius: 5px; margin: 15px 0;">
                            <p style="margin: 0;"><strong>Your Review:</strong></p>
                            <p style="margin: 10px 0 0 0; font-style: italic;">"{rating.review_text}"</p>
                        </div>
                        ''' if rating.review_text else ''}
                        
                        <hr style="border: none; border-top: 2px solid #e9ecef; margin: 20px 0;">
                        
                        <h3 style="color: #28a745; margin-top: 20px;">
                            <i style="color: #28a745;">💬</i> Seller's Response
                        </h3>
                        
                        <div style="background: #e7f9f0; border-left: 4px solid #28a745; padding: 15px; border-radius: 5px; margin: 15px 0;">
                            <p style="margin: 0;"><strong>From:</strong> {seller.full_name or seller.username}</p>
                            <p style="margin: 10px 0 0 0;">{seller_response.response_text}</p>
                            <p style="margin: 10px 0 0 0; font-size: 12px; color: #6c757d;">
                                {seller_response.created_at.strftime('%B %d, %Y at %I:%M %p')}
                            </p>
                        </div>
                    </div>
                    
                    <div style="text-align: center; margin: 30px 0;">
                        <a href="{self.base_url}/ratings/product/{rating.product_id}/ratings" 
                           style="background: #17a2b8; color: white; padding: 15px 30px; text-decoration: none; border-radius: 5px; display: inline-block;">
                            View Full Conversation
                        </a>
                    </div>
                    
                    <p style="color: #6c757d; font-size: 14px; margin-top: 30px;">
                        This is an automated notification. You can manage your notification preferences in your account settings.
                    </p>
                </div>
                
                <div style="background: #343a40; color: white; padding: 20px; text-align: center;">
                    <p style="margin: 0;">© 2024 FarmLink AI. Connecting Agriculture, Powering Growth.</p>
                </div>
            </div>
            """
            
            # Send email
            result = self.email_service.send_email(
                to_email=buyer.email,
                subject=subject,
                html_content=html_content
            )
            
            if result.get('success'):
                logger.info(f"Seller response notification sent to buyer {buyer.id} for rating {rating_id}")
            else:
                logger.error(f"Failed to send seller response notification: {result.get('error')}")
            
            return result
            
        except Exception as e:
            logger.error(f"Error sending seller response notification: {str(e)}")
            return {"success": False, "error": str(e)}
    
    def notify_buyer_helpful_milestone(self, rating_id, milestone=5):
        """
        Notify buyer when their rating reaches helpful vote milestone
        Requirement 10.2: Send notification when rating reaches 5 helpful votes
        
        Args:
            rating_id: ID of the rating
            milestone: Number of helpful votes reached (default: 5)
            
        Returns:
            dict: Result of email send operation
        """
        try:
            # Get rating
            rating = ProductRating.query.get(rating_id)
            if not rating:
                logger.error(f"Rating {rating_id} not found")
                return {"success": False, "error": "Rating not found"}
            
            # Verify milestone reached
            if rating.helpful_count < milestone:
                logger.warning(f"Rating {rating_id} has not reached milestone {milestone}")
                return {"success": False, "error": f"Milestone {milestone} not reached"}
            
            # Get buyer
            buyer = rating.buyer
            if not buyer:
                logger.error(f"Buyer not found for rating {rating_id}")
                return {"success": False, "error": "Buyer not found"}
            
            # Check notification preferences
            if not self._should_send_notification(buyer.id, 'helpful_milestone'):
                logger.info(f"Buyer {buyer.id} has disabled helpful milestone notifications")
                return {"success": True, "message": "Notification disabled by user preference"}
            
            # Prepare email content
            subject = f"🎉 Your Rating Reached {milestone} Helpful Votes!"
            
            stars_html = self._generate_stars_html(rating.rating)
            
            html_content = f"""
            <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                <div style="background: linear-gradient(135deg, #ffc107 0%, #ff9800 100%); padding: 30px; text-align: center;">
                    <h1 style="color: white; margin: 0;">🎉 Milestone Reached!</h1>
                </div>
                
                <div style="padding: 30px; background-color: #f8f9fa;">
                    <h2 style="color: #ffc107;">Hello {buyer.full_name or buyer.username},</h2>
                    
                    <p>Congratulations! Your rating has been found helpful by the community.</p>
                    
                    <div style="background: white; padding: 25px; border-radius: 10px; margin: 20px 0; box-shadow: 0 2px 4px rgba(0,0,0,0.1); text-align: center;">
                        <div style="font-size: 48px; margin: 20px 0;">👍</div>
                        <h3 style="color: #ffc107; margin: 10px 0;">
                            {rating.helpful_count} people found your rating helpful!
                        </h3>
                    </div>
                    
                    <div style="background: white; padding: 25px; border-radius: 10px; margin: 20px 0; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                        <h3 style="color: #28a745; margin-top: 0;">Your Rating</h3>
                        
                        <div style="text-align: center; margin: 15px 0;">
                            {stars_html}
                        </div>
                        
                        <p><strong>Product:</strong> {rating.product.name}</p>
                        <p><strong>Rating Date:</strong> {rating.created_at.strftime('%B %d, %Y')}</p>
                        
                        {f'''
                        <div style="background: #f8f9fa; padding: 15px; border-radius: 5px; margin: 15px 0;">
                            <p style="margin: 0;"><strong>Your Review:</strong></p>
                            <p style="margin: 10px 0 0 0; font-style: italic;">"{rating.review_text}"</p>
                        </div>
                        ''' if rating.review_text else ''}
                    </div>
                    
                    <div style="background: #d4edda; border-left: 4px solid #28a745; padding: 15px; border-radius: 5px; margin: 20px 0;">
                        <p style="margin: 0;"><strong>Thank you for contributing!</strong></p>
                        <p style="margin: 10px 0 0 0;">Your detailed and helpful reviews help other buyers make informed decisions. Keep up the great work!</p>
                    </div>
                    
                    <div style="text-align: center; margin: 30px 0;">
                        <a href="{self.base_url}/ratings/product/{rating.product_id}/ratings" 
                           style="background: #ffc107; color: #212529; padding: 15px 30px; text-decoration: none; border-radius: 5px; display: inline-block; font-weight: bold;">
                            View Your Rating
                        </a>
                    </div>
                    
                    <p style="color: #6c757d; font-size: 14px; margin-top: 30px;">
                        This is an automated notification. You can manage your notification preferences in your account settings.
                    </p>
                </div>
                
                <div style="background: #343a40; color: white; padding: 20px; text-align: center;">
                    <p style="margin: 0;">© 2024 FarmLink AI. Connecting Agriculture, Powering Growth.</p>
                </div>
            </div>
            """
            
            # Send email
            result = self.email_service.send_email(
                to_email=buyer.email,
                subject=subject,
                html_content=html_content
            )
            
            if result.get('success'):
                logger.info(f"Helpful milestone notification sent to buyer {buyer.id} for rating {rating_id}")
            else:
                logger.error(f"Failed to send helpful milestone notification: {result.get('error')}")
            
            return result
            
        except Exception as e:
            logger.error(f"Error sending helpful milestone notification: {str(e)}")
            return {"success": False, "error": str(e)}
    
    def notify_rating_removed(self, rating_id, user_id, reason):
        """
        Notify user when their rating is removed by admin
        Requirement 8.5, 10.3: Notify user within 10 minutes when rating is removed
        
        Args:
            rating_id: ID of the removed rating
            user_id: ID of the user whose rating was removed
            reason: Reason for removal
            
        Returns:
            dict: Result of email send operation
        """
        try:
            # Get user
            user = User.query.get(user_id)
            if not user:
                logger.error(f"User {user_id} not found")
                return {"success": False, "error": "User not found"}
            
            # Check notification preferences
            if not self._should_send_notification(user.id, 'rating_removed'):
                logger.info(f"User {user.id} has disabled rating removed notifications")
                return {"success": True, "message": "Notification disabled by user preference"}
            
            # Prepare email content
            subject = "Rating Removed - FarmLink AI"
            
            html_content = f"""
            <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                <div style="background: #dc3545; padding: 30px; text-align: center;">
                    <h1 style="color: white; margin: 0;">Rating Removed</h1>
                </div>
                
                <div style="padding: 30px; background-color: #f8f9fa;">
                    <h2 style="color: #dc3545;">Hello {user.full_name or user.username},</h2>
                    
                    <p>We're writing to inform you that one of your product ratings has been removed by our moderation team.</p>
                    
                    <div style="background: white; padding: 25px; border-radius: 10px; margin: 20px 0; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                        <h3 style="color: #dc3545; margin-top: 0;">Removal Details</h3>
                        
                        <p><strong>Rating ID:</strong> #{rating_id}</p>
                        <p><strong>Removal Date:</strong> {datetime.utcnow().strftime('%B %d, %Y at %I:%M %p')}</p>
                        <p><strong>Reason:</strong> {reason}</p>
                    </div>
                    
                    <div style="background: #fff3cd; border-left: 4px solid #ffc107; padding: 15px; border-radius: 5px; margin: 20px 0;">
                        <p style="margin: 0;"><strong>Why was this removed?</strong></p>
                        <p style="margin: 10px 0 0 0;">
                            Our moderation team reviews flagged content to ensure all ratings comply with our community guidelines. 
                            Your rating was found to violate these guidelines.
                        </p>
                    </div>
                    
                    <div style="background: white; padding: 20px; border-radius: 10px; margin: 20px 0;">
                        <h3 style="color: #28a745; margin-top: 0;">Community Guidelines</h3>
                        <ul style="line-height: 1.8;">
                            <li>Ratings must be based on actual purchase experience</li>
                            <li>Reviews should be honest and constructive</li>
                            <li>No spam, offensive language, or inappropriate content</li>
                            <li>No fake or fraudulent reviews</li>
                            <li>Respect other users and sellers</li>
                        </ul>
                    </div>
                    
                    <p>If you believe this removal was made in error, please contact our support team.</p>
                    
                    <div style="text-align: center; margin: 30px 0;">
                        <a href="{self.base_url}/support/contact" 
                           style="background: #28a745; color: white; padding: 15px 30px; text-decoration: none; border-radius: 5px; display: inline-block;">
                            Contact Support
                        </a>
                        <a href="{self.base_url}/community-guidelines" 
                           style="background: #6c757d; color: white; padding: 15px 30px; text-decoration: none; border-radius: 5px; display: inline-block; margin-left: 10px;">
                            View Guidelines
                        </a>
                    </div>
                    
                    <p style="color: #6c757d; font-size: 14px; margin-top: 30px;">
                        Thank you for helping us maintain a trustworthy marketplace.
                    </p>
                </div>
                
                <div style="background: #343a40; color: white; padding: 20px; text-align: center;">
                    <p style="margin: 0;">© 2024 FarmLink AI. Connecting Agriculture, Powering Growth.</p>
                </div>
            </div>
            """
            
            # Send email
            result = self.email_service.send_email(
                to_email=user.email,
                subject=subject,
                html_content=html_content
            )
            
            if result.get('success'):
                logger.info(f"Rating removed notification sent to user {user_id} for rating {rating_id}")
            else:
                logger.error(f"Failed to send rating removed notification: {result.get('error')}")
            
            return result
            
        except Exception as e:
            logger.error(f"Error sending rating removed notification: {str(e)}")
            return {"success": False, "error": str(e)}
    
    def _generate_stars_html(self, rating):
        """
        Generate HTML for star visualization
        
        Args:
            rating: Rating value (1-5)
            
        Returns:
            str: HTML string with star visualization
        """
        full_stars = int(rating)
        empty_stars = 5 - full_stars
        
        stars_html = '<div style="font-size: 24px; color: #ffc107;">'
        stars_html += '★' * full_stars
        stars_html += '☆' * empty_stars
        stars_html += '</div>'
        
        return stars_html
    
    def _should_send_notification(self, user_id, notification_type):
        """
        Check if user wants to receive this type of notification
        Requirement 10.4: Allow users to configure notification preferences
        
        Args:
            user_id: ID of the user
            notification_type: Type of notification (new_rating, seller_response, helpful_milestone, rating_removed)
            
        Returns:
            bool: True if notification should be sent
        """
        try:
            # Get user's notification preferences
            prefs = RatingNotificationPreference.query.filter_by(user_id=user_id).first()
            
            if not prefs:
                # Default: all notifications enabled
                return True
            
            # Check specific preference
            preference_map = {
                'new_rating': prefs.notify_new_rating,
                'seller_response': prefs.notify_seller_response,
                'helpful_milestone': prefs.notify_helpful_milestone,
                'rating_removed': prefs.notify_rating_removed
            }
            
            return preference_map.get(notification_type, True)
            
        except Exception as e:
            logger.error(f"Error checking notification preferences: {str(e)}")
            # Default to sending notification if check fails
            return True


# Create singleton instance
rating_notification_service = RatingNotificationService()

# Export for use in other modules
__all__ = ['RatingNotificationService', 'rating_notification_service']
