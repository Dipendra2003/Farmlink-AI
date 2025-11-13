"""
Achievement Service
Manages user achievements and badges for the learning hub
"""
from datetime import datetime, timedelta
from models import UserAchievement, UserReadingProgress, User
from extensions import db
import logging

logger = logging.getLogger(__name__)

# Define all available achievements
ACHIEVEMENTS = {
    'first_article': {
        'name': 'First Steps',
        'description': 'Complete your first article',
        'icon': 'fa-star',
        'color': 'warning',
        'requirement': lambda stats: stats['completed'] >= 1
    },
    'bookworm': {
        'name': 'Bookworm',
        'description': 'Complete 5 articles',
        'icon': 'fa-book',
        'color': 'info',
        'requirement': lambda stats: stats['completed'] >= 5
    },
    'scholar': {
        'name': 'Scholar',
        'description': 'Complete 10 articles',
        'icon': 'fa-graduation-cap',
        'color': 'primary',
        'requirement': lambda stats: stats['completed'] >= 10
    },
    'expert_reader': {
        'name': 'Expert Reader',
        'description': 'Complete 25 articles',
        'icon': 'fa-crown',
        'color': 'success',
        'requirement': lambda stats: stats['completed'] >= 25
    },
    'master_learner': {
        'name': 'Master Learner',
        'description': 'Complete 50 articles',
        'icon': 'fa-trophy',
        'color': 'danger',
        'requirement': lambda stats: stats['completed'] >= 50
    },
    'speed_reader': {
        'name': 'Speed Reader',
        'description': 'Complete 5 articles in one day',
        'icon': 'fa-bolt',
        'color': 'warning',
        'requirement': lambda stats: stats.get('articles_today', 0) >= 5
    },
    'dedicated_learner': {
        'name': 'Dedicated Learner',
        'description': 'Maintain a 7-day reading streak',
        'icon': 'fa-fire',
        'color': 'danger',
        'requirement': lambda stats: stats.get('reading_streak', 0) >= 7
    },
    'consistent_reader': {
        'name': 'Consistent Reader',
        'description': 'Maintain a 30-day reading streak',
        'icon': 'fa-calendar-check',
        'color': 'success',
        'requirement': lambda stats: stats.get('reading_streak', 0) >= 30
    },
    'category_explorer': {
        'name': 'Category Explorer',
        'description': 'Read articles from 5 different categories',
        'icon': 'fa-compass',
        'color': 'info',
        'requirement': lambda stats: len(stats.get('categories', {})) >= 5
    },
    'knowledge_seeker': {
        'name': 'Knowledge Seeker',
        'description': 'Spend 10 hours reading',
        'icon': 'fa-clock',
        'color': 'primary',
        'requirement': lambda stats: stats.get('total_time_minutes', 0) >= 600
    },
    'early_bird': {
        'name': 'Early Bird',
        'description': 'Read an article before 8 AM',
        'icon': 'fa-sun',
        'color': 'warning',
        'requirement': lambda stats: stats.get('early_bird', False)
    },
    'night_owl': {
        'name': 'Night Owl',
        'description': 'Read an article after 10 PM',
        'icon': 'fa-moon',
        'color': 'info',
        'requirement': lambda stats: stats.get('night_owl', False)
    }
}


def get_user_stats(user_id):
    """Get comprehensive user statistics for achievement checking"""
    try:
        progress_items = UserReadingProgress.query.filter_by(user_id=user_id).all()
        
        if not progress_items:
            return {
                'completed': 0,
                'total': 0,
                'categories': {},
                'reading_streak': 0,
                'total_time_minutes': 0,
                'articles_today': 0,
                'early_bird': False,
                'night_owl': False
            }
        
        # Basic stats
        completed = sum(1 for p in progress_items if p.completed)
        total = len(progress_items)
        
        # Category breakdown
        categories = {}
        for p in progress_items:
            if p.article and p.completed:
                cat = p.article.category
                categories[cat] = categories.get(cat, 0) + 1
        
        # Reading streak
        dates = sorted([p.last_read_at.date() for p in progress_items if p.last_read_at], reverse=True)
        streak = 0
        if dates:
            streak = 1
            for i in range(len(dates) - 1):
                if (dates[i] - dates[i + 1]).days == 1:
                    streak += 1
                else:
                    break
        
        # Total time
        total_time = sum(p.time_spent_seconds for p in progress_items) // 60
        
        # Articles completed today
        today = datetime.utcnow().date()
        articles_today = sum(1 for p in progress_items 
                           if p.completed_at and p.completed_at.date() == today)
        
        # Time-based achievements
        early_bird = any(p.last_read_at and p.last_read_at.hour < 8 
                        for p in progress_items)
        night_owl = any(p.last_read_at and p.last_read_at.hour >= 22 
                       for p in progress_items)
        
        return {
            'completed': completed,
            'total': total,
            'categories': categories,
            'reading_streak': streak,
            'total_time_minutes': total_time,
            'articles_today': articles_today,
            'early_bird': early_bird,
            'night_owl': night_owl
        }
    except Exception as e:
        logger.error(f"Error getting user stats: {str(e)}")
        return {
            'completed': 0,
            'total': 0,
            'categories': {},
            'reading_streak': 0,
            'total_time_minutes': 0,
            'articles_today': 0,
            'early_bird': False,
            'night_owl': False
        }


def check_and_award_achievements(user_id):
    """Check if user has earned any new achievements"""
    try:
        stats = get_user_stats(user_id)
        newly_earned = []
        
        # Get existing achievements
        existing = {a.achievement_type for a in 
                   UserAchievement.query.filter_by(user_id=user_id).all()}
        
        # Check each achievement
        for achievement_type, achievement_data in ACHIEVEMENTS.items():
            # Skip if already earned
            if achievement_type in existing:
                continue
            
            # Check if requirement is met
            if achievement_data['requirement'](stats):
                # Award achievement
                achievement = UserAchievement(
                    user_id=user_id,
                    achievement_type=achievement_type,
                    achievement_name=achievement_data['name'],
                    achievement_description=achievement_data['description'],
                    icon=achievement_data['icon']
                )
                db.session.add(achievement)
                newly_earned.append(achievement_data)
        
        if newly_earned:
            db.session.commit()
            logger.info(f"User {user_id} earned {len(newly_earned)} new achievements")
        
        return newly_earned
    except Exception as e:
        logger.error(f"Error checking achievements: {str(e)}")
        db.session.rollback()
        return []


def get_user_achievements(user_id):
    """Get all achievements for a user with progress"""
    try:
        stats = get_user_stats(user_id)
        earned_achievements = UserAchievement.query.filter_by(user_id=user_id).all()
        earned_types = {a.achievement_type for a in earned_achievements}
        
        achievements_list = []
        for achievement_type, achievement_data in ACHIEVEMENTS.items():
            is_earned = achievement_type in earned_types
            earned_date = None
            
            if is_earned:
                earned_achievement = next(a for a in earned_achievements 
                                        if a.achievement_type == achievement_type)
                earned_date = earned_achievement.earned_at
            
            # Calculate progress
            progress = 0
            progress_text = ""
            
            if achievement_type == 'first_article':
                progress = min(100, stats['completed'] * 100)
                progress_text = f"{stats['completed']}/1"
            elif achievement_type == 'bookworm':
                progress = min(100, (stats['completed'] / 5) * 100)
                progress_text = f"{stats['completed']}/5"
            elif achievement_type == 'scholar':
                progress = min(100, (stats['completed'] / 10) * 100)
                progress_text = f"{stats['completed']}/10"
            elif achievement_type == 'expert_reader':
                progress = min(100, (stats['completed'] / 25) * 100)
                progress_text = f"{stats['completed']}/25"
            elif achievement_type == 'master_learner':
                progress = min(100, (stats['completed'] / 50) * 100)
                progress_text = f"{stats['completed']}/50"
            elif achievement_type == 'speed_reader':
                progress = min(100, (stats['articles_today'] / 5) * 100)
                progress_text = f"{stats['articles_today']}/5 today"
            elif achievement_type == 'dedicated_learner':
                progress = min(100, (stats['reading_streak'] / 7) * 100)
                progress_text = f"{stats['reading_streak']}/7 days"
            elif achievement_type == 'consistent_reader':
                progress = min(100, (stats['reading_streak'] / 30) * 100)
                progress_text = f"{stats['reading_streak']}/30 days"
            elif achievement_type == 'category_explorer':
                progress = min(100, (len(stats['categories']) / 5) * 100)
                progress_text = f"{len(stats['categories'])}/5 categories"
            elif achievement_type == 'knowledge_seeker':
                progress = min(100, (stats['total_time_minutes'] / 600) * 100)
                progress_text = f"{stats['total_time_minutes']}/600 minutes"
            
            achievements_list.append({
                'type': achievement_type,
                'name': achievement_data['name'],
                'description': achievement_data['description'],
                'icon': achievement_data['icon'],
                'color': achievement_data['color'],
                'is_earned': is_earned,
                'earned_date': earned_date,
                'progress': int(progress),
                'progress_text': progress_text
            })
        
        return achievements_list
    except Exception as e:
        logger.error(f"Error getting user achievements: {str(e)}")
        return []


def mark_achievements_notified(user_id):
    """Mark all achievements as notified for a user"""
    try:
        UserAchievement.query.filter_by(
            user_id=user_id,
            is_notified=False
        ).update({'is_notified': True})
        db.session.commit()
    except Exception as e:
        logger.error(f"Error marking achievements as notified: {str(e)}")
        db.session.rollback()
