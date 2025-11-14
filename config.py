"""
Configuration settings for the application
"""
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class Config:
    """Base configuration"""
    SECRET_KEY = os.environ.get('SESSION_SECRET', 'dev-secret-key-change-in-production')
    
    # PostgreSQL Database Configuration
    database_url = os.environ.get('DATABASE_URL')
    
    # Render uses postgres:// but SQLAlchemy needs postgresql://
    if database_url and database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)
    
    SQLALCHEMY_DATABASE_URI = database_url
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_size": 10,
        "pool_recycle": 300,
        "pool_pre_ping": True,
        "max_overflow": 20,
        "pool_timeout": 30,
    }
    
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # API Keys
    GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
    WEATHER_API_KEY = os.environ.get('WEATHER_API_KEY')
    
    # KYC Encryption Configuration
    KYC_ENCRYPTION_KEY = os.environ.get('KYC_ENCRYPTION_KEY')
    KYC_UPLOAD_DIR = os.environ.get('KYC_UPLOAD_DIR', 'static/uploads/kyc')
    KYC_MAX_FILE_SIZE = int(os.environ.get('KYC_MAX_FILE_SIZE', 5242880))  # 5MB in bytes

    # Rating System Configuration
    RATING_EDIT_WINDOW_DAYS = 30
    RATING_SUBMISSION_WINDOW_DAYS = 90
    RATING_DELETE_WINDOW_DAYS = 30
    RATING_MIN_ORDER_VALUE = 10

    # Fraud Prevention Configuration
    RATING_MAX_PER_HOUR = 10
    RATING_SUSPICIOUS_IP_THRESHOLD = 5
    RATING_SUSPICIOUS_IP_WINDOW_HOURS = 1

    # SendGrid Configuration (Primary)
    SENDGRID_API_KEY = os.environ.get('SENDGRID_API_KEY')
    SENDGRID_FROM_EMAIL = os.environ.get('SENDGRID_FROM_EMAIL')
    
    # Mail Configuration (SMTP Fallback)
    MAIL_SERVER = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
    MAIL_PORT = int(os.environ.get('MAIL_PORT', 587))
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'True').lower() == 'true'
    MAIL_USE_SSL = os.environ.get('MAIL_USE_SSL', 'False').lower() == 'true'
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER', 'noreply@farmlink-ai.com')
    MAIL_MAX_EMAILS = None  # No limit on emails per connection
    MAIL_SUPPRESS_SEND = False  # Set to True to disable email sending in dev
    MAIL_ASCII_ATTACHMENTS = False

class DevelopmentConfig(Config):
    """Development configuration"""
    DEBUG = True
    SQLALCHEMY_ECHO = True  # Log SQL queries
    SQLALCHEMY_RECORD_QUERIES = True  # Record query performance
    SQLALCHEMY_SLOW_QUERY_THRESHOLD = 0.5  # Log queries slower than 0.5 seconds

class ProductionConfig(Config):
    """Production configuration"""
    DEBUG = False
    SQLALCHEMY_ECHO = False
    
    # Production uses DATABASE_URL from environment (Render provides this automatically)

# Configuration dictionary
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}
