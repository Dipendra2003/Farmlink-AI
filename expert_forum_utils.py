"""
Expert Forum Utilities
Helper functions for expert forum functionality to prevent circular imports
"""

from datetime import datetime
from flask import current_app as app
from models import (
    UserRating, ExpertPost, ExpertReply, PostVote, ReplyVote,
    ForumNotification, EditHistory, db
)

def get_avg_rating(user_id):
    try:
        ratings = UserRating.query.filter_by(rated_user_id=user_id).all()
        if not ratings:
            return 0.0
        return sum(r.rating for r in ratings) / len(ratings)
    except Exception as e:
        app.logger.error(f'Error calculating average rating: {str(e)}')
        return 0.0

def get_rating_stats(user_id):
    try:
        ratings = UserRating.query.filter_by(rated_user_id=user_id).all()
        if not ratings:
            return {'avg_rating': 0.0, 'total_ratings': 0}
        avg = sum(r.rating for r in ratings) / len(ratings)
        return {'avg_rating': avg, 'total_ratings': len(ratings)}
    except Exception as e:
        app.logger.error(f'Error getting rating stats: {str(e)}')
        return {'avg_rating': 0.0, 'total_ratings': 0}

def calculate_user_reputation(user_id):
    try:
        # Get basic stats
        total_posts = ExpertPost.query.filter_by(author_id=user_id).count()
        total_replies = ExpertReply.query.filter_by(author_id=user_id).count()
        solved_posts = ExpertPost.query.filter_by(author_id=user_id, is_answered=True).count()
        solution_replies = ExpertReply.query.filter_by(author_id=user_id, is_solution=True).count()
        
        # Calculate total upvotes
        post_upvotes = db.session.query(db.func.sum(ExpertPost.upvotes)).filter_by(author_id=user_id).scalar() or 0
        reply_upvotes = db.session.query(db.func.sum(ExpertReply.upvotes)).filter_by(author_id=user_id).scalar() or 0
        total_upvotes = post_upvotes + reply_upvotes
        
        # Calculate reputation points
        points = (solution_replies * 15) + (solved_posts * 10) + (total_upvotes * 2) + (total_posts * 1) + (total_replies * 1)
        
        # Determine level
        if points >= 1000:
            level = "Expert"
            level_class = "success"
        elif points >= 500:
            level = "Advanced"
            level_class = "primary"
        elif points >= 100:
            level = "Intermediate"
            level_class = "warning"
        else:
            level = "Beginner"
            level_class = "secondary"
        
        # Get rating statistics
        rating_stats = get_rating_stats(user_id)
        
        return {
            'total_posts': total_posts,
            'total_replies': total_replies,
            'solved_posts': solved_posts,
            'solution_replies': solution_replies,
            'total_upvotes': total_upvotes,
            'points': points,
            'level': level,
            'level_class': level_class,
            'avg_rating': rating_stats['avg_rating'],
            'total_ratings': rating_stats['total_ratings'],
            'reputation_score': points
        }
    except Exception as e:
        app.logger.error(f'Error calculating reputation: {str(e)}')
        return {
            'total_posts': 0,
            'total_replies': 0,
            'solved_posts': 0,
            'solution_replies': 0,
            'total_upvotes': 0,
            'points': 0,
            'level': 'Beginner',
            'level_class': 'secondary',
            'avg_rating': 0.0,
            'total_ratings': 0,
            'reputation_score': 0
        }

def calculate_vote_weight(user):
    if not user:
        return 1.0
    return user.get_reputation_weight()

def create_notification(user_id, notification_type, title, message, sender_id=None, post_id=None, reply_id=None):
    """Create a notification for a user. Validates user exists before creating."""
    from models import User
    try:
        # Validate that the user exists
        user = User.query.get(user_id)
        if not user:
            app.logger.warning(f'Cannot create notification: User {user_id} does not exist')
            return False
        
        notification = ForumNotification(
            user_id=user_id,
            notification_type=notification_type,
            title=title,
            message=message,
            sender_id=sender_id,
            post_id=post_id,
            reply_id=reply_id
        )
        db.session.add(notification)
        db.session.commit()
        return True
    except Exception as e:
        db.session.rollback()
        app.logger.error(f'Error creating notification: {str(e)}')
        return False

def log_edit_history(content_type, content_id, field_name, old_value, new_value, editor_id, reason=None):
    try:
        history = EditHistory(
            content_type=content_type,
            content_id=content_id,
            field_name=field_name,
            old_value=old_value,
            new_value=new_value,
            editor_id=editor_id,
            edit_reason=reason
        )
        db.session.add(history)
        db.session.commit()
    except Exception as e:
        app.logger.error(f'Error logging edit history: {str(e)}')

def check_spam_content(content, user_id):
    """Check if content appears to be spam. Returns True if spam detected."""
    if not content:
        return False
    
    from models import User
    
    # Skip spam check for admins
    user = User.query.get(user_id)
    if user and user.role == 'admin':
        return False
        
    # Check for excessive links (more than 5 links is suspicious)
    link_count = content.lower().count('http://') + content.lower().count('https://') + content.lower().count('www.')
    if link_count > 5:
        app.logger.warning(f'Spam detected: User {user_id} posted content with {link_count} links')
        return True
        
    # Check for repetitive content (more than 10 posts in an hour)
    from datetime import timedelta
    recent_posts = ExpertPost.query.filter_by(author_id=user_id).filter(
        ExpertPost.created_at > datetime.utcnow() - timedelta(hours=1)
    ).count()
    
    if recent_posts > 10:
        app.logger.warning(f'Spam detected: User {user_id} created {recent_posts} posts in the last hour')
        return True
    
    # Check for very short repetitive content
    if len(content) < 20:
        recent_similar = ExpertPost.query.filter_by(author_id=user_id).filter(
            ExpertPost.created_at > datetime.utcnow() - timedelta(minutes=5),
            ExpertPost.content == content
        ).count()
        if recent_similar > 0:
            app.logger.warning(f'Spam detected: User {user_id} posted duplicate content')
            return True
        
    return False

def update_post_votes(post, commit=True):
    """Update post vote counts. Set commit=False if calling within an existing transaction."""
    upvotes = PostVote.query.filter_by(post_id=post.id, vote_type='upvote').count()
    downvotes = PostVote.query.filter_by(post_id=post.id, vote_type='downvote').count()
    
    post.upvotes = upvotes
    post.downvotes = downvotes
    
    if commit:
        db.session.commit()

def update_reply_votes(reply, commit=True):
    """Update reply vote counts. Set commit=False if calling within an existing transaction."""
    upvotes = ReplyVote.query.filter_by(reply_id=reply.id, vote_type='upvote').count()
    downvotes = ReplyVote.query.filter_by(reply_id=reply.id, vote_type='downvote').count()
    
    reply.upvotes = upvotes
    reply.downvotes = downvotes
    
    if commit:
        db.session.commit()
