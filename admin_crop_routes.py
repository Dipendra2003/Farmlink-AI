"""
FarmLink AI - Admin Crop Management Routes
Handles crop approval workflow and admin crop management
"""
from datetime import datetime
from flask import render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from app import app, db
from models import Crop, User, Order
from forms import CropForm
from role_hierarchy import admin_required
from email_service import EmailService
from security_enhancements import log_admin_action
import logging

logger = logging.getLogger(__name__)
email_service = EmailService()


@app.route('/admin/crops')
@login_required
@admin_required
def admin_crops():
    """Admin crop listing with approval workflow"""
    page = request.args.get('page', 1, type=int)
    per_page = 20
    
    # Get filter parameters
    status_filter = request.args.get('status', 'all')
    approval_filter = request.args.get('approval', 'all')
    search_query = request.args.get('search', '')
    
    # Build query
    query = Crop.query
    
    # Apply filters
    if status_filter != 'all':
        query = query.filter_by(status=status_filter)
    
    if approval_filter != 'all':
        query = query.filter_by(approval_status=approval_filter)
    
    if search_query:
        query = query.filter(
            db.or_(
                Crop.name.ilike(f'%{search_query}%'),
                Crop.category.ilike(f'%{search_query}%'),
                Crop.location.ilike(f'%{search_query}%')
            )
        )
    
    # Order by created date (newest first)
    query = query.order_by(Crop.created_at.desc())
    
    # Paginate results
    crops = query.paginate(page=page, per_page=per_page, error_out=False)
    
    # Get statistics
    total_crops = Crop.query.count()
    pending_approval = Crop.query.filter_by(approval_status='pending').count()
    approved_crops = Crop.query.filter_by(approval_status='approved').count()
    rejected_crops = Crop.query.filter_by(approval_status='rejected').count()
    
    return render_template('admin/crops.html',
                         crops=crops,
                         total_crops=total_crops,
                         pending_approval=pending_approval,
                         approved_crops=approved_crops,
                         rejected_crops=rejected_crops,
                         status_filter=status_filter,
                         approval_filter=approval_filter,
                         search_query=search_query)


@app.route('/admin/crops/<int:crop_id>')
@login_required
@admin_required
def admin_crop_detail(crop_id):
    """View detailed crop information"""
    crop = Crop.query.get_or_404(crop_id)
    
    # Get related orders
    orders = Order.query.filter_by(crop_id=crop_id).order_by(Order.created_at.desc()).all()
    
    return render_template('admin/crop_detail.html', crop=crop, orders=orders)


@app.route('/admin/crops/<int:crop_id>/approve', methods=['POST'])
@login_required
@admin_required
@log_admin_action('approve_crop', 'crop')
def approve_crop(crop_id):
    """Approve a crop listing"""
    crop = Crop.query.get_or_404(crop_id)
    
    if crop.approval_status == 'approved':
        flash('This crop is already approved.', 'info')
        return redirect(url_for('admin_crop_detail', crop_id=crop_id))
    
    try:
        # Update crop approval status
        crop.approval_status = 'approved'
        crop.approved_by = current_user.id
        crop.approved_at = datetime.utcnow()
        crop.rejection_reason = None  # Clear any previous rejection reason
        crop.status = 'available'  # Make it available in marketplace
        
        db.session.commit()
        
        # Send approval notification to farmer
        try:
            email_service.send_crop_notification(
                user=crop.farmer,
                crop=crop,
                notification_type="crop_approved",
                details=f"Your crop listing '{crop.name}' has been approved and is now visible in the marketplace."
            )
        except Exception as e:
            logger.error(f"Failed to send approval email: {str(e)}")
        
        flash(f'Crop "{crop.name}" has been approved successfully!', 'success')
        logger.info(f"Admin {current_user.username} approved crop {crop_id}")
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error approving crop {crop_id}: {str(e)}")
        flash('An error occurred while approving the crop.', 'danger')
    
    return redirect(url_for('admin_crops'))


@app.route('/admin/crops/<int:crop_id>/reject', methods=['POST'])
@login_required
@admin_required
@log_admin_action('reject_crop', 'crop')
def reject_crop(crop_id):
    """Reject a crop listing with reason"""
    crop = Crop.query.get_or_404(crop_id)
    
    rejection_reason = request.form.get('rejection_reason', '').strip()
    
    if not rejection_reason:
        flash('Please provide a reason for rejection.', 'warning')
        return redirect(url_for('admin_crop_detail', crop_id=crop_id))
    
    try:
        # Update crop approval status
        crop.approval_status = 'rejected'
        crop.rejection_reason = rejection_reason
        crop.approved_by = current_user.id
        crop.approved_at = datetime.utcnow()
        crop.status = 'rejected'  # Remove from marketplace
        
        db.session.commit()
        
        # Send rejection notification to farmer
        try:
            email_service.send_crop_notification(
                user=crop.farmer,
                crop=crop,
                notification_type="crop_rejected",
                details=f"Your crop listing '{crop.name}' was not approved. Reason: {rejection_reason}"
            )
        except Exception as e:
            logger.error(f"Failed to send rejection email: {str(e)}")
        
        flash(f'Crop "{crop.name}" has been rejected.', 'info')
        logger.info(f"Admin {current_user.username} rejected crop {crop_id}: {rejection_reason}")
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error rejecting crop {crop_id}: {str(e)}")
        flash('An error occurred while rejecting the crop.', 'danger')
    
    return redirect(url_for('admin_crops'))


@app.route('/admin/crops/<int:crop_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
@log_admin_action('edit_crop', 'crop')
def admin_edit_crop(crop_id):
    """Admin edit crop details"""
    crop = Crop.query.get_or_404(crop_id)
    form = CropForm(obj=crop)
    
    if form.validate_on_submit():
        try:
            # Update crop details
            crop.name = form.name.data.strip()
            crop.category = form.category.data
            crop.description = form.description.data.strip() if form.description.data else None
            crop.quantity = float(form.quantity.data)
            crop.unit = form.unit.data
            crop.price_per_unit = float(form.price_per_unit.data)
            crop.harvest_date = form.harvest_date.data
            crop.location = form.location.data.strip()
            crop.updated_at = datetime.utcnow()
            
            # Handle image upload if provided
            if form.image.data:
                from storage_utils import save_image, delete_image
                new_image_url = save_image(form.image.data)
                if new_image_url:
                    # Delete old image if exists
                    if crop.image_url and crop.image_url != 'uploads/crops/default-crop.jpg':
                        delete_image(crop.image_url)
                    crop.image_url = new_image_url
            
            db.session.commit()
            
            # Notify farmer of admin edit
            try:
                email_service.send_crop_notification(
                    user=crop.farmer,
                    crop=crop,
                    notification_type="crop_updated",
                    details=f"Your crop listing '{crop.name}' was updated by an administrator."
                )
            except Exception as e:
                logger.error(f"Failed to send update notification: {str(e)}")
            
            flash('Crop details updated successfully!', 'success')
            logger.info(f"Admin {current_user.username} edited crop {crop_id}")
            return redirect(url_for('admin_crop_detail', crop_id=crop_id))
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error updating crop {crop_id}: {str(e)}")
            flash('An error occurred while updating the crop.', 'danger')
    
    return render_template('admin/edit_crop.html', form=form, crop=crop)


@app.route('/admin/crops/<int:crop_id>/delete', methods=['POST'])
@login_required
@admin_required
def admin_delete_crop(crop_id):
    """Admin delete crop listing"""
    crop = Crop.query.get_or_404(crop_id)
    
    # Check for active orders
    active_orders = Order.query.filter_by(crop_id=crop_id).filter(
        Order.status.in_(['pending', 'paid', 'accepted'])
    ).count()
    
    if active_orders > 0:
        flash(f'Cannot delete crop with {active_orders} active order(s).', 'warning')
        return redirect(url_for('admin_crop_detail', crop_id=crop_id))
    
    try:
        crop_name = crop.name
        farmer = crop.farmer
        
        # Delete associated image
        if crop.image_url and crop.image_url != 'uploads/crops/default-crop.jpg':
            from storage_utils import delete_image
            delete_image(crop.image_url)
        
        # Delete crop
        db.session.delete(crop)
        db.session.commit()
        
        # Notify farmer
        try:
            email_service.send_crop_notification(
                user=farmer,
                crop=crop,
                notification_type="crop_deleted",
                details=f"Your crop listing '{crop_name}' was removed by an administrator."
            )
        except Exception as e:
            logger.error(f"Failed to send deletion notification: {str(e)}")
        
        flash(f'Crop "{crop_name}" has been deleted successfully.', 'success')
        logger.info(f"Admin {current_user.username} deleted crop {crop_id}")
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error deleting crop {crop_id}: {str(e)}")
        flash('An error occurred while deleting the crop.', 'danger')
    
    return redirect(url_for('admin_crops'))


@app.route('/admin/crops/bulk-approve', methods=['POST'])
@login_required
@admin_required
def bulk_approve_crops():
    """Bulk approve multiple crops"""
    crop_ids = request.form.getlist('crop_ids[]')
    
    if not crop_ids:
        return jsonify({'success': False, 'message': 'No crops selected'}), 400
    
    try:
        approved_count = 0
        for crop_id in crop_ids:
            crop = Crop.query.get(int(crop_id))
            if crop and crop.approval_status == 'pending':
                crop.approval_status = 'approved'
                crop.approved_by = current_user.id
                crop.approved_at = datetime.utcnow()
                crop.status = 'available'
                
                # Send notification
                try:
                    email_service.send_crop_notification(
                        user=crop.farmer,
                        crop=crop,
                        notification_type="crop_approved",
                        details=f"Your crop listing '{crop.name}' has been approved."
                    )
                except Exception as e:
                    logger.error(f"Failed to send bulk approval email for crop {crop_id}: {str(e)}")
                
                approved_count += 1
        
        db.session.commit()
        logger.info(f"Admin {current_user.username} bulk approved {approved_count} crops")
        
        return jsonify({
            'success': True,
            'message': f'Successfully approved {approved_count} crop(s)'
        })
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error in bulk approval: {str(e)}")
        return jsonify({'success': False, 'message': 'An error occurred'}), 500
