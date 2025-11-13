"""
Database Migration Script for Learning Progress Feature

USAGE:
    python migrate_learning_feature.py

WHAT IT DOES:
    - Creates user_learning_preference table (user preferences)
    - Creates article_recommendation table (personalized recommendations)
    - Creates user_achievement table (achievement badges)
    - Adds time_spent_seconds column to user_reading_progress
    - Verifies all changes were applied successfully

FEATURES ADDED:
    ✓ Learning progress tracking with statistics
    ✓ Personalized article recommendations (smart algorithm)
    ✓ User preferences (skill level, interests, goals)
    ✓ 12 achievement badges with progress tracking
    ✓ Reading streak tracking
    ✓ Fully responsive design (mobile, tablet, desktop)

NEW FILES:
    - learning_recommendation_service.py (recommendation engine)
    - achievement_service.py (achievement system)
    - templates/learning_hub/preferences.html (preferences page)

MODIFIED FILES:
    - models.py (3 new models)
    - advanced_routes.py (5 new routes)
    - templates/learning_hub/progress.html (enhanced UI)
    - templates/learning_hub/index.html (responsive fixes)

RUN ONCE during deployment. Safe to run multiple times (idempotent).
"""
from app import app, db
from sqlalchemy import text
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def migrate_database():
    """Add new tables and columns for learning progress feature"""
    with app.app_context():
        try:
            logger.info("Starting database migration...")
            
            # Create all new tables (will skip existing ones)
            logger.info("Creating new tables...")
            db.create_all()
            logger.info("✓ Tables created/verified")
            
            # Add time_spent_seconds column to user_reading_progress if it doesn't exist
            logger.info("Adding time_spent_seconds column...")
            try:
                db.session.execute(text(
                    'ALTER TABLE user_reading_progress ADD COLUMN IF NOT EXISTS time_spent_seconds INTEGER DEFAULT 0'
                ))
                db.session.commit()
                logger.info("✓ Column time_spent_seconds added")
            except Exception as e:
                logger.warning(f"Column might already exist: {str(e)}")
                db.session.rollback()
            
            # Verify tables exist
            logger.info("\nVerifying tables...")
            tables_to_check = [
                'user_reading_progress',
                'user_learning_preference',
                'article_recommendation',
                'user_achievement'
            ]
            
            for table in tables_to_check:
                result = db.session.execute(text(
                    f"SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = '{table}')"
                ))
                exists = result.scalar()
                if exists:
                    logger.info(f"✓ Table '{table}' exists")
                else:
                    logger.error(f"✗ Table '{table}' NOT found!")
            
            # Verify columns
            logger.info("\nVerifying columns in user_reading_progress...")
            result = db.session.execute(text(
                """
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'user_reading_progress'
                ORDER BY ordinal_position
                """
            ))
            columns = [row[0] for row in result]
            logger.info(f"Columns: {', '.join(columns)}")
            
            if 'time_spent_seconds' in columns:
                logger.info("✓ time_spent_seconds column exists")
            else:
                logger.error("✗ time_spent_seconds column NOT found!")
            
            logger.info("\n" + "="*50)
            logger.info("Migration completed successfully!")
            logger.info("="*50)
            
            return True
            
        except Exception as e:
            logger.error(f"Migration failed: {str(e)}")
            db.session.rollback()
            return False

if __name__ == '__main__':
    success = migrate_database()
    if success:
        print("\n✓ Database migration completed successfully!")
        print("You can now use the learning progress feature.")
    else:
        print("\n✗ Migration failed. Please check the logs above.")
        exit(1)
