"""
Rating Service - Business logic for product rating system
"""
from datetime import datetime, timedelta
from flask import request
from sqlalchemy import func
from extensions import db
from models import (
    ProductRating, SellerReputation, RatingAuditLog, 
    Order, Crop, User, RatingHelpfulVote, SellerResponse
)
from fraud_prevention_service import FraudPreventionService
from rating_notification_service import rating_notification_service
from utils import sanitize_text
from flask import current_app
import json
import logging

logger = logging.getLogger(__name__)


class RatingService:
    """Business logic for rating operations"""
    
    # Defaults for configuration constants in case they're not set in app.config
    DEFAULT_RATING_SUBMISSION_WINDOW_DAYS = 90
    DEFAULT_RATING_EDIT_WINDOW_DAYS = 30
    DEFAULT_RATING_DELETE_WINDOW_DAYS = 30
    DEFAULT_RATING_MIN_ORDER_VALUE = 10
    
    @staticmethod
    def can_rate_order(user_id, order_id):
        """
        Check if user can rate an order
        
        Args:
            user_id: ID of the user attempting to rate
            order_id: ID of the order to rate
            
        Returns:
            tuple: (bool, str) - (can_rate, error_message)
        """
        # Verify order exists
        order = Order.query.get(order_id)
        if not order:
            return False, "Order not found"
        
        # Verify order belongs to user
        if order.buyer_id != user_id:
            return False, "You can only rate your own orders"
        
        # Prevent sellers from rating their own products
        is_allowed, error_msg = FraudPreventionService.prevent_seller_self_rating(user_id, order_id)
        if not is_allowed:
            return False, error_msg
        
        # Check order is delivered (final successful state)
        if order.status != 'delivered':
            return False, "You can only rate delivered orders"
        
        # Check payment is successful
        if order.payment_status != 'paid':
            return False, "Order must be paid before rating"
        
        # Check rating doesn't already exist for order
        # (Database constraint also enforces this)
        existing_rating = ProductRating.query.filter_by(order_id=order_id).first()
        if existing_rating:
            return False, "You have already rated this order"
        
        # Verify within 90-day submission window
        if order.updated_at:
            days_since_completion = (datetime.utcnow() - order.updated_at).days
            window_days = current_app.config.get('RATING_SUBMISSION_WINDOW_DAYS', RatingService.DEFAULT_RATING_SUBMISSION_WINDOW_DAYS)
            if days_since_completion > window_days:
                return False, f"Rating window expired. You can only rate orders within {window_days} days of completion"
        
        # Check minimum order value requirement
        min_order_value = current_app.config.get('RATING_MIN_ORDER_VALUE', RatingService.DEFAULT_RATING_MIN_ORDER_VALUE)
        is_valid, error_msg = FraudPreventionService.verify_minimum_order_value(
            order_id, 
            min_order_value
        )
        if not is_valid:
            return False, error_msg
        
        # Check rate limiting
        is_allowed, error_msg = FraudPreventionService.check_rate_limit(user_id)
        if not is_allowed:
            return False, error_msg
        
        return True, None
    
    @staticmethod
    def create_rating(buyer_id, order_id, rating, review_text=None):
        """
        Create a new product rating
        
        Args:
            buyer_id: ID of the buyer submitting the rating
            order_id: ID of the order being rated
            rating: Rating value (1-5)
            review_text: Optional review text
            
        Returns:
            ProductRating: The created rating object
            
        Raises:
            ValueError: If validation fails
        """
        # Validate inputs
        if not isinstance(rating, int) or rating < 1 or rating > 5:
            raise ValueError("Rating must be an integer between 1 and 5")
        
        # Check eligibility
        can_rate, error_msg = RatingService.can_rate_order(buyer_id, order_id)
        if not can_rate:
            raise ValueError(error_msg)
        
        # Get order details
        order = Order.query.get(order_id)
        if not order:
            raise ValueError("Order not found")
        
        # Sanitize review text input
        sanitized_review = None
        if review_text:
            # Remove all HTML tags and clean the text
            sanitized_review = sanitize_text(review_text)
            
            # Validate length
            if len(sanitized_review) < 10:
                raise ValueError("Review text must be at least 10 characters")
            if len(sanitized_review) > 1000:
                raise ValueError("Review text cannot exceed 1000 characters")
        
        # Create rating record in database
        new_rating = ProductRating(
            buyer_id=buyer_id,
            product_id=order.crop_id,
            order_id=order_id,
            rating=rating,
            review_text=sanitized_review,
            is_verified_purchase=True,
            created_at=datetime.utcnow()
        )
        
        db.session.add(new_rating)
        db.session.flush()  # Get the rating ID
        
        # Log audit trail entry
        RatingService._log_rating_action(
            action='create',
            rating_id=new_rating.id,
            user_id=buyer_id,
            old_value=None,
            new_value=json.dumps({
                'rating': rating,
                'review_text': sanitized_review
            })
        )
        
        # Detect suspicious patterns and flag for admin review
        try:
            ip_address = request.remote_addr if request else None
            fraud_check = FraudPreventionService.detect_suspicious_patterns(
                user_id=buyer_id,
                ip_address=ip_address
            )
            
            if fraud_check['should_flag']:
                logger.warning(
                    f"Suspicious pattern detected for rating {new_rating.id}: "
                    f"{', '.join(fraud_check['reasons'])}"
                )
                # Flag the rating for admin review
                FraudPreventionService.flag_suspicious_rating(
                    new_rating.id,
                    fraud_check['reasons']
                )
        except Exception as fraud_err:
            # Don't fail the rating creation if fraud detection fails
            logger.error(f"Error in fraud detection: {str(fraud_err)}")
        
        # Trigger reputation recalculation
        seller_id = order.farmer_id
        RatingService.calculate_seller_reputation(seller_id)
        
        db.session.commit()
        
        # Send notification to seller about new rating
        # Notify seller within 10 minutes of new rating
        try:
            rating_notification_service.notify_seller_new_rating(new_rating.id)
        except Exception as notif_err:
            # Don't fail the rating creation if notification fails
            logger.error(f"Error sending new rating notification: {str(notif_err)}")
        
        return new_rating
    
    @staticmethod
    def update_rating(rating_id, user_id, new_rating, new_review_text):
        """
        Update an existing rating
        
        Args:
            rating_id: ID of the rating to update
            user_id: ID of the user attempting to update
            new_rating: New rating value (1-5)
            new_review_text: New review text
            
        Returns:
            ProductRating: The updated rating object
            
        Raises:
            ValueError: If validation fails
        """
        # Validate new rating value
        if not isinstance(new_rating, int) or new_rating < 1 or new_rating > 5:
            raise ValueError("Rating must be an integer between 1 and 5")
        
        # Get existing rating
        rating = ProductRating.query.get(rating_id)
        if not rating:
            raise ValueError("Rating not found")
        
        # Verify ownership
        if rating.buyer_id != user_id:
            raise ValueError("You can only edit your own ratings")
        
        # Check edit window (30 days)
        days_since_creation = (datetime.utcnow() - rating.created_at).days
        window_days = current_app.config.get('RATING_EDIT_WINDOW_DAYS', RatingService.DEFAULT_RATING_EDIT_WINDOW_DAYS)
        if days_since_creation > window_days:
            raise ValueError(f"Edit window expired. You can only edit ratings within {window_days} days of submission")
        
        # Sanitize new review text
        sanitized_review = None
        if new_review_text:
            sanitized_review = sanitize_text(new_review_text)
            
            # Validate length
            if len(sanitized_review) < 10:
                raise ValueError("Review text must be at least 10 characters")
            if len(sanitized_review) > 1000:
                raise ValueError("Review text cannot exceed 1000 characters")
        
        # Store old values for audit log
        old_value = json.dumps({
            'rating': rating.rating,
            'review_text': rating.review_text
        })
        
        # Update rating
        rating.rating = new_rating
        rating.review_text = sanitized_review
        rating.edited_at = datetime.utcnow()
        rating.updated_at = datetime.utcnow()
        
        # Log audit trail
        RatingService._log_rating_action(
            action='update',
            rating_id=rating_id,
            user_id=user_id,
            old_value=old_value,
            new_value=json.dumps({
                'rating': new_rating,
                'review_text': sanitized_review
            })
        )
        
        # Recalculate seller reputation
        seller_id = rating.product.farmer_id
        RatingService.calculate_seller_reputation(seller_id)
        
        db.session.commit()
        
        return rating
    
    @staticmethod
    def delete_rating(rating_id, user_id):
        """
        Delete a rating
        
        Args:
            rating_id: ID of the rating to delete
            user_id: ID of the user attempting to delete
            
        Returns:
            bool: True if successful
            
        Raises:
            ValueError: If validation fails
        """
        # Get rating
        rating = ProductRating.query.get(rating_id)
        if not rating:
            raise ValueError("Rating not found")
        
        # Verify ownership
        if rating.buyer_id != user_id:
            raise ValueError("You can only delete your own ratings")
        
        # Check delete window (30 days)
        days_since_creation = (datetime.utcnow() - rating.created_at).days
        window_days = current_app.config.get('RATING_DELETE_WINDOW_DAYS', RatingService.DEFAULT_RATING_DELETE_WINDOW_DAYS)
        if days_since_creation > window_days:
            raise ValueError(f"Delete window expired. You can only delete ratings within {window_days} days of submission")
        
        # Store seller ID before deletion
        seller_id = rating.product.farmer_id
        
        # Store old value for audit log
        old_value = json.dumps({
            'rating': rating.rating,
            'review_text': rating.review_text,
            'product_id': rating.product_id,
            'order_id': rating.order_id
        })
        
        # Log audit trail before deletion
        RatingService._log_rating_action(
            action='delete',
            rating_id=rating_id,
            user_id=user_id,
            old_value=old_value,
            new_value=None
        )
        
        # Delete rating (cascade will handle related records)
        db.session.delete(rating)
        
        # Recalculate seller reputation
        RatingService.calculate_seller_reputation(seller_id)
        
        db.session.commit()
        
        return True
    
    @staticmethod
    def calculate_seller_reputation(seller_id):
        """
        Calculate and update seller reputation
        
        Args:
            seller_id: ID of the seller
            
        Returns:
            SellerReputation: The updated reputation object
        """
        # Query all non-hidden ratings for seller's products
        ratings_query = db.session.query(
            ProductRating.rating
        ).join(
            Crop, ProductRating.product_id == Crop.id
        ).filter(
            Crop.farmer_id == seller_id,
            ProductRating.is_hidden == False
        )
        
        # Get all ratings
        all_ratings = ratings_query.all()
        
        if not all_ratings:
            # No ratings - set defaults or remove reputation record
            reputation = SellerReputation.query.filter_by(seller_id=seller_id).first()
            if reputation:
                reputation.average_rating = 0.0
                reputation.total_ratings = 0
                reputation.five_star_count = 0
                reputation.four_star_count = 0
                reputation.three_star_count = 0
                reputation.two_star_count = 0
                reputation.one_star_count = 0
                reputation.last_updated = datetime.utcnow()
            else:
                # Create new reputation record with zeros
                reputation = SellerReputation(
                    seller_id=seller_id,
                    average_rating=0.0,
                    total_ratings=0,
                    five_star_count=0,
                    four_star_count=0,
                    three_star_count=0,
                    two_star_count=0,
                    one_star_count=0
                )
                db.session.add(reputation)
            
            db.session.commit()
            return reputation
        
        # Calculate average rating
        rating_values = [r.rating for r in all_ratings]
        average_rating = sum(rating_values) / len(rating_values)
        
        # Calculate distribution
        five_star = sum(1 for r in rating_values if r == 5)
        four_star = sum(1 for r in rating_values if r == 4)
        three_star = sum(1 for r in rating_values if r == 3)
        two_star = sum(1 for r in rating_values if r == 2)
        one_star = sum(1 for r in rating_values if r == 1)
        
        # Update SellerReputation table
        reputation = SellerReputation.query.filter_by(seller_id=seller_id).first()
        
        if reputation:
            # Update existing record
            reputation.average_rating = round(average_rating, 2)
            reputation.total_ratings = len(rating_values)
            reputation.five_star_count = five_star
            reputation.four_star_count = four_star
            reputation.three_star_count = three_star
            reputation.two_star_count = two_star
            reputation.one_star_count = one_star
            reputation.last_updated = datetime.utcnow()
        else:
            # Create new reputation record
            reputation = SellerReputation(
                seller_id=seller_id,
                average_rating=round(average_rating, 2),
                total_ratings=len(rating_values),
                five_star_count=five_star,
                four_star_count=four_star,
                three_star_count=three_star,
                two_star_count=two_star,
                one_star_count=one_star
            )
            db.session.add(reputation)
        
        db.session.commit()
        
        return reputation
    
    @staticmethod
    def _log_rating_action(action, rating_id, user_id, old_value=None, new_value=None):
        """
        Log rating action to audit trail
        
        Args:
            action: Action type (create, update, delete, hide, etc.)
            rating_id: ID of the rating
            user_id: ID of the user performing the action
            old_value: Previous value (JSON string)
            new_value: New value (JSON string)
        """
        # Get IP address and user agent from request context
        ip_address = None
        user_agent = None
        
        try:
            if request:
                ip_address = request.remote_addr
                user_agent = request.user_agent.string if request.user_agent else None
        except RuntimeError:
            # No request context (e.g., in tests or background tasks)
            pass
        
        audit_log = RatingAuditLog(
            action=action,
            rating_id=rating_id,
            user_id=user_id,
            old_value=old_value,
            new_value=new_value,
            ip_address=ip_address,
            user_agent=user_agent,
            created_at=datetime.utcnow()
        )
        
        db.session.add(audit_log)
        # Note: commit is handled by the calling method
