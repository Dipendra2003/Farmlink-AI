import os
import logging
from flask import Flask, render_template
from flask_mail import Mail
from flask_wtf.csrf import CSRFProtect
from werkzeug.middleware.proxy_fix import ProxyFix
from dotenv import load_dotenv
from extensions import db, login_manager

# Initialize Flask extensions
csrf = CSRFProtect()
mail = Mail()

# Load environment variables first
# Force load .env file even in production (Render doesn't auto-load it)
load_dotenv(override=False)  # Don't override existing env vars

# Validate critical environment variables
database_url_check = os.environ.get('DATABASE_URL')
if not database_url_check:
    error_msg = """
    ================================================================================
    ERROR: DATABASE_URL environment variable is not set!
    
    For Render deployment:
    1. Go to your Render dashboard
    2. Select your web service
    3. Go to "Environment" tab
    4. Add DATABASE_URL with your Supabase connection string
    
    Example: postgresql://postgres.xxx:password@aws-1-us-east-1.pooler.supabase.com:5432/postgres
    
    See RENDER_SETUP_INSTRUCTIONS.md for complete setup guide.
    ================================================================================
    """
    print(error_msg, flush=True)
    logging.error(error_msg)
    import sys
    sys.exit(1)

if not os.environ.get('SESSION_SECRET'):
    warning_msg = "WARNING: SESSION_SECRET not set, using default (not secure for production)"
    print(warning_msg, flush=True)
    logging.warning(warning_msg)

# Import and setup structured logging
from logging_config import setup_logging

# Configure logging for debugging
# Use JSON structured logging in production, standard format in development
use_json_logging = os.environ.get('USE_JSON_LOGGING', 'false').lower() == 'true'
setup_logging(use_json=use_json_logging)

# Set werkzeug to INFO to show HTTP requests, but filter out debugger messages
logging.getLogger('werkzeug').setLevel(logging.INFO)

# Suppress verbose torch/transformers logging
logging.getLogger('torch').setLevel(logging.WARNING)
logging.getLogger('torch.fx').setLevel(logging.ERROR)
logging.getLogger('transformers').setLevel(logging.WARNING)
os.environ['TORCH_LOGS'] = ''  # Disable torch logging entirely

# Create the app with explicit template and static folders
template_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), 'templates'))
static_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), 'static'))
app = Flask(__name__, 
           template_folder=template_dir,
           static_folder=static_dir)

# Import utility functions
from utils import format_datetime, format_currency, get_order_status_badge_class, get_shipment_status_badge_class, get_weather_history
import json

# Add custom Jinja2 filters
def parse_json(value):
    """Parse JSON string to Python object"""
    try:
        return json.loads(value) if value else None
    except (json.JSONDecodeError, TypeError):
        return None

def get_image_url(image_path):
    """
    Get proper image URL - handles both local paths and Cloudinary URLs
    
    Args:
        image_path: Local path or Cloudinary URL
        
    Returns:
        str: Proper URL for the image
    """
    if not image_path:
        return None
    
    # If it's already a full URL (Cloudinary), return as-is
    if image_path.startswith('http'):
        return image_path
    
    # If it's a local path, convert to static URL
    from flask import url_for
    return url_for('static', filename=image_path)

def markdown_to_html(text):
    """Convert markdown text to HTML"""
    if not text:
        return ""
    try:
        import markdown
        # Convert markdown to HTML with extensions for better formatting
        html = markdown.markdown(
            text,
            extensions=['extra', 'nl2br', 'sane_lists', 'tables', 'fenced_code']
        )
        return html
    except ImportError:
        # Fallback if markdown is not installed - basic formatting
        import re
        # Convert headers
        text = re.sub(r'^### (.*?)$', r'<h3>\1</h3>', text, flags=re.MULTILINE)
        text = re.sub(r'^## (.*?)$', r'<h2>\1</h2>', text, flags=re.MULTILINE)
        text = re.sub(r'^# (.*?)$', r'<h1>\1</h1>', text, flags=re.MULTILINE)
        # Convert bold
        text = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', text)
        # Convert lists
        text = re.sub(r'^\- (.*?)$', r'<li>\1</li>', text, flags=re.MULTILINE)
        # Convert paragraphs
        text = text.replace('\n\n', '</p><p>')
        text = '<p>' + text + '</p>'
        return text

# Add utility functions and filters to template context
app.jinja_env.filters['markdown'] = markdown_to_html
app.jinja_env.globals.update(
    format_datetime=format_datetime,
    format_currency=format_currency,
    get_order_status_badge_class=get_order_status_badge_class,
    get_shipment_status_badge_class=get_shipment_status_badge_class,
    get_weather_history=get_weather_history,
    get_image_url=get_image_url
)
app.jinja_env.filters['parse_json'] = parse_json

app.secret_key = os.environ.get("SESSION_SECRET", "dev-secret-key-change-in-production")
app.config['WTF_CSRF_SECRET_KEY'] = app.secret_key  # Use same secret key for CSRF
app.config['RAZORPAY_KEY_ID'] = os.environ.get('RAZORPAY_KEY_ID')
app.config['RAZORPAY_KEY_SECRET'] = os.environ.get('RAZORPAY_KEY_SECRET')

# Configure Flask-Mail (using environment variables)
app.config['MAIL_SERVER'] = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
app.config['MAIL_PORT'] = int(os.environ.get('MAIL_PORT', 587))
app.config['MAIL_USE_TLS'] = os.environ.get('MAIL_USE_TLS', 'True').lower() == 'true'
app.config['MAIL_USE_SSL'] = os.environ.get('MAIL_USE_SSL', 'False').lower() == 'true'
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = ('FarmLink AI', os.environ.get('MAIL_DEFAULT_SENDER', 'farmlink76@gmail.com'))
app.config['MAIL_MAX_EMAILS'] = 10
app.config['MAIL_ASCII_ATTACHMENTS'] = False
app.config['MAIL_SUPPRESS_SEND'] = False  # Ensure emails are actually sent
app.config['MAIL_DEBUG'] = False  # Disable SMTP debug logs

# Configure the database - PostgreSQL
# Get DATABASE_URL from environment (supports both local and Render deployment)
database_url = os.environ.get("DATABASE_URL")

# Render uses postgres:// but SQLAlchemy needs postgresql://
if database_url and database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_size": 5,
    "max_overflow": 10,
    "pool_timeout": 30,
    "pool_recycle": 1800,
    "pool_pre_ping": True,
}
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False  # Disable modification tracking
app.config["SQLALCHEMY_ECHO"] = False  # Disable SQL query logging for cleaner output

# Exclude library files from triggering reloads
import sys
from werkzeug.serving import is_running_from_reloader
if is_running_from_reloader():
    # Exclude site-packages and virtual environment from watchdog
    site_packages = [p for p in sys.path if 'site-packages' in p or '.venv' in p or 'AppData' in p]
    for path in site_packages:
        try:
            from werkzeug._reloader import WatchdogReloaderLoop
            # Note: This is best effort - werkzeug doesn't expose a public API for this
        except:
            pass

# Initialize Flask extensions
mail.init_app(app)
db.init_app(app)
login_manager.init_app(app)
csrf.init_app(app)

# Initialize rate limiter for fraud prevention
from extensions import limiter
limiter.init_app(app)

# Add CSRF token to template globals
from flask_wtf.csrf import generate_csrf

@app.template_global()
def csrf_token():
    return generate_csrf()

# Configure session
app.config['SESSION_COOKIE_NAME'] = 'farmlink_session'  # Set the session cookie name
app.config['SESSION_COOKIE_SECURE'] = True  # Only send cookie over HTTPS
app.config['SESSION_COOKIE_HTTPONLY'] = True  # Prevent JavaScript access to session cookie
app.config['PERMANENT_SESSION_LIFETIME'] = 3600  # Session timeout in seconds (1 hour)
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'  # Protect against CSRF

# Initialize security middleware
from middleware import init_security_middleware
init_security_middleware(app)
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

# Use custom session interface
from custom_session import CustomSessionInterface
app.session_interface = CustomSessionInterface()

# Mail configuration is already set above - removed duplicate

# Rating System Configuration
app.config['RATING_EDIT_WINDOW_DAYS'] = 30
app.config['RATING_SUBMISSION_WINDOW_DAYS'] = 90
app.config['RATING_DELETE_WINDOW_DAYS'] = 30
app.config['RATING_MIN_ORDER_VALUE'] = 10

# Configure login manager settings
login_manager.login_view = 'login'
login_manager.login_message = 'Please log in to access this page.'
login_manager.login_message_category = 'info'

@login_manager.user_loader
def load_user(user_id):
    from models import User
    return User.query.get(int(user_id))

with app.app_context():
    # Import models to ensure tables are created
    try:
        import models
    except Exception as e:
        app.logger.error(f"Failed to import models: {str(e)}")
        import traceback
        app.logger.error(traceback.format_exc())
        raise
    
    # Only create tables in development - use migrations in production
    if os.environ.get('FLASK_ENV') != 'production':
        try:
            db.create_all()
        except Exception as e:
            if os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
                app.logger.warning(f"Could not create tables (may already exist): {str(e)}")
    else:
        # In production, verify database connection
        try:
            db.engine.connect()
        except Exception as e:
            app.logger.error(f"Database connection failed: {str(e)}")
            import traceback
            app.logger.error(traceback.format_exc())
            # Don't exit - let the app start and show error pages
    
    # Import and register routes
    try:
        import advanced_routes  # Import first for helper functions
    except Exception as e:
        app.logger.error(f"Failed to import advanced_routes: {str(e)}")
        import traceback
        app.logger.error(traceback.format_exc())
        raise
    
    try:
        import routes
    except Exception as e:
        app.logger.error(f"Failed to import routes: {str(e)}")
        import traceback
        app.logger.error(traceback.format_exc())
        raise
    
    try:
        import expert_forum_routes  # Import consolidated Expert Forum routes
    except Exception as e:
        app.logger.error(f"Failed to import expert_forum_routes: {str(e)}")
        import traceback
        app.logger.error(traceback.format_exc())
        raise
    
    try:
        import admin_crop_routes  # Import admin crop management routes
    except Exception as e:
        app.logger.error(f"Failed to import admin_crop_routes: {str(e)}")
        import traceback
        app.logger.error(traceback.format_exc())
        raise
    
    try:
        import admin_order_routes  # Import admin order management routes
    except Exception as e:
        app.logger.error(f"Failed to import admin_order_routes: {str(e)}")
        import traceback
        app.logger.error(traceback.format_exc())
        raise
    
    try:
        import admin_analytics_routes  # Import admin analytics routes
    except Exception as e:
        app.logger.error(f"Failed to import admin_analytics_routes: {str(e)}")
        import traceback
        app.logger.error(traceback.format_exc())
        raise
    
    try:
        import admin_security_routes  # Import admin security routes
    except Exception as e:
        app.logger.error(f"Failed to import admin_security_routes: {str(e)}")
        import traceback
        app.logger.error(traceback.format_exc())
        raise
    
    try:
        from payment_routes import payment_bp
        app.register_blueprint(payment_bp, url_prefix='/payment')
    except Exception as e:
        app.logger.error(f"Failed to register payment routes: {str(e)}")
        import traceback
        app.logger.error(traceback.format_exc())
        raise
    
    # Register rating routes
    try:
        from rating_routes import rating_bp
        app.register_blueprint(rating_bp, url_prefix='/ratings')
    except Exception as e:
        app.logger.error(f"Failed to register rating routes: {str(e)}")
        import traceback
        app.logger.error(traceback.format_exc())
        raise
    
    # Import API routes
    try:
        import api_routes  # REST API endpoints for mobile/third-party integrations
    except Exception as e:
        app.logger.error(f"Failed to import api_routes: {str(e)}")
        import traceback
        app.logger.error(traceback.format_exc())
        raise
    
    # Import tracking routes
    try:
        import tracking_routes  # Shipment tracking routes
    except Exception as e:
        app.logger.error(f"Failed to import tracking_routes: {str(e)}")
        import traceback
        app.logger.error(traceback.format_exc())
        raise
    
    try:
        import admin_shipment_routes  # Admin shipment management routes
    except Exception as e:
        app.logger.error(f"Failed to import admin_shipment_routes: {str(e)}")
        import traceback
        app.logger.error(traceback.format_exc())
        raise
    
    # Initialize tracking scheduler for background jobs
    try:
        from tracking_scheduler import init_tracking_scheduler
        init_tracking_scheduler(app)
    except Exception as e:
        if os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
            app.logger.error(f"Failed to initialize tracking scheduler: {str(e)}")
            import traceback
            app.logger.error(traceback.format_exc())
        # Continue without scheduler - jobs can be run manually if needed
    
    # Add security headers for all responses
    @app.after_request
    def add_security_headers(response):
        # Enable microphone access for speech recognition
        # Only use Permissions-Policy (newer standard)
        response.headers['Permissions-Policy'] = 'microphone=*, camera=*, geolocation=*'
        
        # Prevent Vercel from caching dynamic responses and breaking CSRF/Sessions
        if 'Cache-Control' not in response.headers:
            if request.path.startswith('/static/'):
                response.headers['Cache-Control'] = 'public, max-age=604800'  # 7 days for static assets
            else:
                response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        
        # Ensure session cookie changes are respected by proxies
        response.vary.add('Cookie')
        
        return response
    
    # Register error handlers
    @app.errorhandler(500)
    def internal_error(error):
        app.logger.error(f'Server Error: {error}')
        try:
            db.session.rollback()  # Roll back the session in case of database errors
        except Exception as e:
            app.logger.error(f'Error during rollback: {e}')
        
        try:
            return render_template('errors/500.html'), 500
        except Exception as e:
            app.logger.error(f'Error rendering 500 template: {e}')
            return "Internal Server Error", 500
            
    @app.errorhandler(404)
    def not_found_error(error):
        return render_template('errors/404.html'), 404

# Application startup complete - only log in main process
if os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
    print("\n✅ FarmLink AI Application Started Successfully!")
    print(f"   Environment: {os.environ.get('FLASK_ENV', 'development')}")
    print(f"   Debug Mode: {'On' if os.environ.get('FLASK_DEBUG', '0') == '1' else 'Off'}")
    print(f"   Database: Connected\n")
