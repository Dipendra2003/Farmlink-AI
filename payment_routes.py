from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for, current_app
from flask_login import current_user, login_required
import os
from app import db
from models import Payment, Order
from payment_service import payment_service

payment_bp = Blueprint('payment_routes', __name__)

@payment_bp.route('/process/<int:order_id>', methods=['GET'])
@login_required
def process_payment(order_id):
    """Show payment page for an order"""
    from error_handlers import Validator, ErrorHandler
    
    order = Order.query.get_or_404(order_id)
    
    # Validate user permission
    is_valid, error_msg = Validator.validate_user_permission(current_user, order, 'view')
    if not is_valid:
        flash(error_msg, 'danger')
        return redirect(url_for('my_orders'))
    
    # Check if order belongs to current user (additional check)
    if order.buyer_id != current_user.id:
        flash(ErrorHandler.get_error_message('ORDER_UNAUTHORIZED'), 'danger')
        return redirect(url_for('my_orders'))
    
    # Get or create payment
    payment = Payment.query.filter_by(order_id=order.id).first()
    if not payment:
        payment = payment_service.create_order(order)
        if not payment:
            flash(ErrorHandler.get_error_message('PAYMENT_INIT_FAILED'), 'danger')
            return redirect(url_for('my_orders'))
    
    return render_template('payment/process.html',
                         key_id=os.environ.get('RAZORPAY_KEY_ID'),
                         order_id=payment.razorpay_order_id,
                         order=order,
                         payment=payment)

@payment_bp.route('/callback', methods=['POST'])
def payment_callback():
    """Handle payment callback from Razorpay"""
    from flask import session
    from order_service import CartService
    
    try:
        # Get payment details from request
        payment_id = request.form.get('razorpay_payment_id')
        order_id = request.form.get('razorpay_order_id')
        signature = request.form.get('razorpay_signature')
        
        # Verify payment signature
        if payment_service.verify_payment_signature(payment_id, order_id, signature):
            # Get the order to show invoice download link
            payment = Payment.query.filter_by(razorpay_order_id=order_id).first()
            
            # Clear cart after successful payment (for both buyers and farmers)
            if payment and payment.order:
                buyer_id = payment.order.buyer_id
                
                # Get buyer's cart and clear it
                from models import Cart
                buyer_cart = Cart.query.filter_by(user_id=buyer_id).first()
                if buyer_cart:
                    clear_result = CartService.clear_cart(buyer_cart.id)
                    if clear_result.get('success'):
                        current_app.logger.info(f"Cart cleared for user {buyer_id} after successful payment for order {payment.order.id}")
                    else:
                        current_app.logger.warning(f"Failed to clear cart for user {buyer_id} after payment: {clear_result.get('error')}")
                
                # Clear session data if exists
                session.pop('pending_order_ids', None)
                session.pop('checkout_cart_id', None)
                
                flash('Payment successful! Your order is confirmed. You can download your invoice from My Orders.', 'success')
            else:
                flash('Payment successful! Your order is confirmed.', 'success')
            return redirect(url_for('my_orders'))
        else:
            flash('Payment verification failed. Please contact support.', 'danger')
            return redirect(url_for('my_orders'))
            
    except Exception as e:
        current_app.logger.error(f"Payment callback error: {str(e)}")
        flash('An error occurred during payment processing.', 'danger')
        return redirect(url_for('my_orders'))

@payment_bp.route('/status/<int:order_id>')
def payment_status(order_id):
    """Check payment status for an order"""
    order = Order.query.get_or_404(order_id)
    
    # Check if order belongs to current user
    if order.buyer_id != current_user.id:
        return jsonify({'error': 'Access denied'}), 403
    
    payment = Payment.query.filter_by(order_id=order.id).first()
    if not payment:
        return jsonify({'error': 'No payment found'}), 404
        
    return jsonify({
        'status': payment.status,
        'razorpay_order_id': payment.razorpay_order_id,
        'amount': payment.amount,
        'created_at': payment.created_at.isoformat()
    })

@payment_bp.route('/refund/<int:order_id>', methods=['POST'])
def initiate_refund(order_id):
    """Initiate refund for an order"""
    from error_handlers import ErrorHandler
    
    order = Order.query.get_or_404(order_id)
    
    # Only admin can initiate refund
    if not current_user.role == 'admin':
        return jsonify({'error': ErrorHandler.get_error_message('USER_UNAUTHORIZED')}), 403
    
    payment = Payment.query.filter_by(order_id=order.id).first()
    if not payment:
        return jsonify({'error': ErrorHandler.get_error_message('PAYMENT_NOT_FOUND')}), 404
    
    if payment.status != 'completed':
        return jsonify({'error': ErrorHandler.get_error_message('PAYMENT_ALREADY_COMPLETED')}), 400
    
    # Get refund amount from request
    amount = request.form.get('amount', type=float)
    if amount and amount > payment.amount:
        return jsonify({'error': ErrorHandler.get_error_message('PAYMENT_AMOUNT_INVALID')}), 400
    
    if payment_service.initiate_refund(payment, amount):
        return jsonify({'message': 'Refund initiated successfully'})
    else:
        return jsonify({'error': 'Failed to initiate refund'}), 500


@payment_bp.route('/webhook/refund', methods=['POST'])
def refund_webhook():
    """Handle refund webhook from Razorpay"""
    try:
        # Get webhook payload
        payload = request.get_json()
        
        if not payload:
            current_app.logger.error("Empty webhook payload received")
            return jsonify({'error': 'Invalid payload'}), 400
        
        # Log webhook event
        event = payload.get('event')
        current_app.logger.info(f"Received refund webhook event: {event}")
        
        # Handle refund webhook
        result = payment_service.handle_refund_webhook(payload)
        
        if result.get('success'):
            return jsonify({'status': 'ok', 'message': result.get('message', 'Webhook processed')}), 200
        else:
            current_app.logger.error(f"Webhook processing failed: {result.get('error')}")
            return jsonify({'status': 'error', 'message': result.get('error')}), 400
            
    except Exception as e:
        current_app.logger.error(f"Refund webhook error: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500


@payment_bp.route('/process-bulk', methods=['GET'])
@login_required
def process_bulk_payment():
    """Show payment page for bulk orders from cart checkout"""
    from flask import session
    
    # Get order IDs from session
    order_ids = session.get('pending_order_ids', [])
    cart_id = session.get('checkout_cart_id')
    
    if not order_ids:
        flash('No pending orders found. Please checkout again.', 'warning')
        return redirect(url_for('view_cart'))
    
    # Get all orders
    orders = Order.query.filter(Order.id.in_(order_ids)).all()
    
    if not orders:
        flash('Orders not found. Please try again.', 'danger')
        return redirect(url_for('view_cart'))
    
    # Verify all orders belong to current user
    if not all(order.buyer_id == current_user.id for order in orders):
        flash('Access denied', 'danger')
        return redirect(url_for('index'))
    
    # Create or get bulk payment
    payment = Payment.query.filter_by(order_id=orders[0].id).first()
    if not payment:
        payment = payment_service.create_bulk_order(orders)
        if not payment:
            flash('Failed to initialize payment. Please try again.', 'danger')
            return redirect(url_for('checkout'))
    
    # Calculate total
    total_amount = sum(order.total_amount for order in orders)
    
    return render_template('payment/process_bulk.html',
                         key_id=os.environ.get('RAZORPAY_KEY_ID'),
                         razorpay_order_id=payment.razorpay_order_id,
                         orders=orders,
                         order_ids=order_ids,
                         payment=payment,
                         total_amount=total_amount,
                         order_count=len(orders))


@payment_bp.route('/callback-bulk', methods=['POST'])
@login_required
def bulk_payment_callback():
    """Handle payment callback for bulk orders"""
    from flask import session
    from order_service import CartService
    
    try:
        # Get payment details from request
        payment_id = request.form.get('razorpay_payment_id')
        order_id = request.form.get('razorpay_order_id')
        signature = request.form.get('razorpay_signature')
        order_ids_str = request.form.get('order_ids', '')
        
        # Parse order IDs
        order_ids = [int(id) for id in order_ids_str.split(',') if id.strip()]
        
        if not order_ids:
            flash('Invalid order information.', 'danger')
            return redirect(url_for('my_orders'))
        
        # Verify payment signature and update all orders
        if payment_service.verify_bulk_payment(payment_id, order_id, signature, order_ids):
            # Clear cart after successful payment (for both buyers and farmers)
            cart_id = session.get('checkout_cart_id')
            if cart_id:
                clear_result = CartService.clear_cart(cart_id)
                if clear_result.get('success'):
                    current_app.logger.info(f"Cart {cart_id} cleared after successful bulk payment for {len(order_ids)} orders")
                else:
                    current_app.logger.warning(f"Failed to clear cart {cart_id} after bulk payment: {clear_result.get('error')}")
            else:
                current_app.logger.warning(f"No cart_id found in session for bulk payment callback")
            
            # Clear session data
            session.pop('pending_order_ids', None)
            session.pop('checkout_cart_id', None)
            
            # ⚡ Email notifications are now sent in background by payment_service
            # This makes the callback return faster to the user
            
            flash(f'Payment successful! {len(order_ids)} order(s) confirmed. You can download invoices from My Orders.', 'success')
            return redirect(url_for('my_orders'))
        else:
            flash('Payment verification failed. Please contact support.', 'danger')
            return redirect(url_for('my_orders'))
            
    except Exception as e:
        current_app.logger.error(f"Bulk payment callback error: {str(e)}")
        flash('An error occurred during payment processing.', 'danger')
        return redirect(url_for('my_orders'))
