"""
FarmLink AI - Logging Configuration Module
Provides structured logging with request ID tracking for monitoring and debugging
"""

import logging
import uuid
import json
from datetime import datetime
from flask import has_request_context, request, g
from functools import wraps
from typing import Any, Dict, Optional


class StructuredFormatter(logging.Formatter):
    """Custom formatter that outputs structured JSON logs"""
    
    def format(self, record):
        """Format log record as structured JSON"""
        log_data = {
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno
        }
        
        # Add request ID if available
        if has_request_context():
            log_data['request_id'] = getattr(g, 'request_id', None)
            log_data['path'] = request.path
            log_data['method'] = request.method
            log_data['remote_addr'] = request.remote_addr
        
        # Add extra fields from record
        if hasattr(record, 'user_id'):
            log_data['user_id'] = record.user_id
        if hasattr(record, 'order_id'):
            log_data['order_id'] = record.order_id
        if hasattr(record, 'cart_id'):
            log_data['cart_id'] = record.cart_id
        if hasattr(record, 'crop_id'):
            log_data['crop_id'] = record.crop_id
        if hasattr(record, 'payment_id'):
            log_data['payment_id'] = record.payment_id
        if hasattr(record, 'operation'):
            log_data['operation'] = record.operation
        if hasattr(record, 'duration_ms'):
            log_data['duration_ms'] = record.duration_ms
        if hasattr(record, 'error_code'):
            log_data['error_code'] = record.error_code
        
        # Add exception info if present
        if record.exc_info:
            log_data['exception'] = self.formatException(record.exc_info)
        
        return json.dumps(log_data)


class RequestIDFilter(logging.Filter):
    """Filter that adds request ID to log records"""
    
    def filter(self, record):
        """Add request ID to record if in request context"""
        if has_request_context():
            record.request_id = getattr(g, 'request_id', None)
        else:
            record.request_id = None
        
        # Suppress debugger messages
        if 'Debugger is active' in record.getMessage() or 'Debugger PIN' in record.getMessage():
            return False
        
        return True


def setup_logging(app=None, use_json=False):
    """
    Setup application logging configuration
    
    Args:
        app: Flask application instance
        use_json: Whether to use JSON structured logging
    """
    # Get root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.WARNING)  # Changed from INFO to WARNING
    
    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Create console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.WARNING)  # Changed from INFO to WARNING
    
    # Set formatter based on configuration
    if use_json:
        formatter = StructuredFormatter()
    else:
        formatter = logging.Formatter(
            '[%(asctime)s] %(levelname)s [%(name)s.%(funcName)s:%(lineno)d] '
            '[request_id:%(request_id)s] %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
    
    console_handler.setFormatter(formatter)
    
    # Add request ID filter
    console_handler.addFilter(RequestIDFilter())
    
    # Add handler to root logger
    root_logger.addHandler(console_handler)
    
    # Set specific logger levels - suppress all INFO logs
    logging.getLogger('werkzeug').setLevel(logging.WARNING)
    logging.getLogger('sqlalchemy.engine').setLevel(logging.WARNING)
    logging.getLogger('apscheduler').setLevel(logging.WARNING)
    logging.getLogger('app').setLevel(logging.WARNING)
    logging.getLogger('ai_services').setLevel(logging.WARNING)
    logging.getLogger('crop_ai_service').setLevel(logging.WARNING)
    logging.getLogger('pest_detection_service').setLevel(logging.WARNING)
    logging.getLogger('api_routes').setLevel(logging.WARNING)
    logging.getLogger('tracking_scheduler').setLevel(logging.WARNING)
    
    if app:
        pass  # Removed the info log to keep console clean


def get_request_id() -> Optional[str]:
    """Get current request ID from Flask g object"""
    if has_request_context():
        return getattr(g, 'request_id', None)
    return None


def generate_request_id() -> str:
    """Generate a unique request ID"""
    return str(uuid.uuid4())


def init_request_id():
    """Initialize request ID for current request"""
    if has_request_context() and not hasattr(g, 'request_id'):
        g.request_id = generate_request_id()


class OperationLogger:
    """Context manager for logging operations with timing"""
    
    def __init__(self, logger: logging.Logger, operation: str, **context):
        """
        Initialize operation logger
        
        Args:
            logger: Logger instance to use
            operation: Name of the operation being logged
            **context: Additional context fields (user_id, order_id, etc.)
        """
        self.logger = logger
        self.operation = operation
        self.context = context
        self.start_time = None
        self.success = False
    
    def __enter__(self):
        """Start operation logging"""
        self.start_time = datetime.utcnow()
        
        # Log operation start
        extra = {
            'operation': self.operation,
            **self.context
        }
        self.logger.info(f"Starting operation: {self.operation}", extra=extra)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """End operation logging"""
        duration_ms = int((datetime.utcnow() - self.start_time).total_seconds() * 1000)
        
        extra = {
            'operation': self.operation,
            'duration_ms': duration_ms,
            **self.context
        }
        
        if exc_type is None:
            # Operation succeeded
            self.logger.info(
                f"Completed operation: {self.operation} (duration: {duration_ms}ms)",
                extra=extra
            )
        else:
            # Operation failed
            extra['error_code'] = getattr(exc_val, 'code', 'UNKNOWN_ERROR')
            self.logger.error(
                f"Failed operation: {self.operation} (duration: {duration_ms}ms) - {exc_val}",
                extra=extra,
                exc_info=True
            )
        
        return False  # Don't suppress exceptions


def log_cart_operation(logger: logging.Logger, operation: str, cart_id: int = None, 
                       user_id: int = None, crop_id: int = None, **kwargs):
    """
    Log cart operation with structured context
    
    Args:
        logger: Logger instance
        operation: Operation name (add_item, update_quantity, remove_item, etc.)
        cart_id: Cart ID
        user_id: User ID
        crop_id: Crop ID
        **kwargs: Additional context
    """
    extra = {
        'operation': f'cart.{operation}',
        'cart_id': cart_id,
        'user_id': user_id,
        'crop_id': crop_id,
        **kwargs
    }
    logger.info(f"Cart operation: {operation}", extra=extra)


def log_order_operation(logger: logging.Logger, operation: str, order_id: int = None,
                       user_id: int = None, buyer_id: int = None, farmer_id: int = None,
                       **kwargs):
    """
    Log order operation with structured context
    
    Args:
        logger: Logger instance
        operation: Operation name (create, update_status, cancel, etc.)
        order_id: Order ID
        user_id: User ID performing the operation
        buyer_id: Buyer user ID
        farmer_id: Farmer user ID
        **kwargs: Additional context
    """
    extra = {
        'operation': f'order.{operation}',
        'order_id': order_id,
        'user_id': user_id,
        'buyer_id': buyer_id,
        'farmer_id': farmer_id,
        **kwargs
    }
    logger.info(f"Order operation: {operation}", extra=extra)


def log_payment_operation(logger: logging.Logger, operation: str, payment_id: int = None,
                         order_id: int = None, razorpay_order_id: str = None,
                         amount: float = None, **kwargs):
    """
    Log payment operation with structured context
    
    Args:
        logger: Logger instance
        operation: Operation name (create, verify, refund, etc.)
        payment_id: Payment ID
        order_id: Order ID
        razorpay_order_id: Razorpay order ID
        amount: Payment amount
        **kwargs: Additional context
    """
    extra = {
        'operation': f'payment.{operation}',
        'payment_id': payment_id,
        'order_id': order_id,
        'razorpay_order_id': razorpay_order_id,
        'amount': amount,
        **kwargs
    }
    logger.info(f"Payment operation: {operation}", extra=extra)


def log_inventory_operation(logger: logging.Logger, operation: str, crop_id: int = None,
                           quantity: float = None, old_quantity: float = None,
                           new_quantity: float = None, **kwargs):
    """
    Log inventory operation with structured context
    
    Args:
        logger: Logger instance
        operation: Operation name (check, reduce, release, etc.)
        crop_id: Crop ID
        quantity: Quantity involved in operation
        old_quantity: Previous quantity
        new_quantity: New quantity
        **kwargs: Additional context
    """
    extra = {
        'operation': f'inventory.{operation}',
        'crop_id': crop_id,
        'quantity': quantity,
        'old_quantity': old_quantity,
        'new_quantity': new_quantity,
        **kwargs
    }
    logger.info(f"Inventory operation: {operation}", extra=extra)


def log_notification_operation(logger: logging.Logger, operation: str, notification_type: str,
                              recipient_email: str = None, order_id: int = None,
                              success: bool = None, error: str = None, **kwargs):
    """
    Log notification operation with structured context
    
    Args:
        logger: Logger instance
        operation: Operation name (send, retry, fail, etc.)
        notification_type: Type of notification (order_placed, payment_confirmed, etc.)
        recipient_email: Email recipient
        order_id: Related order ID
        success: Whether notification was successful
        error: Error message if failed
        **kwargs: Additional context
    """
    extra = {
        'operation': f'notification.{operation}',
        'notification_type': notification_type,
        'recipient_email': recipient_email,
        'order_id': order_id,
        'success': success,
        **kwargs
    }
    
    if success:
        logger.info(f"Notification sent: {notification_type}", extra=extra)
    else:
        extra['error'] = error
        logger.error(f"Notification failed: {notification_type} - {error}", extra=extra)


def log_error(logger: logging.Logger, error_code: str, message: str, **context):
    """
    Log error with structured context
    
    Args:
        logger: Logger instance
        error_code: Error code
        message: Error message
        **context: Additional context
    """
    extra = {
        'error_code': error_code,
        **context
    }
    logger.error(message, extra=extra)


# Export main functions
__all__ = [
    'setup_logging',
    'get_request_id',
    'generate_request_id',
    'init_request_id',
    'OperationLogger',
    'log_cart_operation',
    'log_order_operation',
    'log_payment_operation',
    'log_inventory_operation',
    'log_notification_operation',
    'log_error'
]
