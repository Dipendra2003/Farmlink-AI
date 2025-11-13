"""
FarmLink AI - Role Hierarchy System
Centralized role management and permission checking
"""

from functools import wraps
from flask import flash, redirect, url_for, request, abort
from flask_login import current_user
import logging

logger = logging.getLogger('security')

# =============================================================================
# ROLE HIERARCHY DEFINITION
# =============================================================================

ROLE_HIERARCHY = {
    'admin': {
        'level': 100,
        'inherits': [],
        'permissions': ['*'],  # All permissions
        'description': 'System administrator with full access'
    },
    'manager_farmer': {
        'level': 50,
        'inherits': ['farmer'],
        'permissions': ['manage_farmers', 'approve_crops', 'view_farmer_analytics'],
        'description': 'Manager with farmer privileges plus management capabilities'
    },
    'manager_buyer': {
        'level': 50,
        'inherits': ['buyer'],
        'permissions': ['manage_buyers', 'review_orders', 'view_buyer_analytics'],
        'description': 'Manager with buyer privileges plus management capabilities'
    },
    'manager_crop': {
        'level': 50,
        'inherits': ['farmer'],
        'permissions': ['manage_all_crops', 'approve_crops', 'manage_categories'],
        'description': 'Manager with crop management privileges'
    },
    'farmer': {
        'level': 10,
        'inherits': [],
        'permissions': ['add_crop', 'edit_own_crop', 'delete_own_crop', 'view_orders', 'manage_own_profile'],
        'description': 'Farmer with crop listing and order management'
    },
    'buyer': {
        'level': 10,
        'inherits': [],
        'permissions': ['place_order', 'view_marketplace', 'rate_products', 'manage_own_profile'],
        'description': 'Buyer with purchasing capabilities'
    }
}

# =============================================================================
# ROLE CHECKING FUNCTIONS
# =============================================================================

def has_role(user, *roles):
    """
    Check if user has any of the specified roles or inherits from them
    
    Args:
        user: User object
        *roles: Variable number of role names to check
        
    Returns:
        bool: True if user has any of the roles or inherits from them
    """
    if not user or not user.is_authenticated:
        return False
    
    user_role = user.role
    
    # Admin has all roles
    if user_role == 'admin':
        return True
    
    # Check direct role match
    if user_role in roles:
        return True
    
    # Check inherited roles
    for role in roles:
        if user_role in ROLE_HIERARCHY:
            inherited_roles = ROLE_HIERARCHY[user_role].get('inherits', [])
            if role in inherited_roles:
                return True
    
    return False


def is_farmer_or_manager(user):
    """Check if user is a farmer or has farmer management privileges"""
    return has_role(user, 'farmer', 'manager_farmer', 'manager_crop', 'admin')


def is_buyer_or_manager(user):
    """Check if user is a buyer or has buyer management privileges"""
    return has_role(user, 'buyer', 'manager_buyer', 'admin')


def is_manager(user):
    """Check if user has any manager role"""
    return has_role(user, 'manager_farmer', 'manager_buyer', 'manager_crop', 'admin')


def is_admin(user):
    """Check if user is an admin"""
    return user and user.is_authenticated and user.role == 'admin'


def has_permission(user, permission):
    """
    Check if user has a specific permission
    
    Args:
        user: User object
        permission: Permission string to check
        
    Returns:
        bool: True if user has the permission
    """
    if not user or not user.is_authenticated:
        return False
    
    user_role = user.role
    
    if user_role not in ROLE_HIERARCHY:
        return False
    
    role_info = ROLE_HIERARCHY[user_role]
    
    # Admin has all permissions
    if '*' in role_info['permissions']:
        return True
    
    # Check direct permission
    if permission in role_info['permissions']:
        return True
    
    # Check inherited permissions
    for inherited_role in role_info.get('inherits', []):
        if inherited_role in ROLE_HIERARCHY:
            inherited_permissions = ROLE_HIERARCHY[inherited_role]['permissions']
            if permission in inherited_permissions:
                return True
    
    return False


def get_role_level(role):
    """Get the hierarchy level of a role"""
    if role in ROLE_HIERARCHY:
        return ROLE_HIERARCHY[role]['level']
    return 0


def can_manage_user(manager, target_user):
    """
    Check if manager can manage target user
    
    Args:
        manager: User object of the manager
        target_user: User object to be managed
        
    Returns:
        bool: True if manager can manage target user
    """
    if not manager or not target_user:
        return False
    
    # Admin can manage everyone
    if manager.role == 'admin':
        return True
    
    # Manager level must be higher than target
    manager_level = get_role_level(manager.role)
    target_level = get_role_level(target_user.role)
    
    if manager_level <= target_level:
        return False
    
    # Check specific manager permissions
    if manager.role == 'manager_farmer' and target_user.role == 'farmer':
        return True
    if manager.role == 'manager_buyer' and target_user.role == 'buyer':
        return True
    if manager.role == 'manager_crop' and target_user.role in ['farmer', 'manager_farmer']:
        return True
    
    return False


# =============================================================================
# ENHANCED DECORATORS WITH ROLE HIERARCHY
# =============================================================================

def role_required(*roles):
    """
    Enhanced role-based access control decorator with hierarchy support
    
    Usage:
        @role_required('farmer', 'manager_farmer')
        def farmer_route():
            ...
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                logger.warning(f'Unauthenticated access attempt to {request.endpoint} from IP: {request.remote_addr}')
                flash('Please log in to access this page.', 'warning')
                return redirect(url_for('login', next=request.url))
            
            if not current_user.is_active:
                logger.warning(f'Deactivated user {current_user.id} attempted access to {request.endpoint}')
                flash('Your account has been deactivated. Please contact support.', 'danger')
                return redirect(url_for('index'))
            
            if not has_role(current_user, *roles):
                logger.warning(
                    f'Unauthorized access attempt by user {current_user.id} '
                    f'(role: {current_user.role}) to {request.endpoint} '
                    f'(requires: {roles})'
                )
                flash('Access denied. You do not have permission to access this page.', 'danger')
                return redirect(url_for('index'))
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def admin_required(f):
    """Admin-only access decorator"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            logger.warning(f'Unauthenticated admin access attempt from IP: {request.remote_addr}')
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('login', next=request.url))
        
        if not current_user.is_active:
            logger.warning(f'Deactivated user {current_user.id} attempted admin access')
            flash('Your account has been deactivated.', 'danger')
            return redirect(url_for('index'))
        
        if not is_admin(current_user):
            logger.warning(f'Unauthorized admin access attempt by user {current_user.id} (role: {current_user.role})')
            flash('Access denied. Admin privileges required.', 'danger')
            return redirect(url_for('index'))
        
        return f(*args, **kwargs)
    return decorated_function


def verified_required(f):
    """Email verification required decorator"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('login', next=request.url))
        
        if not current_user.is_active:
            flash('Your account has been deactivated. Please contact support.', 'danger')
            return redirect(url_for('index'))
        
        # Admins bypass verification check
        if current_user.role != 'admin' and not current_user.email_verified:
            logger.warning(f'Unverified user {current_user.id} attempted access to {request.endpoint}')
            flash('Please verify your email address to access this feature.', 'warning')
            return redirect(url_for('verification_status'))
        
        return f(*args, **kwargs)
    return decorated_function


def farmer_required(f):
    """Farmer or farmer manager access decorator"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            logger.warning(f'Unauthenticated farmer access attempt from IP: {request.remote_addr}')
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('login', next=request.url))
        
        if not current_user.is_active:
            logger.warning(f'Deactivated user {current_user.id} attempted farmer access')
            flash('Your account has been deactivated. Please contact support.', 'danger')
            return redirect(url_for('index'))
        
        # Check email verification (admins bypass)
        if current_user.role != 'admin' and not current_user.email_verified:
            logger.warning(f'Unverified farmer {current_user.id} attempted access')
            flash('Please verify your email address before accessing farmer features.', 'warning')
            return redirect(url_for('verification_status'))
        
        if not is_farmer_or_manager(current_user):
            logger.warning(f'Unauthorized farmer access attempt by user {current_user.id} (role: {current_user.role})')
            flash('Access denied. This page is for farmers only.', 'danger')
            return redirect(url_for('index'))
        
        return f(*args, **kwargs)
    return decorated_function


def buyer_required(f):
    """Buyer or buyer manager access decorator"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            logger.warning(f'Unauthenticated buyer access attempt from IP: {request.remote_addr}')
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('login', next=request.url))
        
        if not current_user.is_active:
            logger.warning(f'Deactivated user {current_user.id} attempted buyer access')
            flash('Your account has been deactivated. Please contact support.', 'danger')
            return redirect(url_for('index'))
        
        # Check email verification (admins bypass)
        if current_user.role != 'admin' and not current_user.email_verified:
            logger.warning(f'Unverified buyer {current_user.id} attempted access')
            flash('Please verify your email address before accessing buyer features.', 'warning')
            return redirect(url_for('verification_status'))
        
        if not is_buyer_or_manager(current_user):
            logger.warning(f'Unauthorized buyer access attempt by user {current_user.id} (role: {current_user.role})')
            flash('Access denied. This page is for buyers only.', 'danger')
            return redirect(url_for('index'))
        
        return f(*args, **kwargs)
    return decorated_function


def manager_required(f):
    """Manager-only access decorator"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('login', next=request.url))
        
        if not current_user.is_active:
            flash('Your account has been deactivated. Please contact support.', 'danger')
            return redirect(url_for('index'))
        
        if not is_manager(current_user):
            logger.warning(f'Unauthorized manager access attempt by user {current_user.id} (role: {current_user.role})')
            flash('Access denied. Manager privileges required.', 'danger')
            return redirect(url_for('index'))
        
        return f(*args, **kwargs)
    return decorated_function


def permission_required(permission):
    """
    Permission-based access control decorator
    
    Usage:
        @permission_required('add_crop')
        def add_crop_route():
            ...
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                flash('Please log in to access this page.', 'warning')
                return redirect(url_for('login', next=request.url))
            
            if not current_user.is_active:
                flash('Your account has been deactivated. Please contact support.', 'danger')
                return redirect(url_for('index'))
            
            if not has_permission(current_user, permission):
                logger.warning(
                    f'User {current_user.id} (role: {current_user.role}) '
                    f'lacks permission: {permission}'
                )
                flash('Access denied. You do not have the required permission.', 'danger')
                return redirect(url_for('index'))
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator


# =============================================================================
# RESOURCE OWNERSHIP VERIFICATION
# =============================================================================

def verify_resource_ownership(resource_owner_id, allow_managers=False):
    """
    Verify that current user owns a resource or has permission to access it
    
    Args:
        resource_owner_id: ID of the resource owner
        allow_managers: Whether to allow managers to access the resource
        
    Returns:
        bool: True if user has access
    """
    if not current_user.is_authenticated or not current_user.is_active:
        return False
    
    # Admin always has access
    if is_admin(current_user):
        return True
    
    # Owner has access
    if current_user.id == int(resource_owner_id):
        return True
    
    # Managers may have access
    if allow_managers and is_manager(current_user):
        return True
    
    return False


def get_role_display_name(role):
    """Get human-readable role name"""
    role_names = {
        'admin': 'Administrator',
        'farmer': 'Farmer',
        'buyer': 'Buyer',
        'manager_farmer': 'Farmer Manager',
        'manager_buyer': 'Buyer Manager',
        'manager_crop': 'Crop Manager'
    }
    return role_names.get(role, role.title())


def get_all_roles():
    """Get list of all available roles"""
    return list(ROLE_HIERARCHY.keys())


def get_manageable_roles(manager_role):
    """Get list of roles that a manager can assign"""
    if manager_role == 'admin':
        return get_all_roles()
    elif manager_role == 'manager_farmer':
        return ['farmer']
    elif manager_role == 'manager_buyer':
        return ['buyer']
    elif manager_role == 'manager_crop':
        return ['farmer']
    return []


def kyc_required(f):
    """
    KYC verification required decorator for seller actions
    
    Ensures that sellers (farmers/manager_farmers) have completed and verified KYC
    before they can access certain features like listing crops or receiving payments.
    
    Usage:
        @kyc_required
        def add_crop():
            ...
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            logger.warning(f'Unauthenticated KYC-protected access attempt from IP: {request.remote_addr}')
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('login', next=request.url))
        
        if not current_user.is_active:
            logger.warning(f'Deactivated user {current_user.id} attempted KYC-protected access')
            flash('Your account has been deactivated. Please contact support.', 'danger')
            return redirect(url_for('index'))
        
        # Only check KYC for sellers (farmers and manager_farmers)
        if current_user.role in ['farmer', 'manager_farmer']:
            # Admins bypass KYC check
            if current_user.role != 'admin':
                # Check KYC verification status using the User model property
                if not current_user.is_kyc_verified:
                    # Import here to avoid circular dependency
                    from kyc_service import KYCService
                    kyc_record = KYCService.get_kyc_status(current_user.id)
                    
                    if not kyc_record:
                        # No KYC submission yet
                        logger.warning(f'User {current_user.id} attempted KYC-protected action without KYC submission')
                        flash('Please complete KYC verification to start selling. Identity verification is required for all sellers.', 'warning')
                        return redirect(url_for('seller_kyc'))
                    elif kyc_record.status == 'pending':
                        # KYC pending review
                        logger.info(f'User {current_user.id} attempted KYC-protected action with pending KYC')
                        flash('Your KYC is under review. You will be notified once verified. Please wait for approval before listing products.', 'info')
                        return redirect(url_for('kyc_status'))
                    elif kyc_record.status == 'rejected':
                        # KYC rejected
                        logger.warning(f'User {current_user.id} attempted KYC-protected action with rejected KYC')
                        flash(f'Your KYC was rejected: {kyc_record.rejection_reason}. Please resubmit with correct documents to start selling.', 'danger')
                        return redirect(url_for('kyc_resubmit'))
                    else:
                        # Unknown status
                        logger.error(f'User {current_user.id} has unknown KYC status: {kyc_record.status}')
                        flash('KYC verification status unknown. Please contact support.', 'danger')
                        return redirect(url_for('index'))
        
        return f(*args, **kwargs)
    return decorated_function
