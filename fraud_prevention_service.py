"""
Fraud Prevention Service - Detect and prevent fraudulent rating activities
"""
from datetime import datetime, timedelta
from flask import request
from sqlalchemy import func
from extensions import db
from models import ProductRating, RatingAuditLog, RatingFlag, Crop, User
import logging

logger = logging.getLogger(__name__)


class FraudPreventionService:
    """Service for detecting and preventing fraudulent rating activities"""
    
    # Configuration constants
    MAX_RATINGS_PER_HOUR = 10
    SUSPICIOUS_IP_WINDOW_HOURS = 1
    SUSPICIOUS_IP_THRESHOLD = 5
    
    @staticmethod
    def detect_suspicious_patterns(user_id=None, ip_address=None):
        """
        Detect suspicious rating patterns for fraud prevention
        
        Requirements: 9.4
        
        Args:
            user_id: Optional user ID to check
            ip_address: Optional IP address to check
            
        Returns:
            dict: {
                'is_suspicious': bool,
                'reasons': list of str,
                'should_flag': bool
            }
        """
        reasons = []
        is_suspicious = False
        
        # Requirement 9.4: Check for multiple ratings from same IP within 1 hour
        if ip_address:
            ip_suspicious, ip_reasons = FraudPreventionService._check_ip_patterns(ip_address)
            if ip_suspicious:
                is_suspicious = True
                reasons.extend(ip_reasons)
        
        # Check for suspicious user patterns
        if user_id:
            user_suspicious, user_reasons = FraudPreventionService._check_user_patterns(user_id)
            if user_suspicious:
                is_suspicious = True
                reasons.extend(user_reasons)
        
        # Determine if ratings should be flagged for admin review
        should_flag = is_suspicious and len(reasons) > 0
        
        return {
            'is_suspicious': is_suspicious,
            'reasons': reasons,
            'should_flag': should_flag
        }
    
    @staticmethod
    def _check_ip_patterns(ip_address):
        """
        Check for suspicious patterns from an IP address
        
        Requirement: 9.4
        
        Args:
            ip_address: IP address to check
            
        Returns:
            tuple: (is_suspicious: bool, reasons: list)
        """
        reasons = []
        is_suspicious = False
        
        # Check for multiple ratings from same IP within 1 hour
        one_hour_ago = datetime.utcnow() - timedelta(hours=FraudPreventionService.SUSPICIOUS_IP_WINDOW_HOURS)
        
        recent_ratings_from_ip = db.session.query(
            func.count(RatingAuditLog.id)
        ).filter(
            RatingAuditLog.ip_address == ip_address,
            RatingAuditLog.action == 'create',
            RatingAuditLog.created_at >= one_hour_ago
        ).scalar()
        
        if recent_ratings_from_ip >= FraudPreventionService.SUSPICIOUS_IP_THRESHOLD:
            is_suspicious = True
            reasons.append(
                f"Multiple ratings ({recent_ratings_from_ip}) from same IP address within 1 hour"
            )
            logger.warning(
                f"Suspicious IP pattern detected: {ip_address} - "
                f"{recent_ratings_from_ip} ratings in 1 hour"
            )
        
        return is_suspicious, reasons
    
    @staticmethod
    def _check_user_patterns(user_id):
        """
        Check for suspicious patterns from a user
        
        Args:
            user_id: User ID to check
            
        Returns:
            tuple: (is_suspicious: bool, reasons: list)
        """
        reasons = []
        is_suspicious = False
        
        # Check for rapid rating submissions
        one_hour_ago = datetime.utcnow() - timedelta(hours=1)
        
        recent_ratings = ProductRating.query.filter(
            ProductRating.buyer_id == user_id,
            ProductRating.created_at >= one_hour_ago
        ).count()
        
        if recent_ratings >= FraudPreventionService.MAX_RATINGS_PER_HOUR:
            is_suspicious = True
            reasons.append(
                f"User submitted {recent_ratings} ratings within 1 hour (limit: {FraudPreventionService.MAX_RATINGS_PER_HOUR})"
            )
            logger.warning(
                f"Suspicious user pattern detected: user {user_id} - "
                f"{recent_ratings} ratings in 1 hour"
            )
        
        # Check for unusual rating patterns (all same rating value)
        user_ratings = ProductRating.query.filter_by(
            buyer_id=user_id
        ).order_by(
            ProductRating.created_at.desc()
        ).limit(10).all()
        
        if len(user_ratings) >= 5:
            rating_values = [r.rating for r in user_ratings]
            unique_ratings = set(rating_values)
            
            # If all ratings are the same (all 5-star or all 1-star)
            if len(unique_ratings) == 1 and rating_values[0] in [1, 5]:
                is_suspicious = True
                reasons.append(
                    f"User's last {len(user_ratings)} ratings are all {rating_values[0]} stars"
                )
                logger.warning(
                    f"Suspicious rating pattern: user {user_id} - "
                    f"all recent ratings are {rating_values[0]} stars"
                )
        
        return is_suspicious, reasons
    
    @staticmethod
    def check_rate_limit(user_id):
        """
        Check if user has exceeded rate limit for rating submissions
        
        Requirement: 11.3
        
        Args:
            user_id: User ID to check
            
        Returns:
            tuple: (is_allowed: bool, error_message: str or None)
        """
        one_hour_ago = datetime.utcnow() - timedelta(hours=1)
        
        # Count ratings submitted in the last hour
        recent_ratings_count = ProductRating.query.filter(
            ProductRating.buyer_id == user_id,
            ProductRating.created_at >= one_hour_ago
        ).count()
        
        if recent_ratings_count >= FraudPreventionService.MAX_RATINGS_PER_HOUR:
            logger.warning(
                f"Rate limit exceeded for user {user_id}: "
                f"{recent_ratings_count} ratings in last hour"
            )
            return False, (
                f"Rate limit exceeded. You can submit a maximum of "
                f"{FraudPreventionService.MAX_RATINGS_PER_HOUR} ratings per hour. "
                f"Please try again later."
            )
        
        return True, None
    
    @staticmethod
    def prevent_seller_self_rating(user_id, order_id):
        """
        Prevent sellers from rating their own products
        
        Requirement: 9.3
        
        Args:
            user_id: User ID attempting to rate
            order_id: Order ID being rated
            
        Returns:
            tuple: (is_allowed: bool, error_message: str or None)
        """
        from models import Order
        
        # Get the order
        order = Order.query.get(order_id)
        if not order:
            return False, "Order not found"
        
        # Check if user is the seller (farmer) of the product
        if order.farmer_id == user_id:
            logger.warning(
                f"Seller self-rating attempt blocked: user {user_id} "
                f"attempted to rate their own product (order {order_id})"
            )
            return False, "You cannot rate your own products"
        
        return True, None
    
    @staticmethod
    def flag_suspicious_rating(rating_id, reasons):
        """
        Flag a rating for admin review due to suspicious patterns
        
        Requirement: 9.4
        
        Args:
            rating_id: ID of the rating to flag
            reasons: List of reasons for flagging
            
        Returns:
            RatingFlag: The created flag object
        """
        # Create a system-generated flag
        flag = RatingFlag(
            rating_id=rating_id,
            flagger_id=1,  # System user ID (admin)
            reason='suspicious_pattern',
            description='; '.join(reasons),
            status='pending',
            created_at=datetime.utcnow()
        )
        
        db.session.add(flag)
        
        # Mark the rating as flagged
        rating = ProductRating.query.get(rating_id)
        if rating:
            rating.is_flagged = True
            rating.updated_at = datetime.utcnow()
        
        db.session.commit()
        
        logger.info(
            f"Rating {rating_id} flagged for suspicious activity: {'; '.join(reasons)}"
        )
        
        return flag
    
    @staticmethod
    def verify_minimum_order_value(order_id, min_value=10):
        """
        Verify order meets minimum value requirement for rating
        
        Requirement: 9.5
        
        Args:
            order_id: Order ID to check
            min_value: Minimum order value required (default: 10)
            
        Returns:
            tuple: (is_valid: bool, error_message: str or None)
        """
        from models import Order
        
        order = Order.query.get(order_id)
        if not order:
            return False, "Order not found"
        
        if order.total_amount < min_value:
            logger.info(
                f"Order {order_id} does not meet minimum value for rating: "
                f"{order.total_amount} < {min_value}"
            )
            return False, (
                f"Order value must be at least {min_value} to enable rating. "
                f"This order's value is {order.total_amount}."
            )
        
        return True, None
