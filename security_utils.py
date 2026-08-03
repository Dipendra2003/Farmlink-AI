from functools import wraps
from flask import request, abort, flash, redirect, url_for
from flask_login import current_user
from datetime import datetime, timedelta
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('security')

# Rate limiting settings
RATE_LIMIT_DURATION = timedelta(minutes=15)
MAX_ATTEMPTS = 5
login_attempts = {}

def role_required(*roles):
    """
    Enhanced role-based access control decorator with hierarchy support
    DEPRECATED: Use role_hierarchy.role_required instead for better hierarchy support
    """
    from role_hierarchy import has_role
    
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                flash('Please log in to access this page.', 'warning')
                return redirect(url_for('login', next=request.url))
            
            if not has_role(current_user, *roles):
                flash('Access denied. You do not have permission to access this page.', 'danger')
                return redirect(url_for('index'))
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def verify_user_access(user_id):
    """Enhanced verification of user access with logging and security checks"""
    from models import User
    
    if not current_user.is_authenticated:
        logger.warning(f'Unauthenticated access attempt for user_id {user_id} from IP {request.remote_addr}')
        return False
        
    if not current_user.is_active:
        logger.warning(f'Deactivated user {current_user.id} attempted to access user_id {user_id}')
        return False
        
    # Check if the target user exists and is active
    target_user = User.query.get(user_id)
    if not target_user:
        logger.warning(f'Access attempt to non-existent user {user_id} by {current_user.id}')
        return False
    
    # Admin has access to all users, but we log it
    if current_user.role == 'admin':
        logger.info(f'Admin {current_user.id} accessed user {user_id}')
        return True
        
    # Users can only access their own data
    has_access = current_user.id == int(user_id)
    if not has_access:
        logger.warning(f'User {current_user.id} attempted unauthorized access to user {user_id}')
        
    return has_access

def rate_limit_login(ip_address):
    """Rate limit login attempts by IP address"""
    now = datetime.utcnow()
    if ip_address in login_attempts:
        attempts = login_attempts[ip_address]
        # Clean old attempts
        attempts = [attempt for attempt in attempts 
                   if attempt > now - RATE_LIMIT_DURATION]
        if len(attempts) >= MAX_ATTEMPTS:
            return False
        attempts.append(now)
        login_attempts[ip_address] = attempts
    else:
        login_attempts[ip_address] = [now]
    return True

def log_login_attempt(user_id, ip_address, success, user_agent):
    """Log login attempts to database"""
    from models import LoginAttempt
    from app import db
    
    try:
        attempt = LoginAttempt(
            user_id=user_id,
            ip_address=ip_address,
            user_agent=user_agent,
            success=success,
            timestamp=datetime.utcnow()
        )
        db.session.add(attempt)
        db.session.commit()
        
        # Log to file system as well
        logger.info(
            f"Login attempt - User: {user_id}, IP: {ip_address}, "
            f"Success: {success}, Agent: {user_agent}"
        )
    except Exception as e:
        logger.error(f"Failed to log login attempt: {e}")

def clear_login_attempts(ip_address):
    """Clear failed login attempts for an IP address after successful login"""
    if ip_address in login_attempts:
        del login_attempts[ip_address]

# Define public routes that don't require authentication
PUBLIC_ROUTES = {
    # Basic pages
    'index': '/',
    'about': '/about',
    'contact': '/contact',
    'privacy': '/privacy',
    'terms': '/terms',
    'faq': '/faq',
    'help_center': '/help',
    'govt_schemes': '/govt-schemes',
    'return_policy': '/return-policy',
    'report_issue': '/report-issue',
    'weather_info': '/weather-info',
    'weather': '/weather',
    'testing_mode': '/testing-mode',
    'static': '/static/',  # Static files

    # SEO & Crawler Endpoints
    'sitemap': '/sitemap.xml',
    'sitemap_static': '/sitemap/static.xml',
    'sitemap_products': '/sitemap/products.xml',
    'sitemap_articles': '/sitemap/articles.xml',
    'sitemap_forum': '/sitemap/forum.xml',
    'sitemap_images': '/sitemap/images.xml',
    'learning_hub_rss': '/learning-hub/rss.xml',
    'robots': '/robots.txt',
    'web_manifest': '/site.webmanifest',
    'favicon': '/favicon.ico',

    # Authentication routes
    'login': '/login',
    'register': '/register',
    'forgot_password': '/forgot-password',
    'verify_reset_otp': '/verify-reset-otp',
    'reset_password': '/reset-password/',
    'verify_email': '/verify-email/',
    'resend_verification': '/resend-verification/',

    # Public views & Community Hubs (for SEO Crawling)
    'marketplace': '/marketplace',
    'product_detail': '/marketplace/crop/',
    'expert_forum': '/expert-forum',
    'expert_forum_sub': '/expert-forum/',
    'learning_hub': '/learning-hub',
    'learning_hub_sub': '/learning-hub/'
}

def is_public_route():
    """Check if current route is public"""
    # Check by endpoint name
    if request.endpoint in PUBLIC_ROUTES:
        return True
    
    # Check by path pattern for routes with dynamic segments
    path = request.path
    for route_path in PUBLIC_ROUTES.values():
        if route_path.endswith('/') and path.startswith(route_path):
            return True
    
    return False

def role_redirect():
    """Redirect user based on their role"""
    if not current_user.is_authenticated:
        return redirect(url_for('login'))
    
    role_routes = {
        'admin': 'admin_dashboard',
        'farmer': 'farmer_dashboard',
        'buyer': 'buyer_dashboard'
    }
    
    return redirect(url_for(role_routes.get(current_user.role, 'index')))