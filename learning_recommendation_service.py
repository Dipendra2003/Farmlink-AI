"""
Learning Recommendation Service
Provides personalized article recommendations based on user behavior and preferences
"""
import json
from datetime import datetime, timedelta
from sqlalchemy import func, and_, or_
from models import (
    User, LearningArticle, UserReadingProgress, UserLearningPreference,
    ArticleRecommendation, ArticleLike, ArticleBookmark
)
from extensions import db
import logging

logger = logging.getLogger(__name__)


class LearningRecommendationEngine:
    """Engine for generating personalized learning recommendations"""
    
    def __init__(self, user_id):
        self.user_id = user_id
        self.user = User.query.get(user_id)
        
    def get_user_preferences(self):
        """Get or create user learning preferences"""
        pref = UserLearningPreference.query.filter_by(user_id=self.user_id).first()
        if not pref:
            # Create default preferences based on user role
            pref = UserLearningPreference(
                user_id=self.user_id,
                skill_level='beginner',
                preferred_categories=json.dumps([]),
                learning_goals=json.dumps([]),
                interests=json.dumps([])
            )
            db.session.add(pref)
            db.session.commit()
        return pref
    
    def analyze_reading_history(self):
        """Analyze user's reading history to understand preferences"""
        progress = UserReadingProgress.query.filter_by(user_id=self.user_id).all()
        
        if not progress:
            return {
                'categories': [],
                'difficulty_levels': [],
                'avg_reading_time': 10,
                'completion_rate': 0
            }
        
        # Extract categories from read articles
        categories = {}
        difficulty_levels = {}
        total_time = 0
        completed_count = 0
        
        for p in progress:
            if p.article:
                # Count categories
                cat = p.article.category
                categories[cat] = categories.get(cat, 0) + 1
                
                # Count difficulty levels
                diff = p.article.difficulty_level
                difficulty_levels[diff] = difficulty_levels.get(diff, 0) + 1
                
                # Track reading time
                total_time += p.article.reading_time or 10
                
                # Track completion
                if p.completed:
                    completed_count += 1
        
        return {
            'categories': sorted(categories.items(), key=lambda x: x[1], reverse=True),
            'difficulty_levels': sorted(difficulty_levels.items(), key=lambda x: x[1], reverse=True),
            'avg_reading_time': total_time // len(progress) if progress else 10,
            'completion_rate': (completed_count / len(progress) * 100) if progress else 0
        }
    
    def get_skill_level(self):
        """Determine user's current skill level"""
        pref = self.get_user_preferences()
        history = self.analyze_reading_history()
        
        # Check if user has manually set skill level
        if pref.skill_level and pref.skill_level != 'beginner':
            return pref.skill_level
        
        # Auto-detect based on reading history
        completed = UserReadingProgress.query.filter_by(
            user_id=self.user_id, 
            completed=True
        ).count()
        
        if completed >= 20:
            return 'advanced'
        elif completed >= 10:
            return 'intermediate'
        else:
            return 'beginner'
    
    def calculate_article_score(self, article, history_data, preferences):
        """Calculate relevance score for an article"""
        score = 0.0
        reasons = []
        
        # Check if already read
        already_read = UserReadingProgress.query.filter_by(
            user_id=self.user_id,
            article_id=article.id
        ).first()
        
        if already_read and already_read.completed:
            return 0.0, []  # Don't recommend completed articles
        
        # Category match (30 points)
        if history_data['categories']:
            top_categories = [cat[0] for cat in history_data['categories'][:3]]
            if article.category in top_categories:
                score += 30
                reasons.append(f"Matches your interest in {article.category.replace('_', ' ').title()}")
        
        # Difficulty level match (25 points)
        skill_level = self.get_skill_level()
        if article.difficulty_level == skill_level:
            score += 25
            reasons.append(f"Perfect for your {skill_level} level")
        elif skill_level == 'beginner' and article.difficulty_level == 'intermediate':
            score += 15
            reasons.append("Next step in your learning journey")
        elif skill_level == 'intermediate' and article.difficulty_level == 'advanced':
            score += 15
            reasons.append("Challenge yourself with advanced content")
        
        # Reading time preference (15 points)
        pref_time = preferences.preferred_reading_time or 10
        article_time = article.reading_time or 10
        time_diff = abs(article_time - pref_time)
        if time_diff <= 3:
            score += 15
            reasons.append(f"Quick {article_time} min read")
        elif time_diff <= 5:
            score += 10
        
        # Popularity (15 points)
        views = article.views or 0
        likes = article.get_like_count()
        if views > 100:
            score += 10
            if likes > 20:
                score += 5
                reasons.append("Highly rated by community")
        
        # Recency (10 points)
        if article.created_at:
            days_old = (datetime.utcnow() - article.created_at).days
            if days_old <= 30:
                score += 10
                reasons.append("Recently published")
            elif days_old <= 90:
                score += 5
        
        # User role relevance (5 points)
        if self.user.role in ['farmer', 'manager_farmer']:
            if article.category in ['crop-cultivation', 'pest-management', 'soil-science']:
                score += 5
                reasons.append("Relevant to farmers")
        
        return score, reasons
    
    def generate_recommendations(self, limit=10, refresh=False):
        """Generate personalized recommendations for the user"""
        try:
            # Check if we have recent recommendations (less than 24 hours old)
            if not refresh:
                recent_recs = ArticleRecommendation.query.filter(
                    and_(
                        ArticleRecommendation.user_id == self.user_id,
                        ArticleRecommendation.is_dismissed == False,
                        ArticleRecommendation.created_at >= datetime.utcnow() - timedelta(hours=24)
                    )
                ).order_by(ArticleRecommendation.recommendation_score.desc()).limit(limit).all()
                
                if recent_recs:
                    return recent_recs
            
            # Get user data
            preferences = self.get_user_preferences()
            history_data = self.analyze_reading_history()
            
            # Get all published articles
            articles = LearningArticle.query.filter_by(
                is_published=True,
                is_draft=False
            ).all()
            
            # Calculate scores for each article
            scored_articles = []
            for article in articles:
                score, reasons = self.calculate_article_score(article, history_data, preferences)
                if score > 0:
                    scored_articles.append({
                        'article': article,
                        'score': score,
                        'reason': reasons[0] if reasons else 'Recommended for you'
                    })
            
            # Sort by score
            scored_articles.sort(key=lambda x: x['score'], reverse=True)
            
            # Save top recommendations
            recommendations = []
            for item in scored_articles[:limit]:
                # Check if recommendation already exists
                existing = ArticleRecommendation.query.filter_by(
                    user_id=self.user_id,
                    article_id=item['article'].id
                ).first()
                
                if existing:
                    # Update existing recommendation
                    existing.recommendation_score = item['score']
                    existing.recommendation_reason = item['reason']
                    existing.created_at = datetime.utcnow()
                    existing.is_dismissed = False
                    recommendations.append(existing)
                else:
                    # Create new recommendation
                    rec = ArticleRecommendation(
                        user_id=self.user_id,
                        article_id=item['article'].id,
                        recommendation_score=item['score'],
                        recommendation_reason=item['reason']
                    )
                    db.session.add(rec)
                    recommendations.append(rec)
            
            db.session.commit()
            return recommendations
            
        except Exception as e:
            logger.error(f"Error generating recommendations: {str(e)}")
            db.session.rollback()
            return []
    
    def get_trending_articles(self, limit=5):
        """Get trending articles based on recent activity"""
        try:
            # Get articles with most views/likes in last 30 days
            thirty_days_ago = datetime.utcnow() - timedelta(days=30)
            
            trending = LearningArticle.query.filter(
                and_(
                    LearningArticle.is_published == True,
                    LearningArticle.is_draft == False,
                    LearningArticle.created_at >= thirty_days_ago
                )
            ).order_by(
                (LearningArticle.views + LearningArticle.likes * 5).desc()
            ).limit(limit).all()
            
            return trending
        except Exception as e:
            logger.error(f"Error getting trending articles: {str(e)}")
            return []
    
    def get_continue_reading(self, limit=5):
        """Get articles user started but didn't finish"""
        try:
            in_progress = UserReadingProgress.query.filter(
                and_(
                    UserReadingProgress.user_id == self.user_id,
                    UserReadingProgress.completed == False,
                    UserReadingProgress.progress_percentage > 0
                )
            ).order_by(UserReadingProgress.last_read_at.desc()).limit(limit).all()
            
            return in_progress
        except Exception as e:
            logger.error(f"Error getting continue reading: {str(e)}")
            return []
    
    def update_preferences(self, preferences_data):
        """Update user learning preferences"""
        try:
            pref = self.get_user_preferences()
            
            if 'skill_level' in preferences_data:
                pref.skill_level = preferences_data['skill_level']
            
            if 'preferred_categories' in preferences_data:
                pref.preferred_categories = json.dumps(preferences_data['preferred_categories'])
            
            if 'learning_goals' in preferences_data:
                pref.learning_goals = json.dumps(preferences_data['learning_goals'])
            
            if 'preferred_reading_time' in preferences_data:
                pref.preferred_reading_time = preferences_data['preferred_reading_time']
            
            if 'interests' in preferences_data:
                pref.interests = json.dumps(preferences_data['interests'])
            
            pref.updated_at = datetime.utcnow()
            db.session.commit()
            
            return True
        except Exception as e:
            logger.error(f"Error updating preferences: {str(e)}")
            db.session.rollback()
            return False


def get_learning_stats(user_id):
    """Get comprehensive learning statistics for a user"""
    try:
        progress_items = UserReadingProgress.query.filter_by(user_id=user_id).all()
        
        total_articles = len(progress_items)
        completed_articles = sum(1 for p in progress_items if p.completed)
        in_progress = sum(1 for p in progress_items if not p.completed and p.progress_percentage > 0)
        total_time_spent = sum(p.time_spent_seconds for p in progress_items) // 60  # Convert to minutes
        
        # Calculate streak (consecutive days of reading)
        if progress_items:
            dates = sorted([p.last_read_at.date() for p in progress_items], reverse=True)
            streak = 1
            for i in range(len(dates) - 1):
                if (dates[i] - dates[i + 1]).days == 1:
                    streak += 1
                else:
                    break
        else:
            streak = 0
        
        # Category breakdown
        categories = {}
        for p in progress_items:
            if p.article:
                cat = p.article.category
                categories[cat] = categories.get(cat, 0) + 1
        
        return {
            'total': total_articles,
            'completed': completed_articles,
            'in_progress': in_progress,
            'completion_rate': round((completed_articles / total_articles * 100) if total_articles > 0 else 0, 1),
            'total_time_minutes': total_time_spent,
            'reading_streak': streak,
            'categories': categories
        }
    except Exception as e:
        logger.error(f"Error getting learning stats: {str(e)}")
        return {
            'total': 0,
            'completed': 0,
            'in_progress': 0,
            'completion_rate': 0,
            'total_time_minutes': 0,
            'reading_streak': 0,
            'categories': {}
        }
