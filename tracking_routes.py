"""
Tracking Routes Module
Flask routes for shipment tracking operations
"""
from flask import render_template, redirect, url_for, flash, request, abort, jsonify
from flask_login import login_required, current_user
from app import app, db
from extensions import limiter
from models import Order, ShipmentStatusHistory, User
from tracking_service import TrackingService
from tracking_notifications import TrackingNotificationService
from tracking_webhooks import WebhookHandler
from role_hierarchy import farmer_required, buyer_required
from datetime import datetime, timedelta
import logging
import os

logger = logging.getLogger(__name__)

# Simple in-memory cache for tracking status (use Redis in production)
_tracking_cache = {}
_cache_ttl = 60  # seconds


def _get_cached_tracking_status(order_id):
    """Get tracking status from cache if available and not expired"""
    if order_id in _tracking_cache:
        cached_data, timestamp = _tracking_cache[order_id]
        if (datetime.utcnow() - timestamp).total_seconds() < _cache_ttl:
            return cached_data
    return None


def _set_cached_tracking_status(order_id, data):
    """Store tracking status in cache with timestamp"""
    _tracking_cache[order_id] = (data, datetime.utcnow())


def _clear_cached_tracking_status(order_id):
    """Clear cached tracking status for an order"""
    if order_id in _tracking_cache:
        del _tracking_cache[order_id]


@app.route('/orders/<int:order_id>/track')
@login_required
def track_order(order_id):
    """
    Display tracking page for an order
    
    Requirements: 4.1, 4.2, 4.3, 4.4, 4.5
    """
    # Fetch order with tracking information
    order = Order.query.get_or_404(order_id)
    
    # Authorization check: only buyer, farmer, or admin can access
    if current_user.role not in ['admin'] and \
       current_user.id != order.buyer_id and \
       current_user.id != order.farmer_id:
        flash('You do not have permission to view this tracking information.', 'danger')
        abort(403)
    
    # Check if order has tracking information
    if not order.tracking_number:
        flash('This order does not have tracking information yet.', 'warning')
        return redirect(url_for('order_detail', order_id=order_id))
    
    # Fetch shipment status history
    tracking_history = ShipmentStatusHistory.query.filter_by(
        order_id=order_id
    ).order_by(ShipmentStatusHistory.created_at.asc()).all()
    
    # Prepare tracking data for template
    tracking_data = {
        'order': order,
        'tracking_number': order.tracking_number,
        'courier_name': order.courier_name,
        'current_status': order.shipment_status,
        'estimated_delivery_date': order.estimated_delivery_date,
        'actual_delivery_date': order.actual_delivery_date,
        'last_updated': order.last_api_sync or order.shipment_created_at,
        'tracking_url': order.courier_tracking_url,
        'awb_code': order.awb_code,
        'tracking_history': tracking_history,
        'delivery_confirmed': order.delivery_confirmed_by_buyer,
        'delivery_confirmation_date': order.delivery_confirmation_date
    }
    
    # Render tracking template with visual progress timeline
    return render_template('tracking/track_order.html', **tracking_data)


@app.route('/api/orders/<int:order_id>/tracking-status')
@login_required
def get_tracking_status_api(order_id):
    """
    AJAX endpoint for real-time tracking status updates
    
    Returns JSON with tracking information
    Requirements: 4.6, 4.7
    """
    # Fetch order
    order = Order.query.get_or_404(order_id)
    
    # Authorization check
    if current_user.role not in ['admin'] and \
       current_user.id != order.buyer_id and \
       current_user.id != order.farmer_id:
        return jsonify({'error': 'Unauthorized'}), 403
    
    # Check cache first (60-second TTL)
    cached_data = _get_cached_tracking_status(order_id)
    if cached_data:
        logger.info(f"Returning cached tracking status for order {order_id}")
        return jsonify(cached_data)
    
    # Fetch latest tracking status from database
    tracking_history = ShipmentStatusHistory.query.filter_by(
        order_id=order_id
    ).order_by(ShipmentStatusHistory.created_at.desc()).all()
    
    # Prepare response data
    response_data = {
        'success': True,
        'tracking_number': order.tracking_number,
        'courier_name': order.courier_name,
        'shipment_status': order.shipment_status,
        'estimated_delivery_date': order.estimated_delivery_date.isoformat() if order.estimated_delivery_date else None,
        'actual_delivery_date': order.actual_delivery_date.isoformat() if order.actual_delivery_date else None,
        'last_updated': (order.last_api_sync or order.shipment_created_at).isoformat() if (order.last_api_sync or order.shipment_created_at) else None,
        'tracking_url': order.courier_tracking_url,
        'awb_code': order.awb_code,
        'delivery_confirmed': order.delivery_confirmed_by_buyer,
        'tracking_history': [
            {
                'status': h.new_status,
                'description': h.status_description,
                'location': h.location,
                'timestamp': (h.courier_timestamp or h.created_at).isoformat(),
                'source': h.updated_by_source
            }
            for h in tracking_history
        ]
    }
    
    # Cache the response
    _set_cached_tracking_status(order_id, response_data)
    
    return jsonify(response_data)


@app.route('/orders/<int:order_id>/create-shipment', methods=['GET', 'POST'])
@login_required
@farmer_required
def create_shipment(order_id):
    """
    Create shipment for an order
    
    Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7
    """
    # Fetch order
    order = Order.query.get_or_404(order_id)
    
    # Authorization check: only the farmer who owns this order can create shipment
    if current_user.id != order.farmer_id:
        flash('You can only create shipments for your own orders.', 'danger')
        abort(403)
    
    # Validate order state
    if order.payment_status != 'paid':
        flash('Shipment can only be created for paid orders.', 'warning')
        return redirect(url_for('order_detail', order_id=order_id))
    
    if order.status not in ['confirmed', 'pending']:
        flash('Shipment can only be created for confirmed orders.', 'warning')
        return redirect(url_for('order_detail', order_id=order_id))
    
    # Check if shipment already exists
    if order.tracking_number:
        flash('Shipment has already been created for this order.', 'info')
        return redirect(url_for('track_order', order_id=order_id))
    
    if request.method == 'POST':
        try:
            # Get form data
            pickup_address = request.form.get('pickup_address', '').strip()
            package_weight = request.form.get('package_weight', '').strip()
            package_length = request.form.get('package_length', '').strip()
            package_width = request.form.get('package_width', '').strip()
            package_height = request.form.get('package_height', '').strip()
            courier_preference = request.form.get('courier_preference', 'shiprocket')
            
            # Validate required fields
            if not all([pickup_address, package_weight, package_length, package_width, package_height]):
                flash('All fields are required.', 'danger')
                return render_template('tracking/create_shipment.html', order=order)
            
            # Validate numeric fields
            try:
                weight = float(package_weight)
                length = float(package_length)
                width = float(package_width)
                height = float(package_height)
            except ValueError:
                flash('Please enter valid numbers for weight and dimensions.', 'danger')
                return render_template('tracking/create_shipment.html', order=order)
            
            # Validate ranges
            if weight <= 0 or weight >= 1000:
                flash('Package weight must be between 0 and 1000 kg.', 'danger')
                return render_template('tracking/create_shipment.html', order=order)
            
            if length <= 0 or width <= 0 or height <= 0:
                flash('Package dimensions must be greater than 0.', 'danger')
                return render_template('tracking/create_shipment.html', order=order)
            
            # Prepare shipment data
            shipment_data = {
                'pickup_address': pickup_address,
                'package_weight': weight,
                'package_length': length,
                'package_width': width,
                'package_height': height,
                'courier_preference': courier_preference
            }
            
            # Call TrackingService to create shipment
            logger.info(f"Creating shipment for order {order_id}")
            result = TrackingService.create_shipment(order_id, shipment_data)
            
            if result.get('success'):
                # Clear cache for this order
                _clear_cached_tracking_status(order_id)
                
                # Display success message with tracking number
                flash(f'Shipment created successfully! Tracking Number: {result["tracking_number"]}', 'success')
                
                # Send notification to buyer
                try:
                    TrackingNotificationService.send_shipment_created_notification(order)
                except Exception as e:
                    logger.error(f"Failed to send shipment notification: {str(e)}")
                    # Don't fail the request if notification fails
                
                return redirect(url_for('track_order', order_id=order_id))
            else:
                error_message = result.get('error', 'Failed to create shipment')
                flash(f'Error creating shipment: {error_message}', 'danger')
                return render_template('tracking/create_shipment.html', order=order)
                
        except ValueError as e:
            flash(f'Validation error: {str(e)}', 'danger')
            return render_template('tracking/create_shipment.html', order=order)
        
        except RuntimeError as e:
            flash(f'Error creating shipment: {str(e)}', 'danger')
            return render_template('tracking/create_shipment.html', order=order)
        
        except Exception as e:
            logger.error(f"Unexpected error creating shipment for order {order_id}: {str(e)}", exc_info=True)
            flash('An unexpected error occurred. Please try again later.', 'danger')
            return render_template('tracking/create_shipment.html', order=order)
    
    # GET request - display form
    return render_template('tracking/create_shipment.html', order=order)


@app.route('/orders/<int:order_id>/confirm-delivery', methods=['POST'])
@login_required
@buyer_required
def confirm_delivery(order_id):
    """
    Buyer confirms delivery receipt
    
    Requirements: 8.3, 8.4
    """
    # Fetch order
    order = Order.query.get_or_404(order_id)
    
    # Authorization check: only the buyer can confirm delivery
    if current_user.id != order.buyer_id:
        flash('Only the buyer can confirm delivery.', 'danger')
        abort(403)
    
    # Validate that shipment status is "delivered"
    if order.shipment_status != 'delivered':
        flash('Delivery can only be confirmed for delivered orders.', 'warning')
        return redirect(url_for('order_detail', order_id=order_id))
    
    # Check if already confirmed
    if order.delivery_confirmed_by_buyer:
        flash('Delivery has already been confirmed.', 'info')
        return redirect(url_for('order_detail', order_id=order_id))
    
    # Validate 7-day confirmation window
    if order.actual_delivery_date:
        days_since_delivery = (datetime.utcnow() - order.actual_delivery_date).days
        if days_since_delivery > 7:
            flash('The 7-day confirmation window has expired. Delivery has been auto-confirmed.', 'info')
            return redirect(url_for('order_detail', order_id=order_id))
    
    try:
        # Update delivery confirmation
        order.delivery_confirmed_by_buyer = True
        order.delivery_confirmation_date = datetime.utcnow()
        
        # Commit changes
        db.session.commit()
        
        # Clear cache
        _clear_cached_tracking_status(order_id)
        
        logger.info(f"Buyer {current_user.id} confirmed delivery for order {order_id}")
        
        # Send confirmation notification to farmer
        try:
            TrackingNotificationService.send_delivery_confirmation_notification(order)
        except Exception as e:
            logger.error(f"Failed to send delivery confirmation notification: {str(e)}")
            # Don't fail the request if notification fails
        
        flash('Delivery confirmed successfully! Thank you for your confirmation.', 'success')
        return redirect(url_for('order_detail', order_id=order_id))
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error confirming delivery for order {order_id}: {str(e)}", exc_info=True)
        flash('An error occurred while confirming delivery. Please try again.', 'danger')
        return redirect(url_for('order_detail', order_id=order_id))



# ============================================================================
# Webhook Routes
# ============================================================================

@app.route('/webhooks/shiprocket', methods=['POST'])
@limiter.limit("100 per minute")
def shiprocket_webhook():
    """
    Receive Shiprocket webhook callbacks
    
    Requirements: 3.1, 3.2, 12.4
    """
    try:
        # Get client IP address
        ip_address = request.remote_addr
        
        # Check rate limit using WebhookHandler's built-in rate limiting
        if not WebhookHandler.check_rate_limit(ip_address):
            logger.warning(f"Rate limit exceeded for Shiprocket webhook from IP {ip_address}")
            return jsonify({
                'success': False,
                'error': 'Rate limit exceeded'
            }), 429
        
        # Get raw request body for signature validation
        payload_bytes = request.get_data()
        
        # Get signature from header (Shiprocket typically uses X-Shiprocket-Signature)
        signature = request.headers.get('X-Shiprocket-Signature') or request.headers.get('X-Signature')
        
        # Get webhook secret from environment
        webhook_secret = os.getenv('SHIPROCKET_WEBHOOK_SECRET')
        
        if not webhook_secret:
            logger.error("SHIPROCKET_WEBHOOK_SECRET not configured")
            return jsonify({
                'success': False,
                'error': 'Webhook not configured'
            }), 500
        
        # Validate signature
        if not WebhookHandler.validate_signature(payload_bytes, signature, webhook_secret):
            logger.warning(f"Invalid signature for Shiprocket webhook from IP {ip_address}")
            WebhookHandler.log_webhook_attempt('shiprocket', {}, False, 'Invalid signature')
            return jsonify({
                'success': False,
                'error': 'Invalid signature'
            }), 401
        
        # Parse JSON payload
        try:
            payload = request.get_json()
        except Exception as e:
            logger.error(f"Failed to parse Shiprocket webhook payload: {str(e)}")
            WebhookHandler.log_webhook_attempt('shiprocket', {}, False, 'Invalid JSON payload')
            return jsonify({
                'success': False,
                'error': 'Invalid JSON payload'
            }), 400
        
        # Process webhook
        logger.info(f"Processing Shiprocket webhook from IP {ip_address}")
        result = WebhookHandler.process_shiprocket_webhook(payload)
        
        if result.get('success'):
            logger.info(f"Successfully processed Shiprocket webhook for order {result.get('order_id')}")
            return jsonify({
                'success': True,
                'message': 'Webhook processed successfully'
            }), 200
        else:
            error_message = result.get('error', 'Unknown error')
            logger.error(f"Failed to process Shiprocket webhook: {error_message}")
            return jsonify({
                'success': False,
                'error': error_message
            }), 500
            
    except Exception as e:
        logger.error(f"Unexpected error processing Shiprocket webhook: {str(e)}", exc_info=True)
        WebhookHandler.log_webhook_attempt('shiprocket', {}, False, f'Unexpected error: {str(e)}')
        return jsonify({
            'success': False,
            'error': 'Internal server error'
        }), 500


@app.route('/farmer/shipments')
@login_required
@farmer_required
def farmer_shipments():
    """
    Farmer shipment dashboard showing all shipments
    
    Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6
    """
    # Get filter parameters
    status_filter = request.args.get('status', '').strip()
    search_query = request.args.get('search', '').strip()
    
    # Base query - get all orders where current user is the farmer
    query = Order.query.filter_by(farmer_id=current_user.id)
    
    # Filter by shipment status if provided
    if status_filter:
        query = query.filter_by(shipment_status=status_filter)
    
    # Search by tracking number or buyer name
    if search_query:
        query = query.join(User, Order.buyer_id == User.id).filter(
            db.or_(
                Order.tracking_number.ilike(f'%{search_query}%'),
                User.full_name.ilike(f'%{search_query}%')
            )
        )
    
    # Get shipments with tracking numbers (exclude orders without shipments)
    shipments = query.filter(Order.tracking_number.isnot(None)).order_by(
        Order.shipment_created_at.desc()
    ).all()
    
    # Calculate shipment counts grouped by status
    all_shipments = Order.query.filter_by(farmer_id=current_user.id).filter(
        Order.tracking_number.isnot(None)
    ).all()
    
    shipment_counts = {
        'active': 0,
        'shipped': 0,
        'delivered': 0,
        'failed': 0
    }
    
    for order in all_shipments:
        status = order.shipment_status
        if status == 'delivered':
            shipment_counts['delivered'] += 1
        elif status in ['failed', 'returned']:
            shipment_counts['failed'] += 1
        elif status in ['shipped', 'in_transit', 'out_for_delivery']:
            shipment_counts['shipped'] += 1
        else:
            shipment_counts['active'] += 1
    
    return render_template(
        'tracking/farmer_shipments.html',
        shipments=shipments,
        shipment_counts=shipment_counts
    )


@app.route('/webhooks/indiapost', methods=['POST'])
@limiter.limit("100 per minute")
def indiapost_webhook():
    """
    Receive India Post webhook callbacks
    
    Requirements: 3.1, 3.2, 12.4
    """
    try:
        # Get client IP address
        ip_address = request.remote_addr
        
        # Check rate limit using WebhookHandler's built-in rate limiting
        if not WebhookHandler.check_rate_limit(ip_address):
            logger.warning(f"Rate limit exceeded for India Post webhook from IP {ip_address}")
            return jsonify({
                'success': False,
                'error': 'Rate limit exceeded'
            }), 429
        
        # Get raw request body for signature validation
        payload_bytes = request.get_data()
        
        # Get signature from header (India Post typically uses X-India-Post-Signature)
        signature = request.headers.get('X-India-Post-Signature') or request.headers.get('X-Signature')
        
        # Get webhook secret from environment
        webhook_secret = os.getenv('INDIA_POST_WEBHOOK_SECRET')
        
        if not webhook_secret:
            logger.error("INDIA_POST_WEBHOOK_SECRET not configured")
            return jsonify({
                'success': False,
                'error': 'Webhook not configured'
            }), 500
        
        # Validate signature
        if not WebhookHandler.validate_signature(payload_bytes, signature, webhook_secret):
            logger.warning(f"Invalid signature for India Post webhook from IP {ip_address}")
            WebhookHandler.log_webhook_attempt('india_post', {}, False, 'Invalid signature')
            return jsonify({
                'success': False,
                'error': 'Invalid signature'
            }), 401
        
        # Parse JSON payload
        try:
            payload = request.get_json()
        except Exception as e:
            logger.error(f"Failed to parse India Post webhook payload: {str(e)}")
            WebhookHandler.log_webhook_attempt('india_post', {}, False, 'Invalid JSON payload')
            return jsonify({
                'success': False,
                'error': 'Invalid JSON payload'
            }), 400
        
        # Process webhook
        logger.info(f"Processing India Post webhook from IP {ip_address}")
        result = WebhookHandler.process_indiapost_webhook(payload)
        
        if result.get('success'):
            logger.info(f"Successfully processed India Post webhook for order {result.get('order_id')}")
            return jsonify({
                'success': True,
                'message': 'Webhook processed successfully'
            }), 200
        else:
            error_message = result.get('error', 'Unknown error')
            logger.error(f"Failed to process India Post webhook: {error_message}")
            return jsonify({
                'success': False,
                'error': error_message
            }), 500
            
    except Exception as e:
        logger.error(f"Unexpected error processing India Post webhook: {str(e)}", exc_info=True)
        WebhookHandler.log_webhook_attempt('india_post', {}, False, f'Unexpected error: {str(e)}')
        return jsonify({
            'success': False,
            'error': 'Internal server error'
        }), 500
