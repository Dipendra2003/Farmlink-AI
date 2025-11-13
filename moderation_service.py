"""
Moderation Service - Business logic for rating moderation system
"""
from datetime import datetime
from flask import request
from extensions import db
from models import (
    ProductRating, RatingFlag, User, RatingAuditLog
)
from rating_service import RatingService
from rating_notification_service import rating_notification_service
from email_service import EmailService
import logging

logger = logging.getLogger(__name__)


class ModerationService:
    """Business logic for rating moderation"""
    
    @staticmethod
    def flag_rating(rating_id, flagger_id, reason, description=None):
        """
        Flag a rating for moderation
        
        Args:
            rating_id: ID of the rating to flag
            flagger_id: ID of the user flagging the rating
            reason: Reason for flagging (spam, inappropriate, fake, offensive, other)
            description: Optional additional details
            
        Returns:
            RatingFlag: The created flag object
            
        Raises:
            ValueError: If validation fails
        """
        # Validate rating exists
        rating = ProductRating.query.get(rating_id)
        if not rating:
            raise ValueError("Rating not found")
        
        # Validate flagger exists
        flagger = User.query.get(flagger_id)
        if not flagger:
            raise ValueError("User not found")
        
        # Prevent users from flagging their own ratings
        if rating.buyer_id == flagger_id:
            raise ValueError("You cannot flag your own rating")
        
        # Check if user has already flagged this rating
        existing_flag = RatingFlag.query.filter_by(
            rating_id=rating_id,
            flagger_id=flagger_id,
            status='pending'
        ).first()
        
        if existing_flag:
            raise ValueError("You have already flagged this rating")
        
        # Validate reason
        valid_reasons = ['spam', 'inappropriate', 'fake', 'offensive', 'other']
        if reason not in valid_reasons:
            raise ValueError(f"Invalid reason. Must be one of: {', '.join(valid_reasons)}")
        
        # Create RatingFlag record with reason
        flag = RatingFlag(
            rating_id=rating_id,
            flagger_id=flagger_id,
            reason=reason,
            description=description,
            status='pending',
            created_at=datetime.utcnow()
        )
        
        db.session.add(flag)
        
        # Add rating to moderation queue by setting is_flagged
        rating.is_flagged = True
        
        # Log the flag action
        RatingService._log_rating_action(
            action='flag',
            rating_id=rating_id,
            user_id=flagger_id,
            old_value=None,
            new_value=f"Flagged for: {reason}"
        )
        
        db.session.commit()
        
        logger.info(f"Rating {rating_id} flagged by user {flagger_id} for reason: {reason}")
        
        return flag
    
    @staticmethod
    def get_moderation_queue(status='pending', page=1, per_page=20):
        """
        Get all flagged ratings pending review
        
        Args:
            status: Filter by flag status (pending, reviewed, resolved)
            page: Page number for pagination
            per_page: Number of items per page
            
        Returns:
            dict: Paginated results with flags and metadata
        """
        # Query flagged ratings with details
        query = RatingFlag.query.filter_by(status=status).order_by(
            RatingFlag.created_at.desc()
        )
        
        # Paginate results
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        
        # Build response with flag details
        flags_data = []
        for flag in pagination.items:
            rating = flag.rating
            flags_data.append({
                'flag_id': flag.id,
                'rating_id': rating.id,
                'reason': flag.reason,
                'description': flag.description,
                'flagger': {
                    'id': flag.flagger.id,
                    'username': flag.flagger.username,
                    'full_name': flag.flagger.full_name
                },
                'rating_details': {
                    'rating': rating.rating,
                    'review_text': rating.review_text,
                    'buyer': {
                        'id': rating.buyer.id,
                        'username': rating.buyer.username,
                        'full_name': rating.buyer.full_name
                    },
                    'product': {
                        'id': rating.product.id,
                        'name': rating.product.name
                    },
                    'created_at': rating.created_at.isoformat(),
                    'is_hidden': rating.is_hidden,
                    'helpful_count': rating.helpful_count
                },
                'created_at': flag.created_at.isoformat(),
                'status': flag.status
            })
        
        return {
            'flags': flags_data,
            'total': pagination.total,
            'page': pagination.page,
            'per_page': pagination.per_page,
            'pages': pagination.pages,
            'has_next': pagination.has_next,
            'has_prev': pagination.has_prev
        }
    
    @staticmethod
    def moderate_rating(flag_id, moderator_id, action, notes=None):
        """
        Take moderation action on a flagged rating
        
        Args:
            flag_id: ID of the flag to moderate
            moderator_id: ID of the moderator taking action
            action: Action to take (approve, hide, delete)
            notes: Optional moderator notes
            
        Returns:
            dict: Result of moderation action
            
        Raises:
            ValueError: If validation fails
        """
        # Validate flag exists
        flag = RatingFlag.query.get(flag_id)
        if not flag:
            raise ValueError("Flag not found")
        
        # Validate moderator exists and has admin role
        moderator = User.query.get(moderator_id)
        if not moderator:
            raise ValueError("Moderator not found")
        
        if moderator.role != 'admin':
            raise ValueError("Only administrators can moderate ratings")
        
        # Validate action
        valid_actions = ['approve', 'hide', 'delete']
        if action not in valid_actions:
            raise ValueError(f"Invalid action. Must be one of: {', '.join(valid_actions)}")
        
        # Get the rating
        rating = flag.rating
        if not rating:
            raise ValueError("Associated rating not found")
        
        # Store seller ID before potential deletion
        seller_id = rating.product.farmer_id
        rating_author_id = rating.buyer_id
        rating_author = rating.buyer
        
        # Perform the action
        if action == 'approve':
            # Approve the rating - remove flag and keep rating visible
            rating.is_flagged = False
            rating.is_hidden = False
            flag.status = 'resolved'
            flag.moderator_id = moderator_id
            flag.resolved_at = datetime.utcnow()
            
            # Log the action
            RatingService._log_rating_action(
                action='approve',
                rating_id=rating.id,
                user_id=moderator_id,
                old_value=f"Flagged for: {flag.reason}",
                new_value="Approved by moderator"
            )
            
            logger.info(f"Rating {rating.id} approved by moderator {moderator_id}")
            
        elif action == 'hide':
            # Hide the rating from public display
            rating.is_hidden = True
            rating.is_flagged = False
            flag.status = 'resolved'
            flag.moderator_id = moderator_id
            flag.resolved_at = datetime.utcnow()
            
            # Log the action
            RatingService._log_rating_action(
                action='hide',
                rating_id=rating.id,
                user_id=moderator_id,
                old_value=f"Visible, flagged for: {flag.reason}",
                new_value="Hidden by moderator"
            )
            
            # Recalculate seller reputation after hiding
            RatingService.calculate_seller_reputation(seller_id)
            
            # Send notification to rating author when removed
            # Requirement 8.5, 10.3: Notify user within 10 minutes when rating is removed
            try:
                rating_notification_service.notify_rating_removed(
                    rating_id=rating.id,
                    user_id=rating_author_id,
                    reason=f"{flag.reason}: {notes}" if notes else flag.reason
                )
            except Exception as notif_err:
                logger.error(f"Error sending rating removed notification: {str(notif_err)}")
            
            logger.info(f"Rating {rating.id} hidden by moderator {moderator_id}")
            
        elif action == 'delete':
            # Delete the rating permanently
            rating_id = rating.id
            
            # Log the action before deletion
            RatingService._log_rating_action(
                action='delete_moderation',
                rating_id=rating_id,
                user_id=moderator_id,
                old_value=f"Rating: {rating.rating}, Review: {rating.review_text}, Flagged for: {flag.reason}",
                new_value="Deleted by moderator"
            )
            
            # Update flag status before deleting rating
            flag.status = 'resolved'
            flag.moderator_id = moderator_id
            flag.resolved_at = datetime.utcnow()
            db.session.flush()
            
            # Send notification before deletion
            # Requirement 8.5, 10.3: Notify user within 10 minutes when rating is removed
            try:
                rating_notification_service.notify_rating_removed(
                    rating_id=rating_id,
                    user_id=rating_author_id,
                    reason=f"{flag.reason}: {notes}" if notes else flag.reason
                )
            except Exception as notif_err:
                logger.error(f"Error sending rating removed notification: {str(notif_err)}")
            
            # Delete the rating (cascade will handle related records except flags)
            db.session.delete(rating)
            
            # Recalculate seller reputation after deletion
            RatingService.calculate_seller_reputation(seller_id)
            
            logger.info(f"Rating {rating_id} deleted by moderator {moderator_id}")
        
        db.session.commit()
        
        return {
            'success': True,
            'action': action,
            'flag_id': flag_id,
            'rating_id': rating.id if action != 'delete' else None,
            'message': f"Rating {action}d successfully"
        }
    
    @staticmethod
    def _notify_rating_removed(user, rating, reason, moderator_notes=None, is_deleted=False):
        """
        Send notification to user when their rating is removed
        
        Args:
            user: User object (rating author)
            rating: ProductRating object
            reason: Reason for removal
            moderator_notes: Optional notes from moderator
            is_deleted: Whether rating was deleted (vs hidden)
        """
        try:
            email_service = EmailService()
            
            action_text = "deleted" if is_deleted else "hidden"
            subject = f"Your Product Rating Has Been {action_text.title()} - FarmLink AI"
            
            html_content = f"""
            <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                <div style="background: #dc3545; padding: 20px; text-align: center;">
                    <h1 style="color: white; margin: 0;">Rating Moderation Notice</h1>
                </div>
                
                <div style="padding: 30px;">
                    <h2>Hello {user.full_name or user.username},</h2>
                    
                    <p>We're writing to inform you that your rating for <strong>{rating.product.name}</strong> has been {action_text} by our moderation team.</p>
                    
                    <div style="background: #f8f9fa; padding: 20px; border-radius: 10px; margin: 20px 0;">
                        <h3 style="color: #dc3545; margin-top: 0;">Moderation Details</h3>
                        <p><strong>Product:</strong> {rating.product.name}</p>
                        <p><strong>Your Rating:</strong> {rating.rating} stars</p>
                        <p><strong>Reason:</strong> {reason.replace('_', ' ').title()}</p>
                        {f'<p><strong>Moderator Notes:</strong> {moderator_notes}</p>' if moderator_notes else ''}
                        <p><strong>Action Taken:</strong> Rating {action_text}</p>
                        <p><strong>Date:</strong> {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC</p>
                    </div>
                    
                    <div style="background: #fff3cd; border: 1px solid #ffeaa7; padding: 15px; border-radius: 5px; margin: 20px 0;">
                        <p style="margin: 0;"><strong>Community Guidelines:</strong> Please ensure your ratings and reviews comply with our community guidelines. Ratings should be honest, relevant, and respectful.</p>
                    </div>
                    
                    <p>If you believe this action was taken in error, please contact our support team for review.</p>
                    
                    <div style="text-align: center; margin: 30px 0;">
                        <a href="{os.environ.get('BASE_URL', 'http://localhost:5000')}/support" 
                           style="background: #28a745; color: white; padding: 15px 30px; text-decoration: none; border-radius: 5px; display: inline-block;">
                            Contact Support
                        </a>
                    </div>
                    
                    <p>Thank you for helping us maintain a trustworthy marketplace.</p>
                    
                    <p>Best regards,<br>
                    The FarmLink AI Moderation Team</p>
                </div>
                
                <div style="background: #343a40; color: white; padding: 20px; text-align: center;">
                    <p style="margin: 0;">© 2024 FarmLink AI. Connecting Agriculture, Powering Growth.</p>
                </div>
            </div>
            """
            
            result = email_service.send_email(user.email, subject, html_content)
            
            if result.get('success'):
                logger.info(f"Removal notification sent to user {user.id} for rating {rating.id}")
            else:
                logger.error(f"Failed to send removal notification to user {user.id}: {result.get('error')}")
                
        except Exception as e:
            logger.error(f"Error sending rating removal notification: {str(e)}")
            # Don't raise exception - notification failure shouldn't block moderation
    
    @staticmethod
    def get_flag_statistics():
        """
        Get statistics about flagged ratings
        
        Returns:
            dict: Statistics about flags
        """
        from sqlalchemy import func
        
        # Count flags by status
        status_counts = db.session.query(
            RatingFlag.status,
            func.count(RatingFlag.id).label('count')
        ).group_by(RatingFlag.status).all()
        
        # Count flags by reason
        reason_counts = db.session.query(
            RatingFlag.reason,
            func.count(RatingFlag.id).label('count')
        ).filter_by(status='pending').group_by(RatingFlag.reason).all()
        
        # Get total hidden ratings
        hidden_count = ProductRating.query.filter_by(is_hidden=True).count()
        
        # Get total flagged ratings
        flagged_count = ProductRating.query.filter_by(is_flagged=True).count()
        
        return {
            'status_counts': {status: count for status, count in status_counts},
            'reason_counts': {reason: count for reason, count in reason_counts},
            'hidden_ratings': hidden_count,
            'flagged_ratings': flagged_count,
            'pending_flags': dict(status_counts).get('pending', 0)
        }
    
    @staticmethod
    def get_rating_flags(rating_id):
        """
        Get all flags for a specific rating
        
        Args:
            rating_id: ID of the rating
            
        Returns:
            list: List of flags for the rating
        """
        flags = RatingFlag.query.filter_by(rating_id=rating_id).order_by(
            RatingFlag.created_at.desc()
        ).all()
        
        return [{
            'id': flag.id,
            'reason': flag.reason,
            'description': flag.description,
            'status': flag.status,
            'flagger': {
                'id': flag.flagger.id,
                'username': flag.flagger.username,
                'full_name': flag.flagger.full_name
            },
            'moderator': {
                'id': flag.moderator.id,
                'username': flag.moderator.username,
                'full_name': flag.moderator.full_name
            } if flag.moderator else None,
            'created_at': flag.created_at.isoformat(),
            'resolved_at': flag.resolved_at.isoformat() if flag.resolved_at else None
        } for flag in flags]
