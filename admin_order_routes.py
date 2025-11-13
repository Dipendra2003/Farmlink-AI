"""
FarmLink AI - Admin Order Management Routes
Handles all admin operations for order management
"""

from flask import render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from app import app, db
from models import Order, User, Crop
from role_hierarchy import admin_required
from security_enhancements import log_admin_action
from sqlalchemy import or_, func
from sqlalchemy.orm import aliased
import logging

logger = logging.getLogger(__name__)


@app.route('/admin/orders')
@login_required
@admin_required
def admin_orders():
    """Main admin orders page with filtering and search"""
    from datetime import datetime, timedelta
    from sqlalchemy.orm import joinedload
    
    page = request.args.get('page', 1, type=int)
    status_filter = request.args.get('status', 'all')
    payment_filter = request.args.get('payment', 'all')
    search_query = request.args.get('search', '')
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    
    # Base query with eager loading to prevent N+1 queries
    query = Order.query.options(
        joinedload(Order.buyer),
        joinedload(Order.farmer_user),
        joinedload(Order.crop)
    )
    
    # Apply status filter
    if status_filter != 'all':
        query = query.filter(Order.status == status_filter)
    
    # Apply payment filter
    if payment_filter != 'all':
        query = query.filter(Order.payment_status == payment_filter)
    
    # Apply date range filter
    if date_from:
        try:
            date_from_obj = datetime.strptime(date_from, '%Y-%m-%d')
            query = query.filter(Order.created_at >= date_from_obj)
        except ValueError:
            flash('Invalid date format for "Date From"', 'warning')
    
    if date_to:
        try:
            date_to_obj = datetime.strptime(date_to, '%Y-%m-%d')
            # Add one day to include the entire end date
            date_to_obj = date_to_obj + timedelta(days=1)
            query = query.filter(Order.created_at < date_to_obj)
        except ValueError:
            flash('Invalid date format for "Date To"', 'warning')
    
    # Apply search filter
    if search_query:
        # Create aliases for buyer and farmer
        buyer_alias = db.aliased(User)
        farmer_alias = db.aliased(User)
        
        query = query.join(buyer_alias, Order.buyer_id == buyer_alias.id).join(
            farmer_alias, Order.farmer_id == farmer_alias.id
        ).join(
            Crop, Order.crop_id == Crop.id
        ).filter(
            or_(
                Order.id == int(search_query) if search_query.isdigit() else False,
                buyer_alias.full_name.ilike(f'%{search_query}%'),
                buyer_alias.username.ilike(f'%{search_query}%'),
                buyer_alias.email.ilike(f'%{search_query}%'),
                farmer_alias.full_name.ilike(f'%{search_query}%'),
                farmer_alias.username.ilike(f'%{search_query}%'),
                Crop.name.ilike(f'%{search_query}%')
            )
        )
    
    # Paginate results
    orders = query.order_by(Order.created_at.desc()).paginate(
        page=page, per_page=20, error_out=False
    )
    
    # Calculate statistics
    total_orders = Order.query.count()
    pending_orders = Order.query.filter(Order.status.in_(['pending', 'confirmed'])).count()
    completed_orders = Order.query.filter_by(status='delivered').count()
    shipped_orders = Order.query.filter_by(status='shipped').count()
    cancelled_orders = Order.query.filter(Order.status.in_(['cancelled', 'rejected'])).count()
    total_revenue = db.session.query(func.sum(Order.total_amount)).filter(
        Order.payment_status == 'paid'
    ).scalar() or 0
    
    logger.info(f"Admin viewing orders page: {len(orders.items)} orders displayed, "
                f"filters - status: {status_filter}, payment: {payment_filter}, search: {search_query}")
    
    return render_template(
        'admin/orders.html',
        orders=orders,
        total_orders=total_orders,
        pending_orders=pending_orders,
        completed_orders=completed_orders,
        shipped_orders=shipped_orders,
        cancelled_orders=cancelled_orders,
        total_revenue=total_revenue,
        status_filter=status_filter,
        payment_filter=payment_filter,
        search_query=search_query,
        date_from=date_from,
        date_to=date_to
    )


@app.route('/admin/orders/<int:order_id>')
@login_required
@admin_required
def admin_order_detail(order_id):
    """View detailed information about a specific order"""
    from order_service import OrderService
    from sqlalchemy.orm import joinedload
    
    # Get order with eager loading to prevent N+1 queries
    order = Order.query.options(
        joinedload(Order.buyer),
        joinedload(Order.farmer_user),
        joinedload(Order.crop),
        joinedload(Order.payment)
    ).get_or_404(order_id)
    
    # Get order status history
    history_result = OrderService.get_order_history(order_id)
    order_history = history_result.get('history', []) if history_result.get('success') else []
    
    logger.info(f"Admin viewing order detail: order_id={order_id}, status={order.status}, "
                f"payment_status={order.payment_status}")
    
    return render_template('admin/order_detail.html', order=order, order_history=order_history)


@app.route('/admin/orders/<int:order_id>/update-status', methods=['POST'])
@login_required
@admin_required
@log_admin_action('update_order_status', 'order')
def admin_update_order_status(order_id):
    """Update order status with enhanced workflow support"""
    from order_service import OrderService
    from error_handlers import Validator, ErrorHandler
    
    order = Order.query.get_or_404(order_id)
    new_status = request.form.get('status')
    tracking_number = request.form.get('tracking_number', '').strip()
    notes = request.form.get('notes', '').strip()
    
    # Validate status
    valid_statuses = ['pending', 'confirmed', 'processing', 'shipped', 'delivered', 'rejected', 'cancelled']
    if new_status not in valid_statuses:
        logger.warning(f"Admin attempted invalid status update: order_id={order_id}, status={new_status}")
        flash(ErrorHandler.get_error_message('INVALID_STATUS'), 'danger')
        return redirect(url_for('admin_order_detail', order_id=order_id))
    
    # Validate status transition
    is_valid, error_msg = Validator.validate_status_transition(order.status, new_status)
    if not is_valid:
        logger.warning(f"Admin attempted invalid status transition: order_id={order_id}, "
                      f"from={order.status}, to={new_status}")
        flash(error_msg, 'warning')
        return redirect(url_for('admin_order_detail', order_id=order_id))
    
    # For shipped status, tracking number is required
    if new_status == 'shipped' and not tracking_number:
        logger.warning(f"Admin attempted to ship order without tracking number: order_id={order_id}")
        flash('Tracking number is required for shipped orders', 'warning')
        return redirect(url_for('admin_order_detail', order_id=order_id))
    
    # Use OrderService to update status with validation
    result = OrderService.update_order_status(
        order_id=order_id,
        new_status=new_status,
        user_id=current_user.id,
        notes=notes,
        tracking_number=tracking_number if new_status == 'shipped' else None
    )
    
    if result.get('success'):
        logger.info(f"Admin updated order status: order_id={order_id}, "
                   f"old_status={result.get('old_status')}, new_status={new_status}, "
                   f"admin_id={current_user.id}")
        flash(f'Order status updated to {new_status}', 'success')
    else:
        logger.error(f"Admin failed to update order status: order_id={order_id}, "
                    f"new_status={new_status}, error={result.get('error')}")
        flash(result.get('error', 'Failed to update order status'), 'danger')
    
    return redirect(url_for('admin_order_detail', order_id=order_id))


@app.route('/admin/orders/<int:order_id>/update-payment', methods=['POST'])
@login_required
@admin_required
@log_admin_action('update_payment_status', 'order')
def admin_update_payment_status(order_id):
    """Update payment status"""
    order = Order.query.get_or_404(order_id)
    new_payment_status = request.form.get('payment_status')
    
    if new_payment_status not in ['pending', 'paid', 'failed', 'refunded']:
        flash('Invalid payment status', 'danger')
        return redirect(url_for('admin_order_detail', order_id=order_id))
    
    order.payment_status = new_payment_status
    db.session.commit()
    
    flash(f'Payment status updated to {new_payment_status}', 'success')
    return redirect(url_for('admin_order_detail', order_id=order_id))


@app.route('/admin/orders/<int:order_id>/cancel', methods=['POST'])
@login_required
@admin_required
@log_admin_action('cancel_order', 'order')
def admin_cancel_order(order_id):
    """Cancel an order with refund support"""
    from order_service import OrderService
    from error_handlers import Validator, ErrorHandler
    
    order = Order.query.get_or_404(order_id)
    reason = request.form.get('reason', 'Cancelled by admin').strip()
    
    # Validate cancellation eligibility
    is_valid, error_msg = Validator.validate_cancellation_eligibility(order)
    if not is_valid:
        logger.warning(f"Admin attempted to cancel order with invalid status: "
                      f"order_id={order_id}, status={order.status}")
        flash(error_msg, 'warning')
        return redirect(url_for('admin_order_detail', order_id=order_id))
    
    logger.info(f"Admin cancelling order: order_id={order_id}, reason={reason}, "
               f"payment_status={order.payment_status}, admin_id={current_user.id}")
    
    # Use OrderService to cancel with refund handling
    result = OrderService.cancel_order(
        order_id=order_id,
        user_id=current_user.id,
        reason=reason
    )
    
    if result.get('success'):
        message = 'Order cancelled successfully'
        if result.get('refund_initiated'):
            message += ' and refund has been initiated'
            logger.info(f"Refund initiated for cancelled order: order_id={order_id}")
        elif result.get('refund_error'):
            message += f', but refund failed: {result.get("refund_error")}'
            logger.error(f"Refund failed for cancelled order: order_id={order_id}, "
                        f"error={result.get('refund_error')}")
        flash(message, 'success')
    else:
        logger.error(f"Admin failed to cancel order: order_id={order_id}, "
                    f"error={result.get('error')}")
        flash(result.get('error', 'Failed to cancel order'), 'danger')
    
    return redirect(url_for('admin_orders'))


@app.route('/admin/orders/export')
@login_required
@admin_required
def admin_export_orders():
    """Export orders data to CSV"""
    import csv
    from io import StringIO
    from flask import make_response
    from datetime import datetime, timedelta
    from sqlalchemy.orm import joinedload
    
    # Get all orders with filters
    status_filter = request.args.get('status', 'all')
    payment_filter = request.args.get('payment', 'all')
    search_query = request.args.get('search', '')
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    
    # Base query with eager loading to prevent N+1 queries
    query = Order.query.options(
        joinedload(Order.buyer),
        joinedload(Order.farmer_user),
        joinedload(Order.crop)
    )
    
    if status_filter != 'all':
        query = query.filter(Order.status == status_filter)
    
    if payment_filter != 'all':
        query = query.filter(Order.payment_status == payment_filter)
    
    # Apply date range filter
    if date_from:
        try:
            date_from_obj = datetime.strptime(date_from, '%Y-%m-%d')
            query = query.filter(Order.created_at >= date_from_obj)
        except ValueError:
            pass
    
    if date_to:
        try:
            date_to_obj = datetime.strptime(date_to, '%Y-%m-%d')
            date_to_obj = date_to_obj + timedelta(days=1)
            query = query.filter(Order.created_at < date_to_obj)
        except ValueError:
            pass
    
    # Apply search filter
    if search_query:
        buyer_alias = db.aliased(User)
        farmer_alias = db.aliased(User)
        
        query = query.join(buyer_alias, Order.buyer_id == buyer_alias.id).join(
            farmer_alias, Order.farmer_id == farmer_alias.id
        ).join(
            Crop, Order.crop_id == Crop.id
        ).filter(
            or_(
                Order.id == int(search_query) if search_query.isdigit() else False,
                buyer_alias.full_name.ilike(f'%{search_query}%'),
                buyer_alias.username.ilike(f'%{search_query}%'),
                buyer_alias.email.ilike(f'%{search_query}%'),
                farmer_alias.full_name.ilike(f'%{search_query}%'),
                farmer_alias.username.ilike(f'%{search_query}%'),
                Crop.name.ilike(f'%{search_query}%')
            )
        )
    
    orders = query.order_by(Order.created_at.desc()).all()
    
    logger.info(f"Admin exporting orders: {len(orders)} orders, "
               f"filters - status: {status_filter}, payment: {payment_filter}, "
               f"search: {search_query}, date_from: {date_from}, date_to: {date_to}")
    
    # Create CSV
    si = StringIO()
    writer = csv.writer(si)
    
    # Write header
    writer.writerow([
        'Order ID', 'Buyer Name', 'Buyer Email', 'Farmer Name', 'Farmer Email',
        'Crop Name', 'Category', 'Quantity', 'Unit', 'Price per Unit', 'Total Amount',
        'Order Status', 'Payment Status', 'Delivery Method', 'Delivery Address',
        'Tracking Number', 'Shipped At', 'Delivered At', 'Cancelled At', 'Cancellation Reason',
        'Razorpay Order ID', 'Razorpay Payment ID', 'Created At', 'Updated At'
    ])
    
    # Write data
    for order in orders:
        writer.writerow([
            order.id,
            order.buyer.full_name or order.buyer.username,
            order.buyer.email,
            order.farmer_user.full_name or order.farmer_user.username,
            order.farmer_user.email,
            order.crop.name,
            order.crop.category,
            order.quantity_requested,
            order.crop.unit,
            f"{order.price_per_unit:.2f}",
            f"{order.total_amount:.2f}",
            order.status,
            order.payment_status,
            order.delivery_method,
            order.delivery_address or '',
            order.tracking_number or '',
            order.shipped_at.strftime('%Y-%m-%d %H:%M:%S') if order.shipped_at else '',
            order.delivered_at.strftime('%Y-%m-%d %H:%M:%S') if order.delivered_at else '',
            order.cancelled_at.strftime('%Y-%m-%d %H:%M:%S') if order.cancelled_at else '',
            order.cancellation_reason or '',
            order.razorpay_order_id or '',
            order.razorpay_payment_id or '',
            order.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            order.updated_at.strftime('%Y-%m-%d %H:%M:%S')
        ])
    
    # Create response
    output = make_response(si.getvalue())
    output.headers["Content-Disposition"] = "attachment; filename=orders_export.csv"
    output.headers["Content-type"] = "text/csv"
    
    return output
