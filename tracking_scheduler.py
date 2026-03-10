"""
Tracking Scheduler Module
Initialize and configure APScheduler for background tracking jobs
"""
import os
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from tracking_jobs import TrackingJobs

logger = logging.getLogger(__name__)

# Global scheduler instance
scheduler = None


def init_tracking_scheduler(app):
    """
    Initialize APScheduler with tracking jobs
    
    Args:
        app: Flask application instance
    """
    global scheduler
    
    if scheduler is not None:
        logger.warning("Scheduler already initialized")
        return scheduler
    
    try:
        # Create scheduler instance
        scheduler = BackgroundScheduler(daemon=True)
        
        # Get configuration from environment variables
        sync_interval_hours = int(os.environ.get('TRACKING_POLL_INTERVAL', 14400)) // 3600  # Convert seconds to hours
        
        # Job 1: Sync active shipments every 4 hours (default)
        scheduler.add_job(
            func=TrackingJobs.sync_active_shipments,
            trigger=IntervalTrigger(hours=sync_interval_hours),
            id='sync_active_shipments',
            name='Sync Active Shipments',
            replace_existing=True,
            max_instances=1  # Prevent concurrent runs
        )
        if os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
            logger.info(f"Scheduled sync_active_shipments job to run every {sync_interval_hours} hours")
        
        # Job 2: Auto-confirm deliveries daily at midnight
        scheduler.add_job(
            func=TrackingJobs.auto_confirm_deliveries,
            trigger=CronTrigger(hour=0, minute=0),
            id='auto_confirm_deliveries',
            name='Auto-Confirm Deliveries',
            replace_existing=True,
            max_instances=1
        )
        if os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
            logger.info("Scheduled auto_confirm_deliveries job to run daily at midnight")
        
        # Job 3: Send delivery reminders daily at 9 AM
        scheduler.add_job(
            func=TrackingJobs.send_delivery_reminders,
            trigger=CronTrigger(hour=9, minute=0),
            id='send_delivery_reminders',
            name='Send Delivery Reminders',
            replace_existing=True,
            max_instances=1
        )
        if os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
            logger.info("Scheduled send_delivery_reminders job to run daily at 9 AM")
        
        # Job 4: Cleanup old tracking data monthly (1st of each month at 2 AM)
        scheduler.add_job(
            func=TrackingJobs.cleanup_old_tracking_data,
            trigger=CronTrigger(day=1, hour=2, minute=0),
            id='cleanup_old_tracking_data',
            name='Cleanup Old Tracking Data',
            replace_existing=True,
            max_instances=1
        )
        if os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
            logger.info("Scheduled cleanup_old_tracking_data job to run monthly on the 1st at 2 AM")
        
        # Start the scheduler
        scheduler.start()
        if os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
            logger.info("Tracking scheduler started successfully")
        
        # Register shutdown handler
        import atexit
        atexit.register(lambda: shutdown_scheduler())
        
        return scheduler
        
    except Exception as e:
        logger.error(f"Error initializing tracking scheduler: {str(e)}", exc_info=True)
        raise


def shutdown_scheduler():
    """
    Gracefully shutdown the scheduler
    """
    global scheduler
    
    if scheduler is not None:
        try:
            logger.info("Shutting down tracking scheduler...")
            scheduler.shutdown(wait=True)
            logger.info("Tracking scheduler shut down successfully")
        except Exception as e:
            logger.error(f"Error shutting down scheduler: {str(e)}", exc_info=True)


def get_scheduler():
    """
    Get the scheduler instance
    
    Returns:
        BackgroundScheduler instance or None
    """
    return scheduler


def get_job_status():
    """
    Get status of all scheduled jobs
    
    Returns:
        List of job information dictionaries
    """
    global scheduler
    
    if scheduler is None:
        return []
    
    jobs = []
    for job in scheduler.get_jobs():
        jobs.append({
            'id': job.id,
            'name': job.name,
            'next_run_time': job.next_run_time,
            'trigger': str(job.trigger)
        })
    
    return jobs
