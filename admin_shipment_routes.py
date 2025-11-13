"""
FarmLink AI - Admin Shipment Management Routes
Handles all admin operations for shipment tracking and management
"""

from flask import render_template, redirect, url_for, flash, request, jsonify, make_response
from flask_login import login_required, current_user
from app import app, db
from models import Order, User, Crop, ShipmentStatusHistory, OrderStatusHistory
from role_hierarchy import admin_required
from security_enhancements import log_admin_action
from tracking_service import TrackingService
from sqlalchemy import or_, func, and_, case
from sqlalchemy.orm import joinedload
from datetime import datetime, timedelta
import logging
import csv
from io import StringIO

logger = logging.getLogger(__name__)


@app.route('/admin/shipments')
@login_required
@admin_required
def admin_shipments():
    """
    Admin shipment dashboard route
    Display all shipments with filtering, search, and pagination
    
    Requirements: 6.1, 6.6
    """
    page = request.args.get('page', 1, type=int)
    status_filter = request.args.get('status', 'all')
    courier_filter = request.args.get('courier', 'all')
    search_query = request.args.get('search', '')
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    
    # Base query with eager loading to prevent N+1 queries
    query = Order.query.options(
        joinedload(Order.buyer),
        joinedload(Order.farmer_user),
        joinedload(Order.crop)
    ).filter(Order.tracking_number.isnot(None))  # Only orders with tracking
    
    # Apply shipment status filter
    if status_filter != 'all':
        query = query.filter(Order.shipment_status == status_filter)
    
    # Apply courier filter
    if courier_filter != 'all':
        query = query.filter(Order.courier_name == courier_filter)
    
    # Apply date range filter (shipment_created_at)
    if date_from:
        try:
            date_from_obj = datetime.strptime(date_from, '%Y-%m-%d')
            query = query.filter(Order.shipment_created_at >= date_from_obj)
        except ValueError:
            flash('Invalid date format for "Date From"', 'warning')
    
    if date_to:
        try:
            date_to_obj = datetime.strptime(date_to, '%Y-%m-%d')
            # Add one day to include the entire end date
            date_to_obj = date_to_obj + timedelta(days=1)
            query = query.filter(Order.shipment_created_at < date_to_obj)
        except ValueError:
            flash('Invalid date format for "Date To"', 'warning')
    
    # Apply search filter (tracking_number, buyer name, farmer name)
    if search_query:
        buyer_alias = db.aliased(User)
        farmer_alias = db.aliased(User)
        
        query = query.join(buyer_alias, Order.buyer_id == buyer_alias.id).join(
            farmer_alias, Order.farmer_id == farmer_alias.id
        ).filter(
            or_(
                Order.tracking_number.ilike(f'%{search_query}%'),
                Order.awb_code.ilike(f'%{search_query}%'),
                buyer_alias.full_name.ilike(f'%{search_query}%'),
                buyer_alias.username.ilike(f'%{search_query}%'),
                farmer_alias.full_name.ilike(f'%{search_query}%'),
                farmer_alias.username.ilike(f'%{search_query}%')
            )
        )
    
    # Paginate results
    shipments = query.order_by(Order.shipment_created_at.desc()).paginate(
        page=page, per_page=20, error_out=False
    )
    
    # Calculate shipment count grouped by status
    status_counts = db.session.query(
        Order.shipment_status,
        func.count(Order.id)
    ).filter(
        Order.tracking_number.isnot(None)
    ).group_by(Order.shipment_status).all()
    
    # Convert to dictionary for easy access
    status_count_dict = {status: count for status, count in status_counts}
    
    # Calculate total shipments
    total_shipments = sum(status_count_dict.values())
    
    # Get list of available couriers
    couriers = db.session.query(Order.courier_name).filter(
        Order.courier_name.isnot(None)
    ).distinct().all()
    courier_list = [c[0] for c in couriers]
    
    logger.info(f"Admin viewing shipments page: {len(shipments.items)} shipments displayed, "
                f"filters - status: {status_filter}, courier: {courier_filter}, search: {search_query}")
    
    return render_template(
        'admin/shipments.html',
        shipments=shipments,
        total_shipments=total_shipments,
        status_counts=status_count_dict,
        courier_list=courier_list,
        status_filter=status_filter,
        courier_filter=courier_filter,
        search_query=search_query,
        date_from=date_from,
        date_to=date_to
    )


@app.route('/admin/shipments/<int:order_id>/update-status', methods=['POST'])
@login_required
@admin_required
@log_admin_action('update_shipment_status', 'order')
def admin_update_shipment_status(order_id):
    """
    Manually update shipment status
    
    Requirements: 6.2, 6.7
    """
    order = Order.query.get_or_404(order_id)
    
    # Validate order has tracking
    if not order.tracking_number:
        flash('This order does not have a shipment.', 'warning')
        return redirect(url_for('admin_shipments'))
    
    new_status = request.form.get('status', '').strip()
    status_description = request.form.get('description', '').strip()
    location = request.form.get('location', '').strip()
    
    # Validate status
    valid_statuses = ['packed', 'shipped', 'in_transit', 'out_for_delivery', 'delivered', 'failed', 'returned', 'cancelled']
    if new_status not in valid_statuses:
        flash('Invalid shipment status.', 'danger')
        return redirect(url_for('admin_shipments'))
    
    try:
        # Store old status
        old_status = order.shipment_status
        
        # Update order shipment status
        order.shipment_status = new_status
        order.last_api_sync = datetime.utcnow()
        order.api_sync_status = 'manual'
        
        # Update delivery dates based on status
        if new_status == 'delivered' and not order.actual_delivery_date:
            # Check seller KYC status before allowing delivery completion (payment release)
            from kyc_service import KYCService
            if not KYCService.is_seller_verified(order.farmer_id):
                flash(f'Cannot mark as delivered: Seller (User ID: {order.farmer_id}) has not completed KYC verification. Payment cannot be released to unverified sellers.', 'warning')
                return redirect(url_for('admin_shipment_detail', order_id=order_id))
            
            order.actual_delivery_date = datetime.utcnow()
            order.delivered_at = datetime.utcnow()
            # Update order status
            if order.status != 'delivered':
                old_order_status = order.status
                order.status = 'delivered'
                
                # Create order status history
                order_status_history = OrderStatusHistory(
                    order_id=order_id,
                    old_status=old_order_status,
                    new_status='delivered',
                    notes=f'Manually marked as delivered by admin: {status_description}',
                    changed_by_id=current_user.id
                )
                db.session.add(order_status_history)
        
        # Create shipment status history entry
        shipment_history = ShipmentStatusHistory(
            order_id=order_id,
            tracking_number=order.tracking_number,
            old_status=old_status,
            new_status=new_status,
            status_description=status_description or f'Status manually updated by admin to {new_status}',
            location=location,
            updated_by_source='manual',
            courier_timestamp=datetime.utcnow()
        )
        db.session.add(shipment_history)
        
        # Commit changes
        db.session.commit()
        
        logger.info(f"Admin updated shipment status: order_id={order_id}, "
                   f"tracking_number={order.tracking_number}, "
                   f"old_status={old_status}, new_status={new_status}, "
                   f"admin_id={current_user.id}")
        
        flash(f'Shipment status updated to {new_status}.', 'success')
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error updating shipment status: order_id={order_id}, error={str(e)}", exc_info=True)
        flash('An error occurred while updating shipment status.', 'danger')
    
    return redirect(url_for('admin_shipments'))


@app.route('/admin/shipments/<int:order_id>/update-tracking', methods=['POST'])
@login_required
@admin_required
@log_admin_action('update_tracking_number', 'order')
def admin_update_tracking_number(order_id):
    """
    Manually update tracking number
    
    Requirements: 6.3, 6.7
    """
    order = Order.query.get_or_404(order_id)
    
    new_tracking_number = request.form.get('tracking_number', '').strip()
    new_awb_code = request.form.get('awb_code', '').strip()
    new_courier_name = request.form.get('courier_name', '').strip()
    new_tracking_url = request.form.get('tracking_url', '').strip()
    
    # Validate tracking number
    if not new_tracking_number:
        flash('Tracking number is required.', 'danger')
        return redirect(url_for('admin_shipments'))
    
    # Check if tracking number already exists for another order
    existing_order = Order.query.filter(
        Order.tracking_number == new_tracking_number,
        Order.id != order_id
    ).first()
    
    if existing_order:
        flash(f'Tracking number {new_tracking_number} is already assigned to order #{existing_order.id}.', 'danger')
        return redirect(url_for('admin_shipments'))
    
    try:
        # Store old values
        old_tracking_number = order.tracking_number
        old_awb_code = order.awb_code
        old_courier_name = order.courier_name
        
        # Update tracking information
        order.tracking_number = new_tracking_number
        if new_awb_code:
            order.awb_code = new_awb_code
        if new_courier_name:
            order.courier_name = new_courier_name
        if new_tracking_url:
            order.courier_tracking_url = new_tracking_url
        
        order.last_api_sync = datetime.utcnow()
        order.api_sync_status = 'manual'
        
        # If this is the first time tracking is added, set shipment_created_at
        if not old_tracking_number and not order.shipment_created_at:
            order.shipment_created_at = datetime.utcnow()
            order.shipment_status = 'packed'
            
            # Create initial shipment status history
            shipment_history = ShipmentStatusHistory(
                order_id=order_id,
                tracking_number=new_tracking_number,
                old_status=None,
                new_status='packed',
                status_description='Tracking number manually added by admin',
                location=None,
                updated_by_source='manual',
                courier_timestamp=datetime.utcnow()
            )
            db.session.add(shipment_history)
        
        # Update all existing shipment history records with new tracking number
        if old_tracking_number and old_tracking_number != new_tracking_number:
            ShipmentStatusHistory.query.filter_by(
                tracking_number=old_tracking_number
            ).update({'tracking_number': new_tracking_number})
        
        # Commit changes
        db.session.commit()
        
        logger.info(f"Admin updated tracking number: order_id={order_id}, "
                   f"old_tracking={old_tracking_number}, new_tracking={new_tracking_number}, "
                   f"admin_id={current_user.id}")
        
        flash(f'Tracking number updated to {new_tracking_number}.', 'success')
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error updating tracking number: order_id={order_id}, error={str(e)}", exc_info=True)
        flash('An error occurred while updating tracking number.', 'danger')
    
    return redirect(url_for('admin_shipments'))


@app.route('/admin/shipments/<int:order_id>/regenerate', methods=['POST'])
@login_required
@admin_required
@log_admin_action('regenerate_shipment', 'order')
def admin_regenerate_shipment(order_id):
    """
    Regenerate shipment via courier API
    
    Requirements: 6.4, 6.7
    """
    order = Order.query.get_or_404(order_id)
    
    # Validate order state
    if order.payment_status != 'paid':
        flash('Shipment can only be regenerated for paid orders.', 'warning')
        return redirect(url_for('admin_shipments'))
    
    # Get shipment data from form
    pickup_address = request.form.get('pickup_address', order.pickup_address or '').strip()
    package_weight = request.form.get('package_weight', order.package_weight or '').strip()
    package_length = request.form.get('package_length', order.package_length or '').strip()
    package_width = request.form.get('package_width', order.package_width or '').strip()
    package_height = request.form.get('package_height', order.package_height or '').strip()
    courier_preference = request.form.get('courier_preference', order.courier_name or 'shiprocket')
    
    # Validate required fields
    if not all([pickup_address, package_weight, package_length, package_width, package_height]):
        flash('All shipment details are required to regenerate shipment.', 'danger')
        return redirect(url_for('admin_shipments'))
    
    try:
        # Validate numeric fields
        weight = float(package_weight)
        length = float(package_length)
        width = float(package_width)
        height = float(package_height)
        
        # Validate ranges
        if weight <= 0 or weight >= 1000:
            flash('Package weight must be between 0 and 1000 kg.', 'danger')
            return redirect(url_for('admin_shipments'))
        
        if length <= 0 or width <= 0 or height <= 0:
            flash('Package dimensions must be greater than 0.', 'danger')
            return redirect(url_for('admin_shipments'))
        
        # Prepare shipment data
        shipment_data = {
            'pickup_address': pickup_address,
            'package_weight': weight,
            'package_length': length,
            'package_width': width,
            'package_height': height,
            'courier_preference': courier_preference
        }
        
        # Call TrackingService to create/regenerate shipment
        logger.info(f"Admin regenerating shipment for order {order_id}")
        result = TrackingService.create_shipment(order_id, shipment_data)
        
        if result.get('success'):
            logger.info(f"Admin successfully regenerated shipment: order_id={order_id}, "
                       f"tracking_number={result['tracking_number']}, admin_id={current_user.id}")
            flash(f'Shipment regenerated successfully! Tracking Number: {result["tracking_number"]}', 'success')
        else:
            error_message = result.get('error', 'Failed to regenerate shipment')
            logger.error(f"Admin failed to regenerate shipment: order_id={order_id}, error={error_message}")
            flash(f'Error regenerating shipment: {error_message}', 'danger')
            
    except ValueError as e:
        flash(f'Validation error: {str(e)}', 'danger')
    except RuntimeError as e:
        flash(f'Error regenerating shipment: {str(e)}', 'danger')
    except Exception as e:
        logger.error(f"Unexpected error regenerating shipment for order {order_id}: {str(e)}", exc_info=True)
        flash('An unexpected error occurred. Please try again later.', 'danger')
    
    return redirect(url_for('admin_shipments'))


@app.route('/admin/shipments/<int:order_id>/cancel', methods=['POST'])
@login_required
@admin_required
@log_admin_action('cancel_shipment', 'order')
def admin_cancel_shipment(order_id):
    """
    Cancel shipment via courier API
    
    Requirements: 6.5, 6.7
    """
    order = Order.query.get_or_404(order_id)
    
    # Validate order has tracking
    if not order.tracking_number:
        flash('This order does not have a shipment to cancel.', 'warning')
        return redirect(url_for('admin_shipments'))
    
    # Validate shipment can be cancelled
    non_cancellable_statuses = ['delivered', 'cancelled', 'returned']
    if order.shipment_status in non_cancellable_statuses:
        flash(f'Cannot cancel shipment with status "{order.shipment_status}".', 'warning')
        return redirect(url_for('admin_shipments'))
    
    reason = request.form.get('reason', 'Cancelled by admin').strip()
    
    try:
        # Call TrackingService to cancel shipment
        logger.info(f"Admin cancelling shipment: order_id={order_id}, "
                   f"tracking_number={order.tracking_number}, reason={reason}")
        
        result = TrackingService.cancel_shipment(
            tracking_number=order.tracking_number,
            courier_name=order.courier_name,
            reason=reason
        )
        
        if result.get('success'):
            logger.info(f"Admin successfully cancelled shipment: order_id={order_id}, "
                       f"tracking_number={order.tracking_number}, admin_id={current_user.id}")
            flash('Shipment cancelled successfully.', 'success')
        else:
            error_message = result.get('error', 'Failed to cancel shipment')
            logger.error(f"Admin failed to cancel shipment: order_id={order_id}, error={error_message}")
            flash(f'Error cancelling shipment: {error_message}', 'danger')
            
    except ValueError as e:
        flash(f'Validation error: {str(e)}', 'danger')
    except RuntimeError as e:
        flash(f'Error cancelling shipment: {str(e)}', 'danger')
    except Exception as e:
        logger.error(f"Unexpected error cancelling shipment for order {order_id}: {str(e)}", exc_info=True)
        flash('An unexpected error occurred. Please try again later.', 'danger')
    
    return redirect(url_for('admin_shipments'))



@app.route('/admin/tracking-analytics')
@login_required
@admin_required
def admin_tracking_analytics():
    """
    Display tracking analytics dashboard
    
    Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 11.6
    """
    # Calculate average delivery time grouped by courier_name
    # Only include delivered shipments with both shipment_created_at and actual_delivery_date
    avg_delivery_times = db.session.query(
        Order.courier_name,
        func.avg(
            func.julianday(Order.actual_delivery_date) - func.julianday(Order.shipment_created_at)
        ).label('avg_days')
    ).filter(
        and_(
            Order.shipment_status == 'delivered',
            Order.shipment_created_at.isnot(None),
            Order.actual_delivery_date.isnot(None),
            Order.courier_name.isnot(None)
        )
    ).group_by(Order.courier_name).all()
    
    # Convert to dictionary
    avg_delivery_dict = {courier: round(avg_days, 2) for courier, avg_days in avg_delivery_times}
    
    # Calculate on-time vs delayed deliveries
    # On-time: actual_delivery_date <= estimated_delivery_date
    # Delayed: actual_delivery_date > estimated_delivery_date
    ontime_count = db.session.query(func.count(Order.id)).filter(
        and_(
            Order.shipment_status == 'delivered',
            Order.actual_delivery_date.isnot(None),
            Order.estimated_delivery_date.isnot(None),
            func.date(Order.actual_delivery_date) <= Order.estimated_delivery_date
        )
    ).scalar() or 0
    
    delayed_count = db.session.query(func.count(Order.id)).filter(
        and_(
            Order.shipment_status == 'delivered',
            Order.actual_delivery_date.isnot(None),
            Order.estimated_delivery_date.isnot(None),
            func.date(Order.actual_delivery_date) > Order.estimated_delivery_date
        )
    ).scalar() or 0
    
    total_delivered = ontime_count + delayed_count
    ontime_percentage = round((ontime_count / total_delivered * 100), 2) if total_delivered > 0 else 0
    delayed_percentage = round((delayed_count / total_delivered * 100), 2) if total_delivered > 0 else 0
    
    # Count of failed deliveries grouped by failure_reason
    failed_deliveries = db.session.query(
        Order.delivery_failure_reason,
        func.count(Order.id).label('count')
    ).filter(
        Order.shipment_status == 'failed',
        Order.delivery_failure_reason.isnot(None)
    ).group_by(Order.delivery_failure_reason).all()
    
    # Convert to dictionary
    failed_deliveries_dict = {reason or 'Unknown': count for reason, count in failed_deliveries}
    
    # Total failed deliveries
    total_failed = sum(failed_deliveries_dict.values())
    
    # Shipment volume over time (last 12 months)
    twelve_months_ago = datetime.utcnow() - timedelta(days=365)
    
    shipment_volume = db.session.query(
        func.strftime('%Y-%m', Order.shipment_created_at).label('month'),
        func.count(Order.id).label('count')
    ).filter(
        Order.shipment_created_at >= twelve_months_ago,
        Order.tracking_number.isnot(None)
    ).group_by('month').order_by('month').all()
    
    # Convert to lists for Chart.js
    volume_months = [month for month, count in shipment_volume]
    volume_counts = [count for month, count in shipment_volume]
    
    # Most frequently used courier services
    courier_usage = db.session.query(
        Order.courier_name,
        func.count(Order.id).label('count')
    ).filter(
        Order.courier_name.isnot(None)
    ).group_by(Order.courier_name).order_by(func.count(Order.id).desc()).all()
    
    # Convert to dictionary
    courier_usage_dict = {courier: count for courier, count in courier_usage}
    
    # Total shipments
    total_shipments = db.session.query(func.count(Order.id)).filter(
        Order.tracking_number.isnot(None)
    ).scalar() or 0
    
    # Active shipments (not delivered, cancelled, or returned)
    active_shipments = db.session.query(func.count(Order.id)).filter(
        Order.tracking_number.isnot(None),
        Order.shipment_status.notin_(['delivered', 'cancelled', 'returned'])
    ).scalar() or 0
    
    logger.info(f"Admin viewing tracking analytics: total_shipments={total_shipments}, "
               f"active_shipments={active_shipments}, ontime_percentage={ontime_percentage}%")
    
    return render_template(
        'admin/tracking_analytics.html',
        avg_delivery_times=avg_delivery_dict,
        ontime_count=ontime_count,
        delayed_count=delayed_count,
        ontime_percentage=ontime_percentage,
        delayed_percentage=delayed_percentage,
        failed_deliveries=failed_deliveries_dict,
        total_failed=total_failed,
        volume_months=volume_months,
        volume_counts=volume_counts,
        courier_usage=courier_usage_dict,
        total_shipments=total_shipments,
        active_shipments=active_shipments,
        total_delivered=total_delivered
    )


@app.route('/admin/shipments/export')
@login_required
@admin_required
def admin_export_shipments():
    """
    Export shipment data to CSV
    
    Requirements: 11.6
    """
    # Get all shipments with filters
    status_filter = request.args.get('status', 'all')
    courier_filter = request.args.get('courier', 'all')
    search_query = request.args.get('search', '')
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    
    # Base query with eager loading
    query = Order.query.options(
        joinedload(Order.buyer),
        joinedload(Order.farmer_user),
        joinedload(Order.crop)
    ).filter(Order.tracking_number.isnot(None))
    
    # Apply filters
    if status_filter != 'all':
        query = query.filter(Order.shipment_status == status_filter)
    
    if courier_filter != 'all':
        query = query.filter(Order.courier_name == courier_filter)
    
    # Apply date range filter
    if date_from:
        try:
            date_from_obj = datetime.strptime(date_from, '%Y-%m-%d')
            query = query.filter(Order.shipment_created_at >= date_from_obj)
        except ValueError:
            pass
    
    if date_to:
        try:
            date_to_obj = datetime.strptime(date_to, '%Y-%m-%d')
            date_to_obj = date_to_obj + timedelta(days=1)
            query = query.filter(Order.shipment_created_at < date_to_obj)
        except ValueError:
            pass
    
    # Apply search filter
    if search_query:
        buyer_alias = db.aliased(User)
        farmer_alias = db.aliased(User)
        
        query = query.join(buyer_alias, Order.buyer_id == buyer_alias.id).join(
            farmer_alias, Order.farmer_id == farmer_alias.id
        ).filter(
            or_(
                Order.tracking_number.ilike(f'%{search_query}%'),
                Order.awb_code.ilike(f'%{search_query}%'),
                buyer_alias.full_name.ilike(f'%{search_query}%'),
                buyer_alias.username.ilike(f'%{search_query}%'),
                farmer_alias.full_name.ilike(f'%{search_query}%'),
                farmer_alias.username.ilike(f'%{search_query}%')
            )
        )
    
    shipments = query.order_by(Order.shipment_created_at.desc()).all()
    
    logger.info(f"Admin exporting shipments: {len(shipments)} shipments, "
               f"filters - status: {status_filter}, courier: {courier_filter}, "
               f"search: {search_query}, date_from: {date_from}, date_to: {date_to}")
    
    # Create CSV
    si = StringIO()
    writer = csv.writer(si)
    
    # Write header
    writer.writerow([
        'Order ID', 'Tracking Number', 'AWB Code', 'Courier Name', 'Courier Order ID',
        'Buyer Name', 'Buyer Email', 'Farmer Name', 'Farmer Email',
        'Crop Name', 'Quantity', 'Total Amount',
        'Shipment Status', 'Order Status', 'Payment Status',
        'Package Weight (kg)', 'Package Dimensions (L×W×H cm)',
        'Pickup Address', 'Delivery Address',
        'Shipment Created', 'Estimated Delivery', 'Actual Delivery',
        'Delivery Confirmed', 'Delivery Attempts', 'Failure Reason',
        'Last API Sync', 'API Sync Status', 'Tracking URL'
    ])
    
    # Write data
    for order in shipments:
        dimensions = f"{order.package_length}×{order.package_width}×{order.package_height}" if all([
            order.package_length, order.package_width, order.package_height
        ]) else ''
        
        writer.writerow([
            order.id,
            order.tracking_number or '',
            order.awb_code or '',
            order.courier_name or '',
            order.courier_order_id or '',
            order.buyer.full_name or order.buyer.username,
            order.buyer.email,
            order.farmer_user.full_name or order.farmer_user.username,
            order.farmer_user.email,
            order.crop.name,
            order.quantity_requested,
            f"{order.total_amount:.2f}",
            order.shipment_status or '',
            order.status,
            order.payment_status,
            f"{order.package_weight:.2f}" if order.package_weight else '',
            dimensions,
            order.pickup_address or '',
            order.delivery_address or '',
            order.shipment_created_at.strftime('%Y-%m-%d %H:%M:%S') if order.shipment_created_at else '',
            order.estimated_delivery_date.strftime('%Y-%m-%d') if order.estimated_delivery_date else '',
            order.actual_delivery_date.strftime('%Y-%m-%d %H:%M:%S') if order.actual_delivery_date else '',
            'Yes' if order.delivery_confirmed_by_buyer else 'No',
            order.delivery_attempts or 0,
            order.delivery_failure_reason or '',
            order.last_api_sync.strftime('%Y-%m-%d %H:%M:%S') if order.last_api_sync else '',
            order.api_sync_status or '',
            order.courier_tracking_url or ''
        ])
    
    # Create response
    output = make_response(si.getvalue())
    output.headers["Content-Disposition"] = "attachment; filename=shipments_export.csv"
    output.headers["Content-type"] = "text/csv"
    
    return output
