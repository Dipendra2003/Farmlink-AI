"""
Async Email Helper - Prevents blocking on email sending
"""
import threading
import logging
from functools import wraps

def send_async_email(app, email_func, *args, **kwargs):
    """Send email in background thread"""
    with app.app_context():
        try:
            return email_func(*args, **kwargs)
        except Exception as e:
            logging.error(f"Async email error: {str(e)}")
            return {"success": False, "error": str(e)}

def async_email(email_func):
    """Decorator to send emails asynchronously"""
    @wraps(email_func)
    def wrapper(*args, **kwargs):
        from flask import current_app
        
        # Get the app instance
        app = current_app._get_current_object()
        
        # Start background thread
        thread = threading.Thread(
            target=send_async_email,
            args=(app, email_func, *args),
            kwargs=kwargs
        )
        thread.daemon = True
        thread.start()
        
        # Return immediately without waiting
        logging.info(f"Email queued for async sending: {email_func.__name__}")
        return {"success": True, "message": "Email queued for sending", "async": True}
    
    return wrapper
