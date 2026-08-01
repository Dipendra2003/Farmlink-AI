"""
Security Enhancements Module
Provides centralized security features including:
- Admin action logging decorator
- Security headers
- 2FA support
- File upload security
- Input sanitization
- Rate limiting
- User ownership validation
"""

from functools import wraps
from flask import request, make_response, current_app
from flask_login import current_user
from datetime import datetime, timedelta
import logging
import re
import html

logger = logging.getLogger('security')


# ============================================================================
# INPUT SANITIZATION
# ============================================================================

class InputSanitizer:
    """Input sanitization utilities to prevent XSS and injection attacks"""
    
    @staticmethod
    def sanitize_text(text, max_length=None, allow_html=False):
        """
        Sanitize text input to prevent XSS attacks
        
        Args:
            text: Input text to sanitize
            max_length: Maximum allowed length
            allow_html: If False, escape all HTML tags
        
        Returns:
            Sanitized text string
        """
        if not text:
            return text
        
        # Convert to string if not already
        text = str(text)
        
        # Trim whitespace
        text = text.strip()
        
        # Escape HTML if not allowed
        if not allow_html:
            text = html.escape(text)
        
        # Remove null bytes
        text = text.replace('\x00', '')
        
        # Limit length if specified
        if max_length and len(text) > max_length:
            text = text[:max_length]
        
        return text
    
    @staticmethod
    def sanitize_address(address):
        """
        Sanitize delivery address input
        
        Args:
            address: Address string
        
        Returns:
            Sanitized address string
        """
        if not address:
            return address
        
        # Remove HTML tags
        address = html.escape(address)
        
        # Remove excessive whitespace
        address = ' '.join(address.split())
        
        # Remove null bytes and control characters
        address = ''.join(char for char in address if ord(char) >= 32 or char in '\n\r\t')
        
        # Limit length
        max_length = 500
        if len(address) > max_length:
            address = address[:max_length]
        
        return address.strip()
    
    @staticmethod
    def sanitize_notes(notes):
        """
        Sanitize order notes or comments
        
        Args:
            notes: Notes string
        
        Returns:
            Sanitized notes string
        """
        if not notes:
            return notes
        
        # Remove HTML tags
        notes = html.escape(notes)
        
        # Remove excessive whitespace but preserve line breaks
        lines = notes.split('\n')
        lines = [' '.join(line.split()) for line in lines]
        notes = '\n'.join(lines)
        
        # Remove null bytes and dangerous control characters
        notes = ''.join(char for char in notes if ord(char) >= 32 or char in '\n\r\t')
        
        # Limit length
        max_length = 1000
        if len(notes) > max_length:
            notes = notes[:max_length]
        
        return notes.strip()
    
    @staticmethod
    def sanitize_search_query(query):
        """
        Sanitize search query to prevent SQL injection
        
        Args:
            query: Search query string
        
        Returns:
            Sanitized query string
        """
        if not query:
            return query
        
        # Remove HTML
        query = html.escape(query)
        
        # Remove SQL injection patterns
        dangerous_patterns = [
            r'--',  # SQL comments
            r';',   # Statement separator
            r'\/\*', r'\*\/',  # Multi-line comments
            r'xp_',  # Extended stored procedures
            r'sp_',  # System stored procedures
        ]
        
        for pattern in dangerous_patterns:
            query = re.sub(pattern, '', query, flags=re.IGNORECASE)
        
        # Limit length
        max_length = 200
        if len(query) > max_length:
            query = query[:max_length]
        
        return query.strip()


# ============================================================================
# RATE LIMITING
# ============================================================================

class RateLimiter:
    """Enhanced rate limiting for cart and order operations"""
    
    # In-memory storage for rate limits (use Redis in production)
    _rate_limits = {}
    
    @staticmethod
    def _get_key(operation, identifier):
        """Generate rate limit key"""
        return f"{operation}:{identifier}"
    
    @staticmethod
    def _clean_old_entries(key, window_seconds):
        """Remove old entries outside the time window"""
        now = datetime.utcnow()
        cutoff = now - timedelta(seconds=window_seconds)
        
        if key in RateLimiter._rate_limits:
            RateLimiter._rate_limits[key] = [
                timestamp for timestamp in RateLimiter._rate_limits[key]
                if timestamp > cutoff
            ]
    
    @staticmethod
    def check_rate_limit(operation, max_requests, window_seconds, identifier=None):
        """
        Check if rate limit is exceeded
        
        Args:
            operation: Operation name (e.g., 'add_to_cart', 'checkout')
            max_requests: Maximum number of requests allowed
            window_seconds: Time window in seconds
            identifier: User ID or IP address (defaults to current user or IP)
        
        Returns:
            tuple: (is_allowed: bool, remaining: int, reset_time: datetime)
        """
        # Get identifier
        if identifier is None:
            if current_user.is_authenticated:
                identifier = f"user_{current_user.id}"
            else:
                identifier = f"ip_{request.remote_addr}"
        
        key = RateLimiter._get_key(operation, identifier)
        now = datetime.utcnow()
        
        # Clean old entries
        RateLimiter._clean_old_entries(key, window_seconds)
        
        # Get current count
        if key not in RateLimiter._rate_limits:
            RateLimiter._rate_limits[key] = []
        
        current_count = len(RateLimiter._rate_limits[key])
        
        # Check if limit exceeded
        if current_count >= max_requests:
            # Calculate reset time
            oldest_timestamp = min(RateLimiter._rate_limits[key])
            reset_time = oldest_timestamp + timedelta(seconds=window_seconds)
            
            logger.warning(
                f"Rate limit exceeded for {operation}: {identifier}, "
                f"count={current_count}, max={max_requests}"
            )
            
            return False, 0, reset_time
        
        # Add current request
        RateLimiter._rate_limits[key].append(now)
        remaining = max_requests - current_count - 1
        reset_time = now + timedelta(seconds=window_seconds)
        
        return True, remaining, reset_time
    
    @staticmethod
    def rate_limit(operation, max_requests=10, window_seconds=60):
        """
        Decorator for rate limiting routes
        
        Usage:
            @rate_limit('add_to_cart', max_requests=20, window_seconds=60)
            def add_to_cart():
                ...
        """
        def decorator(f):
            @wraps(f)
            def decorated_function(*args, **kwargs):
                from flask import jsonify, flash, redirect, url_for
                
                is_allowed, remaining, reset_time = RateLimiter.check_rate_limit(
                    operation, max_requests, window_seconds
                )
                
                if not is_allowed:
                    # Check if AJAX request
                    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
                    
                    if is_ajax:
                        return jsonify({
                            'success': False,
                            'error': 'Too many requests. Please try again later.',
                            'error_code': 'RATE_LIMIT_EXCEEDED',
                            'reset_time': reset_time.isoformat()
                        }), 429
                    else:
                        flash('Too many requests. Please try again later.', 'warning')
                        return redirect(url_for('index'))
                
                # Add rate limit headers to response
                response = f(*args, **kwargs)
                
                # If response is a tuple (response, status_code), handle it
                if isinstance(response, tuple):
                    actual_response = response[0]
                else:
                    actual_response = response
                
                # Add headers if it's a Response object
                if hasattr(actual_response, 'headers'):
                    actual_response.headers['X-RateLimit-Limit'] = str(max_requests)
                    actual_response.headers['X-RateLimit-Remaining'] = str(remaining)
                    actual_response.headers['X-RateLimit-Reset'] = reset_time.isoformat()
                
                return response
            
            return decorated_function
        return decorator


# ============================================================================
# USER OWNERSHIP VALIDATION
# ============================================================================

class OwnershipValidator:
    """Validate user ownership of resources"""
    
    @staticmethod
    def validate_cart_ownership(cart_id, user_id=None):
        """
        Validate that cart belongs to user
        
        Args:
            cart_id: Cart ID
            user_id: User ID (defaults to current user)
        
        Returns:
            tuple: (is_valid: bool, error_message: str)
        """
        from models import Cart
        
        if user_id is None:
            if not current_user.is_authenticated:
                return False, "Authentication required"
            user_id = current_user.id
        
        cart = Cart.query.get(cart_id)
        if not cart:
            return False, "Cart not found"
        
        if cart.user_id != user_id:
            logger.warning(
                f"Unauthorized cart access attempt: user {user_id} "
                f"tried to access cart {cart_id} owned by user {cart.user_id}"
            )
            return False, "Access denied"
        
        return True, None
    
    @staticmethod
    def validate_cart_item_ownership(item_id, user_id=None):
        """
        Validate that cart item belongs to user's cart
        
        Args:
            item_id: Cart item ID
            user_id: User ID (defaults to current user)
        
        Returns:
            tuple: (is_valid: bool, error_message: str)
        """
        from models import CartItem
        
        if user_id is None:
            if not current_user.is_authenticated:
                return False, "Authentication required"
            user_id = current_user.id
        
        item = CartItem.query.get(item_id)
        if not item:
            return False, "Cart item not found"
        
        if item.cart.user_id != user_id:
            logger.warning(
                f"Unauthorized cart item access attempt: user {user_id} "
                f"tried to access item {item_id} in cart owned by user {item.cart.user_id}"
            )
            return False, "Access denied"
        
        return True, None
    
    @staticmethod
    def validate_order_ownership(order_id, user_id=None, allow_farmer=True):
        """
        Validate that order belongs to user (as buyer or farmer)
        
        Args:
            order_id: Order ID
            user_id: User ID (defaults to current user)
            allow_farmer: If True, allow farmer to access their orders
        
        Returns:
            tuple: (is_valid: bool, error_message: str, role: str)
        """
        from models import Order
        
        if user_id is None:
            if not current_user.is_authenticated:
                return False, "Authentication required", None
            user_id = current_user.id
        
        order = Order.query.get(order_id)
        if not order:
            return False, "Order not found", None
        
        # Check if user is buyer
        if order.buyer_id == user_id:
            return True, None, 'buyer'
        
        # Check if user is farmer (if allowed)
        if allow_farmer and order.farmer_id == user_id:
            return True, None, 'farmer'
        
        # Check if user is admin
        if current_user.is_authenticated and current_user.role == 'admin':
            return True, None, 'admin'
        
        logger.warning(
            f"Unauthorized order access attempt: user {user_id} "
            f"tried to access order {order_id} (buyer: {order.buyer_id}, farmer: {order.farmer_id})"
        )
        
        return False, "Access denied", None
    
    @staticmethod
    def validate_crop_ownership(crop_id, user_id=None):
        """
        Validate that crop belongs to user
        
        Args:
            crop_id: Crop ID
            user_id: User ID (defaults to current user)
        
        Returns:
            tuple: (is_valid: bool, error_message: str)
        """
        from models import Crop
        
        if user_id is None:
            if not current_user.is_authenticated:
                return False, "Authentication required"
            user_id = current_user.id
        
        crop = Crop.query.get(crop_id)
        if not crop:
            return False, "Crop not found"
        
        if crop.farmer_id != user_id:
            logger.warning(
                f"Unauthorized crop access attempt: user {user_id} "
                f"tried to access crop {crop_id} owned by user {crop.farmer_id}"
            )
            return False, "Access denied"
        
        return True, None


def log_admin_action(action_type, target_type=None, target_id=None, description=None):
    """
    Centralized decorator for logging admin actions
    
    Usage:
        @log_admin_action('approve_crop', 'crop')
        def approve_crop(crop_id):
            ...
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            from models import AdminActionLog
            from app import db
            
            # Execute the function first
            result = f(*args, **kwargs)
            
            # Extract target_id from kwargs or args if not provided
            actual_target_id = target_id
            if actual_target_id is None:
                # Try to get from kwargs
                for key in ['crop_id', 'order_id', 'user_id', 'post_id', 'id']:
                    if key in kwargs:
                        actual_target_id = kwargs[key]
                        break
                # Try to get from args (usually first positional argument)
                if actual_target_id is None and len(args) > 0:
                    actual_target_id = args[0]
            
            # Build description if not provided
            actual_description = description
            if actual_description is None:
                actual_description = f"{action_type} on {target_type} {actual_target_id}"
            
            try:
                # Log the action
                log = AdminActionLog(
                    admin_id=current_user.id,
                    action_type=action_type,
                    target_type=target_type,
                    target_id=actual_target_id,
                    description=actual_description,
                    ip_address=request.remote_addr,
                    user_agent=request.user_agent.string[:255] if request.user_agent else None
                )
                db.session.add(log)
                db.session.commit()
                
                logger.info(
                    f"Admin action logged: {action_type} by user {current_user.id} "
                    f"on {target_type} {actual_target_id} from IP {request.remote_addr}"
                )
            except Exception as e:
                logger.error(f"Failed to log admin action: {str(e)}")
                # Don't fail the request if logging fails
                db.session.rollback()
            
            return result
        return decorated_function
    return decorator


def add_security_headers(response):
    """
    Add comprehensive security headers to response
    Should be called in after_request handler
    """
    # Prevent MIME type sniffing
    response.headers['X-Content-Type-Options'] = 'nosniff'
    
    # Prevent clickjacking
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    
    # Enable XSS protection
    response.headers['X-XSS-Protection'] = '1; mode=block'
    
    # Content Security Policy
    csp = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net https://code.jquery.com https://checkout.razorpay.com https://cdnjs.cloudflare.com https://www.googletagmanager.com https://www.google-analytics.com; "
        "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com https://cdnjs.cloudflare.com https://use.fontawesome.com https://unpkg.com; "
        "font-src 'self' https://fonts.gstatic.com https://cdn.jsdelivr.net https://cdnjs.cloudflare.com https://use.fontawesome.com https://unpkg.com data:; "
        "img-src 'self' data: blob: https: https://www.google-analytics.com https://www.googletagmanager.com; "
        "connect-src 'self' https://api.razorpay.com https://lumberjack.razorpay.com https://cdn.jsdelivr.net https://www.google-analytics.com https://analytics.google.com https://stats.g.doubleclick.net; "
        "frame-src https://api.razorpay.com;"
    )
    response.headers['Content-Security-Policy'] = csp
    
    # HSTS - Force HTTPS (only in production)
    if not current_app.debug and request.is_secure:
        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    
    # Referrer Policy
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    
    # Permissions Policy (formerly Feature-Policy)
    response.headers['Permissions-Policy'] = (
        'geolocation=(), '
        'microphone=(), '
        'camera=(), '
        'payment=(self "https://api.razorpay.com")'
    )
    
    return response


def init_security_headers(app):
    """Initialize security headers for the Flask app"""
    @app.after_request
    def apply_security_headers(response):
        return add_security_headers(response)


# ============================================================================
# TWO-FACTOR AUTHENTICATION (2FA) SUPPORT
# ============================================================================

class TwoFactorAuth:
    """Two-Factor Authentication handler"""
    
    @staticmethod
    def generate_totp_secret():
        """Generate a new TOTP secret for a user"""
        import pyotp
        return pyotp.random_base32()
    
    @staticmethod
    def get_totp_uri(secret, username, issuer='FarmLink AI'):
        """Get TOTP provisioning URI for QR code generation"""
        import pyotp
        totp = pyotp.TOTP(secret)
        return totp.provisioning_uri(name=username, issuer_name=issuer)
    
    @staticmethod
    def verify_totp(secret, token):
        """Verify a TOTP token"""
        import pyotp
        totp = pyotp.TOTP(secret)
        return totp.verify(token, valid_window=1)
    
    @staticmethod
    def generate_backup_codes(count=10):
        """Generate backup codes for 2FA recovery"""
        import secrets
        import string
        codes = []
        for _ in range(count):
            code = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(8))
            # Format as XXXX-XXXX
            formatted_code = f"{code[:4]}-{code[4:]}"
            codes.append(formatted_code)
        return codes


def require_2fa(f):
    """Decorator to require 2FA verification for sensitive operations"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        from flask import session, redirect, url_for, flash
        
        # Check if user has 2FA enabled
        if hasattr(current_user, 'two_factor_enabled') and current_user.two_factor_enabled:
            # Check if 2FA is verified in this session
            if not session.get('2fa_verified', False):
                flash('Please verify your identity with 2FA.', 'warning')
                return redirect(url_for('verify_2fa', next=request.url))
        
        return f(*args, **kwargs)
    return decorated_function


# ============================================================================
# FILE UPLOAD SECURITY
# ============================================================================

class FileUploadSecurity:
    """File upload security utilities"""
    
    # Allowed file extensions
    ALLOWED_EXTENSIONS = {
        'image': {'png', 'jpg', 'jpeg', 'gif', 'webp'},
        'document': {'pdf', 'doc', 'docx', 'txt'},
        'spreadsheet': {'xls', 'xlsx', 'csv'}
    }
    
    # Maximum file sizes (in bytes)
    MAX_FILE_SIZES = {
        'image': 5 * 1024 * 1024,  # 5MB
        'document': 10 * 1024 * 1024,  # 10MB
        'spreadsheet': 10 * 1024 * 1024  # 10MB
    }
    
    @staticmethod
    def allowed_file(filename, file_type='image'):
        """Check if file extension is allowed"""
        if '.' not in filename:
            return False
        ext = filename.rsplit('.', 1)[1].lower()
        return ext in FileUploadSecurity.ALLOWED_EXTENSIONS.get(file_type, set())
    
    @staticmethod
    def check_file_size(file, file_type='image'):
        """Check if file size is within limits"""
        file.seek(0, 2)  # Seek to end
        size = file.tell()
        file.seek(0)  # Reset to beginning
        
        max_size = FileUploadSecurity.MAX_FILE_SIZES.get(file_type, 5 * 1024 * 1024)
        return size <= max_size
    
    @staticmethod
    def sanitize_filename(filename):
        """Sanitize filename to prevent directory traversal"""
        import os
        import re
        
        # Remove any directory components
        filename = os.path.basename(filename)
        
        # Remove any non-alphanumeric characters except dots, dashes, and underscores
        filename = re.sub(r'[^\w\s.-]', '', filename)
        
        # Replace spaces with underscores
        filename = filename.replace(' ', '_')
        
        # Limit length
        name, ext = os.path.splitext(filename)
        if len(name) > 100:
            name = name[:100]
        
        return name + ext
    
    @staticmethod
    def scan_file_for_viruses(file_path):
        """
        Scan file for viruses using ClamAV
        
        This method attempts to use ClamAV for virus scanning. If ClamAV is not
        available, it logs a warning and allows the file (fail-open approach).
        
        Installation:
            Ubuntu/Debian: sudo apt-get install clamav clamav-daemon
            macOS: brew install clamav
            Python: pip install pyclamd
        
        Configuration:
            1. Start ClamAV daemon: sudo systemctl start clamav-daemon
            2. Update virus definitions: sudo freshclam
        
        Args:
            file_path (str): Full path to the file to scan
        
        Returns:
            tuple: (is_safe: bool, message: str)
                - (True, "Clean") if file is safe
                - (False, "Virus detected: <name>") if virus found
                - (True, "Scanning not available") if ClamAV not configured
        """
        try:
            # Try to import pyclamd
            import pyclamd
            
            # Try to connect to ClamAV daemon
            try:
                # Try Unix socket first (Linux/macOS)
                cd = pyclamd.ClamdUnixSocket()
                if not cd.ping():
                    raise ConnectionError("ClamAV daemon not responding")
            except Exception:
                try:
                    # Try network socket (Windows or remote)
                    cd = pyclamd.ClamdNetworkSocket()
                    if not cd.ping():
                        raise ConnectionError("ClamAV daemon not responding")
                except Exception as e:
                    logger.warning(f"ClamAV not available: {str(e)}")
                    return (True, "Virus scanning not available - file allowed")
            
            # Scan the file
            scan_result = cd.scan_file(file_path)
            
            if scan_result is None:
                # File is clean
                logger.info(f"File scanned clean: {file_path}")
                return (True, "Clean")
            else:
                # Virus detected
                virus_name = scan_result[file_path][1] if file_path in scan_result else "Unknown"
                logger.error(f"VIRUS DETECTED in {file_path}: {virus_name}")
                return (False, f"Virus detected: {virus_name}")
        
        except ImportError:
            # pyclamd not installed
            logger.warning(
                "pyclamd not installed - virus scanning disabled. "
                "Install with: pip install pyclamd"
            )
            return (True, "Virus scanning not configured - file allowed")
        
        except Exception as e:
            # Unexpected error - fail open (allow file) but log the error
            logger.error(f"Error during virus scan: {str(e)}")
            return (True, f"Virus scanning error - file allowed: {str(e)}")
    
    @staticmethod
    def validate_image(file):
        """Validate that file is actually an image"""
        try:
            from PIL import Image
            img = Image.open(file)
            img.verify()
            file.seek(0)  # Reset file pointer
            return True
        except Exception as e:
            logger.error(f"Image validation failed: {str(e)}")
            return False


# ============================================================================
# IP WHITELISTING (OPTIONAL)
# ============================================================================

class IPWhitelist:
    """IP whitelisting for admin access"""
    
    @staticmethod
    def is_ip_whitelisted(ip_address):
        """Check if IP is whitelisted for admin access"""
        from models import SystemSettings
        
        try:
            # Get whitelist from system settings
            setting = SystemSettings.query.filter_by(setting_key='admin_ip_whitelist').first()
            if not setting or not setting.get_value():
                # If no whitelist configured, allow all
                return True
            
            whitelist = setting.get_value()
            if isinstance(whitelist, str):
                whitelist = [ip.strip() for ip in whitelist.split(',')]
            
            # Check if IP is in whitelist
            return ip_address in whitelist
        except Exception as e:
            logger.error(f"Error checking IP whitelist: {str(e)}")
            # Fail open - allow access if check fails
            return True
    
    @staticmethod
    def check_admin_ip(f):
        """Decorator to check if admin IP is whitelisted"""
        @wraps(f)
        def decorated_function(*args, **kwargs):
            from flask import abort, flash, redirect, url_for
            
            if current_user.role == 'admin':
                if not IPWhitelist.is_ip_whitelisted(request.remote_addr):
                    logger.warning(
                        f"Admin access denied from non-whitelisted IP: {request.remote_addr} "
                        f"for user {current_user.id}"
                    )
                    flash('Access denied from this IP address.', 'danger')
                    return redirect(url_for('index'))
            
            return f(*args, **kwargs)
        return decorated_function


# ============================================================================
# RATE LIMITING ENHANCEMENTS
# ============================================================================

def get_rate_limit_key():
    """Get rate limit key based on user or IP"""
    if current_user.is_authenticated:
        return f"user_{current_user.id}"
    return f"ip_{request.remote_addr}"


# ============================================================================
# AUDIT LOG VIEWER
# ============================================================================

def get_admin_action_logs(page=1, per_page=50, filters=None):
    """
    Get admin action logs with filtering
    
    Args:
        page: Page number
        per_page: Items per page
        filters: Dict with optional keys: admin_id, action_type, target_type, date_from, date_to
    
    Returns:
        Paginated query result
    """
    from models import AdminActionLog
    
    query = AdminActionLog.query
    
    if filters:
        if filters.get('admin_id'):
            query = query.filter_by(admin_id=filters['admin_id'])
        
        if filters.get('action_type'):
            query = query.filter_by(action_type=filters['action_type'])
        
        if filters.get('target_type'):
            query = query.filter_by(target_type=filters['target_type'])
        
        if filters.get('date_from'):
            query = query.filter(AdminActionLog.created_at >= filters['date_from'])
        
        if filters.get('date_to'):
            query = query.filter(AdminActionLog.created_at <= filters['date_to'])
    
    return query.order_by(AdminActionLog.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
