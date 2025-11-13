"""
FarmLink AI - Analytics Service
Comprehensive analytics and reporting functionality
"""

from datetime import datetime, timedelta
from sqlalchemy import func, and_, or_, extract
from models import User, Crop, Order, Payment, Analytics, ExpertPost, LearningArticle, UserRating
from extensions import db
import logging

logger = logging.getLogger(__name__)


class AnalyticsService:
    """Service for generating analytics and reports"""
    
    @staticmethod
    def get_platform_overview(start_date=None, end_date=None):
        """Get overall platform statistics"""
        if not end_date:
            end_date = datetime.utcnow()
        if not start_date:
            start_date = end_date - timedelta(days=30)
        
        # User statistics
        total_users = User.query.count()
        total_farmers = User.query.filter_by(role='farmer').count()
        total_buyers = User.query.filter_by(role='buyer').count()
        new_users = User.query.filter(User.created_at.between(start_date, end_date)).count()
        
        # Crop statistics
        total_crops = Crop.query.count()
        active_crops = Crop.query.filter_by(status='available').count()
        pending_approval = Crop.query.filter_by(approval_status='pending').count()
        
        # Order statistics
        total_orders = Order.query.count()
        completed_orders = Order.query.filter_by(status='delivered').count()
        pending_orders = Order.query.filter_by(status='pending').count()
        
        # Revenue statistics
        total_revenue = db.session.query(func.sum(Order.total_amount)).filter(
            Order.payment_status == 'paid'
        ).scalar() or 0
        
        period_revenue = db.session.query(func.sum(Order.total_amount)).filter(
            and_(
                Order.payment_status == 'paid',
                Order.created_at.between(start_date, end_date)
            )
        ).scalar() or 0
        
        # Average order value
        avg_order_value = db.session.query(func.avg(Order.total_amount)).filter(
            Order.payment_status == 'paid'
        ).scalar() or 0
        
        # Engagement statistics
        total_posts = ExpertPost.query.count()
        total_articles = LearningArticle.query.filter_by(is_published=True).count()
        
        return {
            'users': {
                'total': total_users,
                'farmers': total_farmers,
                'buyers': total_buyers,
                'new_users': new_users
            },
            'crops': {
                'total': total_crops,
                'active': active_crops,
                'pending_approval': pending_approval
            },
            'orders': {
                'total': total_orders,
                'completed': completed_orders,
                'pending': pending_orders,
                'completion_rate': (completed_orders / total_orders * 100) if total_orders > 0 else 0
            },
            'revenue': {
                'total': float(total_revenue),
                'period': float(period_revenue),
                'average_order': float(avg_order_value)
            },
            'engagement': {
                'posts': total_posts,
                'articles': total_articles
            }
        }
    
    @staticmethod
    def get_sales_report(start_date=None, end_date=None):
        """Generate detailed sales report"""
        if not end_date:
            end_date = datetime.utcnow()
        if not start_date:
            start_date = end_date - timedelta(days=30)
        
        # Orders in period
        orders = Order.query.filter(
            Order.created_at.between(start_date, end_date)
        ).all()
        
        # Calculate metrics
        total_orders = len(orders)
        completed_orders = len([o for o in orders if o.status == 'delivered'])
        total_revenue = sum(o.total_amount for o in orders if o.payment_status == 'paid')
        
        # Daily breakdown
        daily_sales = db.session.query(
            func.date(Order.created_at).label('date'),
            func.count(Order.id).label('order_count'),
            func.sum(Order.total_amount).label('revenue')
        ).filter(
            and_(
                Order.created_at.between(start_date, end_date),
                Order.payment_status == 'paid'
            )
        ).group_by(func.date(Order.created_at)).all()
        
        # Top selling crops
        top_crops = db.session.query(
            Crop.name,
            Crop.category,
            func.count(Order.id).label('order_count'),
            func.sum(Order.total_amount).label('revenue')
        ).join(Order).filter(
            and_(
                Order.created_at.between(start_date, end_date),
                Order.payment_status == 'paid'
            )
        ).group_by(Crop.id, Crop.name, Crop.category).order_by(
            func.sum(Order.total_amount).desc()
        ).limit(10).all()
        
        # Payment method breakdown
        payment_methods = db.session.query(
            Payment.method,
            func.count(Payment.id).label('count'),
            func.sum(Payment.amount).label('total')
        ).filter(
            and_(
                Payment.created_at.between(start_date, end_date),
                Payment.status == 'completed'
            )
        ).group_by(Payment.method).all()
        
        return {
            'period': {
                'start': start_date.strftime('%Y-%m-%d'),
                'end': end_date.strftime('%Y-%m-%d')
            },
            'summary': {
                'total_orders': total_orders,
                'completed_orders': completed_orders,
                'total_revenue': float(total_revenue),
                'average_order_value': float(total_revenue / total_orders) if total_orders > 0 else 0
            },
            'daily_sales': [
                {
                    'date': sale.date.strftime('%Y-%m-%d'),
                    'orders': sale.order_count,
                    'revenue': float(sale.revenue or 0)
                } for sale in daily_sales
            ],
            'top_crops': [
                {
                    'name': crop.name,
                    'category': crop.category,
                    'orders': crop.order_count,
                    'revenue': float(crop.revenue or 0)
                } for crop in top_crops
            ],
            'payment_methods': [
                {
                    'method': pm.method or 'Unknown',
                    'count': pm.count,
                    'total': float(pm.total or 0)
                } for pm in payment_methods
            ]
        }
    
    @staticmethod
    def get_crop_analytics():
        """Generate crop statistics and analytics"""
        # Category distribution
        category_stats = db.session.query(
            Crop.category,
            func.count(Crop.id).label('count'),
            func.sum(Crop.quantity).label('total_quantity'),
            func.avg(Crop.price_per_unit).label('avg_price')
        ).group_by(Crop.category).all()
        
        # Status distribution
        status_stats = db.session.query(
            Crop.status,
            func.count(Crop.id).label('count')
        ).group_by(Crop.status).all()
        
        # Approval status
        approval_stats = db.session.query(
            Crop.approval_status,
            func.count(Crop.id).label('count')
        ).group_by(Crop.approval_status).all()
        
        # Top farmers by crop count
        top_farmers = db.session.query(
            User.id,
            User.full_name,
            User.username,
            func.count(Crop.id).label('crop_count'),
            func.sum(Crop.quantity * Crop.price_per_unit).label('total_value')
        ).join(Crop, User.id == Crop.farmer_id).group_by(
            User.id, User.full_name, User.username
        ).order_by(func.count(Crop.id).desc()).limit(10).all()
        
        # Price trends by category
        price_trends = db.session.query(
            Crop.category,
            func.min(Crop.price_per_unit).label('min_price'),
            func.max(Crop.price_per_unit).label('max_price'),
            func.avg(Crop.price_per_unit).label('avg_price')
        ).group_by(Crop.category).all()
        
        return {
            'categories': [
                {
                    'category': cat.category,
                    'count': cat.count,
                    'total_quantity': float(cat.total_quantity or 0),
                    'avg_price': float(cat.avg_price or 0)
                } for cat in category_stats
            ],
            'status': [
                {
                    'status': stat.status,
                    'count': stat.count
                } for stat in status_stats
            ],
            'approval': [
                {
                    'status': stat.approval_status,
                    'count': stat.count
                } for stat in approval_stats
            ],
            'top_farmers': [
                {
                    'id': farmer.id,
                    'name': farmer.full_name or farmer.username,
                    'crop_count': farmer.crop_count,
                    'total_value': float(farmer.total_value or 0)
                } for farmer in top_farmers
            ],
            'price_trends': [
                {
                    'category': trend.category,
                    'min_price': float(trend.min_price or 0),
                    'max_price': float(trend.max_price or 0),
                    'avg_price': float(trend.avg_price or 0)
                } for trend in price_trends
            ]
        }
    
    @staticmethod
    def get_user_analytics_report():
        """Generate user analytics report"""
        # User growth over time
        user_growth = db.session.query(
            func.date(User.created_at).label('date'),
            func.count(User.id).label('new_users')
        ).group_by(func.date(User.created_at)).order_by(
            func.date(User.created_at).desc()
        ).limit(30).all()
        
        # Active users (logged in last 30 days)
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        active_users = User.query.filter(
            User.last_login >= thirty_days_ago
        ).count()
        
        # Top buyers by spending
        top_buyers = db.session.query(
            User.id,
            User.full_name,
            User.username,
            func.count(Order.id).label('order_count'),
            func.sum(Order.total_amount).label('total_spent')
        ).join(Order, User.id == Order.buyer_id).filter(
            Order.payment_status == 'paid'
        ).group_by(User.id, User.full_name, User.username).order_by(
            func.sum(Order.total_amount).desc()
        ).limit(10).all()
        
        # Top farmers by revenue
        top_farmers = db.session.query(
            User.id,
            User.full_name,
            User.username,
            func.count(Order.id).label('order_count'),
            func.sum(Order.total_amount).label('total_revenue')
        ).join(Order, User.id == Order.farmer_id).filter(
            Order.payment_status == 'paid'
        ).group_by(User.id, User.full_name, User.username).order_by(
            func.sum(Order.total_amount).desc()
        ).limit(10).all()
        
        # User ratings summary
        avg_ratings = db.session.query(
            User.id,
            User.full_name,
            User.username,
            func.avg(UserRating.rating).label('avg_rating'),
            func.count(UserRating.id).label('rating_count')
        ).join(UserRating, User.id == UserRating.rated_user_id).group_by(
            User.id, User.full_name, User.username
        ).having(func.count(UserRating.id) >= 3).order_by(
            func.avg(UserRating.rating).desc()
        ).limit(10).all()
        
        return {
            'user_growth': [
                {
                    'date': ug.date.strftime('%Y-%m-%d'),
                    'new_users': ug.new_users
                } for ug in reversed(user_growth)
            ],
            'active_users': active_users,
            'top_buyers': [
                {
                    'id': buyer.id,
                    'name': buyer.full_name or buyer.username,
                    'orders': buyer.order_count,
                    'total_spent': float(buyer.total_spent or 0)
                } for buyer in top_buyers
            ],
            'top_farmers': [
                {
                    'id': farmer.id,
                    'name': farmer.full_name or farmer.username,
                    'orders': farmer.order_count,
                    'total_revenue': float(farmer.total_revenue or 0)
                } for farmer in top_farmers
            ],
            'top_rated_users': [
                {
                    'id': user.id,
                    'name': user.full_name or user.username,
                    'avg_rating': float(user.avg_rating or 0),
                    'rating_count': user.rating_count
                } for user in avg_ratings
            ]
        }
    
    @staticmethod
    def get_engagement_metrics():
        """Get platform engagement metrics"""
        # Expert forum metrics
        total_posts = ExpertPost.query.count()
        answered_questions = ExpertPost.query.filter_by(is_answered=True).count()
        
        # Learning hub metrics
        total_articles = LearningArticle.query.filter_by(is_published=True).count()
        total_views = db.session.query(func.sum(LearningArticle.views)).scalar() or 0
        total_likes = db.session.query(func.sum(LearningArticle.likes)).scalar() or 0
        
        # Most viewed articles
        top_articles = LearningArticle.query.filter_by(
            is_published=True
        ).order_by(LearningArticle.views.desc()).limit(10).all()
        
        # Most active forum users
        active_forum_users = db.session.query(
            User.id,
            User.full_name,
            User.username,
            func.count(ExpertPost.id).label('post_count')
        ).join(ExpertPost, User.id == ExpertPost.author_id).group_by(
            User.id, User.full_name, User.username
        ).order_by(func.count(ExpertPost.id).desc()).limit(10).all()
        
        return {
            'forum': {
                'total_posts': total_posts,
                'answered_questions': answered_questions,
                'answer_rate': (answered_questions / total_posts * 100) if total_posts > 0 else 0
            },
            'learning_hub': {
                'total_articles': total_articles,
                'total_views': int(total_views),
                'total_likes': int(total_likes),
                'avg_views_per_article': float(total_views / total_articles) if total_articles > 0 else 0
            },
            'top_articles': [
                {
                    'id': article.id,
                    'title': article.title,
                    'views': article.views,
                    'likes': article.likes
                } for article in top_articles
            ],
            'active_users': [
                {
                    'id': user.id,
                    'name': user.full_name or user.username,
                    'post_count': user.post_count
                } for user in active_forum_users
            ]
        }
    
    @staticmethod
    def get_monthly_comparison(months=6):
        """Get month-over-month comparison"""
        results = []
        
        for i in range(months):
            # Calculate date range for each month
            end_date = datetime.utcnow().replace(day=1) - timedelta(days=i*30)
            start_date = end_date - timedelta(days=30)
            
            # Orders and revenue for the month
            orders = Order.query.filter(
                Order.created_at.between(start_date, end_date)
            ).all()
            
            revenue = sum(o.total_amount for o in orders if o.payment_status == 'paid')
            
            # New users
            new_users = User.query.filter(
                User.created_at.between(start_date, end_date)
            ).count()
            
            # New crops
            new_crops = Crop.query.filter(
                Crop.created_at.between(start_date, end_date)
            ).count()
            
            results.append({
                'month': start_date.strftime('%B %Y'),
                'orders': len(orders),
                'revenue': float(revenue),
                'new_users': new_users,
                'new_crops': new_crops
            })
        
        return list(reversed(results))
