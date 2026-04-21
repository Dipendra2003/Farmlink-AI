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
    
    # Fix for Supabase IPv6 issue on Render and local development
    # Supabase direct connections use IPv6, but many networks don't support it
    # Solution: Use Supabase's IPv4 connection pooler
    # Only convert if using direct connection (db.*.supabase.co), not if already using pooler
    if database_url and "supabase.co" in database_url:
        if "db." in database_url and ":5432" in database_url:
            # Convert direct connection to pooler
            database_url = database_url.replace(":5432", ":6543")
            if "?" in database_url:
                database_url += "&pgbouncer=true"
            else:
                database_url += "?pgbouncer=true"
        # If already using pooler (pooler.supabase.com), leave it as-is
    
    SQLALCHEMY_DATABASE_URI = database_url
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_size": 10,
        "pool_recycle": 300,
        "pool_pre_ping": True,
        "max_overflow": 20,
        "pool_timeout": 30,
        "connect_args": {
            "options": "-c statement_timeout=30000",
            "connect_timeout": 10,
        }
    }
    
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # API Keys
    GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
    WEATHER_API_KEY = os.environ.get('WEATHER_API_KEY')
    
    # Crop AI Configuration
    CROP_AI_STRICT_MODE = os.environ.get('CROP_AI_STRICT_MODE', 'true').lower() == 'true'
    CROP_AI_MIN_QUALITY_SCORE = int(os.environ.get('CROP_AI_MIN_QUALITY_SCORE', '70'))
    
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

    # MailerSend Configuration (Primary - Recommended for Production)
    # Free tier: 12,000 emails/month - Much better than SendGrid!
    MAILERSEND_API_KEY = os.environ.get('MAILERSEND_API_KEY', '').strip()
    MAILERSEND_FROM_EMAIL = os.environ.get('MAILERSEND_FROM_EMAIL', 'noreply@trial-0r83ql3xjx3lzw1j.mlsender.net').strip()
    MAILERSEND_FROM_NAME = os.environ.get('MAILERSEND_FROM_NAME', 'FarmLink AI').strip()

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
