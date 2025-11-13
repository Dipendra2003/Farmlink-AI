"""
FarmLink AI - Error Handlers and Validation Module
Centralized error handling and validation for the order system
"""

import logging
from typing import Dict, Any, Optional, Tuple
from functools import wraps
from flask import flash, redirect, url_for, jsonify, request
from flask_login import current_user

logger = logging.getLogger(__name__)


class OrderSystemError(Exception):
    """Base exception for order system errors"""
    def __init__(self, message: str, error_code: str = None, details: Dict = None):
        self.message = message
        self.error_code = error_code or 'SYSTEM_ERROR'
        self.details = details or {}
        super().__init__(self.message)


class CartError(OrderSystemError):
    """Exception for cart-related errors"""
    pass


class OrderError(OrderSystemError):
    """Exception for order-related errors"""
    pass


class PaymentError(OrderSystemError):
    """Exception for payment-related errors"""
    pass


class InventoryError(OrderSystemError):
    """Exception for inventory-related errors"""
    pass


class ValidationError(OrderSystemError):
    """Exception for validation errors"""
    pass


class ErrorHandler:
    """Centralized error handling for the order system"""
    
    # Default language for error messages
    DEFAULT_LANGUAGE = 'en'
    
    # Error message templates (English)
    ERROR_MESSAGES = {
        # Cart errors
        'CART_NOT_FOUND': 'Shopping cart not found. Please try again.',
        'CART_EMPTY': 'Your cart is empty. Please add items before proceeding.',
        'CART_ITEM_NOT_FOUND': 'Cart item not found.',
        'CART_ITEM_UNAVAILABLE': 'One or more items in your cart are no longer available.',
        'CART_ITEM_DUPLICATE': 'Item already exists in cart. Please refresh and try again.',
        'CART_QUANTITY_INVALID': 'Please enter a valid quantity greater than zero.',
        'CART_QUANTITY_EXCEEDS_STOCK': 'Requested quantity exceeds available stock.',
        'CART_OWN_CROP': 'You cannot add your own crops to cart.',
        'CART_CREATION_FAILED': 'Failed to create shopping cart. Please try again.',
        
        # Order errors
        'ORDER_NOT_FOUND': 'Order not found.',
        'ORDER_INVALID_STATUS': 'Invalid order status.',
        'ORDER_INVALID_TRANSITION': 'Cannot change order status from {old_status} to {new_status}.',
        'ORDER_ALREADY_SHIPPED': 'Cannot cancel order that has already been shipped.',
        'ORDER_ALREADY_DELIVERED': 'Cannot modify order that has been delivered.',
        'ORDER_ALREADY_CANCELLED': 'Order has already been cancelled.',
        'ORDER_UNAUTHORIZED': 'You are not authorized to perform this action.',
        'ORDER_CREATION_FAILED': 'Failed to create order. Please try again.',
        'ORDER_UPDATE_FAILED': 'Failed to update order. Please try again.',
        'ORDER_CANCELLATION_FAILED': 'Failed to cancel order. Please try again.',
        
        # Payment errors
        'PAYMENT_INIT_FAILED': 'Failed to initialize payment. Please try again.',
        'PAYMENT_VERIFICATION_FAILED': 'Payment verification failed. Please contact support.',
        'PAYMENT_ALREADY_COMPLETED': 'Payment has already been completed.',
        'PAYMENT_REFUND_FAILED': 'Failed to process refund. Please contact support.',
        'PAYMENT_NOT_FOUND': 'Payment record not found.',
        'PAYMENT_FAILED': 'Payment processing failed. Please try again.',
        'PAYMENT_AMOUNT_INVALID': 'Invalid payment amount.',
        
        # Inventory errors
        'INVENTORY_INSUFFICIENT': 'Insufficient stock available. Only {available} {unit} remaining.',
        'INVENTORY_CONFLICT': 'Inventory conflict detected. Please try again.',
        'INVENTORY_UPDATE_FAILED': 'Failed to update inventory. Please try again.',
        'INVENTORY_REDUCTION_FAILED': 'Failed to reduce inventory. Please try again.',
        'INVENTORY_RESTORATION_FAILED': 'Failed to restore inventory. Please try again.',
        
        # Crop errors
        'CROP_NOT_FOUND': 'Product not found.',
        'CROP_NOT_APPROVED': 'This product is not approved for sale.',
        'CROP_NOT_AVAILABLE': 'This product is no longer available.',
        'CROP_SOLD_OUT': 'This product is sold out.',
        
        # Validation errors
        'VALIDATION_FAILED': 'Validation failed. Please check your input.',
        'INVALID_QUANTITY': 'Please enter a valid quantity.',
        'INVALID_ADDRESS': 'Please provide a valid delivery address.',
        'INVALID_USER': 'User not found or invalid.',
        'INVALID_PERMISSION': 'You do not have permission to perform this action.',
        'INVALID_REFERENCE': 'Invalid reference. Please try again.',
        'MISSING_FIELD': 'Required field is missing: {field}.',
        'INVALID_STATUS': 'Invalid status value.',
        
        # User errors
        'USER_NOT_FOUND': 'User not found.',
        'USER_UNAUTHORIZED': 'You are not authorized to perform this action.',
        
        # Generic errors
        'SYSTEM_ERROR': 'An unexpected error occurred. Please try again later.',
        'DATABASE_ERROR': 'Database error occurred. Please try again.',
        'NETWORK_ERROR': 'Network error occurred. Please check your connection.',
    }
    
    @staticmethod
    def get_error_message(error_code: str, language: str = None, **kwargs) -> str:
        """
        Get formatted error message for error code with internationalization support
        
        Args:
            error_code: Error code to look up
            language: Language code (e.g., 'en', 'hi', 'es') - defaults to DEFAULT_LANGUAGE
            **kwargs: Format parameters for message template
            
        Returns:
            Formatted error message
        """
        # Use default language if not specified
        if language is None:
            language = ErrorHandler.DEFAULT_LANGUAGE
        
        # For now, only English is supported. Future: add language-specific message dictionaries
        # ERROR_MESSAGES_HI = {...}  # Hindi translations
        # ERROR_MESSAGES_ES = {...}  # Spanish translations
        
        template = ErrorHandler.ERROR_MESSAGES.get(error_code, ErrorHandler.ERROR_MESSAGES['SYSTEM_ERROR'])
        try:
            return template.format(**kwargs)
        except KeyError as e:
            logger.warning(f"Missing format parameter for error code {error_code}: {str(e)}")
            return template
        except Exception as e:
            logger.error(f"Error formatting message for code {error_code}: {str(e)}")
            return template
    
    @staticmethod
    def handle_service_error(result: Dict[str, Any], default_error: str = None) -> Tuple[bool, Optional[str]]:
        """
        Handle service layer error results
        
        Args:
            result: Service method result dictionary
            default_error: Default error message if none provided
            
        Returns:
            Tuple of (success, error_message)
        """
        if result.get('success'):
            return True, None
        
        error_message = result.get('error', default_error or 'An error occurred')
        error_code = result.get('error_code')
        
        if error_code:
            error_message = ErrorHandler.get_error_message(error_code, **result.get('details', {}))
        
        logger.error(f"Service error: {error_message} (code: {error_code})")
        
        return False, error_message
    
    @staticmethod
    def handle_route_error(result: Dict[str, Any], success_url: str = None, 
                          error_url: str = None, is_ajax: bool = False):
        """
        Handle errors in route handlers with appropriate response
        
        Args:
            result: Service method result dictionary
            success_url: URL to redirect on success
            error_url: URL to redirect on error
            is_ajax: Whether this is an AJAX request
            
        Returns:
            Flask response (redirect or JSON)
        """
        success, error_message = ErrorHandler.handle_service_error(result)
        
        if is_ajax:
            if success:
                return jsonify({
                    'success': True,
                    'message': result.get('message', 'Operation successful'),
                    'data': result.get('data', {})
                })
            else:
                return jsonify({
                    'success': False,
                    'error': error_message
                }), 400
        else:
            if success:
                if result.get('message'):
                    flash(result['message'], 'success')
                if success_url:
                    return redirect(url_for(success_url))
            else:
                flash(error_message, 'danger')
                if error_url:
                    return redirect(url_for(error_url))
        
        return None


class Validator:
    """Input validation utilities"""
    
    @staticmethod
    def validate_quantity(quantity: Any, available: float = None, unit: str = '') -> Tuple[bool, Optional[str]]:
        """
        Validate quantity input
        
        Args:
            quantity: Quantity to validate
            available: Available stock (optional)
            unit: Unit of measurement (optional)
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        # Check if quantity is provided
        if quantity is None:
            logger.warning(f"Quantity validation failed: quantity is None")
            return False, ErrorHandler.get_error_message('INVALID_QUANTITY')
        
        # Try to convert to float
        try:
            qty = float(quantity)
        except (ValueError, TypeError) as e:
            logger.warning(f"Quantity validation failed: invalid format - {quantity}, error: {str(e)}")
            return False, ErrorHandler.get_error_message('INVALID_QUANTITY')
        
        # Check if positive
        if qty <= 0:
            logger.warning(f"Quantity validation failed: non-positive value - {qty}")
            return False, ErrorHandler.get_error_message('CART_QUANTITY_INVALID')
        
        # Check against available stock if provided
        if available is not None and qty > available:
            logger.warning(f"Quantity validation failed: exceeds stock - requested: {qty}, available: {available} {unit}")
            return False, ErrorHandler.get_error_message(
                'INVENTORY_INSUFFICIENT',
                available=available,
                unit=unit
            )
        
        return True, None
    
    @staticmethod
    def validate_order_status_transition(current_status: str, new_status: str) -> Tuple[bool, Optional[str]]:
        """
        Validate order status transition
        
        Args:
            current_status: Current order status
            new_status: Desired new status
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        from order_service import OrderService
        
        if not OrderService.validate_status_transition(current_status, new_status):
            logger.warning(f"Status transition validation failed: {current_status} -> {new_status}")
            return False, ErrorHandler.get_error_message(
                'ORDER_INVALID_TRANSITION',
                old_status=current_status,
                new_status=new_status
            )
        
        return True, None
    
    @staticmethod
    def validate_cancellation_eligibility(order) -> Tuple[bool, Optional[str]]:
        """
        Validate if order can be cancelled
        
        Args:
            order: Order object to validate
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        if order.status == 'delivered':
            logger.warning(f"Cancellation validation failed for order {order.id}: already delivered")
            return False, ErrorHandler.get_error_message('ORDER_ALREADY_DELIVERED')
        
        if order.status == 'cancelled':
            logger.warning(f"Cancellation validation failed for order {order.id}: already cancelled")
            return False, ErrorHandler.get_error_message('ORDER_ALREADY_CANCELLED')
        
        if order.status == 'shipped':
            logger.warning(f"Cancellation validation failed for order {order.id}: already shipped")
            return False, ErrorHandler.get_error_message('ORDER_ALREADY_SHIPPED')
        
        return True, None
    
    @staticmethod
    def validate_user_permission(user, order, action: str) -> Tuple[bool, Optional[str]]:
        """
        Validate user permission for order action
        
        Args:
            user: User object
            order: Order object
            action: Action being performed (cancel, update_status, view, etc.)
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        # Admin can do anything
        if user.role == 'admin':
            return True, None
        
        # Buyer can view and cancel their own orders
        if action in ['view', 'cancel'] and order.buyer_id == user.id:
            return True, None
        
        # Farmer can view and update status of their orders
        if action in ['view', 'update_status'] and order.farmer_id == user.id:
            return True, None
        
        # Otherwise, not authorized
        logger.warning(f"Permission validation failed: user {user.id} attempted {action} on order {order.id}")
        return False, ErrorHandler.get_error_message('ORDER_UNAUTHORIZED')
    
    @staticmethod
    def validate_delivery_address(address: str) -> Tuple[bool, Optional[str]]:
        """
        Validate delivery address
        
        Args:
            address: Delivery address string
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        if not address or not address.strip():
            logger.warning("Delivery address validation failed: empty address")
            return False, ErrorHandler.get_error_message('INVALID_ADDRESS')
        
        if len(address.strip()) < 10:
            logger.warning(f"Delivery address validation failed: too short - {len(address.strip())} characters")
            return False, 'Delivery address must be at least 10 characters long.'
        
        return True, None
    
    @staticmethod
    def validate_crop_availability(crop, quantity: float = None) -> Tuple[bool, Optional[str]]:
        """
        Validate crop availability for purchase
        
        Args:
            crop: Crop object to validate
            quantity: Optional quantity to check against stock
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        if not crop:
            logger.warning("Crop availability validation failed: crop not found")
            return False, ErrorHandler.get_error_message('CROP_NOT_FOUND')
        
        if crop.approval_status != 'approved':
            logger.warning(f"Crop availability validation failed for crop {crop.id}: not approved - status: {crop.approval_status}")
            return False, ErrorHandler.get_error_message('CROP_NOT_APPROVED')
        
        if crop.status != 'available':
            logger.warning(f"Crop availability validation failed for crop {crop.id}: status is {crop.status}")
            if crop.status == 'sold':
                return False, ErrorHandler.get_error_message('CROP_SOLD_OUT')
            else:
                return False, ErrorHandler.get_error_message('CROP_NOT_AVAILABLE')
        
        if crop.quantity <= 0:
            logger.warning(f"Crop availability validation failed for crop {crop.id}: quantity is {crop.quantity}")
            return False, ErrorHandler.get_error_message('CROP_SOLD_OUT')
        
        # If quantity is provided, validate against available stock
        if quantity is not None:
            if quantity > crop.quantity:
                logger.warning(f"Crop availability validation failed for crop {crop.id}: "
                             f"requested {quantity} exceeds available {crop.quantity} {crop.unit}")
                return False, ErrorHandler.get_error_message(
                    'INVENTORY_INSUFFICIENT',
                    available=crop.quantity,
                    unit=crop.unit
                )
        
        return True, None
    
    @staticmethod
    def validate_status_transition(current_status: str, new_status: str) -> Tuple[bool, Optional[str]]:
        """
        Validate order status transition (alias for validate_order_status_transition)
        
        Args:
            current_status: Current order status
            new_status: Desired new status
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        return Validator.validate_order_status_transition(current_status, new_status)


def handle_errors(default_error_url: str = None):
    """
    Decorator for route error handling
    
    Args:
        default_error_url: Default URL to redirect on error
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            try:
                return f(*args, **kwargs)
            except CartError as e:
                logger.error(f"Cart error in {f.__name__}: {str(e)}")
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return jsonify({'success': False, 'error': str(e)}), 400
                flash(str(e), 'danger')
                return redirect(url_for(default_error_url or 'view_cart'))
            except OrderError as e:
                logger.error(f"Order error in {f.__name__}: {str(e)}")
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return jsonify({'success': False, 'error': str(e)}), 400
                flash(str(e), 'danger')
                return redirect(url_for(default_error_url or 'my_orders'))
            except PaymentError as e:
                logger.error(f"Payment error in {f.__name__}: {str(e)}")
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return jsonify({'success': False, 'error': str(e)}), 400
                flash(str(e), 'danger')
                return redirect(url_for(default_error_url or 'view_cart'))
            except InventoryError as e:
                logger.error(f"Inventory error in {f.__name__}: {str(e)}")
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return jsonify({'success': False, 'error': str(e)}), 400
                flash(str(e), 'danger')
                return redirect(url_for(default_error_url or 'marketplace'))
            except ValidationError as e:
                logger.error(f"Validation error in {f.__name__}: {str(e)}")
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return jsonify({'success': False, 'error': str(e)}), 400
                flash(str(e), 'warning')
                return redirect(url_for(default_error_url or 'index'))
            except Exception as e:
                logger.exception(f"Unexpected error in {f.__name__}: {str(e)}")
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return jsonify({'success': False, 'error': 'An unexpected error occurred'}), 500
                flash('An unexpected error occurred. Please try again later.', 'danger')
                return redirect(url_for(default_error_url or 'index'))
        
        return decorated_function
    return decorator
