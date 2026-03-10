"""
FarmLink AI - Order Service Module
Handles cart management, order processing, and inventory operations
"""

import logging
from datetime import datetime
from sqlalchemy.exc import IntegrityError
from models import db, Cart, CartItem, Crop, Order, User, OrderStatusHistory
from typing import Dict, List, Optional, Any
from email_service import EmailService
from logging_config import (
    OperationLogger, 
    log_cart_operation, 
    log_order_operation,
    log_inventory_operation,
    log_error
)

logger = logging.getLogger(__name__)
email_service = EmailService()


def generate_invoice_number(order_id: int) -> str:
    """
    Generate unique invoice number for an order
    Format: INV-YYYYMMDD-XXXXX (e.g., INV-20241111-00123)
    
    Args:
        order_id: Order ID
        
    Returns:
        Formatted invoice number
    """
    date_str = datetime.utcnow().strftime('%Y%m%d')
    invoice_num = f"INV-{date_str}-{order_id:05d}"
    return invoice_num


class CartService:
    """Service class for managing shopping cart operations"""
    
    # Standard error codes for consistent error handling
    ERROR_CODES = {
        'CART_NOT_FOUND': 'CART_NOT_FOUND',
        'CART_CREATION_FAILED': 'CART_CREATION_FAILED',
        'CROP_NOT_FOUND': 'CROP_NOT_FOUND',
        'CROP_NOT_APPROVED': 'CROP_NOT_APPROVED',
        'CROP_NOT_AVAILABLE': 'CROP_NOT_AVAILABLE',
        'QUANTITY_INVALID': 'CART_QUANTITY_INVALID',
        'QUANTITY_EXCEEDS_STOCK': 'CART_QUANTITY_EXCEEDS_STOCK',
        'ITEM_NOT_FOUND': 'CART_ITEM_NOT_FOUND',
        'ITEM_DUPLICATE': 'CART_ITEM_DUPLICATE',
        'INVALID_REFERENCE': 'INVALID_REFERENCE',
        'DATABASE_ERROR': 'DATABASE_ERROR',
        'SYSTEM_ERROR': 'SYSTEM_ERROR',
        'CART_EMPTY': 'CART_EMPTY',
        'USER_NOT_FOUND': 'USER_NOT_FOUND'
    }
    
    @staticmethod
    def _validate_user_exists(user_id: int) -> Dict[str, Any]:
        """
        Validate that user exists
        
        Args:
            user_id: ID of the user to validate
            
        Returns:
            Dictionary with validation result
        """
        try:
            user = User.query.get(user_id)
            if not user:
                return {
                    'valid': False,
                    'error': 'User not found',
                    'error_code': CartService.ERROR_CODES['USER_NOT_FOUND']
                }
            return {'valid': True, 'user': user}
        except Exception as e:
            logger.error(f"Error validating user {user_id}: {str(e)}")
            return {
                'valid': False,
                'error': 'Error validating user',
                'error_code': CartService.ERROR_CODES['SYSTEM_ERROR']
            }
    
    @staticmethod
    def _validate_crop_for_cart(crop_id: int, quantity: float) -> Dict[str, Any]:
        """
        Comprehensive crop validation for cart operations
        
        Args:
            crop_id: ID of the crop to validate
            quantity: Quantity being requested
            
        Returns:
            Dictionary with validation result
        """
        try:
            # Check if crop exists
            crop = Crop.query.get(crop_id)
            if not crop:
                return {
                    'valid': False,
                    'error': 'Crop not found',
                    'error_code': CartService.ERROR_CODES['CROP_NOT_FOUND']
                }
            
            # Check approval status
            if crop.approval_status != 'approved':
                return {
                    'valid': False,
                    'error': 'Crop is not approved for sale',
                    'error_code': CartService.ERROR_CODES['CROP_NOT_APPROVED']
                }
            
            # Check availability status
            if crop.status != 'available':
                return {
                    'valid': False,
                    'error': 'Crop is not available',
                    'error_code': CartService.ERROR_CODES['CROP_NOT_AVAILABLE']
                }
            
            # Validate quantity
            if quantity is None or quantity <= 0:
                return {
                    'valid': False,
                    'error': 'Quantity must be greater than zero',
                    'error_code': CartService.ERROR_CODES['QUANTITY_INVALID']
                }
            
            # Check stock availability
            if quantity > crop.quantity:
                return {
                    'valid': False,
                    'error': f'Requested quantity exceeds available stock ({crop.quantity} {crop.unit} available)',
                    'error_code': CartService.ERROR_CODES['QUANTITY_EXCEEDS_STOCK'],
                    'details': {'available': crop.quantity, 'unit': crop.unit}
                }
            
            return {'valid': True, 'crop': crop}
            
        except Exception as e:
            logger.error(f"Error validating crop {crop_id}: {str(e)}")
            return {
                'valid': False,
                'error': 'Error validating crop',
                'error_code': CartService.ERROR_CODES['SYSTEM_ERROR']
            }
    
    @staticmethod
    def get_or_create_cart(user_id: int) -> Optional[Cart]:
        """
        Get existing cart for user or create a new one
        
        Args:
            user_id: ID of the user
            
        Returns:
            Cart object or None if error occurs
        """
        try:
            # Check if user exists
            user = User.query.get(user_id)
            if not user:
                logger.error(f"User {user_id} not found when getting/creating cart")
                return None
            
            # Try to get existing cart
            cart = Cart.query.filter_by(user_id=user_id).first()
            
            if not cart:
                # Create new cart
                cart = Cart(user_id=user_id)
                db.session.add(cart)
                db.session.commit()
                logger.info(f"Created new cart {cart.id} for user {user_id}")
            else:
                logger.debug(f"Retrieved existing cart {cart.id} for user {user_id} with {len(cart.items)} items")
            
            return cart
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error getting/creating cart for user {user_id}: {str(e)}")
            logger.exception("Detailed traceback for cart creation error:")
            return None
    
    @staticmethod
    def add_item(cart_id: int, crop_id: int, quantity: float) -> Dict[str, Any]:
        """
        Add item to cart with duplicate handling
        If item already exists, update quantity instead
        
        Args:
            cart_id: ID of the cart
            crop_id: ID of the crop to add
            quantity: Quantity to add
            
        Returns:
            Dictionary with success status and message/data
        """
        with OperationLogger(logger, 'cart.add_item', cart_id=cart_id, crop_id=crop_id, quantity=quantity):
            try:
                # Validate cart exists
                cart = Cart.query.get(cart_id)
                if not cart:
                    return {
                        'success': False,
                        'error': 'Cart not found',
                        'error_code': 'CART_NOT_FOUND'
                    }
                
                # Validate crop exists and is available
                crop = Crop.query.get(crop_id)
                if not crop:
                    return {
                        'success': False,
                        'error': 'Crop not found',
                        'error_code': 'CROP_NOT_FOUND'
                    }
                
                # Prevent buyers from adding their own crops (Requirement 1.7)
                if crop.farmer_id == cart.user_id:
                    return {
                        'success': False,
                        'error': 'You cannot add your own crops to cart',
                        'error_code': 'INVALID_REFERENCE'
                    }
                
                # Check if crop is approved and available
                if crop.approval_status != 'approved':
                    return {
                        'success': False,
                        'error': 'Crop is not approved for sale',
                        'error_code': 'CROP_NOT_APPROVED'
                    }
                
                if crop.status != 'available':
                    return {
                        'success': False,
                        'error': 'Crop is not available',
                        'error_code': 'CROP_NOT_AVAILABLE'
                    }
                
                # Validate quantity
                if quantity is None or quantity <= 0:
                    return {
                        'success': False,
                        'error': 'Quantity must be greater than zero',
                        'error_code': 'CART_QUANTITY_INVALID'
                    }
                
                if quantity > crop.quantity:
                    return {
                        'success': False,
                        'error': f'Requested quantity exceeds available stock ({crop.quantity} {crop.unit} available)',
                        'error_code': 'CART_QUANTITY_EXCEEDS_STOCK',
                        'details': {'available': crop.quantity, 'unit': crop.unit}
                    }
                
                # Check if item already exists in cart
                existing_item = CartItem.query.filter_by(
                    cart_id=cart_id,
                    crop_id=crop_id
                ).first()
                
                if existing_item:
                    # Update existing item quantity
                    new_quantity = existing_item.quantity + quantity
                    
                    # Validate new total quantity
                    if new_quantity > crop.quantity:
                        return {
                            'success': False,
                            'error': f'Total quantity would exceed available stock ({crop.quantity} {crop.unit} available)',
                            'error_code': 'CART_QUANTITY_EXCEEDS_STOCK',
                            'details': {'available': crop.quantity, 'unit': crop.unit}
                        }
                    
                    existing_item.quantity = new_quantity
                    existing_item.updated_at = datetime.utcnow()
                    db.session.commit()
                    
                    log_cart_operation(
                        logger, 'update_quantity', 
                        cart_id=cart_id, 
                        crop_id=crop_id,
                        item_id=existing_item.id,
                        old_quantity=existing_item.quantity - quantity,
                        new_quantity=new_quantity
                    )
                    
                    return {
                        'success': True,
                        'message': 'Cart item quantity updated',
                        'item': existing_item,
                        'updated': True
                    }
                else:
                    # Create new cart item
                    cart_item = CartItem(
                        cart_id=cart_id,
                        crop_id=crop_id,
                        quantity=quantity,
                        price_per_unit=crop.price_per_unit
                    )
                    
                    db.session.add(cart_item)
                    cart.updated_at = datetime.utcnow()
                    db.session.commit()
                    
                    log_cart_operation(
                        logger, 'add_item', 
                        cart_id=cart_id, 
                        crop_id=crop_id,
                        item_id=cart_item.id,
                        quantity=quantity,
                        price_per_unit=crop.price_per_unit
                    )
                    
                    return {
                        'success': True,
                        'message': 'Item added to cart',
                        'item': cart_item,
                        'updated': False
                    }
                    
            except IntegrityError as e:
                db.session.rollback()
                log_error(logger, 'DATABASE_ERROR', f"Integrity error adding item to cart: {str(e)}", 
                         cart_id=cart_id, crop_id=crop_id)
                return {
                    'success': False,
                    'error': 'Database integrity error',
                    'error_code': 'DATABASE_ERROR'
                }
            except Exception as e:
                db.session.rollback()
                log_error(logger, 'SYSTEM_ERROR', f"Error adding item to cart {cart_id}: {str(e)}", 
                         cart_id=cart_id, crop_id=crop_id)
                logger.exception("Detailed traceback:")
                
                # Provide more specific error messages based on exception type
                if "unique constraint" in str(e).lower():
                    return {
                        'success': False,
                        'error': 'Item already exists in cart. Please refresh and try again.',
                        'error_code': 'CART_ITEM_DUPLICATE'
                    }
                elif "foreign key" in str(e).lower():
                    return {
                        'success': False,
                        'error': 'Invalid cart or crop reference',
                        'error_code': 'INVALID_REFERENCE'
                    }
                else:
                    return {
                        'success': False,
                        'error': 'An error occurred while adding item to cart',
                        'error_code': 'SYSTEM_ERROR'
                    }

    @staticmethod
    def update_item_quantity(item_id: int, quantity: float) -> Dict[str, Any]:
        """
        Update cart item quantity with validation
        
        Args:
            item_id: ID of the cart item
            quantity: New quantity
            
        Returns:
            Dictionary with success status and message/data
        """
        try:
            # Get cart item
            cart_item = CartItem.query.get(item_id)
            if not cart_item:
                return {
                    'success': False,
                    'error': 'Cart item not found',
                    'error_code': 'CART_ITEM_NOT_FOUND'
                }
            
            # Validate quantity
            if quantity is None or quantity <= 0:
                return {
                    'success': False,
                    'error': 'Quantity must be greater than zero',
                    'error_code': 'CART_QUANTITY_INVALID'
                }
            
            # Check crop availability
            crop = cart_item.crop
            if not crop:
                return {
                    'success': False,
                    'error': 'Associated crop not found',
                    'error_code': 'CROP_NOT_FOUND'
                }
            
            if crop.status != 'available':
                return {
                    'success': False,
                    'error': 'Crop is no longer available',
                    'error_code': 'CROP_NOT_AVAILABLE'
                }
            
            if quantity > crop.quantity:
                return {
                    'success': False,
                    'error': f'Requested quantity exceeds available stock ({crop.quantity} {crop.unit} available)',
                    'error_code': 'CART_QUANTITY_EXCEEDS_STOCK',
                    'details': {'available': crop.quantity, 'unit': crop.unit}
                }
            
            # Update quantity
            old_quantity = cart_item.quantity
            cart_item.quantity = quantity
            cart_item.updated_at = datetime.utcnow()
            cart_item.cart.updated_at = datetime.utcnow()
            db.session.commit()
            
            logger.info(f"Updated cart item {item_id} quantity from {old_quantity} to {quantity}")
            
            return {
                'success': True,
                'message': 'Cart item quantity updated',
                'item': cart_item
            }
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error updating cart item {item_id}: {str(e)}")
            logger.exception("Detailed traceback:")
            return {
                'success': False,
                'error': 'An error occurred while updating cart item',
                'error_code': 'SYSTEM_ERROR'
            }
    
    @staticmethod
    def remove_item(item_id: int, user_id: int = None) -> Dict[str, Any]:
        """
        Remove item from cart
        
        Args:
            item_id: ID of the cart item to remove
            user_id: Optional user ID to verify ownership
            
        Returns:
            Dictionary with success status and message
        """
        try:
            # Get cart item
            cart_item = CartItem.query.get(item_id)
            if not cart_item:
                return {
                    'success': False,
                    'error': 'Cart item not found',
                    'error_code': 'CART_ITEM_NOT_FOUND'
                }
            
            cart = cart_item.cart
            
            # Verify item belongs to user's cart (Requirement 1.6)
            if user_id is not None and cart.user_id != user_id:
                logger.warning(f"User {user_id} attempted to remove item {item_id} from another user's cart")
                return {
                    'success': False,
                    'error': 'Cart item not found',
                    'error_code': 'CART_ITEM_NOT_FOUND'
                }
            
            crop_name = cart_item.crop.name if cart_item.crop else 'Unknown'
            
            # Delete item
            db.session.delete(cart_item)
            cart.updated_at = datetime.utcnow()
            db.session.commit()
            
            logger.info(f"Removed cart item {item_id} ({crop_name}) from cart {cart.id}")
            
            return {
                'success': True,
                'message': f'{crop_name} removed from cart'
            }
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error removing cart item {item_id}: {str(e)}")
            return {
                'success': False,
                'error': 'An error occurred while removing item from cart',
                'error_code': 'SYSTEM_ERROR'
            }
    
    @staticmethod
    def clear_cart(cart_id: int) -> Dict[str, Any]:
        """
        Clear all items from cart
        
        Args:
            cart_id: ID of the cart to clear
            
        Returns:
            Dictionary with success status and message
        """
        try:
            # Get cart
            cart = Cart.query.get(cart_id)
            if not cart:
                return {
                    'success': False,
                    'error': 'Cart not found'
                }
            
            # Count items before deletion
            item_count = len(cart.items)
            
            # Delete all items
            CartItem.query.filter_by(cart_id=cart_id).delete()
            cart.updated_at = datetime.utcnow()
            db.session.commit()
            
            logger.info(f"Cleared {item_count} items from cart {cart_id}")
            
            return {
                'success': True,
                'message': f'Cart cleared ({item_count} items removed)'
            }
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error clearing cart {cart_id}: {str(e)}")
            return {
                'success': False,
                'error': 'An error occurred while clearing cart'
            }
    
    @staticmethod
    def get_cart_total(cart_id: int) -> Dict[str, Any]:
        """
        Calculate cart total and item count
        
        Args:
            cart_id: ID of the cart
            
        Returns:
            Dictionary with total amount, item count, and breakdown
        """
        try:
            # Get cart with items
            cart = Cart.query.get(cart_id)
            if not cart:
                return {
                    'success': False,
                    'error': 'Cart not found'
                }
            
            total_amount = 0.0
            item_count = 0
            items_breakdown = []
            
            for item in cart.items:
                if item.crop and item.is_available:
                    subtotal = item.subtotal
                    total_amount += subtotal
                    item_count += 1
                    
                    items_breakdown.append({
                        'item_id': item.id,
                        'crop_name': item.crop.name,
                        'quantity': item.quantity,
                        'unit': item.crop.unit,
                        'price_per_unit': item.price_per_unit,
                        'subtotal': subtotal
                    })
            
            return {
                'success': True,
                'total_amount': round(total_amount, 2),
                'item_count': item_count,
                'items': items_breakdown
            }
            
        except Exception as e:
            logger.error(f"Error calculating cart total for cart {cart_id}: {str(e)}")
            return {
                'success': False,
                'error': 'An error occurred while calculating cart total'
            }
    
    @staticmethod
    def validate_cart_items(cart_id: int) -> Dict[str, Any]:
        """
        Validate all cart items for checkout
        Check availability, stock levels, and approval status
        
        Args:
            cart_id: ID of the cart to validate
            
        Returns:
            Dictionary with validation results and any issues found
        """
        try:
            # Get cart with items
            cart = Cart.query.get(cart_id)
            if not cart:
                return {
                    'success': False,
                    'error': 'Cart not found',
                    'error_code': 'CART_NOT_FOUND'
                }
            
            if not cart.items:
                return {
                    'success': False,
                    'error': 'Cart is empty',
                    'error_code': 'CART_EMPTY'
                }
            
            valid_items = []
            invalid_items = []
            warnings = []
            
            for item in cart.items:
                issues = []
                
                # Check if crop exists
                if not item.crop:
                    issues.append('Crop no longer exists')
                else:
                    crop = item.crop
                    
                    # Check approval status
                    if crop.approval_status != 'approved':
                        issues.append('Crop is not approved for sale')
                    
                    # Check availability status
                    if crop.status != 'available':
                        issues.append('Crop is no longer available')
                    
                    # Check stock quantity
                    if item.quantity > crop.quantity:
                        issues.append(f'Insufficient stock (only {crop.quantity} {crop.unit} available)')
                    
                    # Check for price changes
                    if item.price_per_unit != crop.price_per_unit:
                        warnings.append({
                            'item_id': item.id,
                            'crop_name': crop.name,
                            'message': f'Price changed from ₹{item.price_per_unit} to ₹{crop.price_per_unit} per {crop.unit}'
                        })
                
                if issues:
                    invalid_items.append({
                        'item_id': item.id,
                        'crop_name': item.crop.name if item.crop else 'Unknown',
                        'issues': issues
                    })
                else:
                    valid_items.append({
                        'item_id': item.id,
                        'crop_id': item.crop_id,
                        'crop_name': item.crop.name,
                        'farmer_id': item.crop.farmer_id,
                        'quantity': item.quantity,
                        'price_per_unit': item.crop.price_per_unit,  # Use current price
                        'subtotal': item.quantity * item.crop.price_per_unit
                    })
            
            # Determine overall validation result
            is_valid = len(invalid_items) == 0 and len(valid_items) > 0
            
            result = {
                'success': True,
                'is_valid': is_valid,
                'valid_items': valid_items,
                'invalid_items': invalid_items,
                'warnings': warnings,
                'total_items': len(cart.items),
                'valid_count': len(valid_items),
                'invalid_count': len(invalid_items)
            }
            
            if is_valid:
                # Calculate total for valid items
                total_amount = sum(item['subtotal'] for item in valid_items)
                result['total_amount'] = round(total_amount, 2)
            
            logger.info(f"Cart {cart_id} validation: {len(valid_items)} valid, {len(invalid_items)} invalid")
            
            return result
            
        except Exception as e:
            logger.error(f"Error validating cart {cart_id}: {str(e)}")
            logger.exception("Detailed traceback:")
            return {
                'success': False,
                'error': 'An error occurred while validating cart',
                'error_code': 'SYSTEM_ERROR'
            }



class OrderService:
    """Service class for managing order operations"""
    
    # Valid status transitions mapping
    VALID_TRANSITIONS = {
        'pending': ['confirmed', 'cancelled'],
        'confirmed': ['processing', 'rejected', 'cancelled'],
        'processing': ['shipped', 'cancelled'],
        'shipped': ['delivered'],
        'delivered': [],  # Terminal state
        'rejected': [],   # Terminal state
        'cancelled': []   # Terminal state
    }
    
    @staticmethod
    def validate_status_transition(current_status: str, new_status: str) -> bool:
        """
        Validate if a status transition is allowed
        
        Args:
            current_status: Current order status
            new_status: Desired new status
            
        Returns:
            True if transition is valid, False otherwise
        """
        if current_status not in OrderService.VALID_TRANSITIONS:
            logger.error(f"Invalid current status: {current_status}")
            return False
        
        allowed_transitions = OrderService.VALID_TRANSITIONS[current_status]
        is_valid = new_status in allowed_transitions
        
        if not is_valid:
            logger.warning(f"Invalid transition from {current_status} to {new_status}")
        
        return is_valid
    
    @staticmethod
    def create_single_order(order_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create a single order (used for direct purchase without cart)
        
        Args:
            order_data: Dictionary containing order details (crop_id, buyer_id, farmer_id, 
                       quantity_requested, price_per_unit, delivery_address, delivery_method, notes)
            
        Returns:
            Dictionary with success status and created order or error message
        """
        try:
            # Validate required fields
            required_fields = ['crop_id', 'buyer_id', 'farmer_id', 'quantity_requested', 
                             'price_per_unit', 'delivery_address']
            for field in required_fields:
                if field not in order_data:
                    return {
                        'success': False,
                        'error': f'Missing required field: {field}',
                        'error_code': 'MISSING_FIELD'
                    }
            
            # Validate delivery address
            delivery_address = order_data.get('delivery_address', '').strip()
            if not delivery_address or len(delivery_address) < 10:
                return {
                    'success': False,
                    'error': 'Delivery address must be at least 10 characters long',
                    'error_code': 'INVALID_ADDRESS'
                }
            
            # Calculate total amount
            total_amount = order_data['quantity_requested'] * order_data['price_per_unit']
            
            # Create order
            order = Order(
                buyer_id=order_data['buyer_id'],
                farmer_id=order_data['farmer_id'],
                crop_id=order_data['crop_id'],
                quantity_requested=order_data['quantity_requested'],
                price_per_unit=order_data['price_per_unit'],
                total_amount=total_amount,
                delivery_address=delivery_address,
                delivery_method=order_data.get('delivery_method', 'standard'),
                notes=order_data.get('notes', ''),
                status='pending',
                payment_status='pending'
            )
            
            db.session.add(order)
            db.session.flush()  # Get order ID without committing
            
            # Create initial status history entry
            status_history = OrderStatusHistory(
                order_id=order.id,
                old_status=None,
                new_status='pending',
                changed_by_id=order_data['buyer_id'],
                notes='Order created via direct purchase'
            )
            
            db.session.add(status_history)
            db.session.commit()
            
            logger.info(f"Created single order {order.id} for buyer {order_data['buyer_id']}, "
                       f"farmer {order_data['farmer_id']}, crop {order_data['crop_id']}")
            
            # Send order placed notification to farmer
            try:
                email_service.send_order_placed_notification(order)
            except Exception as e:
                logger.error(f"Failed to send order placed notification for order {order.id}: {str(e)}")
                # Don't fail the order creation if notification fails
            
            return {
                'success': True,
                'message': 'Order created successfully',
                'order': order
            }
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error creating single order: {str(e)}")
            logger.exception("Detailed traceback:")
            return {
                'success': False,
                'error': 'An error occurred while creating the order',
                'error_code': 'ORDER_CREATION_FAILED'
            }
    
    @staticmethod
    def create_orders_from_cart(cart_id: int, delivery_info: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convert cart items to individual orders grouped by farmer
        
        Args:
            cart_id: ID of the cart to convert
            delivery_info: Dictionary containing delivery_address, delivery_method, notes
            
        Returns:
            Dictionary with success status and created orders or error message
        """
        try:
            # Validate cart
            validation_result = CartService.validate_cart_items(cart_id)
            
            if not validation_result.get('success'):
                return {
                    'success': False,
                    'error': validation_result.get('error', 'Cart validation failed'),
                    'error_code': validation_result.get('error_code', 'VALIDATION_FAILED')
                }
            
            if not validation_result.get('is_valid'):
                return {
                    'success': False,
                    'error': 'Cart contains invalid items',
                    'error_code': 'CART_ITEM_UNAVAILABLE',
                    'invalid_items': validation_result.get('invalid_items', [])
                }
            
            valid_items = validation_result.get('valid_items', [])
            if not valid_items:
                return {
                    'success': False,
                    'error': 'No valid items in cart',
                    'error_code': 'CART_EMPTY'
                }
            
            # Get cart to access user_id
            cart = Cart.query.get(cart_id)
            if not cart:
                return {
                    'success': False,
                    'error': 'Cart not found',
                    'error_code': 'CART_NOT_FOUND'
                }
            
            buyer_id = cart.user_id
            
            # Extract delivery information
            delivery_address = delivery_info.get('delivery_address', '')
            delivery_method = delivery_info.get('delivery_method', 'standard')
            notes = delivery_info.get('notes', '')
            
            # Validate required fields
            if not delivery_address or not delivery_address.strip():
                return {
                    'success': False,
                    'error': 'Delivery address is required',
                    'error_code': 'INVALID_ADDRESS'
                }
            
            if len(delivery_address.strip()) < 10:
                return {
                    'success': False,
                    'error': 'Delivery address must be at least 10 characters long',
                    'error_code': 'INVALID_ADDRESS'
                }
            
            # Create orders for each valid item
            created_orders = []
            
            for item in valid_items:
                try:
                    # Create order
                    order = Order(
                        buyer_id=buyer_id,
                        farmer_id=item['farmer_id'],
                        crop_id=item['crop_id'],
                        quantity_requested=item['quantity'],
                        price_per_unit=item['price_per_unit'],
                        total_amount=item['subtotal'],
                        delivery_address=delivery_address,
                        delivery_method=delivery_method,
                        notes=notes,
                        status='pending',
                        payment_status='pending'
                    )
                    
                    db.session.add(order)
                    db.session.flush()  # Get order ID without committing
                    
                    # Create initial status history entry
                    status_history = OrderStatusHistory(
                        order_id=order.id,
                        old_status=None,
                        new_status='pending',
                        changed_by_id=buyer_id,
                        notes='Order created from cart'
                    )
                    
                    db.session.add(status_history)
                    created_orders.append(order)
                    
                    logger.info(f"Created order {order.id} for buyer {buyer_id}, farmer {item['farmer_id']}, crop {item['crop_id']}")
                    
                except Exception as e:
                    logger.error(f"Error creating order for item {item['crop_id']}: {str(e)}")
                    logger.exception("Detailed traceback:")
                    db.session.rollback()
                    return {
                        'success': False,
                        'error': f"Failed to create order for {item['crop_name']}",
                        'error_code': 'ORDER_CREATION_FAILED'
                    }
            
            # Commit all orders
            db.session.commit()
            
            logger.info(f"Successfully created {len(created_orders)} orders from cart {cart_id}")
            
            # Send order placed notifications to farmers
            for order in created_orders:
                try:
                    email_service.send_order_placed_notification(order)
                except Exception as e:
                    logger.error(f"Failed to send order placed notification for order {order.id}: {str(e)}")
                    # Don't fail the order creation if notification fails
            
            return {
                'success': True,
                'message': f'{len(created_orders)} order(s) created successfully',
                'orders': created_orders,
                'order_count': len(created_orders),
                'total_amount': sum(order.total_amount for order in created_orders)
            }
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error creating orders from cart {cart_id}: {str(e)}")
            logger.exception("Detailed traceback:")
            return {
                'success': False,
                'error': 'An error occurred while creating orders',
                'error_code': 'ORDER_CREATION_FAILED'
            }
    
    @staticmethod
    def update_order_status(order_id: int, new_status: str, user_id: int, notes: str = None, 
                           tracking_number: str = None) -> Dict[str, Any]:
        """
        Update order status with validation and history tracking
        
        Args:
            order_id: ID of the order to update
            new_status: New status to set
            user_id: ID of user making the change
            notes: Optional notes about the status change
            tracking_number: Optional tracking number (for shipped status)
            
        Returns:
            Dictionary with success status and updated order or error message
        """
        try:
            # Get order
            order = Order.query.get(order_id)
            if not order:
                return {
                    'success': False,
                    'error': 'Order not found',
                    'error_code': 'ORDER_NOT_FOUND'
                }
            
            current_status = order.status
            
            # Validate status transition
            if not OrderService.validate_status_transition(current_status, new_status):
                return {
                    'success': False,
                    'error': f'Invalid status transition from {current_status} to {new_status}',
                    'error_code': 'ORDER_INVALID_TRANSITION',
                    'details': {'old_status': current_status, 'new_status': new_status}
                }
            
            # Update order status
            old_status = order.status
            order.status = new_status
            order.updated_at = datetime.utcnow()
            
            # Update timestamp fields based on status
            if new_status == 'shipped':
                order.shipped_at = datetime.utcnow()
                if tracking_number:
                    order.tracking_number = tracking_number
            elif new_status == 'delivered':
                # Check seller KYC status before allowing delivery completion (payment release)
                from kyc_service import KYCService
                if not KYCService.is_seller_verified(order.farmer_id):
                    return {
                        'success': False,
                        'error': 'Payment on hold pending seller KYC verification. Seller must complete KYC before receiving payments.',
                        'error_code': 'ORDER_SELLER_KYC_NOT_VERIFIED',
                        'details': {'farmer_id': order.farmer_id}
                    }
                order.delivered_at = datetime.utcnow()
            elif new_status == 'cancelled':
                order.cancelled_at = datetime.utcnow()
                if notes:
                    order.cancellation_reason = notes
            
            # Create status history entry
            status_history = OrderStatusHistory(
                order_id=order_id,
                old_status=old_status,
                new_status=new_status,
                changed_by_id=user_id,
                notes=notes
            )
            
            db.session.add(status_history)
            db.session.commit()
            
            logger.info(f"Order {order_id} status updated from {old_status} to {new_status} by user {user_id}")
            
            # Send appropriate notification based on new status
            try:
                if new_status == 'shipped':
                    email_service.send_order_shipped_notification(order)
                elif new_status == 'delivered':
                    email_service.send_order_delivered_notification(order)
                else:
                    # Send general status update notification
                    email_service.send_order_status_update_notification(order, old_status)
            except Exception as e:
                logger.error(f"Failed to send status update notification for order {order_id}: {str(e)}")
                # Don't fail the status update if notification fails
            
            return {
                'success': True,
                'message': f'Order status updated to {new_status}',
                'order': order,
                'old_status': old_status,
                'new_status': new_status
            }
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error updating order {order_id} status: {str(e)}")
            logger.exception("Detailed traceback:")
            return {
                'success': False,
                'error': 'An error occurred while updating order status',
                'error_code': 'SYSTEM_ERROR'
            }
    
    @staticmethod
    def cancel_order(order_id: int, user_id: int, reason: str) -> Dict[str, Any]:
        """
        Cancel an order with inventory restoration and refund processing
        
        Args:
            order_id: ID of the order to cancel
            user_id: ID of user cancelling the order
            reason: Reason for cancellation
            
        Returns:
            Dictionary with success status and message
        """
        try:
            # Get order
            order = Order.query.get(order_id)
            if not order:
                return {
                    'success': False,
                    'error': 'Order not found',
                    'error_code': 'ORDER_NOT_FOUND'
                }
            
            # Check if order can be cancelled
            if order.status == 'delivered':
                return {
                    'success': False,
                    'error': 'Cannot cancel order that has been delivered',
                    'error_code': 'ORDER_ALREADY_DELIVERED'
                }
            
            if order.status == 'cancelled':
                return {
                    'success': False,
                    'error': 'Order has already been cancelled',
                    'error_code': 'ORDER_ALREADY_CANCELLED'
                }
            
            # Check if order is already shipped
            if order.status == 'shipped':
                return {
                    'success': False,
                    'error': 'Cannot cancel order that has already been shipped',
                    'error_code': 'ORDER_ALREADY_SHIPPED'
                }
            
            # Check payment status and initiate refund if needed
            refund_initiated = False
            refund_error = None
            
            if order.payment_status == 'paid':
                # For bulk payments, find payment by razorpay_payment_id from order
                from models import Payment
                payment = None
                
                if order.razorpay_payment_id:
                    # Try to find payment by razorpay_payment_id (works for bulk payments)
                    payment = Payment.query.filter_by(razorpay_payment_id=order.razorpay_payment_id).first()
                
                if not payment:
                    # Fallback: Try to find by order_id (works for single payments)
                    payment = Payment.query.filter_by(order_id=order_id).first()
                
                if payment and payment.razorpay_payment_id:
                    # Initiate refund through payment service
                    from payment_service import payment_service
                    refund_result = payment_service.initiate_refund(
                        payment=payment,
                        amount=order.total_amount,
                        reason=reason
                    )
                    
                    if refund_result:
                        refund_initiated = True
                        # Update order payment status
                        order.payment_status = 'refunded'
                        logger.info(f"Refund initiated for order {order_id}, payment {payment.razorpay_payment_id}")
                    else:
                        # Check if payment was marked as refunded in system (test mode)
                        if payment.status == 'refunded':
                            refund_initiated = True
                            order.payment_status = 'refunded'
                            logger.info(f"Order {order_id} marked as refunded (test/development mode)")
                        else:
                            refund_error = "Refund could not be processed automatically. Our team will process it manually within 24 hours."
                            logger.error(f"Failed to initiate refund for order {order_id}")
                        # Continue with cancellation even if refund fails
                else:
                    logger.warning(f"No payment record found for order {order_id} with paid status")
                    # Mark as refunded anyway since we can't process it
                    order.payment_status = 'refunded'
            
            # Restore inventory (regardless of payment status)
            crop = Crop.query.get(order.crop_id)
            if crop:
                crop.quantity += order.quantity_requested
                
                # Update crop status if it was sold
                if crop.status == 'sold' and crop.quantity > 0:
                    crop.status = 'available'
                
                logger.info(f"Restored {order.quantity_requested} {crop.unit} to crop {crop.id}")
            
            # Update order status to cancelled
            old_status = order.status
            order.status = 'cancelled'
            order.cancelled_at = datetime.utcnow()
            order.cancellation_reason = reason
            order.updated_at = datetime.utcnow()
            
            # Create status history entry
            status_history = OrderStatusHistory(
                order_id=order_id,
                old_status=old_status,
                new_status='cancelled',
                changed_by_id=user_id,
                notes=f'Cancellation reason: {reason}' + (f' | Refund initiated' if refund_initiated else '')
            )
            
            db.session.add(status_history)
            db.session.commit()
            
            logger.info(f"Order {order_id} cancelled by user {user_id}. Reason: {reason}")
            
            # Send cancellation notification
            try:
                email_service.send_order_cancelled_notification(order)
            except Exception as e:
                logger.error(f"Failed to send cancellation notification for order {order_id}: {str(e)}")
                # Don't fail the cancellation if notification fails
            
            result = {
                'success': True,
                'message': 'Order cancelled successfully',
                'order': order,
                'inventory_restored': True,
                'refund_initiated': refund_initiated
            }
            
            if refund_error:
                result['refund_error'] = refund_error
            
            return result
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error cancelling order {order_id}: {str(e)}")
            logger.exception("Detailed traceback:")
            return {
                'success': False,
                'error': 'An error occurred while cancelling order',
                'error_code': 'SYSTEM_ERROR'
            }
    
    @staticmethod
    def get_user_orders(user_id: int, role: str, status_filter: str = None, 
                       limit: int = None, offset: int = 0) -> Dict[str, Any]:
        """
        Get orders for a user with role-based filtering
        
        Args:
            user_id: ID of the user
            role: User role (buyer, farmer, admin)
            status_filter: Optional status to filter by
            limit: Optional limit for pagination
            offset: Optional offset for pagination
            
        Returns:
            Dictionary with success status and orders list
        """
        try:
            from sqlalchemy.orm import joinedload
            
            # Build base query based on role with eager loading
            if role == 'admin':
                # Admin sees all orders
                query = Order.query
            elif role == 'farmer':
                # Farmer sees orders where they are the seller
                query = Order.query.filter_by(farmer_id=user_id)
            else:
                # Buyer sees orders where they are the buyer
                query = Order.query.filter_by(buyer_id=user_id)
            
            # Apply eager loading for related objects to reduce N+1 queries
            query = query.options(
                joinedload(Order.crop),
                joinedload(Order.buyer),
                joinedload(Order.farmer_user),
                joinedload(Order.status_history)
            )
            
            # Apply status filter if provided
            if status_filter:
                query = query.filter_by(status=status_filter)
            
            # Order by creation date (newest first)
            query = query.order_by(Order.created_at.desc())
            
            # Get total count before pagination
            total_count = query.count()
            
            # Apply pagination if limit is provided
            if limit:
                query = query.limit(limit).offset(offset)
            
            # Execute query
            orders = query.all()
            
            logger.info(f"Retrieved {len(orders)} orders for user {user_id} (role: {role})")
            
            return {
                'success': True,
                'orders': orders,
                'count': len(orders),
                'total_count': total_count,
                'has_more': (offset + len(orders)) < total_count if limit else False
            }
            
        except Exception as e:
            logger.error(f"Error getting orders for user {user_id}: {str(e)}")
            logger.exception("Detailed traceback:")
            return {
                'success': False,
                'error': 'An error occurred while retrieving orders'
            }
    
    @staticmethod
    def get_order_history(order_id: int) -> Dict[str, Any]:
        """
        Get status history for an order
        
        Args:
            order_id: ID of the order
            
        Returns:
            Dictionary with success status and history list
        """
        try:
            # Verify order exists
            order = Order.query.get(order_id)
            if not order:
                return {
                    'success': False,
                    'error': 'Order not found'
                }
            
            # Get status history ordered by creation date
            history = OrderStatusHistory.query.filter_by(
                order_id=order_id
            ).order_by(OrderStatusHistory.created_at.asc()).all()
            
            # Format history entries
            history_entries = []
            for entry in history:
                history_entries.append({
                    'id': entry.id,
                    'old_status': entry.old_status,
                    'new_status': entry.new_status,
                    'changed_by': entry.changed_by.username if entry.changed_by else 'System',
                    'changed_by_id': entry.changed_by_id,
                    'notes': entry.notes,
                    'created_at': entry.created_at
                })
            
            logger.info(f"Retrieved {len(history_entries)} history entries for order {order_id}")
            
            return {
                'success': True,
                'order_id': order_id,
                'current_status': order.status,
                'history': history_entries,
                'count': len(history_entries)
            }
            
        except Exception as e:
            logger.error(f"Error getting history for order {order_id}: {str(e)}")
            return {
                'success': False,
                'error': 'An error occurred while retrieving order history'
            }



class InventoryService:
    """Service class for managing crop inventory operations"""
    
    @staticmethod
    def check_availability(crop_id: int, quantity: float) -> Dict[str, Any]:
        """
        Check if sufficient inventory is available for a crop
        
        Args:
            crop_id: ID of the crop to check
            quantity: Quantity requested
            
        Returns:
            Dictionary with availability status and details
        """
        try:
            # Get crop
            crop = Crop.query.get(crop_id)
            if not crop:
                return {
                    'success': False,
                    'available': False,
                    'error': 'Crop not found',
                    'error_code': 'CROP_NOT_FOUND'
                }
            
            # Check if crop is approved
            if crop.approval_status != 'approved':
                return {
                    'success': True,
                    'available': False,
                    'reason': 'Crop is not approved for sale',
                    'error_code': 'CROP_NOT_APPROVED',
                    'crop_status': crop.status,
                    'approval_status': crop.approval_status
                }
            
            # Check if crop is available
            if crop.status != 'available':
                return {
                    'success': True,
                    'available': False,
                    'reason': f'Crop status is {crop.status}',
                    'error_code': 'CROP_NOT_AVAILABLE',
                    'crop_status': crop.status,
                    'approval_status': crop.approval_status
                }
            
            # Check quantity
            if quantity is None or quantity <= 0:
                return {
                    'success': False,
                    'available': False,
                    'error': 'Quantity must be greater than zero',
                    'error_code': 'INVALID_QUANTITY'
                }
            
            # Check if sufficient stock is available
            is_available = crop.quantity >= quantity
            
            result = {
                'success': True,
                'available': is_available,
                'crop_id': crop_id,
                'requested_quantity': quantity,
                'available_quantity': crop.quantity,
                'unit': crop.unit,
                'crop_status': crop.status,
                'approval_status': crop.approval_status
            }
            
            if not is_available:
                result['reason'] = f'Insufficient stock. Only {crop.quantity} {crop.unit} available'
                result['error_code'] = 'INVENTORY_INSUFFICIENT'
            
            logger.info(f"Availability check for crop {crop_id}: {is_available} (requested: {quantity}, available: {crop.quantity})")
            
            return result
            
        except Exception as e:
            logger.error(f"Error checking availability for crop {crop_id}: {str(e)}")
            logger.exception("Detailed traceback:")
            return {
                'success': False,
                'available': False,
                'error': 'An error occurred while checking availability',
                'error_code': 'SYSTEM_ERROR'
            }
    
    @staticmethod
    def confirm_inventory_reduction(crop_id: int, quantity: float) -> Dict[str, Any]:
        """
        Confirm inventory reduction after payment confirmation
        Uses database transaction to ensure atomicity
        
        Args:
            crop_id: ID of the crop
            quantity: Quantity to reduce
            
        Returns:
            Dictionary with success status and updated crop info
        """
        try:
            # Start transaction (implicit with db.session)
            # Get crop with row-level locking to prevent concurrent updates
            crop = Crop.query.with_for_update().get(crop_id)
            
            if not crop:
                return {
                    'success': False,
                    'error': 'Crop not found',
                    'error_code': 'CROP_NOT_FOUND'
                }
            
            # Validate quantity
            if quantity is None or quantity <= 0:
                return {
                    'success': False,
                    'error': 'Quantity must be greater than zero',
                    'error_code': 'INVALID_QUANTITY'
                }
            
            # Check if sufficient stock is available
            if crop.quantity < quantity:
                return {
                    'success': False,
                    'error': f'Insufficient stock. Only {crop.quantity} {crop.unit} available',
                    'error_code': 'INVENTORY_INSUFFICIENT',
                    'details': {'available': crop.quantity, 'unit': crop.unit}
                }
            
            # Reduce inventory
            old_quantity = crop.quantity
            crop.quantity -= quantity
            crop.updated_at = datetime.utcnow()
            
            # Update crop status if quantity reaches zero
            if crop.quantity == 0:
                crop.status = 'sold'
                logger.info(f"Crop {crop_id} marked as sold (quantity reached zero)")
            
            # Commit transaction
            db.session.commit()
            
            logger.info(f"Inventory reduced for crop {crop_id}: {old_quantity} → {crop.quantity} {crop.unit}")
            
            return {
                'success': True,
                'message': 'Inventory reduced successfully',
                'crop_id': crop_id,
                'old_quantity': old_quantity,
                'new_quantity': crop.quantity,
                'reduced_by': quantity,
                'unit': crop.unit,
                'crop_status': crop.status
            }
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error reducing inventory for crop {crop_id}: {str(e)}")
            logger.exception("Detailed traceback:")
            return {
                'success': False,
                'error': 'An error occurred while reducing inventory',
                'error_code': 'INVENTORY_UPDATE_FAILED'
            }
    
    @staticmethod
    def release_inventory(crop_id: int, quantity: float) -> Dict[str, Any]:
        """
        Release inventory back to available stock (for cancellations/rejections)
        Uses database transaction to ensure atomicity
        
        Args:
            crop_id: ID of the crop
            quantity: Quantity to restore
            
        Returns:
            Dictionary with success status and updated crop info
        """
        try:
            # Start transaction (implicit with db.session)
            # Get crop with row-level locking to prevent concurrent updates
            crop = Crop.query.with_for_update().get(crop_id)
            
            if not crop:
                return {
                    'success': False,
                    'error': 'Crop not found',
                    'error_code': 'CROP_NOT_FOUND'
                }
            
            # Validate quantity
            if quantity is None or quantity <= 0:
                return {
                    'success': False,
                    'error': 'Quantity must be greater than zero',
                    'error_code': 'INVALID_QUANTITY'
                }
            
            # Restore inventory
            old_quantity = crop.quantity
            crop.quantity += quantity
            crop.updated_at = datetime.utcnow()
            
            # Update crop status if it was sold
            if crop.status == 'sold' and crop.quantity > 0:
                crop.status = 'available'
                logger.info(f"Crop {crop_id} status changed from sold to available")
            
            # Commit transaction
            db.session.commit()
            
            logger.info(f"Inventory released for crop {crop_id}: {old_quantity} → {crop.quantity} {crop.unit}")
            
            return {
                'success': True,
                'message': 'Inventory released successfully',
                'crop_id': crop_id,
                'old_quantity': old_quantity,
                'new_quantity': crop.quantity,
                'restored_by': quantity,
                'unit': crop.unit,
                'crop_status': crop.status
            }
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error releasing inventory for crop {crop_id}: {str(e)}")
            logger.exception("Detailed traceback:")
            return {
                'success': False,
                'error': 'An error occurred while releasing inventory',
                'error_code': 'INVENTORY_UPDATE_FAILED'
            }
    
    @staticmethod
    def update_crop_status(crop_id: int) -> Dict[str, Any]:
        """
        Update crop status based on current quantity
        Sets to 'sold' if quantity is 0, 'available' if quantity > 0
        
        Args:
            crop_id: ID of the crop
            
        Returns:
            Dictionary with success status and updated status
        """
        try:
            # Get crop
            crop = Crop.query.get(crop_id)
            
            if not crop:
                return {
                    'success': False,
                    'error': 'Crop not found'
                }
            
            old_status = crop.status
            
            # Determine new status based on quantity
            if crop.quantity == 0:
                new_status = 'sold'
            elif crop.quantity > 0 and crop.approval_status == 'approved':
                new_status = 'available'
            else:
                # Keep current status if not approved or other conditions
                new_status = old_status
            
            # Update status if changed
            if old_status != new_status:
                crop.status = new_status
                crop.updated_at = datetime.utcnow()
                db.session.commit()
                
                logger.info(f"Crop {crop_id} status updated: {old_status} → {new_status}")
                
                return {
                    'success': True,
                    'message': f'Crop status updated to {new_status}',
                    'crop_id': crop_id,
                    'old_status': old_status,
                    'new_status': new_status,
                    'quantity': crop.quantity,
                    'unit': crop.unit
                }
            else:
                return {
                    'success': True,
                    'message': 'Crop status unchanged',
                    'crop_id': crop_id,
                    'status': crop.status,
                    'quantity': crop.quantity,
                    'unit': crop.unit
                }
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error updating crop status for crop {crop_id}: {str(e)}")
            return {
                'success': False,
                'error': 'An error occurred while updating crop status'
            }
