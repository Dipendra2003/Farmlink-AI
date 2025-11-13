"""
KYC Security Enhancements
Additional security measures for KYC system
"""

import logging
from functools import wraps
from flask import request, flash, redirect, url_for, current_app
from flask_login import current_user
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# Rate limiting for KYC operations
kyc_rate_limits = {}


def https_required(f):
    """
    Decorator to enforce HTTPS for KYC routes in production
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if current_app.config.get('ENV') == 'production' and not request.is_secure:
            logger.warning(f"Insecure KYC access attempt from {request.remote_addr}")
            flash('This operation requires a secure connection (HTTPS).', 'danger')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function


def validate_kyc_file_security(file):
    """
    Additional security validation for uploaded KYC files
    
    Args:
        file: FileStorage object
    
    Returns:
        tuple: (is_valid: bool, error_message: str or None)
    """
    if not file or not file.filename:
        return False, "No file provided"
    
    # Check file size (max 5MB)
    file.seek(0, 2)
    size = file.tell()
    file.seek(0)
    
    max_size = current_app.config.get('KYC_MAX_FILE_SIZE', 5 * 1024 * 1024)
    if size > max_size:
        logger.warning(f"File size {size} exceeds maximum {max_size}")
        return False, f"File size exceeds maximum {max_size / (1024 * 1024):.1f}MB"
    
    # Check for suspicious file names
    filename = file.filename.lower()
    suspicious_patterns = [
        '.exe', '.bat', '.cmd', '.sh', '.php', '.asp', '.jsp',
        '.js', '.vbs', '.ps1', '.dll', '.so', '.dylib'
    ]
    
    for pattern in suspicious_patterns:
        if pattern in filename:
            logger.warning(f"Suspicious file upload attempt: {filename} from {request.remote_addr}")
            return False, "Invalid file type detected"
    
    # Validate file extension
    allowed_extensions = {'jpg', 'jpeg', 'png', 'pdf'}
    if '.' not in filename:
        return False, "File must have an extension"
    
    ext = filename.rsplit('.', 1)[1].lower()
    if ext not in allowed_extensions:
        return False, f"Only {', '.join(allowed_extensions).upper()} files are allowed"
    
    return True, None


def sanitize_kyc_input(data):
    """
    Sanitize KYC form input data
    
    Args:
        data: Dictionary of form data
    
    Returns:
        dict: Sanitized data
    """
    sanitized = {}
    
    for key, value in data.items():
        if isinstance(value, str):
            # Remove any HTML tags
            import re
            value = re.sub(r'<[^>]+>', '', value)
            
            # Remove any script tags or javascript
            value = re.sub(r'javascript:', '', value, flags=re.IGNORECASE)
            value = re.sub(r'on\w+\s*=', '', value, flags=re.IGNORECASE)
            
            # Trim whitespace
            value = value.strip()
        
        sanitized[key] = value
    
    return sanitized


def log_kyc_security_event(event_type, user_id, details, severity='INFO'):
    """
    Log security events related to KYC operations
    
    Args:
        event_type: Type of security event
        user_id: User ID involved
        details: Event details
        severity: Log severity (INFO, WARNING, ERROR)
    """
    log_message = f"KYC Security Event - Type: {event_type}, User: {user_id}, IP: {request.remote_addr}, Details: {details}"
    
    if severity == 'ERROR':
        logger.error(log_message)
    elif severity == 'WARNING':
        logger.warning(log_message)
    else:
        logger.info(log_message)


def check_kyc_rate_limit(user_id, action='submission', limit=3, window_hours=24):
    """
    Check rate limiting for KYC operations
    
    Args:
        user_id: User ID
        action: Type of action (submission, view, etc.)
        limit: Maximum number of actions allowed
        window_hours: Time window in hours
    
    Returns:
        tuple: (allowed: bool, remaining: int)
    """
    now = datetime.utcnow()
    key = f"{user_id}_{action}"
    
    if key not in kyc_rate_limits:
        kyc_rate_limits[key] = []
    
    # Clean old attempts
    cutoff_time = now - timedelta(hours=window_hours)
    kyc_rate_limits[key] = [
        timestamp for timestamp in kyc_rate_limits[key]
        if timestamp > cutoff_time
    ]
    
    # Check if limit exceeded
    current_count = len(kyc_rate_limits[key])
    if current_count >= limit:
        log_kyc_security_event(
            'rate_limit_exceeded',
            user_id,
            f"Action: {action}, Limit: {limit}, Window: {window_hours}h",
            severity='WARNING'
        )
        return False, 0
    
    # Add current attempt
    kyc_rate_limits[key].append(now)
    remaining = limit - (current_count + 1)
    
    return True, remaining


def validate_kyc_access(kyc_record, user_id, is_admin=False):
    """
    Validate if user has access to view/modify KYC record
    
    Args:
        kyc_record: SellerKYC record
        user_id: User ID attempting access
        is_admin: Whether user is admin
    
    Returns:
        bool: True if access allowed
    """
    if not kyc_record:
        return False
    
    # Admins can access all records
    if is_admin:
        log_kyc_security_event(
            'admin_access',
            user_id,
            f"Accessed KYC record {kyc_record.id}",
            severity='INFO'
        )
        return True
    
    # Users can only access their own records
    if kyc_record.user_id == user_id:
        return True
    
    # Unauthorized access attempt
    log_kyc_security_event(
        'unauthorized_access',
        user_id,
        f"Attempted to access KYC record {kyc_record.id} belonging to user {kyc_record.user_id}",
        severity='WARNING'
    )
    return False


def validate_document_path(file_path):
    """
    Validate document path to prevent directory traversal attacks
    
    Args:
        file_path: File path to validate
    
    Returns:
        bool: True if path is safe
    """
    if not file_path:
        return False
    
    # Normalize path separators to forward slashes for consistent validation
    normalized_path = file_path.replace('\\', '/')
    
    # Check for directory traversal patterns
    dangerous_patterns = ['..', '~', '//', '%2e', '%2f', '%5c']
    
    for pattern in dangerous_patterns:
        if pattern in normalized_path.lower():
            logger.warning(f"Directory traversal attempt detected: {file_path} from {request.remote_addr}")
            return False
    
    # Ensure path starts with expected directory
    expected_prefix = 'static/uploads/kyc/'
    if not normalized_path.startswith(expected_prefix):
        logger.warning(f"Invalid file path prefix: {file_path}")
        return False
    
    return True


def mask_sensitive_data(data_type, value):
    """
    Mask sensitive data for logging purposes
    
    Args:
        data_type: Type of data (aadhaar, pan, bank_account)
        value: Value to mask
    
    Returns:
        str: Masked value
    """
    if not value:
        return "****"
    
    if data_type == 'aadhaar':
        # Show only last 4 digits
        if len(value) >= 4:
            return f"XXXX-XXXX-{value[-4:]}"
        return "XXXX-XXXX-XXXX"
    
    elif data_type == 'pan':
        # Show first 2 and last 1 characters
        if len(value) >= 3:
            return f"{value[:2]}XXXXX{value[-1]}"
        return "XXXXXXXXXX"
    
    elif data_type == 'bank_account':
        # Show only last 4 digits
        if len(value) >= 4:
            return f"XXXX{value[-4:]}"
        return "XXXX"
    
    return "****"


def audit_kyc_action(action, kyc_id, user_id, details=None):
    """
    Audit KYC actions for compliance
    
    Args:
        action: Action performed (view, approve, reject, etc.)
        kyc_id: KYC record ID
        user_id: User performing action
        details: Additional details
    """
    from models import KYCAuditLog
    from extensions import db
    
    try:
        # This is already handled by KYCService, but we log it here too
        log_kyc_security_event(
            f'kyc_{action}',
            user_id,
            f"KYC ID: {kyc_id}, Details: {details}",
            severity='INFO'
        )
    except Exception as e:
        logger.error(f"Failed to audit KYC action: {str(e)}")


def check_suspicious_activity(user_id):
    """
    Check for suspicious KYC-related activity
    
    Args:
        user_id: User ID to check
    
    Returns:
        tuple: (is_suspicious: bool, reason: str or None)
    """
    # Check for multiple rapid submissions
    key = f"{user_id}_submission"
    if key in kyc_rate_limits:
        recent_attempts = len(kyc_rate_limits[key])
        if recent_attempts >= 3:
            return True, "Multiple rapid KYC submissions detected"
    
    # Check for access from multiple IPs in short time
    # This would require session tracking - placeholder for now
    
    return False, None
