from functools import wraps
from flask import request, redirect, url_for, flash, current_app, g
from flask_login import current_user
from security_utils import is_public_route, role_redirect
from role_hierarchy import is_admin, is_farmer_or_manager, is_buyer_or_manager
from security_enhancements import add_security_headers
import logging
from logging_config import init_request_id, get_request_id

logger = logging.getLogger('security')

def init_security_middleware(app):
    """Initialize security middleware with role hierarchy support"""
    
    # Initialize request ID for all requests
    @app.before_request
    def setup_request_id():
        """Generate and store request ID for tracing"""
        init_request_id()
        logger.debug(f"Request ID initialized: {get_request_id()}")
    
    # Add security headers and request ID to all responses
    @app.after_request
    def apply_security_headers(response):
        response = add_security_headers(response)
        # Add request ID to response headers for client-side tracing
        request_id = get_request_id()
        if request_id:
            response.headers['X-Request-ID'] = request_id
        return response
    
    @app.before_request
    def check_route_access():
        # Skip for static files, public routes, and API routes
        # API routes use their own authentication via @api_token_required decorator
        if (request.path.startswith('/static/') or 
            request.path.startswith('/api/') or 
            is_public_route()):
            return None
            
        # All other routes require authentication
        if not current_user.is_authenticated:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('login', next=request.path))
        
        # Check if user account is active
        if not current_user.is_active:
            logger.warning(f'Deactivated user {current_user.id} attempted to access {request.path}')
            flash('Your account has been deactivated. Please contact support.', 'danger')
            return redirect(url_for('index'))
            
        # Check role-specific routes using role hierarchy
        path = request.path.lower()
        
        # Admin routes check
        if path.startswith('/admin/'):
            if not is_admin(current_user):
                logger.warning(f'Non-admin user {current_user.id} attempted to access admin route: {path}')
                flash('Access denied. Admin privileges required.', 'danger')
                return role_redirect()
            return None
            
        # Farmer routes check - includes farmer managers and crop managers
        if path.startswith('/farmer/'):
            if not is_farmer_or_manager(current_user):
                logger.warning(f'User {current_user.id} (role: {current_user.role}) attempted to access farmer route: {path}')
                flash('Access denied. Farmer privileges required.', 'danger')
                return role_redirect()
            return None
            
        # Buyer routes check - includes buyer managers
        if path.startswith('/buyer/'):
            if not is_buyer_or_manager(current_user):
                logger.warning(f'User {current_user.id} (role: {current_user.role}) attempted to access buyer route: {path}')
                flash('Access denied. Buyer privileges required.', 'danger')
                return role_redirect()
            return None
            
        # Crop management routes - farmers, farmer managers, and crop managers
        if path.startswith('/crops/'):
            if not is_farmer_or_manager(current_user):
                logger.warning(f'User {current_user.id} (role: {current_user.role}) attempted to access crop route: {path}')
                flash('Access denied. Crop management privileges required.', 'danger')
                return role_redirect()
            return None
            
        return None
