import os
import logging
from flask import Flask, render_template
from flask_mail import Mail
from flask_wtf.csrf import CSRFProtect
from werkzeug.middleware.proxy_fix import ProxyFix
from dotenv import load_dotenv
from extensions import db, login_manager
from init_uploads import init_upload_directories

# Initialize Flask extensions
csrf = CSRFProtect()
mail = Mail()

# Load environment variables first
load_dotenv()

# Import and setup structured logging
from logging_config import setup_logging

# Configure logging for debugging
# Use JSON structured logging in production, standard format in development
use_json_logging = os.environ.get('USE_JSON_LOGGING', 'false').lower() == 'true'
setup_logging(use_json=use_json_logging)

# Set werkzeug to INFO to show HTTP requests, but filter out debugger messages
logging.getLogger('werkzeug').setLevel(logging.INFO)

# Create the app with explicit template and static folders
template_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), 'templates'))
static_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), 'static'))
app = Flask(__name__, 
           template_folder=template_dir,
           static_folder=static_dir)

# Initialize upload directories
init_upload_directories()

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
    get_weather_history=get_weather_history
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
app.config['MAIL_DEBUG'] = os.environ.get('FLASK_DEBUG', '0') == '1'  # Enable debug in development

# Configure the database - PostgreSQL
# Get DATABASE_URL from environment (supports both local and Render deployment)
database_url = os.environ.get("DATABASE_URL")

# Render uses postgres:// but SQLAlchemy needs postgresql://
if database_url and database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 300,
    "pool_pre_ping": True,
    "pool_size": 10,
    "max_overflow": 20,
}
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False  # Disable modification tracking
app.config["SQLALCHEMY_ECHO"] = False  # Disable SQL query logging for cleaner output

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
    import models
    # Only create tables in development - use migrations in production
    if os.environ.get('FLASK_ENV') != 'production':
        try:
            db.create_all()
            # Only log in main process to avoid duplicate messages
            if os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
                app.logger.info("Database tables created successfully")
        except Exception as e:
            if os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
                app.logger.warning(f"Could not create tables (may already exist): {str(e)}")
    
    # Import and register routes
    import advanced_routes  # Import first for helper functions
    import routes
    import expert_forum_routes  # Import consolidated Expert Forum routes
    import admin_crop_routes  # Import admin crop management routes
    import admin_order_routes  # Import admin order management routes
    import admin_analytics_routes  # Import admin analytics routes
    import admin_security_routes  # Import admin security routes
    from payment_routes import payment_bp
    app.register_blueprint(payment_bp, url_prefix='/payment')
    
    # Register rating routes
    from rating_routes import rating_bp
    app.register_blueprint(rating_bp, url_prefix='/ratings')
    
    # Import API routes
    import api_routes  # REST API endpoints for mobile/third-party integrations
    
    # Import tracking routes
    import tracking_routes  # Shipment tracking routes
    import admin_shipment_routes  # Admin shipment management routes
    
    # Initialize tracking scheduler for background jobs
    try:
        from tracking_scheduler import init_tracking_scheduler
        init_tracking_scheduler(app)
        # Only log in main process to avoid duplicate messages
        if os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
            app.logger.info("Tracking scheduler initialized successfully")
    except Exception as e:
        if os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
            app.logger.error(f"Failed to initialize tracking scheduler: {str(e)}")
        # Continue without scheduler - jobs can be run manually if needed
    
    # Add security headers for all responses
    @app.after_request
    def add_security_headers(response):
        # Enable microphone access for speech recognition
        # Only use Permissions-Policy (newer standard)
        response.headers['Permissions-Policy'] = 'microphone=*, camera=*, geolocation=*'
        return response
    
    # Register error handlers
    @app.errorhandler(500)
    def internal_error(error):
        app.logger.error(f'Server Error: {error}')
        db.session.rollback()  # Roll back the session in case of database errors
        return render_template('errors/500.html'), 500
    
    @app.errorhandler(404)
    def not_found_error(error):
        return render_template('errors/404.html'), 404
