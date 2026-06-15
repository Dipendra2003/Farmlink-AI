from flask import render_template, redirect, url_for, flash, request, abort, jsonify
from flask_login import login_user, logout_user, login_required, current_user
from flask_mail import Message as FlaskMailMessage
from app import app, db, mail
from extensions import limiter
import os
from models import User, Crop, Order, OrderStatusHistory, Message, WeatherData, ExpertPost, ExpertReply, LearningArticle, UserRating, Analytics, WeatherData
from forms import RegistrationForm, LoginForm, CropForm, OrderForm, MessageForm, ProfileForm, SearchForm, ExpertPostForm, RatingForm, ForgotPasswordForm, ResetPasswordForm, OTPVerificationForm, ContactForm, LearningArticleForm
import role_hierarchy
from role_hierarchy import admin_required, is_farmer_or_manager, is_buyer_or_manager, farmer_required, buyer_required
from utils import get_weather_data, format_datetime
from email_service import OTPService
from datetime import datetime
import logging

# Initialize email services
otp_service = OTPService()

# Basic Pages
@app.route('/about')
def about():
    return render_template('pages/about.html')

@app.route('/contact', methods=['GET', 'POST'])
def contact():
    form = ContactForm()
    if form.validate_on_submit():
        try:
            # Create email message to admin
            admin_msg = FlaskMailMessage(
                subject=f"New Contact Form Submission - FarmLink AI",
                sender=app.config['MAIL_DEFAULT_SENDER'],
                recipients=[app.config['MAIL_USERNAME']],
                reply_to=form.email.data,
                body=f"""
New contact form submission received:

Name: {form.name.data}
Email: {form.email.data}
Subject: {form.subject.data}

Message:
{form.message.data}

Sent at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
                """
            )
            
            # Send admin notification
            mail.send(admin_msg)
            
            # Send confirmation to user
            user_msg = FlaskMailMessage(
                subject="Thank you for contacting FarmLink AI",
                sender=app.config['MAIL_DEFAULT_SENDER'],
                recipients=[form.email.data],
                body=f"""
Dear {form.name.data},

Thank you for contacting FarmLink AI. We have received your message and will get back to you soon.

Your message details:
Subject: {form.subject.data}
Message: {form.message.data}

Best regards,
The FarmLink AI Team
                """
            )
            
            mail.send(user_msg)
            
            flash('Thank you for your message! We will get back to you soon.', 'success')
            return redirect(url_for('contact'))
            
        except Exception as e:
            app.logger.error(f"Error sending contact form: {str(e)}")
            # Log more detailed error information
            import traceback
            app.logger.error(f"Detailed error: {traceback.format_exc()}")
            flash('Sorry, there was a problem sending your message. Please try again later.', 'danger')
            
    return render_template('pages/contact.html', form=form)

@app.route('/terms')
def terms():
    return render_template('pages/terms.html')

@app.route('/privacy')
def privacy():
    return render_template('pages/privacy.html')

@app.route('/help')
def help_center():
    return render_template('pages/help.html')

@app.route('/faq')
def faq():
    return render_template('pages/faq.html')

@app.route('/testing-mode')
def testing_mode():
    return render_template('pages/testing_mode.html')

# Home Page
@app.route('/')
def index():
    # Show the public homepage to everyone - only show approved crops
    recent_crops = Crop.query.filter_by(status='available', approval_status='approved').order_by(Crop.created_at.desc()).limit(6).all()
    
    # Get active farmers (both regular farmers and manager_farmer)
    total_farmers = User.query.filter(
        User.active == True,
        User.role.in_(['farmer', 'manager_farmer'])
    ).count()
    
    # Get active buyers (both regular buyers and manager_buyer)
    total_buyers = User.query.filter(
        User.active == True,
        User.role.in_(['buyer', 'manager_buyer'])
    ).count()
    
    # Get currently available crops
    total_crops = Crop.query.filter_by(status='available').count()
    
    return render_template('index.html', 
                         recent_crops=recent_crops,
                         total_farmers=total_farmers,
                         total_buyers=total_buyers,
                         total_crops=total_crops)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        flash('You are already registered and logged in.', 'info')
        return redirect(url_for('index'))
    
    form = RegistrationForm()
    if form.validate_on_submit():
        user = User(
            username=form.username.data,
            email=form.email.data,
            full_name=form.full_name.data,
            phone=form.phone.data,
            location=form.location.data,
            role=form.role.data,
            email_verified=False,  # Set to False by default
            active=True  # Account is active but not verified
        )
        user.set_password(form.password.data)
        
        db.session.add(user)
        db.session.commit()
        
        # Send verification OTP
        try:
            otp_service.send_verification_otp(user)
            flash('Registration successful! Please check your email for the verification code.', 'success')
            return redirect(url_for('verify_email', user_id=user.id))
        except Exception as e:
            logging.error(f"Failed to send verification email: {str(e)}")
            flash('Registration successful, but we could not send the verification email. Please contact support.', 'warning')
            return redirect(url_for('login'))
    
    return render_template('auth/register.html', form=form)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    form = LoginForm()
    if form.validate_on_submit():
        identifier = form.identifier.data
        ip_address = request.remote_addr
        user_agent = request.user_agent.string
        
        # Always apply rate limiting regardless of role
        from security_utils import rate_limit_login
        if not rate_limit_login(ip_address):
            flash('Too many login attempts. Please try again later.', 'danger')
            return render_template('auth/login.html', form=form)
            
        # Try to find user by username, email, or phone
        user = User.query.filter(
            db.or_(
                User.username == identifier,
                User.email == identifier,
                User.phone == identifier
            )
        ).first()
        
        login_success = False
        
        if user and user.check_password(form.password.data):
            if not user.is_active:
                flash('Your account has been deactivated. Please contact support.', 'danger')
                login_success = False
            # Check email verification status (admins bypass this check)
            elif not user.email_verified and user.role != 'admin':
                flash('Please verify your email address before logging in. A verification code has been sent to your email.', 'warning')
                return redirect(url_for('verify_email', user_id=user.id))
            # Temporarily allow admin login without HTTPS for development
            # Allow admin login in development
            # Allow admin login in development mode
            elif user.role == 'admin' and not request.is_secure and os.environ.get('FLASK_ENV') == 'production':
                flash('Admin login requires a secure connection in production.', 'danger')
                login_success = False
            else:
                login_success = True
                login_user(user)
                next_page = request.args.get('next')
                if next_page and not next_page.startswith('/'):
                    next_page = None  # Prevent open redirect
                
                # Update last login time and increment login count
                user.last_login = datetime.utcnow()
                user.login_count += 1
                db.session.commit()
                
                # Clear failed login attempts for this IP if successful
                from security_utils import clear_login_attempts
                clear_login_attempts(ip_address)

                # Send login alert
                try:
                    from email_service import EmailService
                    email_service = EmailService()
                    email_service.send_login_alert(user, ip_address, user_agent)
                except Exception as e:
                    logging.error(f"Failed to send login alert: {str(e)}")
            
                flash(f'Welcome back, {user.full_name}!', 'success')
                
                # Role-based redirect
                role_routes = {
                    'admin': 'admin_dashboard',
                    'farmer': 'farmer_dashboard',
                    'buyer': 'buyer_dashboard'
                }
                target_route = role_routes.get(user.role)
                
                if not target_route:
                    flash('Invalid user role. Please contact support.', 'danger')
                    return redirect(url_for('index'))
                
                # Always redirect to role-specific dashboard after login
                return redirect(url_for(target_route))
        else:
            if user:
                app.logger.warning(f"Password check FAILED for user: {user.username}")
            flash('Invalid username or password.', 'danger')
        
        # Log the attempt
        from security_utils import log_login_attempt
        log_login_attempt(
            user_id=user.id if user else None,
            ip_address=ip_address,
            success=login_success,
            user_agent=user_agent
        )
    
    return render_template('auth/login.html', form=form)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('index'))

@app.route('/dashboard')
@login_required
def dashboard():
    """Central dashboard router that redirects to role-specific dashboards"""
    # Define role-specific dashboard routes
    role_routes = {
        'farmer': 'farmer_dashboard',
        'buyer': 'buyer_dashboard',
        'admin': 'admin_dashboard'
    }
    
    # Get the appropriate dashboard route for the user's role
    target_route = role_routes.get(current_user.role)
    
    if target_route:
        return redirect(url_for(target_route))
    
    # Users without a valid role are sent to the public home page
    flash('Access denied. Invalid user role.', 'danger')
    return redirect(url_for('index'))

@app.route('/farmer/dashboard')
@farmer_required
def farmer_dashboard():
    try:
        # Get farmer's crops
        my_crops = Crop.query.filter_by(farmer_id=current_user.id).order_by(Crop.created_at.desc()).all()
        
        # Get recent orders for farmer's crops (as seller)
        recent_orders = Order.query.filter_by(farmer_id=current_user.id).order_by(Order.created_at.desc()).limit(5).all()
        
        # Get recent purchases made by farmer (as buyer)
        my_purchases = Order.query.filter_by(buyer_id=current_user.id).order_by(Order.created_at.desc()).limit(5).all()
        
        # Get unread messages (excluding archived)
        unread_messages = Message.query.filter_by(recipient_id=current_user.id, is_read=False, is_archived=False).count()
        
        # Get weather data for farmer's location
        weather_data = get_weather_data(current_user.location)
        
        # Calculate total earnings from delivered orders (as seller)
        # Only count delivered orders with paid status
        total_earnings = db.session.query(db.func.sum(Order.total_amount)).filter(
            Order.farmer_id == current_user.id,
            Order.status == 'delivered',
            Order.payment_status == 'paid'
        ).scalar() or 0
        
        # Calculate total spent on purchases (as buyer)
        # Only count delivered orders with paid status
        total_spent = db.session.query(db.func.sum(Order.total_amount)).filter(
            Order.buyer_id == current_user.id,
            Order.status == 'delivered',
            Order.payment_status == 'paid'
        ).scalar() or 0
        
        # Get pest detection statistics
        from models import PestDiseaseAnalysis
        from datetime import datetime, timedelta
        
        # Count recent analyses (last 30 days)
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        recent_analyses_count = PestDiseaseAnalysis.query.filter_by(
            user_id=current_user.id
        ).filter(
            PestDiseaseAnalysis.created_at >= thirty_days_ago
        ).count()
        
        # Check for critical severity analyses
        critical_analyses = PestDiseaseAnalysis.query.filter_by(
            user_id=current_user.id,
            severity_level='critical'
        ).filter(
            PestDiseaseAnalysis.created_at >= thirty_days_ago
        ).count()
        
        # Get seller reputation
        from models import SellerReputation, ProductRating
        seller_reputation = SellerReputation.query.filter_by(seller_id=current_user.id).first()
        
        # Get recent ratings received
        recent_ratings_received = ProductRating.query.join(
            Crop, ProductRating.product_id == Crop.id
        ).filter(
            Crop.farmer_id == current_user.id,
            ProductRating.is_hidden == False
        ).order_by(
            ProductRating.created_at.desc()
        ).limit(5).all()
        
        # Get shipment data for farmer
        # Count active shipments (not delivered)
        active_shipments_count = Order.query.filter_by(
            farmer_id=current_user.id
        ).filter(
            Order.tracking_number.isnot(None),
            Order.shipment_status.notin_(['delivered', 'failed', 'returned'])
        ).count()
        
        # Get 5 most recent shipments
        recent_shipments = Order.query.filter_by(
            farmer_id=current_user.id
        ).filter(
            Order.tracking_number.isnot(None)
        ).order_by(
            Order.shipment_created_at.desc()
        ).limit(5).all()
        
        return render_template('dashboard/farmer.html',
                             my_crops=my_crops,
                             recent_orders=recent_orders,
                             my_purchases=my_purchases,
                             unread_messages=unread_messages,
                             weather_data=weather_data,
                             total_earnings=total_earnings,
                             total_spent=total_spent,
                             recent_analyses_count=recent_analyses_count,
                             critical_analyses=critical_analyses,
                             seller_reputation=seller_reputation,
                             recent_ratings_received=recent_ratings_received,
                             active_shipments_count=active_shipments_count,
                             recent_shipments=recent_shipments)
    except Exception as e:
        app.logger.error(f"Error in farmer_dashboard: {str(e)}")
        import traceback
        app.logger.error(traceback.format_exc())
        flash('An error occurred while loading the dashboard. Please try again.', 'error')
        return redirect(url_for('index'))

@app.route('/buyer/dashboard')
@buyer_required
def buyer_dashboard():
    
    # Get buyer's recent orders
    my_orders = Order.query.filter_by(buyer_id=current_user.id).order_by(Order.created_at.desc()).limit(10).all()
    
    # Get unread messages (excluding archived)
    unread_messages = Message.query.filter_by(recipient_id=current_user.id, is_read=False, is_archived=False).count()
    
    # Get available crops in buyer's area
    nearby_crops = Crop.query.filter_by(status='available', location=current_user.location).limit(6).all()
    
    # Calculate total spent on delivered orders
    total_spent = db.session.query(db.func.sum(Order.total_amount)).filter(
        Order.buyer_id == current_user.id,
        Order.status == 'delivered',
        Order.payment_status == 'paid'
    ).scalar() or 0
    
    # Get pending ratings - delivered orders without ratings
    from models import ProductRating
    from datetime import datetime, timedelta
    
    # Get delivered orders from the last 90 days
    ninety_days_ago = datetime.utcnow() - timedelta(days=90)
    completed_orders = Order.query.filter_by(
        buyer_id=current_user.id,
        status='delivered',
        payment_status='paid'
    ).filter(
        Order.updated_at >= ninety_days_ago
    ).all()
    
    # Filter out orders that already have ratings
    pending_ratings = []
    for order in completed_orders:
        existing_rating = ProductRating.query.filter_by(order_id=order.id).first()
        if not existing_rating:
            pending_ratings.append(order)
    
    return render_template('dashboard/buyer.html',
                         my_orders=my_orders,
                         unread_messages=unread_messages,
                         nearby_crops=nearby_crops,
                         total_spent=total_spent,
                         pending_ratings=pending_ratings)

@app.route('/admin/dashboard')
@login_required
@admin_required
def admin_dashboard():
    # Get system statistics
    total_users = User.query.count()
    total_farmers = User.query.filter_by(role='farmer').count()
    total_buyers = User.query.filter_by(role='buyer').count()
    total_crops = Crop.query.count()
    total_orders = Order.query.count()
    pending_orders = Order.query.filter(Order.status.in_(['pending', 'paid'])).count()
    
    # Get KYC statistics
    from kyc_service import KYCService
    from models import SellerKYC
    kyc_stats = {
        'pending': SellerKYC.query.filter_by(status='pending').count(),
        'verified': SellerKYC.query.filter_by(status='verified').count(),
        'rejected': SellerKYC.query.filter_by(status='rejected').count()
    }
    
    # Get recent activity
    recent_users = User.query.order_by(User.created_at.desc()).limit(5).all()
    recent_crops = Crop.query.order_by(Crop.created_at.desc()).limit(5).all()
    recent_orders = Order.query.order_by(Order.created_at.desc()).limit(5).all()
    
    return render_template('dashboard/admin.html',
                         total_users=total_users,
                         total_farmers=total_farmers,
                         total_buyers=total_buyers,
                         total_crops=total_crops,
                         total_orders=total_orders,
                         pending_orders=pending_orders,
                         kyc_stats=kyc_stats,
                         recent_users=recent_users,
                         recent_crops=recent_crops,
                         recent_orders=recent_orders)

from storage_utils import save_image, delete_image
import os

@app.route('/crops/add', methods=['GET', 'POST'])
@farmer_required
@role_hierarchy.kyc_required
def add_crop():
    
    form = CropForm()
    if form.validate_on_submit():
        try:
            # Handle image upload first
            image_path = None
            if form.image.data:
                try:
                    image_path = save_image(form.image.data)
                    if not image_path:
                        app.logger.warning('Failed to save image, using default')
                        image_path = os.path.join('uploads', 'crops', 'default-crop.jpg')
                except Exception as img_err:
                    app.logger.error(f'Error saving image: {str(img_err)}')
                    flash('Failed to process image. Using default image.', 'warning')
                    image_path = os.path.join('uploads', 'crops', 'default-crop.jpg')
            
            # Validate input fields
            try:
                # Validate numeric fields
                try:
                    quantity = float(form.quantity.data)
                    price = float(form.price_per_unit.data)
                except (ValueError, TypeError):
                    raise ValueError("Please enter valid numbers for quantity and price")

                if quantity <= 0:
                    raise ValueError("Quantity must be greater than 0")
                if price <= 0:
                    raise ValueError("Price must be greater than 0")
                
                # Validate text fields
                if not form.name.data or not form.name.data.strip():
                    raise ValueError("Crop name cannot be empty")
                if len(form.name.data.strip()) < 2:
                    raise ValueError("Crop name must be at least 2 characters long")
                if not form.location.data or not form.location.data.strip():
                    raise ValueError("Location cannot be empty")
                
                # Validate dates
                harvest_date = form.harvest_date.data
                
                # Convert datetime to date if needed
                if isinstance(harvest_date, datetime):
                    harvest_date = harvest_date.date()
                
                if harvest_date is None:
                    raise ValueError("Harvest date is required")
                
                # Past dates are now allowed, no need for date comparison
                
            except ValueError as e:
                flash(str(e), 'danger')
                return render_template('crops/add_crop.html', form=form)
            
            # Create new crop with sanitized data
            try:
                crop = Crop(
                    name=form.name.data.strip(),
                    category=form.category.data,
                    description=form.description.data.strip() if form.description.data else None,
                    quantity=quantity,
                    unit=form.unit.data,
                    price_per_unit=price,
                    harvest_date=form.harvest_date.data,
                    location=form.location.data.strip(),
                    image_url=image_path,
                    farmer=current_user,
                    status='pending',  # Set to pending until admin approves
                    approval_status='pending',  # Explicitly set approval status
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow()
                )
                
                db.session.add(crop)
                db.session.commit()
                app.logger.info(f'Successfully added crop: {crop.name} with image: {image_path}')
                
                # Send crop added notification
                try:
                    from email_service import email_service
                    email_service.send_crop_notification(
                        user=current_user,
                        crop=crop,
                        notification_type="crop_added",
                        details=f"Successfully listed {crop.name} for sale at ₹{crop.price_per_unit}/{crop.unit}"
                    )
                except Exception as notify_err:
                    app.logger.error(f'Error sending crop notification: {str(notify_err)}')
                    # Don't roll back the transaction, just log the notification error
                
                flash('Your crop has been added successfully!', 'success')
                return redirect(url_for('my_crops'))
                
            except Exception as e:
                db.session.rollback()
                app.logger.error(f'Error adding crop: {str(e)}')
                app.logger.exception('Traceback for crop addition error:')
                
                error_message = 'An error occurred while adding your crop. Please try again.'
                if 'unique constraint' in str(e).lower():
                    error_message = 'A crop with this name already exists.'
                elif 'foreign key constraint' in str(e).lower():
                    error_message = 'Invalid reference detected.'
                elif 'not a valid float' in str(e).lower() or 'invalid literal for float()' in str(e).lower():
                    error_message = 'Please enter valid numbers for quantity and price.'
                elif 'check constraint' in str(e).lower():
                    error_message = 'Invalid values provided. Please check your input.'
                
                flash(error_message, 'danger')
                return render_template('crops/add_crop.html', form=form)
                
        except Exception as e:
            db.session.rollback()
            app.logger.error(f'Unexpected error while adding crop: {str(e)}')
            app.logger.exception('Detailed error traceback:')
            flash('An unexpected error occurred. Please try again later.', 'danger')
            return render_template('crops/add_crop.html', form=form)
    
    return render_template('crops/add_crop.html', form=form)

@app.route('/crops/<int:crop_id>/edit', methods=['GET', 'POST'])
@farmer_required
@role_hierarchy.kyc_required
def edit_crop(crop_id):
    
    crop = Crop.query.get_or_404(crop_id)
    if crop.farmer != current_user:
        flash('You can only edit your own crops.', 'danger')
        return redirect(url_for('my_crops'))
    
    form = CropForm(obj=crop)
    if form.validate_on_submit():
        try:
            # Handle image update first
            if form.image.data:
                try:
                    new_image_url = save_image(form.image.data)
                    if not new_image_url:
                        raise ValueError('Failed to save new image')
                    
                    # Only delete old image after successfully saving new one
                    if crop.image_url and crop.image_url != 'uploads/crops/default-crop.jpg':
                        if delete_image(crop.image_url):
                            app.logger.info(f'Successfully deleted old image: {crop.image_url}')
                        else:
                            app.logger.warning(f'Failed to delete old image: {crop.image_url}')
                    
                    crop.image_url = new_image_url
                    app.logger.info(f'Successfully updated image to: {new_image_url}')
                except Exception as img_err:
                    app.logger.error(f'Error handling image: {str(img_err)}')
                    flash('Failed to update image. Please try again with a different image.', 'warning')
                    # Continue with other updates even if image update fails

            try:
                # Update fields with validation
                crop.name = form.name.data.strip()
                crop.category = form.category.data
                crop.description = form.description.data.strip() if form.description.data else None
                crop.quantity = float(form.quantity.data)
                crop.unit = form.unit.data
                crop.price_per_unit = float(form.price_per_unit.data)
                crop.harvest_date = form.harvest_date.data
                crop.location = form.location.data.strip()
                crop.updated_at = datetime.utcnow()
                
                # Save all changes
                db.session.commit()
                
                # Send notification about update
                try:
                    from email_service import email_service
                    email_service.send_crop_notification(
                        user=current_user,
                        crop=crop,
                        notification_type="crop_updated",
                        details=f"Successfully updated {crop.name} details"
                    )
                except Exception as notify_err:
                    app.logger.warning(f'Failed to send notification: {str(notify_err)}')
                    # Don't raise the error as notification is not critical
                
                flash('Your crop has been updated successfully!', 'success')
                return redirect(url_for('my_crops'))
            
            except ValueError as ve:
                db.session.rollback()
                flash(str(ve), 'danger')
                return render_template('crops/edit_crop.html', form=form, crop=crop)
            except Exception as e:
                db.session.rollback()
                app.logger.error(f'Error updating crop data: {str(e)}')
                app.logger.exception('Detailed traceback:')
                flash('An error occurred while updating your crop. Please check your input and try again.', 'danger')
                return render_template('crops/edit_crop.html', form=form, crop=crop)
                
        except Exception as e:
            db.session.rollback()
            app.logger.error(f'Error updating crop: {str(e)}')
            app.logger.exception('Detailed traceback:')
            
            error_message = 'An unexpected error occurred. Please try again.'
            if 'unique constraint' in str(e).lower():
                error_message = 'A crop with this name already exists.'
            elif 'foreign key constraint' in str(e).lower():
                error_message = 'Invalid reference detected.'
            elif 'not a valid float' in str(e).lower():
                error_message = 'Please enter valid numbers for quantity and price.'
            
            flash(error_message, 'danger')
            return render_template('crops/edit_crop.html', form=form, crop=crop)
    
    # If form validation failed, render the form again with errors
    return render_template('crops/edit_crop.html', form=form, crop=crop)

@app.route('/crops/<int:crop_id>/delete', methods=['POST'])
@farmer_required
def delete_crop(crop_id):
    
    crop = Crop.query.get_or_404(crop_id)
    if crop.farmer != current_user:
        flash('You can only delete your own crops.', 'danger')
        return redirect(url_for('my_crops'))
    
    # Check if there are any orders (we cannot delete crops with order history)
    total_orders = Order.query.filter_by(crop_id=crop.id).count()
    if total_orders > 0:
        flash('Cannot delete crop with order history. Please contact support if you need to remove this listing.', 'warning')
        return redirect(url_for('my_crops'))

    # Delete associated image if exists
    if crop.image_url:
        try:
            if delete_image(crop.image_url):
                app.logger.info(f'Successfully deleted image: {crop.image_url}')
            else:
                app.logger.warning(f'Failed to delete image: {crop.image_url}')
        except Exception as img_err:
            app.logger.warning(f'Error deleting image: {str(img_err)}')
            # Continue even if image deletion fails
    
    # Send crop deletion notification before deleting
    try:
        from email_service import email_service
        email_service.send_crop_notification(
            user=current_user,
            crop=crop,
            notification_type="crop_deleted",
            details=f"Successfully removed listing for {crop.name}"
        )
    except Exception as notify_err:
        app.logger.warning(f'Failed to send notification: {str(notify_err)}')
        # Don't raise the error as notification is not critical
    
    # Delete crop from database
    try:
        db.session.delete(crop)
        db.session.commit()
        app.logger.info(f'Successfully deleted crop: {crop.name} (ID: {crop.id})')
        flash('Crop has been deleted successfully.', 'success')
    except Exception as e:
        db.session.rollback()
        app.logger.error(f'Error deleting crop from database: {str(e)}')
        import traceback
        app.logger.error(f'Traceback: {traceback.format_exc()}')
        flash('An error occurred while deleting the crop.', 'danger')
    
    return redirect(url_for('my_crops'))

@app.route('/my-crops')
@farmer_required
def my_crops():
    
    try:
        crops = Crop.query.filter_by(farmer=current_user).order_by(Crop.created_at.desc()).all()
        return render_template('crops/my_crops.html', crops=crops)
    except Exception as e:
        flash('An error occurred while fetching your crops.', 'danger')
        app.logger.error(f'Error fetching crops: {str(e)}')
        return redirect(url_for('dashboard'))

@app.route('/marketplace')
def marketplace():
    form = SearchForm()
    page = request.args.get('page', 1, type=int)
    per_page = 12
    
    # Build query based on search parameters - only show approved crops
    query = Crop.query.filter_by(status='available', approval_status='approved')
    
    # Apply filters from URL parameters
    search_query = request.args.get('query', '')
    category = request.args.get('category', '')
    location = request.args.get('location', '')
    min_price = request.args.get('min_price', type=float)
    max_price = request.args.get('max_price', type=float)
    
    if search_query:
        query = query.filter(Crop.name.ilike(f'%{search_query}%'))
    
    if category and category != 'all':
        query = query.filter(Crop.category == category)
    
    if location:
        query = query.filter(Crop.location.ilike(f'%{location}%'))
    
    if min_price is not None:
        query = query.filter(Crop.price_per_unit >= min_price)
    
    if max_price is not None:
        query = query.filter(Crop.price_per_unit <= max_price)
    
    # Order by creation date (newest first)
    query = query.order_by(Crop.created_at.desc())
    
    crops = query.paginate(page=page, per_page=per_page, error_out=False)
    
    # Get cart items for current user to show which items are already in cart
    cart_items = {}
    if current_user.is_authenticated:
        from order_service import CartService
        cart = CartService.get_or_create_cart(current_user.id)
        if cart:
            from models import CartItem
            items = CartItem.query.filter_by(cart_id=cart.id).all()
            cart_items = {item.crop_id: item.quantity for item in items}
    
    return render_template('marketplace/browse.html', crops=crops, form=form, cart_items=cart_items)

@app.route('/marketplace/crop/<int:crop_id>')
def product_detail(crop_id):
    crop = Crop.query.get_or_404(crop_id)
    
    # Get other crops from the same farmer
    other_crops = Crop.query.filter_by(farmer_id=crop.farmer_id, status='available').filter(Crop.id != crop_id).limit(4).all()
    
    # Get pest and disease analyses linked to this crop
    from models import PestDiseaseAnalysis
    pest_analyses = PestDiseaseAnalysis.query.filter_by(
        crop_id=crop_id
    ).order_by(
        PestDiseaseAnalysis.created_at.desc()
    ).limit(5).all()
    
    # Get crop health trends if user is the farmer
    health_trends = None
    if current_user.is_authenticated and current_user.id == crop.farmer_id:
        from utils import get_crop_health_trends
        health_trends = get_crop_health_trends(crop_id)
    
    # Get product ratings
    from models import ProductRating
    product_ratings = ProductRating.query.filter_by(
        product_id=crop_id,
        is_hidden=False
    ).order_by(ProductRating.created_at.desc()).paginate(
        page=1, per_page=10, error_out=False
    )
    
    # Calculate rating statistics
    average_rating = 0
    total_ratings = 0
    rating_distribution = {5: 0, 4: 0, 3: 0, 2: 0, 1: 0}
    
    all_ratings = ProductRating.query.filter_by(
        product_id=crop_id,
        is_hidden=False
    ).all()
    
    if all_ratings:
        total_ratings = len(all_ratings)
        average_rating = sum(r.rating for r in all_ratings) / total_ratings
        for rating in all_ratings:
            rating_distribution[rating.rating] = rating_distribution.get(rating.rating, 0) + 1
    
    # Check if item is already in user's cart
    in_cart = False
    cart_quantity = 0
    if current_user.is_authenticated:
        from order_service import CartService
        cart = CartService.get_or_create_cart(current_user.id)
        if cart:
            from models import CartItem
            cart_item = CartItem.query.filter_by(cart_id=cart.id, crop_id=crop_id).first()
            if cart_item:
                in_cart = True
                cart_quantity = cart_item.quantity
    
    return render_template('marketplace/product_detail.html', 
                         crop=crop, 
                         other_crops=other_crops,
                         pest_analyses=pest_analyses,
                         health_trends=health_trends,
                         product_ratings=product_ratings,
                         average_rating=average_rating,
                         total_ratings=total_ratings,
                         rating_distribution=rating_distribution,
                         in_cart=in_cart,
                         cart_quantity=cart_quantity)

# ============================================================================
# CART ROUTES
# ============================================================================

@app.route('/cart')
@login_required
def view_cart():
    """Display cart contents - Only accessible by buyers and farmers"""
    from order_service import CartService
    from role_hierarchy import is_admin
    
    # Restrict admin access to cart
    if is_admin(current_user):
        flash('Cart functionality is not available for admin users. Use the admin panel to manage orders.', 'info')
        return redirect(url_for('admin_dashboard'))
    
    # Get or create cart for current user
    cart = CartService.get_or_create_cart(current_user.id)
    
    if not cart:
        flash('Error loading cart. Please try again.', 'danger')
        return redirect(url_for('marketplace'))
    
    # Get cart totals
    cart_data = CartService.get_cart_total(cart.id)
    
    return render_template('cart/view.html', 
                         cart=cart, 
                         cart_data=cart_data)


@app.route('/cart/add/<int:crop_id>', methods=['POST'])
@login_required
def add_to_cart(crop_id):
    """Add item to cart with rate limiting and security checks - Only accessible by buyers and farmers"""
    from order_service import CartService
    from error_handlers import Validator, ErrorHandler
    from flask_wtf.csrf import validate_csrf  # type: ignore
    from werkzeug.exceptions import BadRequest
    from security_enhancements import RateLimiter
    from role_hierarchy import is_admin
    
    # Check if this is an AJAX request
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    
    # Restrict admin access to cart
    if is_admin(current_user):
        if is_ajax:
            return jsonify({
                'success': False,
                'error': 'Cart functionality is not available for admin users.',
                'error_code': 'ADMIN_ACCESS_DENIED'
            }), 403
        flash('Cart functionality is not available for admin users.', 'warning')
        return redirect(url_for('admin_dashboard'))
    
    # Apply rate limiting (20 requests per minute per user)
    is_allowed, remaining, reset_time = RateLimiter.check_rate_limit(
        'add_to_cart', max_requests=20, window_seconds=60
    )
    if not is_allowed:
        app.logger.warning(f'Rate limit exceeded for add_to_cart: user {current_user.id}')
        if is_ajax:
            return jsonify({
                'success': False,
                'error': 'Too many requests. Please try again later.',
                'error_code': 'RATE_LIMIT_EXCEEDED',
                'reset_time': reset_time.isoformat()
            }), 429
        flash('Too many requests. Please slow down.', 'warning')
        return redirect(url_for('product_detail', crop_id=crop_id))
    
    # Validate CSRF token for all requests
    try:
        if is_ajax:
            csrf_token = request.headers.get('X-CSRFToken')
            if not csrf_token:
                app.logger.error(f'CSRF token missing in AJAX request from user {current_user.id}')
                return jsonify({
                    'success': False, 
                    'error': 'Security token missing. Please refresh the page.',
                    'error_code': 'CSRF_TOKEN_MISSING'
                }), 403
            validate_csrf(csrf_token)
        else:
            # For form submissions, Flask-WTF handles CSRF automatically
            pass
    except BadRequest as e:
        app.logger.error(f'CSRF validation failed for user {current_user.id}: {str(e)}')
        if is_ajax:
            return jsonify({
                'success': False, 
                'error': 'Security token invalid. Please refresh the page.',
                'error_code': 'CSRF_TOKEN_INVALID'
            }), 403
        flash('Security token invalid. Please refresh the page.', 'danger')
        return redirect(url_for('product_detail', crop_id=crop_id))
    
    try:
        # Get quantity from JSON or form data
        if request.is_json:
            quantity = request.json.get('quantity')
            if quantity is not None:
                quantity = float(quantity)
        else:
            quantity = request.form.get('quantity', type=float)
    except (ValueError, TypeError) as e:
        app.logger.error(f'Error parsing quantity for user {current_user.id}, crop {crop_id}: {str(e)}')
        if is_ajax:
            return jsonify({
                'success': False, 
                'error': 'Invalid quantity format',
                'error_code': 'INVALID_QUANTITY_FORMAT'
            }), 400
        flash('Invalid quantity format', 'danger')
        return redirect(url_for('product_detail', crop_id=crop_id))
    
    # Log the request for debugging
    app.logger.info(f'Add to cart request - User: {current_user.id}, Crop: {crop_id}, Quantity: {quantity}, IP: {request.remote_addr}')
    
    # Validate quantity input
    is_valid, error_msg = Validator.validate_quantity(quantity)
    if not is_valid:
        app.logger.warning(f'Invalid quantity validation failed for user {current_user.id}, crop {crop_id}: {error_msg}')
        if is_ajax:
            return jsonify({
                'success': False, 
                'error': error_msg,
                'error_code': 'CART_QUANTITY_INVALID'
            }), 400
        flash(error_msg or 'Validation error', 'danger')
        return redirect(url_for('product_detail', crop_id=crop_id))
    
    # Get or create cart
    cart = CartService.get_or_create_cart(current_user.id)
    
    if not cart:
        error_msg = ErrorHandler.get_error_message('CART_NOT_FOUND')
        app.logger.error(f'Failed to get/create cart for user {current_user.id}')
        if is_ajax:
            return jsonify({
                'success': False, 
                'error': error_msg,
                'error_code': 'CART_NOT_FOUND'
            }), 500
        flash(error_msg or 'Validation error', 'danger')
        return redirect(url_for('product_detail', crop_id=crop_id))
    
    # Check if user is trying to add their own crop
    crop = Crop.query.get(crop_id)
    if not crop:
        error_msg = ErrorHandler.get_error_message('CROP_NOT_FOUND')
        app.logger.error(f'Crop {crop_id} not found for add to cart request from user {current_user.id}')
        if is_ajax:
            return jsonify({
                'success': False, 
                'error': error_msg,
                'error_code': 'CROP_NOT_FOUND'
            }), 404
        flash(error_msg or 'Validation error', 'danger')
        return redirect(url_for('product_detail', crop_id=crop_id))
    
    if crop.farmer_id == current_user.id:
        error_msg = ErrorHandler.get_error_message('CART_OWN_CROP')
        app.logger.warning(f'User {current_user.id} attempted to add their own crop {crop_id} to cart')
        if is_ajax:
            return jsonify({
                'success': False, 
                'error': error_msg,
                'error_code': 'CART_OWN_CROP'
            }), 400
        flash(error_msg or 'Warning', 'warning')
        return redirect(url_for('product_detail', crop_id=crop_id))
    
    # Validate crop availability before adding
    is_valid, error_msg = Validator.validate_crop_availability(crop)
    if not is_valid:
        app.logger.warning(f'Crop availability validation failed for crop {crop_id}: {error_msg}')
        if is_ajax:
            return jsonify({
                'success': False, 
                'error': error_msg,
                'error_code': 'CROP_NOT_AVAILABLE'
            }), 400
        flash(error_msg or 'Warning', 'warning')
        return redirect(url_for('product_detail', crop_id=crop_id))
    
    # Validate quantity against available stock
    is_valid, error_msg = Validator.validate_quantity(quantity, crop.quantity, crop.unit)
    if not is_valid:
        app.logger.warning(f'Quantity validation failed for crop {crop_id}, requested: {quantity}, available: {crop.quantity}: {error_msg}')
        if is_ajax:
            return jsonify({
                'success': False, 
                'error': error_msg,
                'error_code': 'CART_QUANTITY_EXCEEDS_STOCK'
            }), 400
        flash(error_msg or 'Warning', 'warning')
        return redirect(url_for('product_detail', crop_id=crop_id))
    
    # Add item to cart
    result = CartService.add_item(cart.id, crop_id, quantity)
    
    # Log the result
    if result['success']:
        app.logger.info(f'Successfully added item to cart - User: {current_user.id}, Crop: {crop_id}, Quantity: {quantity}, Updated: {result.get("updated", False)}')
    else:
        app.logger.error(f'Failed to add item to cart - User: {current_user.id}, Crop: {crop_id}, Error: {result.get("error")}, Code: {result.get("error_code")}')
    
    # Handle AJAX requests
    if is_ajax:
        if result['success']:
            # Get updated cart count - refresh cart to get latest data
            updated_cart = CartService.get_or_create_cart(current_user.id)
            cart_count = len(updated_cart.items) if updated_cart else 0
            
            # Get the cart item details to return quantity
            cart_item = result.get('item')
            item_data = None
            if cart_item:
                item_data = {
                    'quantity': cart_item.quantity,
                    'price_per_unit': cart_item.price_per_unit
                }
            
            return jsonify({
                'success': True,
                'message': result['message'],
                'cart_count': cart_count,
                'updated': result.get('updated', False),
                'item': item_data
            })
        else:
            error_code = result.get('error_code', 'CART_ADD_FAILED')
            return jsonify({
                'success': False, 
                'error': result['error'],
                'error_code': error_code
            }), 400
    
    # Handle regular form submissions
    if result['success']:
        flash(result['message'], 'success')
    else:
        flash(result['error'], 'danger')
    
    return redirect(url_for('view_cart'))


@app.route('/cart/buy-now/<int:crop_id>', methods=['POST'])
@login_required
def buy_now(crop_id):
    """Buy now - add to cart and redirect to checkout - Only accessible by buyers and farmers"""
    from order_service import CartService
    from error_handlers import Validator, ErrorHandler
    from role_hierarchy import is_admin
    
    # Restrict admin access
    if is_admin(current_user):
        flash('Cart functionality is not available for admin users.', 'warning')
        return redirect(url_for('admin_dashboard'))
    from flask_wtf.csrf import validate_csrf  # type: ignore
    from werkzeug.exceptions import BadRequest
    
    # Check if this is an AJAX request
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    
    # Validate CSRF token for all requests
    try:
        if is_ajax:
            csrf_token = request.headers.get('X-CSRFToken')
            if not csrf_token:
                app.logger.error(f'CSRF token missing in buy now AJAX request from user {current_user.id}')
                return jsonify({
                    'success': False, 
                    'error': 'Security token missing. Please refresh the page.',
                    'error_code': 'CSRF_TOKEN_MISSING'
                }), 403
            validate_csrf(csrf_token)
        else:
            # For form submissions, Flask-WTF handles CSRF automatically
            pass
    except BadRequest as e:
        app.logger.error(f'CSRF validation failed for buy now from user {current_user.id}: {str(e)}')
        if is_ajax:
            return jsonify({
                'success': False, 
                'error': 'Security token invalid. Please refresh the page.',
                'error_code': 'CSRF_TOKEN_INVALID'
            }), 403
        flash('Security token invalid. Please refresh the page.', 'danger')
        return redirect(url_for('product_detail', crop_id=crop_id))
    
    try:
        # Get quantity from JSON or form data
        if request.is_json:
            quantity = request.json.get('quantity')
            if quantity is not None:
                quantity = float(quantity)
        else:
            quantity = request.form.get('quantity', type=float)
    except (ValueError, TypeError) as e:
        app.logger.error(f'Error parsing quantity for buy now - user {current_user.id}, crop {crop_id}: {str(e)}')
        if is_ajax:
            return jsonify({
                'success': False, 
                'error': 'Invalid quantity format',
                'error_code': 'INVALID_QUANTITY_FORMAT'
            }), 400
        flash('Invalid quantity format', 'danger')
        return redirect(url_for('product_detail', crop_id=crop_id))
    
    # Log the request for debugging
    app.logger.info(f'Buy now request - User: {current_user.id}, Crop: {crop_id}, Quantity: {quantity}, IP: {request.remote_addr}')
    
    # Validate quantity input
    is_valid, error_msg = Validator.validate_quantity(quantity)
    if not is_valid:
        app.logger.warning(f'Invalid quantity validation failed for buy now - user {current_user.id}, crop {crop_id}: {error_msg}')
        if is_ajax:
            return jsonify({
                'success': False, 
                'error': error_msg,
                'error_code': 'CART_QUANTITY_INVALID'
            }), 400
        flash(error_msg or 'Validation error', 'danger')
        return redirect(url_for('product_detail', crop_id=crop_id))
    
    # Get or create cart
    cart = CartService.get_or_create_cart(current_user.id)
    
    if not cart:
        error_msg = ErrorHandler.get_error_message('CART_NOT_FOUND')
        app.logger.error(f'Failed to get/create cart for buy now - user {current_user.id}')
        if is_ajax:
            return jsonify({
                'success': False, 
                'error': error_msg,
                'error_code': 'CART_NOT_FOUND'
            }), 500
        flash(error_msg or 'Validation error', 'danger')
        return redirect(url_for('product_detail', crop_id=crop_id))
    
    # Check if user is trying to buy their own crop
    crop = Crop.query.get(crop_id)
    if not crop:
        error_msg = ErrorHandler.get_error_message('CROP_NOT_FOUND')
        app.logger.error(f'Crop {crop_id} not found for buy now request from user {current_user.id}')
        if is_ajax:
            return jsonify({
                'success': False, 
                'error': error_msg,
                'error_code': 'CROP_NOT_FOUND'
            }), 404
        flash(error_msg or 'Validation error', 'danger')
        return redirect(url_for('product_detail', crop_id=crop_id))
    
    if crop.farmer_id == current_user.id:
        error_msg = ErrorHandler.get_error_message('CART_OWN_CROP')
        app.logger.warning(f'User {current_user.id} attempted to buy their own crop {crop_id}')
        if is_ajax:
            return jsonify({
                'success': False, 
                'error': error_msg,
                'error_code': 'CART_OWN_CROP'
            }), 400
        flash(error_msg or 'Warning', 'warning')
        return redirect(url_for('product_detail', crop_id=crop_id))
    
    # Validate crop availability before adding
    is_valid, error_msg = Validator.validate_crop_availability(crop)
    if not is_valid:
        app.logger.warning(f'Crop availability validation failed for buy now - crop {crop_id}: {error_msg}')
        if is_ajax:
            return jsonify({
                'success': False, 
                'error': error_msg,
                'error_code': 'CROP_NOT_AVAILABLE'
            }), 400
        flash(error_msg or 'Warning', 'warning')
        return redirect(url_for('product_detail', crop_id=crop_id))
    
    # Validate quantity against available stock
    is_valid, error_msg = Validator.validate_quantity(quantity, crop.quantity, crop.unit)
    if not is_valid:
        app.logger.warning(f'Quantity validation failed for buy now - crop {crop_id}, requested: {quantity}, available: {crop.quantity}: {error_msg}')
        if is_ajax:
            return jsonify({
                'success': False, 
                'error': error_msg,
                'error_code': 'CART_QUANTITY_EXCEEDS_STOCK'
            }), 400
        flash(error_msg or 'Warning', 'warning')
        return redirect(url_for('product_detail', crop_id=crop_id))
    
    # Add item to cart
    result = CartService.add_item(cart.id, crop_id, quantity)
    
    # Log the result
    if result['success']:
        app.logger.info(f'Successfully added item to cart for buy now - User: {current_user.id}, Crop: {crop_id}, Quantity: {quantity}')
    else:
        app.logger.error(f'Failed to add item to cart for buy now - User: {current_user.id}, Crop: {crop_id}, Error: {result.get("error")}, Code: {result.get("error_code")}')
    
    # Handle AJAX requests
    if is_ajax:
        if result['success']:
            # Get updated cart count - refresh cart to get latest data
            updated_cart = CartService.get_or_create_cart(current_user.id)
            cart_count = len(updated_cart.items) if updated_cart else 0
            
            return jsonify({
                'success': True,
                'message': result['message'],
                'cart_count': cart_count,
                'redirect_url': url_for('checkout')
            })
        else:
            error_code = result.get('error_code', 'BUY_NOW_FAILED')
            return jsonify({
                'success': False, 
                'error': result['error'],
                'error_code': error_code
            }), 400
    
    # Handle regular form submissions
    if result['success']:
        flash(result['message'], 'success')
        return redirect(url_for('checkout'))
    else:
        flash(result['error'], 'danger')
        return redirect(url_for('product_detail', crop_id=crop_id))


@app.route('/cart/update/<int:item_id>', methods=['POST'])
@login_required
def update_cart_item(item_id):
    """Update cart item quantity with ownership validation and rate limiting - Only accessible by buyers and farmers"""
    from order_service import CartService
    from models import CartItem
    from error_handlers import Validator, ErrorHandler
    from role_hierarchy import is_admin
    
    # Check if this is an AJAX request
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    
    # Restrict admin access
    if is_admin(current_user):
        if is_ajax:
            return jsonify({
                'success': False,
                'error': 'Cart functionality is not available for admin users.',
                'error_code': 'ADMIN_ACCESS_DENIED'
            }), 403
        flash('Cart functionality is not available for admin users.', 'warning')
        return redirect(url_for('admin_dashboard'))
    from security_enhancements import OwnershipValidator, RateLimiter
    
    # Apply rate limiting (30 requests per minute per user)
    is_allowed, remaining, reset_time = RateLimiter.check_rate_limit(
        'update_cart', max_requests=30, window_seconds=60
    )
    if not is_allowed:
        app.logger.warning(f'Rate limit exceeded for update_cart: user {current_user.id}')
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({
                'success': False,
                'error': 'Too many requests. Please try again later.',
                'error_code': 'RATE_LIMIT_EXCEEDED'
            }), 429
        flash('Too many requests. Please slow down.', 'warning')
        return redirect(url_for('view_cart'))
    
    # Verify item belongs to current user's cart using ownership validator
    is_valid, error_msg = OwnershipValidator.validate_cart_item_ownership(item_id)
    if not is_valid:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'error': error_msg}), 403
        flash(error_msg or 'Validation error', 'danger')
        return redirect(url_for('view_cart'))
    
    cart_item = CartItem.query.get(item_id)
    
    # Get new quantity
    quantity = request.form.get('quantity', type=float)
    
    # Validate quantity input
    is_valid, error_msg = Validator.validate_quantity(quantity)
    if not is_valid:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'error': error_msg}), 400
        flash(error_msg or 'Validation error', 'danger')
        return redirect(url_for('view_cart'))
    
    # Validate quantity against available stock
    if cart_item.crop:
        is_valid, error_msg = Validator.validate_quantity(quantity, cart_item.crop.quantity, cart_item.crop.unit)
        if not is_valid:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'success': False, 'error': error_msg}), 400
            flash(error_msg or 'Warning', 'warning')
            return redirect(url_for('view_cart'))
    
    # Update quantity
    result = CartService.update_item_quantity(item_id, quantity)
    
    # Handle AJAX requests
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        if result['success']:
            # Get updated cart totals
            cart_data = CartService.get_cart_total(cart_item.cart.id)
            return jsonify({
                'success': True,
                'message': result['message'],
                'item_subtotal': result['item'].subtotal,
                'cart_total': cart_data.get('total_amount', 0)
            })
        else:
            return jsonify({'success': False, 'error': result['error']}), 400
    
    # Handle regular form submissions
    if result['success']:
        flash(result['message'], 'success')
    else:
        flash(result['error'], 'danger')
    
    return redirect(url_for('view_cart'))


@app.route('/cart/remove/<int:item_id>', methods=['POST'])
@login_required
def remove_cart_item(item_id):
    """Remove item from cart with ownership validation - Only accessible by buyers and farmers"""
    from order_service import CartService
    from models import CartItem
    from error_handlers import ErrorHandler
    from role_hierarchy import is_admin
    
    # Check if this is an AJAX request
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    
    # Restrict admin access
    if is_admin(current_user):
        if is_ajax:
            return jsonify({
                'success': False,
                'error': 'Cart functionality is not available for admin users.',
                'error_code': 'ADMIN_ACCESS_DENIED'
            }), 403
        flash('Cart functionality is not available for admin users.', 'warning')
        return redirect(url_for('admin_dashboard'))
    from security_enhancements import OwnershipValidator, RateLimiter
    
    # Apply rate limiting (30 requests per minute per user)
    is_allowed, remaining, reset_time = RateLimiter.check_rate_limit(
        'remove_cart_item', max_requests=30, window_seconds=60
    )
    if not is_allowed:
        app.logger.warning(f'Rate limit exceeded for remove_cart_item: user {current_user.id}')
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({
                'success': False,
                'error': 'Too many requests. Please try again later.',
                'error_code': 'RATE_LIMIT_EXCEEDED'
            }), 429
        flash('Too many requests. Please slow down.', 'warning')
        return redirect(url_for('view_cart'))
    
    # Verify item belongs to current user's cart using ownership validator
    is_valid, error_msg = OwnershipValidator.validate_cart_item_ownership(item_id)
    if not is_valid:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'error': error_msg}), 403
        flash(error_msg or 'Validation error', 'danger')
        return redirect(url_for('view_cart'))
    
    # Remove item
    result = CartService.remove_item(item_id)
    
    # Handle AJAX requests
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        if result['success']:
            # Get updated cart totals
            cart = CartService.get_or_create_cart(current_user.id)
            cart_data = CartService.get_cart_total(cart.id)
            cart_count = len(cart.items)
            return jsonify({
                'success': True,
                'message': result['message'],
                'cart_total': cart_data.get('total_amount', 0),
                'cart_count': cart_count
            })
        else:
            return jsonify({'success': False, 'error': result['error']}), 400
    
    # Handle regular form submissions
    if result['success']:
        flash(result['message'], 'success')
    else:
        flash(result['error'], 'danger')
    
    return redirect(url_for('view_cart'))


@app.route('/cart/clear', methods=['POST'])
@login_required
def clear_cart():
    """Clear all items from cart - Only accessible by buyers and farmers"""
    from order_service import CartService
    from role_hierarchy import is_admin
    
    # Check if this is an AJAX request
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    
    # Restrict admin access
    if is_admin(current_user):
        if is_ajax:
            return jsonify({
                'success': False,
                'error': 'Cart functionality is not available for admin users.',
                'error_code': 'ADMIN_ACCESS_DENIED'
            }), 403
        flash('Cart functionality is not available for admin users.', 'warning')
        return redirect(url_for('admin_dashboard'))
    
    # Get user's cart
    cart = CartService.get_or_create_cart(current_user.id)
    
    if not cart:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'error': 'Cart not found'}), 404
        flash('Cart not found.', 'danger')
        return redirect(url_for('marketplace'))
    
    # Clear cart
    result = CartService.clear_cart(cart.id)
    
    # Handle AJAX requests
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        if result['success']:
            return jsonify({
                'success': True,
                'message': result['message']
            })
        else:
            return jsonify({'success': False, 'error': result['error']}), 400
    
    # Handle regular form submissions
    if result['success']:
        flash(result['message'], 'success')
    else:
        flash(result['error'], 'danger')
    
    return redirect(url_for('view_cart'))


# AJAX endpoint for getting cart count
@app.route('/cart/count')
@login_required
@limiter.exempt
def get_cart_count():
    """Get current cart item count - Only accessible by buyers and farmers"""
    from order_service import CartService
    from role_hierarchy import is_admin
    
    # Restrict admin access - return 0 for admins
    if is_admin(current_user):
        return jsonify({'success': True, 'count': 0})
    
    try:
        cart = CartService.get_or_create_cart(current_user.id)
        
        if cart:
            cart_count = len(cart.items)
            # Reduced logging verbosity - only log on actual cart changes
            return jsonify({'success': True, 'count': cart_count})
        else:
            app.logger.error(f'Failed to get cart for user {current_user.id} in cart count endpoint')
            return jsonify({'success': False, 'count': 0, 'error': 'Cart not found'}), 500
    except Exception as e:
        app.logger.error(f'Error getting cart count for user {current_user.id}: {str(e)}')
        return jsonify({'success': False, 'count': 0, 'error': 'Internal server error'}), 500


@app.route('/cart/preview')
@login_required
def get_cart_preview():
    """Get cart preview data for dropdown - Only accessible by buyers and farmers"""
    from order_service import CartService
    from utils import format_currency
    from role_hierarchy import is_admin
    
    # Restrict admin access - return empty cart for admins
    if is_admin(current_user):
        return jsonify({
            'success': True,
            'items': [],
            'total': 0,
            'count': 0
        })
    
    cart = CartService.get_or_create_cart(current_user.id)
    
    if not cart or not cart.items:
        return jsonify({'success': True, 'items': [], 'total': '₹0.00'})
    
    # Prepare cart items for preview (limit to 5 most recent)
    items = []
    for item in cart.items[:5]:
        if item.crop:
            items.append({
                'id': item.id,
                'name': item.crop.name,
                'quantity': item.quantity,
                'unit': item.crop.unit,
                'price': format_currency(item.price_per_unit),
                'subtotal': format_currency(item.subtotal),
                'image': url_for('static', filename=item.crop.image_url) if item.crop.image_url else url_for('static', filename='uploads/crops/default-crop.jpg')
            })
    
    # Calculate total
    total_data = CartService.get_cart_total(cart.id)
    total_amount = total_data.get('total_amount', 0) if isinstance(total_data, dict) else total_data
    
    return jsonify({
        'success': True,
        'items': items,
        'total': format_currency(total_amount),
        'count': len(cart.items)
    })


# ============================================================================
# CHECKOUT ROUTES
# ============================================================================

@app.route('/checkout', methods=['GET', 'POST'])
@login_required
def checkout():
    """Display checkout form and process order creation - Only accessible by buyers and farmers"""
    from order_service import CartService, OrderService
    from forms import CheckoutForm
    from error_handlers import Validator, ErrorHandler
    from role_hierarchy import is_admin
    
    # Restrict admin access
    if is_admin(current_user):
        flash('Checkout functionality is not available for admin users.', 'warning')
        return redirect(url_for('admin_dashboard'))
    
    # ========================================================================
    # GET Handler - Display checkout form
    # ========================================================================
    
    # Get user's cart (Requirement 2.1)
    cart = CartService.get_or_create_cart(current_user.id)
    
    # Validate cart is not empty (Requirement 11.1)
    if not cart or not cart.items:
        flash(ErrorHandler.get_error_message('CART_EMPTY'), 'warning')
        return redirect(url_for('marketplace'))
    
    # Call CartService.validate_cart_items (Requirement 2.1, 11.2-11.5)
    validation_result = CartService.validate_cart_items(cart.id)
    
    if not validation_result.get('success'):
        error_code = validation_result.get('error_code', 'VALIDATION_FAILED')
        error_msg = ErrorHandler.get_error_message(error_code)
        flash(error_msg or 'Validation error', 'danger')
        return redirect(url_for('view_cart'))
    
    # Display invalid items if validation fails (Requirement 11.7)
    if not validation_result.get('is_valid'):
        invalid_items = validation_result.get('invalid_items', [])
        for item in invalid_items:
            for issue in item.get('issues', []):
                flash(f"{item['crop_name']}: {issue}", 'warning')
        flash('Please review your cart and remove unavailable items.', 'danger')
        return redirect(url_for('view_cart'))
    
    # Get valid items and warnings (Requirement 11.6)
    valid_items = validation_result.get('valid_items', [])
    warnings = validation_result.get('warnings', [])
    total_amount = validation_result.get('total_amount', 0)
    
    # Group valid items by farmer (Requirement 2.1)
    items_by_farmer = {}
    for item in valid_items:
        farmer_id = item['farmer_id']
        if farmer_id not in items_by_farmer:
            # Get farmer info
            farmer = User.query.get(farmer_id)
            items_by_farmer[farmer_id] = {
                'farmer': farmer,
                'items': [],
                'subtotal': 0
            }
        items_by_farmer[farmer_id]['items'].append(item)
        items_by_farmer[farmer_id]['subtotal'] += item['subtotal']
    
    # Create checkout form
    form = CheckoutForm()
    
    # Pre-fill delivery address from user profile if available (Requirement 2.1)
    if request.method == 'GET':
        if current_user.location:
            form.delivery_address.data = current_user.location
        if current_user.phone:
            form.contact_phone.data = current_user.phone
    
    # ========================================================================
    # POST Handler - Process order creation
    # ========================================================================
    
    if form.validate_on_submit():
        from security_enhancements import InputSanitizer, RateLimiter
        
        # Apply rate limiting for checkout (5 requests per 5 minutes per user)
        is_allowed, remaining, reset_time = RateLimiter.check_rate_limit(
            'checkout', max_requests=5, window_seconds=300
        )
        if not is_allowed:
            app.logger.warning(f'Rate limit exceeded for checkout: user {current_user.id}')
            flash('Too many checkout attempts. Please try again later.', 'warning')
            return redirect(url_for('view_cart'))
        
        # Validate checkout form submission (Requirement 2.2)
        # Validate delivery address length (Requirement 2.2, 2.7)
        is_valid, error_msg = Validator.validate_delivery_address(form.delivery_address.data)
        if not is_valid:
            flash(error_msg or 'Validation error', 'danger')
            return render_template('checkout/review.html',
                                 form=form,
                                 cart=cart,
                                 items_by_farmer=items_by_farmer,
                                 valid_items=valid_items,
                                 warnings=warnings,
                                 total_amount=total_amount,
                                 item_count=len(valid_items))
        
        # Sanitize user input for delivery address and notes (Security Enhancement)
        sanitized_address = InputSanitizer.sanitize_address(form.delivery_address.data)
        sanitized_notes = InputSanitizer.sanitize_notes(form.notes.data) if form.notes.data else ''
        sanitized_phone = InputSanitizer.sanitize_text(form.contact_phone.data, max_length=20) if form.contact_phone.data else ''
        
        # Log sanitization for security audit
        if sanitized_address != form.delivery_address.data:
            app.logger.info(f'Delivery address sanitized for user {current_user.id}')
        if form.notes.data and sanitized_notes != form.notes.data:
            app.logger.info(f'Order notes sanitized for user {current_user.id}')
        
        # Prepare delivery information dictionary (Requirement 2.2)
        delivery_info = {
            'delivery_address': sanitized_address,
            'delivery_method': form.delivery_method.data,
            'contact_phone': sanitized_phone,
            'notes': sanitized_notes
        }
        
        # Call OrderService.create_orders_from_cart (Requirement 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8)
        result = OrderService.create_orders_from_cart(cart.id, delivery_info)
        
        # Handle order creation errors (Requirement 2.2)
        if not result.get('success'):
            error_code = result.get('error_code', 'ORDER_CREATION_FAILED')
            error_msg = ErrorHandler.get_error_message(error_code)
            flash(error_msg or 'Validation error', 'danger')
            return redirect(url_for('checkout'))
        
        # Get created orders
        orders = result.get('orders', [])
        order_count = result.get('order_count', 0)
        
        if order_count == 0:
            flash('No orders were created. Please try again.', 'danger')
            return redirect(url_for('checkout'))
        
        # Store order IDs in session for payment (Requirement 2.2)
        order_ids = [order.id for order in orders]
        from flask import session
        session['pending_order_ids'] = order_ids
        session['checkout_cart_id'] = cart.id
        
        # Redirect to bulk payment processing (Requirement 2.8)
        flash(f'{order_count} order(s) created successfully. Please complete payment.', 'success')
        return redirect(url_for('payment_routes.process_bulk_payment'))
    
    # Render checkout template with form (Requirement 2.1)
    return render_template('checkout/review.html',
                         form=form,
                         cart=cart,
                         items_by_farmer=items_by_farmer,
                         valid_items=valid_items,
                         warnings=warnings,
                         total_amount=total_amount,
                         item_count=len(valid_items))


# ============================================================================
# ORDER ROUTES
# ============================================================================

@app.route('/order/place/<int:crop_id>', methods=['GET', 'POST'])
@login_required
def place_order(crop_id):
    """Allow both buyers and farmers to place orders, but prevent self-purchase"""
    from order_service import InventoryService, OrderService
    from error_handlers import ErrorHandler
    
    crop = Crop.query.get_or_404(crop_id)
    
    # Prevent farmers from buying their own products
    if current_user.id == crop.farmer_id:
        flash('You cannot purchase your own product.', 'warning')
        return redirect(url_for('marketplace'))
    
    # Check crop availability using InventoryService
    availability = InventoryService.check_availability(crop_id, 1)
    if not availability.get('available'):
        error_code = availability.get('error_code', 'CROP_NOT_AVAILABLE')
        error_msg = ErrorHandler.get_error_message(error_code, **availability.get('details', {}))
        flash(error_msg or 'Warning', 'warning')
        return redirect(url_for('marketplace'))
        
    form = OrderForm()
    if form.validate_on_submit():
        # Validate quantity against available stock
        quantity_check = InventoryService.check_availability(crop_id, form.quantity_requested.data)
        if not quantity_check.get('available'):
            flash(f'Only {crop.quantity} {crop.unit} available.', 'error')
            return redirect(url_for('place_order', crop_id=crop_id))
        
        # Use OrderService to create order
        order_data = {
            'crop_id': crop.id,
            'buyer_id': current_user.id,
            'farmer_id': crop.farmer_id,
            'quantity_requested': form.quantity_requested.data,
            'price_per_unit': crop.price_per_unit,
            'delivery_address': form.delivery_address.data,
            'delivery_method': form.delivery_method.data,
            'notes': form.notes.data
        }
        
        result = OrderService.create_single_order(order_data)
        
        if result['success']:
            order = result['order']
            # Redirect to payment processing page
            return redirect(url_for('payment_routes.process_payment', order_id=order.id))
        else:
            flash(result.get('error', 'Failed to create order. Please try again.'), 'danger')
            return redirect(url_for('place_order', crop_id=crop_id))
            
    return render_template('orders/place_order.html', form=form, crop=crop)

@app.route('/orders/my')
@login_required
def my_orders():
    """Show orders based on user role - farmers see both sales and purchases"""
    from order_service import OrderService
    from role_hierarchy import is_admin
    
    # Redirect admins to admin orders page
    if is_admin(current_user):
        flash('Admin users should use the Admin Orders page to manage all orders.', 'info')
        return redirect(url_for('admin_orders'))
    
    # Get pagination parameters
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    status_filter = request.args.get('status', None)
    
    # Calculate offset
    offset = (page - 1) * per_page
    
    if is_farmer_or_manager(current_user):
        # Farmers see both their sales (as farmer) and purchases (as buyer)
        sales_result = OrderService.get_user_orders(
            current_user.id, 'farmer', 
            status_filter=status_filter,
            limit=per_page, 
            offset=offset
        )
        purchase_result = OrderService.get_user_orders(
            current_user.id, 'buyer',
            status_filter=status_filter,
            limit=per_page,
            offset=offset
        )
        
        sales_orders = sales_result.get('orders', []) if sales_result.get('success') else []
        purchase_orders = purchase_result.get('orders', []) if purchase_result.get('success') else []
        
        return render_template('orders/my_orders.html', 
                             sales_orders=sales_orders, 
                             purchase_orders=purchase_orders,
                             is_farmer=True,
                             page=page,
                             per_page=per_page,
                             sales_total=sales_result.get('total_count', 0),
                             purchase_total=purchase_result.get('total_count', 0),
                             sales_has_more=sales_result.get('has_more', False),
                             purchase_has_more=purchase_result.get('has_more', False))
    elif is_buyer_or_manager(current_user):
        # Buyers only see their purchases
        result = OrderService.get_user_orders(
            current_user.id, 'buyer',
            status_filter=status_filter,
            limit=per_page,
            offset=offset
        )
        orders = result.get('orders', []) if result.get('success') else []
        
        return render_template('orders/my_orders.html', 
                             orders=orders, 
                             is_farmer=False,
                             page=page,
                             per_page=per_page,
                             total_count=result.get('total_count', 0),
                             has_more=result.get('has_more', False))
    else:
        flash('Access denied.', 'danger')
        return redirect(url_for('index'))


@app.route('/order/<int:order_id>')
@login_required
def order_detail(order_id):
    """View detailed information about a specific order"""
    from sqlalchemy.orm import joinedload
    
    # Use eager loading to fetch related objects
    order = Order.query.options(
        joinedload(Order.crop),
        joinedload(Order.buyer),
        joinedload(Order.farmer_user),
        joinedload(Order.status_history).joinedload(OrderStatusHistory.changed_by)
    ).get_or_404(order_id)
    
    # Verify user has access to this order (buyer, farmer, or admin)
    if current_user.id not in [order.buyer_id, order.farmer_id] and current_user.role != 'admin':
        flash('You do not have permission to view this order.', 'danger')
        return redirect(url_for('my_orders'))
    
    return render_template('orders/order_detail.html', order=order)


@app.route('/order/update/<int:order_id>/<status>')
@login_required
def update_order_status(order_id, status):
    """Update order status with validation using OrderService"""
    from order_service import OrderService
    from error_handlers import Validator, ErrorHandler
    
    order = Order.query.get_or_404(order_id)
    
    # Validate user permission
    is_valid, error_msg = Validator.validate_user_permission(current_user, order, 'update_status')
    if not is_valid:
        flash(error_msg or 'Validation error', 'danger')
        return redirect(url_for('my_orders'))
    
    # Validate status transition
    is_valid, error_msg = Validator.validate_order_status_transition(order.status, status)
    if not is_valid:
        flash(error_msg or 'Validation error', 'danger')
        return redirect(url_for('order_detail', order_id=order_id))
    
    # Use OrderService to update status with validation
    result = OrderService.update_order_status(
        order_id=order_id,
        new_status=status,
        user_id=current_user.id,
        notes=f'Status updated by farmer to {status}'
    )
    
    if result['success']:
        flash(result['message'], 'success')
    else:
        error_code = result.get('error_code', 'SYSTEM_ERROR')
        error_msg = ErrorHandler.get_error_message(error_code, **result.get('details', {}))
        flash(error_msg or 'Validation error', 'danger')
    
    return redirect(url_for('order_detail', order_id=order_id))


@app.route('/order/<int:order_id>/ship', methods=['POST'])
@login_required
def ship_order(order_id):
    """Mark order as shipped with tracking number"""
    from order_service import OrderService
    from error_handlers import Validator, ErrorHandler
    
    order = Order.query.get_or_404(order_id)
    
    # Validate user permission
    is_valid, error_msg = Validator.validate_user_permission(current_user, order, 'update_status')
    if not is_valid:
        flash(error_msg or 'Validation error', 'danger')
        return redirect(url_for('my_orders'))
    
    # Get tracking number from form
    tracking_number = request.form.get('tracking_number', '').strip()
    notes = request.form.get('notes', '').strip()
    
    # Validate tracking number
    if not tracking_number or len(tracking_number) < 3:
        flash('Please provide a valid tracking number (at least 3 characters).', 'danger')
        return redirect(url_for('order_detail', order_id=order_id))
    
    # Validate status transition
    is_valid, error_msg = Validator.validate_order_status_transition(order.status, 'shipped')
    if not is_valid:
        flash(error_msg or 'Validation error', 'danger')
        return redirect(url_for('order_detail', order_id=order_id))
    
    # Use OrderService to update status to shipped
    result = OrderService.update_order_status(
        order_id=order_id,
        new_status='shipped',
        user_id=current_user.id,
        notes=notes or f'Order shipped with tracking number: {tracking_number}',
        tracking_number=tracking_number
    )
    
    if result['success']:
        flash(f'Order marked as shipped. Tracking number: {tracking_number}', 'success')
    else:
        error_code = result.get('error_code', 'SYSTEM_ERROR')
        error_msg = ErrorHandler.get_error_message(error_code, **result.get('details', {}))
        flash(error_msg or 'Validation error', 'danger')
    
    return redirect(url_for('order_detail', order_id=order_id))


@app.route('/order/<int:order_id>/deliver')
@login_required
def deliver_order(order_id):
    """Mark order as delivered"""
    from order_service import OrderService
    from error_handlers import Validator, ErrorHandler
    
    order = Order.query.get_or_404(order_id)
    
    # Validate user permission
    is_valid, error_msg = Validator.validate_user_permission(current_user, order, 'update_status')
    if not is_valid:
        flash(error_msg or 'Validation error', 'danger')
        return redirect(url_for('my_orders'))
    
    # Validate status transition
    is_valid, error_msg = Validator.validate_order_status_transition(order.status, 'delivered')
    if not is_valid:
        flash(error_msg or 'Validation error', 'danger')
        return redirect(url_for('order_detail', order_id=order_id))
    
    # Use OrderService to update status to delivered
    result = OrderService.update_order_status(
        order_id=order_id,
        new_status='delivered',
        user_id=current_user.id,
        notes='Order marked as delivered by farmer'
    )
    
    if result['success']:
        flash('Order marked as delivered successfully.', 'success')
    else:
        error_code = result.get('error_code', 'SYSTEM_ERROR')
        error_msg = ErrorHandler.get_error_message(error_code, **result.get('details', {}))
        flash(error_msg or 'Validation error', 'danger')
    
    return redirect(url_for('order_detail', order_id=order_id))


@app.route('/order/<int:order_id>/cancel', methods=['POST'])
@login_required
def cancel_order(order_id):
    """Cancel an order with reason and ownership validation"""
    from order_service import OrderService
    from error_handlers import Validator, ErrorHandler
    from security_enhancements import OwnershipValidator, InputSanitizer, RateLimiter
    
    # Apply rate limiting (10 cancellations per hour per user)
    is_allowed, remaining, reset_time = RateLimiter.check_rate_limit(
        'cancel_order', max_requests=10, window_seconds=3600
    )
    if not is_allowed:
        app.logger.warning(f'Rate limit exceeded for cancel_order: user {current_user.id}')
        flash('Too many cancellation requests. Please try again later.', 'warning')
        return redirect(url_for('my_orders'))
    
    order = Order.query.get_or_404(order_id)
    
    # Validate order ownership using ownership validator
    is_valid, error_msg, role = OwnershipValidator.validate_order_ownership(order_id, allow_farmer=True)
    if not is_valid:
        app.logger.warning(f'Unauthorized order cancellation attempt: user {current_user.id}, order {order_id}')
        flash(error_msg or 'Validation error', 'danger')
        return redirect(url_for('my_orders'))
    
    # Check if user is authorized to cancel
    is_buyer = role == 'buyer'
    is_farmer = role == 'farmer'
    is_reject = request.form.get('reject') == 'true'
    
    # Validate cancellation eligibility
    is_valid, error_msg = Validator.validate_cancellation_eligibility(order)
    if not is_valid:
        flash(error_msg or 'Validation error', 'danger')
        return redirect(url_for('order_detail', order_id=order_id))
    
    # Get and sanitize cancellation reason
    reason = request.form.get('reason', '').strip()
    reason = InputSanitizer.sanitize_notes(reason)
    
    # Validate reason
    if not reason or len(reason) < 5:
        flash('Please provide a cancellation reason (at least 5 characters).', 'danger')
        return redirect(url_for('order_detail', order_id=order_id))
    
    # If farmer is rejecting, update status to rejected instead of cancelled
    if is_farmer and is_reject:
        # Validate status transition for rejection
        is_valid, error_msg = Validator.validate_order_status_transition(order.status, 'rejected')
        if not is_valid:
            flash(error_msg or 'Validation error', 'danger')
            return redirect(url_for('order_detail', order_id=order_id))
        
        result = OrderService.update_order_status(
            order_id=order_id,
            new_status='rejected',
            user_id=current_user.id,
            notes=f'Order rejected by farmer. Reason: {reason}'
        )
        
        # Restore inventory
        if result['success'] and order.payment_status == 'paid':
            crop = Crop.query.get(order.crop_id)
            if crop:
                crop.quantity += order.quantity_requested
                if crop.status == 'sold' and crop.quantity > 0:
                    crop.status = 'available'
                db.session.commit()
        
        if result['success']:
            flash('Order rejected successfully. Inventory has been restored.', 'success')
        else:
            error_code = result.get('error_code', 'SYSTEM_ERROR')
            error_msg = ErrorHandler.get_error_message(error_code, **result.get('details', {}))
            flash(error_msg or 'Validation error', 'danger')
    else:
        # Use OrderService to cancel order
        result = OrderService.cancel_order(
            order_id=order_id,
            user_id=current_user.id,
            reason=reason
        )
        
        if result['success']:
            flash('Order cancelled successfully.', 'success')
            if result.get('inventory_restored'):
                flash('Inventory has been restored.', 'info')
            if result.get('refund_initiated'):
                flash('Refund has been initiated. It will be processed within 5-7 business days.', 'info')
            if result.get('refund_error'):
                flash(result['refund_error'], 'warning')
        else:
            flash(result['error'], 'danger')
    
    return redirect(url_for('order_detail', order_id=order_id))


@app.route('/order/<int:order_id>/invoice/download')
@login_required
def download_invoice(order_id):
    """Download invoice PDF for a paid order"""
    from flask import send_file
    from report_generator import generate_order_invoice
    from error_handlers import Validator, ErrorHandler
    import os
    
    order = Order.query.get_or_404(order_id)
    
    # Validate user permission (buyer or farmer can download)
    if order.buyer_id != current_user.id and order.farmer_id != current_user.id and current_user.role != 'admin':
        flash('You do not have permission to download this invoice.', 'danger')
        return redirect(url_for('my_orders'))
    
    # Check if order is paid
    if order.payment_status != 'paid':
        flash('Invoice is only available for paid orders.', 'warning')
        return redirect(url_for('order_detail', order_id=order_id))
    
    # Generate invoice number if not exists
    if not order.invoice_number:
        from order_service import generate_invoice_number
        order.invoice_number = generate_invoice_number(order.id)
        db.session.commit()
    
    try:
        # Create invoices directory if it doesn't exist
        invoice_dir = os.path.join('static', 'uploads', 'invoices')
        os.makedirs(invoice_dir, exist_ok=True)
        
        # Generate invoice PDF
        invoice_filename = f"invoice_{order.invoice_number}.pdf"
        invoice_path = os.path.join(invoice_dir, invoice_filename)
        
        # Check if invoice already exists, if not generate it
        if not os.path.exists(invoice_path):
            if not generate_order_invoice(order, invoice_path):
                flash('Failed to generate invoice. Please try again.', 'danger')
                return redirect(url_for('order_detail', order_id=order_id))
        
        # Send file for download
        return send_file(
            invoice_path,
            as_attachment=True,
            download_name=f"FarmLink_Invoice_{order.invoice_number}.pdf",
            mimetype='application/pdf'
        )
        
    except Exception as e:
        app.logger.error(f"Error downloading invoice for order {order_id}: {str(e)}")
        flash('An error occurred while downloading the invoice.', 'danger')
        return redirect(url_for('order_detail', order_id=order_id))


@app.route('/order/<int:order_id>/invoice/view')
@login_required
def view_invoice(order_id):
    """View invoice PDF inline in browser"""
    from flask import send_file
    from report_generator import generate_order_invoice
    import os
    
    order = Order.query.get_or_404(order_id)
    
    # Validate user permission
    if order.buyer_id != current_user.id and order.farmer_id != current_user.id and current_user.role != 'admin':
        flash('You do not have permission to view this invoice.', 'danger')
        return redirect(url_for('my_orders'))
    
    # Check if order is paid
    if order.payment_status != 'paid':
        flash('Invoice is only available for paid orders.', 'warning')
        return redirect(url_for('order_detail', order_id=order_id))
    
    # Generate invoice number if not exists
    if not order.invoice_number:
        from order_service import generate_invoice_number
        order.invoice_number = generate_invoice_number(order.id)
        db.session.commit()
    
    try:
        # Create invoices directory if it doesn't exist
        invoice_dir = os.path.join('static', 'uploads', 'invoices')
        os.makedirs(invoice_dir, exist_ok=True)
        
        # Generate invoice PDF
        invoice_filename = f"invoice_{order.invoice_number}.pdf"
        invoice_path = os.path.join(invoice_dir, invoice_filename)
        
        # Check if invoice already exists, if not generate it
        if not os.path.exists(invoice_path):
            if not generate_order_invoice(order, invoice_path):
                flash('Failed to generate invoice. Please try again.', 'danger')
                return redirect(url_for('order_detail', order_id=order_id))
        
        # Send file for inline viewing
        return send_file(
            invoice_path,
            mimetype='application/pdf'
        )
        
    except Exception as e:
        app.logger.error(f"Error viewing invoice for order {order_id}: {str(e)}")
        flash('An error occurred while viewing the invoice.', 'danger')
        return redirect(url_for('order_detail', order_id=order_id))


@app.route('/seller/<int:seller_id>')
def view_seller_profile(seller_id):
    """View seller's public profile with their crops and information"""
    seller = User.query.get_or_404(seller_id)
    
    # Get seller's available crops (only approved ones)
    crops = Crop.query.filter_by(
        farmer_id=seller_id,
        status='available',
        approval_status='approved'
    ).order_by(Crop.created_at.desc()).all()
    
    # Get seller statistics
    total_crops = Crop.query.filter_by(farmer_id=seller_id).count()
    completed_orders = Order.query.filter_by(
        farmer_id=seller_id,
        status='delivered'
    ).count()
    
    # Get seller reputation
    from models import SellerReputation, ProductRating
    seller_reputation = SellerReputation.query.filter_by(seller_id=seller_id).first()
    
    # Get total ratings count
    total_ratings = ProductRating.query.join(
        Crop, ProductRating.product_id == Crop.id
    ).filter(
        Crop.farmer_id == seller_id,
        ProductRating.is_hidden == False
    ).count()
    
    return render_template('profile/seller_profile.html',
                         seller=seller,
                         crops=crops,
                         total_crops=total_crops,
                         completed_orders=completed_orders,
                         seller_reputation=seller_reputation,
                         total_ratings=total_ratings)

@app.route('/messages')
@login_required
def inbox():
    """Show user's message inbox with received and sent messages"""
    # Get all messages for current user (excluding archived), ordered by most recent first
    received_messages = Message.query.filter_by(
        recipient_id=current_user.id,
        is_archived=False
    ).order_by(Message.created_at.desc()).all()
    
    sent_messages = Message.query.filter_by(
        sender_id=current_user.id,
        is_archived=False
    ).order_by(Message.created_at.desc()).all()
    
    # Initialize message form for new messages/replies
    form = MessageForm()
    
    # Get unread message count for UI badge (excluding archived)
    unread_count = Message.query.filter_by(
        recipient_id=current_user.id, 
        is_read=False,
        is_archived=False
    ).count()
    
    return render_template('messages/inbox.html', 
                         received_messages=received_messages, 
                         sent_messages=sent_messages,
                         unread_count=unread_count,
                         form=form)

@app.route('/messages/send/<recipient_identifier>', methods=['GET', 'POST'])
@login_required
def send_message(recipient_identifier):
    """Send a new message to a user (by ID, email, or username)"""
    app.logger.info(f'Message send attempt to: {recipient_identifier}')
    
    # Try to find recipient by ID, email, or username
    recipient = None
    
    # Check if it's a numeric ID
    if recipient_identifier.isdigit():
        recipient = User.query.get(int(recipient_identifier))
        app.logger.info(f'Tried ID lookup: {"Found" if recipient else "Not found"}')
    
    # If not found, try email
    if not recipient:
        recipient = User.query.filter_by(email=recipient_identifier).first()
        app.logger.info(f'Tried email lookup: {"Found" if recipient else "Not found"}')
    
    # If still not found, try username
    if not recipient:
        recipient = User.query.filter_by(username=recipient_identifier).first()
        app.logger.info(f'Tried username lookup: {"Found" if recipient else "Not found"}')
    
    # If no recipient found, return to inbox with error
    if not recipient:
        app.logger.warning(f'❌ User not found: {recipient_identifier}')
        flash(f'User not found: {recipient_identifier}', 'danger')
        return redirect(url_for('inbox'))
    
    app.logger.info(f'Recipient found: {recipient.full_name} (ID: {recipient.id})')
    
    # Can't send messages to yourself
    if recipient.id == current_user.id:
        flash('You cannot send messages to yourself.', 'warning')
        return redirect(url_for('inbox'))
    
    form = MessageForm()
    
    # Add detailed logging
    app.logger.info(f'Form submitted: {request.method == "POST"}')
    if request.method == 'POST':
        app.logger.info(f'Form data: subject={bool(form.subject.data)}, content={bool(form.content.data)}, recipient_id={form.recipient_id.data}')
        app.logger.info(f'Form errors: {form.errors}')
    
    if form.validate_on_submit():
        try:
            # Create new message
            message = Message(
                subject=form.subject.data,
                content=form.content.data,
                sender_id=current_user.id,
                recipient_id=recipient.id,
                created_at=datetime.utcnow(),
                is_read=False
            )
            db.session.add(message)
            db.session.commit()
            
            app.logger.info(f'Message sent successfully: {current_user.full_name} → {recipient.full_name}')
            
            # Send email notification to recipient
            try:
                from email_service import email_service
                email_result = email_service.send_new_message_notification(recipient, current_user, message)
                if email_result.get('success'):
                    app.logger.info(f'📧 Email notification sent to {recipient.email}')
                else:
                    app.logger.warning(f'⚠️ Email notification failed: {email_result.get("error")}')
            except Exception as email_error:
                app.logger.error(f'❌ Email notification error: {str(email_error)}')
                # Don't fail the message send if email fails
            
            flash('Message sent successfully!', 'success')
            return redirect(url_for('inbox'))
            
        except Exception as e:
            db.session.rollback()
            app.logger.error(f'Error sending message: {str(e)}')
            flash('An error occurred while sending the message. Please try again.', 'danger')
    else:
        if request.method == 'POST':
            app.logger.error(f'❌ Form validation failed with errors: {form.errors}')
            for field, errors in form.errors.items():
                for error in errors:
                    flash(f'{field}: {error}', 'danger')
    
    # Set the recipient_id in the form
    form.recipient_id.data = recipient.id
            
    # Get messages for inbox display (excluding archived)
    received_messages = Message.query.filter_by(
        recipient_id=current_user.id,
        is_archived=False
    ).order_by(Message.created_at.desc()).all()
    
    sent_messages = Message.query.filter_by(
        sender_id=current_user.id,
        is_archived=False
    ).order_by(Message.created_at.desc()).all()
    
    return render_template('messages/inbox.html', 
                         form=form,
                         recipient=recipient,
                         received_messages=received_messages,
                         sent_messages=sent_messages)

@app.route('/messages/read/<int:message_id>', methods=['GET', 'POST'])
@login_required
def read_message(message_id):
    """Mark a message as read - supports both GET (direct link) and POST (AJAX)"""
    message = Message.query.get_or_404(message_id)
    
    # Verify the current user is the recipient
    if message.recipient_id != current_user.id:
        if request.method == 'POST' and request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'status': 'error', 'message': 'Access denied'}), 403
        flash('Access denied.', 'danger')
        return redirect(url_for('inbox'))
    
    # Handle GET requests (direct URL access) - redirect to inbox and mark as read
    if request.method == 'GET':
        try:
            if not message.is_read:
                message.is_read = True
                message.read_at = datetime.utcnow()
                db.session.commit()
                flash('Message marked as read.', 'success')
            else:
                flash('Message already read.', 'info')
            return redirect(url_for('inbox'))
        except Exception as e:
            db.session.rollback()
            app.logger.error(f'Error marking message as read via GET: {str(e)}')
            flash('An error occurred. Please try again.', 'danger')
            return redirect(url_for('inbox'))
    
    # Handle POST requests (AJAX calls)
    try:
        # Mark message as read
        if not message.is_read:
            message.is_read = True
            message.read_at = datetime.utcnow()
            db.session.commit()
            
        # Return JSON response for AJAX requests
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({
                'status': 'success',
                'message': {
                    'id': message.id,
                    'is_read': message.is_read,
                    'read_at': message.read_at.isoformat() if message.read_at else None
                }
            })
        
        # Return redirect for regular form submissions
        flash('Message marked as read.', 'success')
        return redirect(url_for('inbox'))
        
    except Exception as e:
        db.session.rollback()
        app.logger.error(f'Error marking message as read: {str(e)}')
        
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'status': 'error', 'message': 'Failed to mark message as read'}), 500
            
        flash('An error occurred. Please try again.', 'danger')
        return redirect(url_for('inbox'))

@app.route('/messages/reply/<int:message_id>', methods=['GET', 'POST'])
@login_required
def reply_message(message_id):
    """Reply to an existing message"""
    # Get the original message
    original_message = Message.query.get_or_404(message_id)
    
    # Verify the current user is the recipient of the original message
    if original_message.recipient_id != current_user.id:
        flash('Access denied.', 'danger')
        return redirect(url_for('inbox'))
    
    # Handle GET request - redirect to inbox (direct URL access not allowed)
    if request.method == 'GET':
        flash('Please use the reply button to respond to messages.', 'info')
        return redirect(url_for('inbox'))
    
    # Handle POST request - process the reply
    # Get reply content
    subject = request.form.get('subject', '').strip()
    content = request.form.get('content', '').strip()
    
    # Validate input
    if not subject or not content:
        flash('Subject and message content are required.', 'danger')
        return redirect(url_for('inbox'))
    
    try:
        # Create reply message
        reply = Message(
            subject=subject,
            content=content,
            sender_id=current_user.id,
            recipient_id=original_message.sender_id,
            created_at=datetime.utcnow(),
            is_read=False
        )
        
        # Mark original as read using utility method
        original_message.mark_as_read()
            
        db.session.add(reply)
        db.session.commit()
        
        flash('Reply sent successfully!', 'success')
        return redirect(url_for('inbox'))
        
    except Exception as e:
        db.session.rollback()
        app.logger.error(f'Error sending reply: {str(e)}')
        flash('An error occurred while sending your reply. Please try again.', 'danger')
        return redirect(url_for('inbox'))

@app.route('/messages/delete/<int:message_id>', methods=['POST'])
@login_required
def delete_message(message_id):
    """Delete a message"""
    message = Message.query.get_or_404(message_id)
    
    # Verify the current user owns this message (either sender or recipient)
    if message.sender_id != current_user.id and message.recipient_id != current_user.id:
        return jsonify({'success': False, 'error': 'Access denied'}), 403
    
    try:
        db.session.delete(message)
        db.session.commit()
        
        app.logger.info(f'🗑️ Message {message_id} deleted by user {current_user.id}')
        
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': True, 'message': 'Message deleted successfully'})
        else:
            flash('Message deleted successfully!', 'success')
            return redirect(url_for('inbox'))
            
    except Exception as e:
        db.session.rollback()
        app.logger.error(f'Error deleting message: {str(e)}')
        
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'error': str(e)}), 500
        else:
            flash('An error occurred while deleting the message.', 'danger')
            return redirect(url_for('inbox'))

@app.route('/messages/archive/<int:message_id>', methods=['POST'])
@login_required
def archive_message(message_id):
    """Archive a message"""
    message = Message.query.get_or_404(message_id)
    
    # Verify the current user owns this message (either sender or recipient)
    if message.sender_id != current_user.id and message.recipient_id != current_user.id:
        return jsonify({'success': False, 'error': 'Access denied'}), 403
    
    try:
        message.is_archived = True
        db.session.commit()
        
        app.logger.info(f'📦 Message {message_id} archived by user {current_user.id}')
        
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': True, 'message': 'Message archived successfully'})
        else:
            flash('Message archived successfully!', 'info')
            return redirect(url_for('inbox'))
            
    except Exception as e:
        db.session.rollback()
        app.logger.error(f'Error archiving message: {str(e)}')
        
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'error': str(e)}), 500
        else:
            flash('An error occurred while archiving the message.', 'info')
            return redirect(url_for('inbox'))

@app.route('/api/users/list')
@login_required
def api_users_list():
    """API endpoint to get list of users for messaging"""
    try:
        # Get all active users except the current user
        users = User.query.filter(
            User.id != current_user.id,
            User.active == True,
            User.email_verified == True
        ).order_by(User.full_name).all()
        
        user_list = [{
            'id': user.id,
            'full_name': user.full_name,
            'role': user.role.replace('_', ' ').title(),
            'username': user.username
        } for user in users]
        
        return jsonify({
            'success': True,
            'users': user_list
        })
    except Exception as e:
        app.logger.error(f'Error fetching users list: {str(e)}')
        return jsonify({
            'success': False,
            'message': 'Failed to load users'
        }), 500

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def edit_profile():
    form = ProfileForm(obj=current_user)
    
    if form.validate_on_submit():
        try:
            # Update basic profile information
            current_user.full_name = form.full_name.data
            current_user.phone = form.phone.data
            current_user.location = form.location.data
            
            # Handle profile picture upload
            if form.profile_picture.data:
                from storage_utils import save_profile_image, delete_profile_image
                
                # Save new profile picture
                new_image_path = save_profile_image(form.profile_picture.data)
                
                if new_image_path:
                    # Delete old profile picture if it exists and is not default
                    if current_user.profile_image and current_user.profile_image != 'default.jpg':
                        delete_profile_image(current_user.profile_image)
                    
                    # Update user's profile image
                    current_user.profile_image = new_image_path
                    app.logger.info(f"Profile picture updated for user {current_user.id}: {new_image_path}")
                else:
                    flash('Failed to upload profile picture. Please try again with a different image.', 'warning')
            
            db.session.commit()
            flash('Profile updated successfully!', 'success')
            return redirect(url_for('edit_profile'))
            
        except Exception as e:
            db.session.rollback()
            app.logger.error(f"Error updating profile: {str(e)}")
            flash('An error occurred while updating your profile. Please try again.', 'danger')
    
    return render_template('profile/edit_profile.html', form=form)

@app.route('/profile/remove-picture', methods=['POST'])
@login_required
def remove_profile_picture():
    """Remove user's profile picture and reset to default"""
    try:
        from storage_utils import delete_profile_image
        
        # Delete current profile picture if it exists and is not default
        if current_user.profile_image and current_user.profile_image != 'default.jpg':
            delete_profile_image(current_user.profile_image)
        
        # Reset to default
        current_user.profile_image = 'default.jpg'
        db.session.commit()
        
        flash('Profile picture removed successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Error removing profile picture: {str(e)}")
        flash('An error occurred while removing profile picture.', 'danger')
    
    return redirect(url_for('edit_profile'))

@app.route('/profile/ai-insights', methods=['GET'])
@login_required
def get_profile_ai_insights():
    """Get AI-powered profile insights and recommendations"""
    import json
    import re
    try:
        from ai_services import client
        import google.generativeai as genai
        
        if not client:
            return jsonify({
                'success': False,
                'error': 'AI service is currently unavailable. Please try again later.'
            }), 503
        
        # Gather user profile data
        user_data = {
            'role': current_user.role,
            'full_name': current_user.full_name,
            'location': current_user.location,
            'member_since': current_user.created_at.strftime('%B %Y'),
            'login_count': current_user.login_count,
            'profile_complete': bool(current_user.phone and current_user.location)
        }
        
        # Add role-specific data
        if current_user.role == 'farmer':
            user_data['total_crops'] = len(current_user.crops)
            user_data['active_crops'] = len([c for c in current_user.crops if c.status == 'available'])
            user_data['orders_received'] = len(current_user.orders_received)
            user_data['crop_types'] = list(set([c.name for c in current_user.crops[:5]]))
        elif current_user.role == 'buyer':
            user_data['orders_placed'] = len(current_user.orders_placed)
            user_data['completed_orders'] = len([o for o in current_user.orders_placed if o.status == 'delivered'])
        
        # Create AI prompt
        prompt = f"""
        As FarmLink AI's profile advisor, analyze this user's profile and provide personalized insights and recommendations.
        
        User Profile:
        - Role: {user_data['role'].title()}
        - Name: {user_data['full_name']}
        - Location: {user_data['location'] or 'Not specified'}
        - Member Since: {user_data['member_since']}
        - Login Count: {user_data['login_count']}
        - Profile Completeness: {'Complete' if user_data['profile_complete'] else 'Incomplete'}
        
        {'Farmer Statistics:' if current_user.role == 'farmer' else 'Buyer Statistics:'}
        {f"- Total Crops Listed: {user_data.get('total_crops', 0)}" if current_user.role == 'farmer' else f"- Orders Placed: {user_data.get('orders_placed', 0)}"}
        {f"- Active Crops: {user_data.get('active_crops', 0)}" if current_user.role == 'farmer' else f"- Completed Orders: {user_data.get('completed_orders', 0)}"}
        {f"- Orders Received: {user_data.get('orders_received', 0)}" if current_user.role == 'farmer' else ''}
        {f"- Crop Types: {', '.join(user_data.get('crop_types', [])) if user_data.get('crop_types') else 'None yet'}" if current_user.role == 'farmer' else ''}
        
        Provide a JSON response with the following structure:
        {{
            "profile_score": <number 0-100>,
            "profile_status": "<Excellent/Good/Fair/Needs Improvement>",
            "key_insights": [
                "<insight 1>",
                "<insight 2>",
                "<insight 3>"
            ],
            "recommendations": [
                {{
                    "title": "<recommendation title>",
                    "description": "<detailed description>",
                    "priority": "<high/medium/low>",
                    "action_url": "<optional URL>"
                }}
            ],
            "next_steps": [
                "<actionable step 1>",
                "<actionable step 2>",
                "<actionable step 3>"
            ],
            "personalized_message": "<encouraging personalized message>"
        }}
        
        Make insights specific to their role ({'farmer' if current_user.role == 'farmer' else 'buyer'}) and activity level.
        Be encouraging and provide actionable advice.
        """
        
        # Get AI response
        response = client.generate_content(
            prompt,
            generation_config=genai.GenerationConfig(
                temperature=0.7,
                top_p=0.9,
                max_output_tokens=2048,
            )
        )
        
        # Parse JSON response
        response_text = response.text.strip()
        
        # Extract JSON from markdown code blocks if present
        json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', response_text, re.DOTALL)
        if json_match:
            response_text = json_match.group(1)
        
        insights_data = json.loads(response_text)
        
        return jsonify({
            'success': True,
            'insights': insights_data,
            'generated_at': datetime.now().isoformat()
        })
        
    except json.JSONDecodeError as e:
        app.logger.error(f"Failed to parse AI response: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'Failed to process AI insights. Please try again.'
        }), 500
    except Exception as e:
        app.logger.error(f"Error generating AI insights: {str(e)}")
        
        # Check for quota exceeded error
        error_message = str(e)
        if 'quota' in error_message.lower() or '429' in error_message:
            return jsonify({
                'success': False,
                'error': 'AI service quota exceeded. Please try again later.'
            }), 429
        
        return jsonify({
            'success': False,
            'error': 'An error occurred while generating insights.'
        }), 500
    
    return redirect(url_for('edit_profile'))



@app.route('/payment-history')
@login_required
def payment_history():
    """Display user's payment history"""
    from models import Payment, Order
    
    # Get user's payments through orders (both as buyer and seller)
    buyer_payments = Payment.query.join(Order).filter(Order.buyer_id == current_user.id).order_by(Payment.created_at.desc()).all()
    
    # Calculate total amounts
    total_paid = sum(p.amount for p in buyer_payments if p.status == 'completed')
    total_pending = sum(p.amount for p in buyer_payments if p.status == 'pending')
    
    return render_template('payment/history.html', 
                         payments=buyer_payments,
                         total_paid=total_paid,
                         total_pending=total_pending)

@app.route('/my-ratings')
@login_required
def my_ratings():
    """Display user's rating dashboard"""
    from models import UserRating
    from sqlalchemy import func
    
    # Get ratings received by current user
    ratings_received = UserRating.query.filter_by(rated_user_id=current_user.id).order_by(UserRating.created_at.desc()).all()
    
    # Get ratings given by current user
    ratings_given = UserRating.query.filter_by(rater_id=current_user.id).order_by(UserRating.created_at.desc()).all()
    
    # Calculate average rating received
    avg_rating = db.session.query(func.avg(UserRating.rating)).filter_by(rated_user_id=current_user.id).scalar() or 0
    
    # Calculate rating distribution
    rating_distribution = {}
    for i in range(1, 6):
        count = UserRating.query.filter_by(rated_user_id=current_user.id, rating=i).count()
        rating_distribution[i] = count
    
    return render_template('ratings/dashboard.html',
                         ratings_received=ratings_received,
                         ratings_given=ratings_given,
                         avg_rating=avg_rating,
                         rating_distribution=rating_distribution)

# =============================================================================
# KYC VERIFICATION ROUTES
# =============================================================================

@app.route('/seller-kyc', methods=['GET', 'POST'])
@login_required
@farmer_required
@limiter.limit("3 per day", methods=["POST"])  # Rate limiting: max 3 submissions per day per user
def seller_kyc():
    """Display and handle KYC submission form for sellers"""
    from forms import SellerKYCForm
    from kyc_service import KYCService
    from kyc_security import https_required, validate_kyc_file_security, sanitize_kyc_input, log_kyc_security_event
    
    # HTTPS-only check for production
    if app.config.get('ENV') == 'production' and not request.is_secure:
        log_kyc_security_event('insecure_access', current_user.id, 'Attempted KYC submission over HTTP', severity='WARNING')
        flash('KYC submission requires a secure connection (HTTPS).', 'danger')
        return redirect(url_for('index'))
    
    # Check if user already has KYC record
    existing_kyc = KYCService.get_kyc_status(current_user.id)
    
    # If verified, redirect to status page
    if existing_kyc and existing_kyc.status == 'verified':
        flash('Your KYC is already verified.', 'info')
        return redirect(url_for('kyc_status'))
    
    # If pending, redirect to status page
    if existing_kyc and existing_kyc.status == 'pending':
        flash('Your KYC application is under review. Please wait for admin verification.', 'info')
        return redirect(url_for('kyc_status'))
    
    # If rejected, show resubmit form
    if existing_kyc and existing_kyc.status == 'rejected':
        return redirect(url_for('kyc_resubmit'))
    
    form = SellerKYCForm()
    
    # Pre-fill full name from user profile
    if request.method == 'GET':
        form.full_name.data = current_user.full_name
    
    if form.validate_on_submit():
        try:
            # Additional file security validation
            files_to_validate = [
                ('aadhaar_front', form.aadhaar_front.data),
                ('aadhaar_back', form.aadhaar_back.data),
                ('pan_card', form.pan_card.data)
            ]
            
            if form.land_proof.data:
                files_to_validate.append(('land_proof', form.land_proof.data))
            
            for file_name, file_obj in files_to_validate:
                is_valid, error_msg = validate_kyc_file_security(file_obj)
                if not is_valid:
                    log_kyc_security_event('invalid_file', current_user.id, f'{file_name}: {error_msg}', severity='WARNING')
                    flash(f'Security validation failed for {file_name}: {error_msg}', 'danger')
                    return render_template('kyc/submit_kyc.html', form=form)
            
            # Prepare form data (XSS prevention: data is already sanitized by WTForms)
            form_data = {
                'aadhaar_no': form.aadhaar_no.data,
                'pan_no': form.pan_no.data,
                'bank_account': form.bank_account.data,
                'ifsc': form.ifsc.data
            }
            
            # Additional sanitization
            form_data = sanitize_kyc_input(form_data)
            
            # Prepare files
            files = {
                'aadhaar_front': form.aadhaar_front.data,
                'aadhaar_back': form.aadhaar_back.data,
                'pan_card': form.pan_card.data,
                'land_proof': form.land_proof.data if form.land_proof.data else None
            }
            
            # Submit KYC (SQL injection prevention: using parameterized queries in service)
            success, message, kyc_record = KYCService.submit_kyc(current_user.id, form_data, files)
            
            if success:
                log_kyc_security_event('kyc_submitted', current_user.id, f'KYC ID: {kyc_record.id if kyc_record else "N/A"}', severity='INFO')
                # Send confirmation email
                try:
                    from email_service import EmailService
                    email_service = EmailService()
                    # TODO: Implement send_kyc_submission_confirmation method
                    # email_service.send_kyc_submission_confirmation(current_user, kyc_record)
                except Exception as e:
                    app.logger.error(f"Failed to send KYC confirmation email: {str(e)}")
                
                flash(message, 'success')
                return redirect(url_for('kyc_status'))
            else:
                flash(message, 'danger')
        
        except Exception as e:
            app.logger.error(f"Error submitting KYC: {str(e)}", exc_info=True)
            flash('An unexpected error occurred. Please try again.', 'danger')
    
    return render_template('kyc/submit_kyc.html', form=form)


@app.route('/kyc-status')
@login_required
@farmer_required
def kyc_status():
    """Display user's KYC verification status"""
    from kyc_service import KYCService
    
    kyc_record = KYCService.get_kyc_status(current_user.id)
    
    if not kyc_record:
        flash('You have not submitted KYC yet. Please submit your documents to get verified.', 'info')
        return redirect(url_for('seller_kyc'))
    
    return render_template('kyc/kyc_status.html', kyc_record=kyc_record)


@app.route('/kyc-resubmit', methods=['GET', 'POST'])
@login_required
@farmer_required
def kyc_resubmit():
    """Handle KYC resubmission for rejected applications"""
    from forms import SellerKYCForm
    from kyc_service import KYCService
    from kyc_security import validate_kyc_file_security, sanitize_kyc_input, log_kyc_security_event
    
    # Check if user has rejected KYC
    existing_kyc = KYCService.get_kyc_status(current_user.id)
    
    if not existing_kyc:
        flash('You have not submitted KYC yet.', 'info')
        return redirect(url_for('seller_kyc'))
    
    if existing_kyc.status != 'rejected':
        flash('Your KYC is not rejected. Cannot resubmit.', 'warning')
        return redirect(url_for('kyc_status'))
    
    form = SellerKYCForm()
    
    # Pre-fill full name from user profile
    if request.method == 'GET':
        form.full_name.data = current_user.full_name
    
    if form.validate_on_submit():
        try:
            # Additional file security validation
            files_to_validate = [
                ('aadhaar_front', form.aadhaar_front.data),
                ('aadhaar_back', form.aadhaar_back.data),
                ('pan_card', form.pan_card.data)
            ]
            
            if form.land_proof.data:
                files_to_validate.append(('land_proof', form.land_proof.data))
            
            for file_name, file_obj in files_to_validate:
                is_valid, error_msg = validate_kyc_file_security(file_obj)
                if not is_valid:
                    log_kyc_security_event('invalid_file_resubmit', current_user.id, f'{file_name}: {error_msg}', severity='WARNING')
                    flash(f'Security validation failed for {file_name}: {error_msg}', 'danger')
                    return render_template('kyc/resubmit_kyc.html', form=form, rejection_reason=existing_kyc.rejection_reason)
            
            # Prepare form data
            form_data = {
                'aadhaar_no': form.aadhaar_no.data,
                'pan_no': form.pan_no.data,
                'bank_account': form.bank_account.data,
                'ifsc': form.ifsc.data
            }
            
            # Additional sanitization
            form_data = sanitize_kyc_input(form_data)
            
            # Prepare files
            files = {
                'aadhaar_front': form.aadhaar_front.data,
                'aadhaar_back': form.aadhaar_back.data,
                'pan_card': form.pan_card.data,
                'land_proof': form.land_proof.data if form.land_proof.data else None
            }
            
            # Submit KYC (service handles resubmission logic)
            success, message, kyc_record = KYCService.submit_kyc(current_user.id, form_data, files)
            
            if success:
                log_kyc_security_event('kyc_resubmitted', current_user.id, f'KYC ID: {kyc_record.id if kyc_record else "N/A"}', severity='INFO')
            
            if success:
                # Send confirmation email
                try:
                    from email_service import EmailService
                    email_service = EmailService()
                    # TODO: Implement send_kyc_submission_confirmation method
                    # email_service.send_kyc_submission_confirmation(current_user, kyc_record)
                except Exception as e:
                    app.logger.error(f"Failed to send KYC confirmation email: {str(e)}")
                
                flash(message, 'success')
                return redirect(url_for('kyc_status'))
            else:
                flash(message, 'danger')
        
        except Exception as e:
            app.logger.error(f"Error resubmitting KYC: {str(e)}", exc_info=True)
            flash('An unexpected error occurred. Please try again.', 'danger')
    
    return render_template('kyc/resubmit_kyc.html', form=form, rejection_reason=existing_kyc.rejection_reason)


# =============================================================================
# ADMIN KYC VERIFICATION ROUTES
# =============================================================================

@app.route('/admin/kyc-verification')
@login_required
@admin_required
def admin_kyc_verification():
    """Admin KYC verification dashboard with statistics and filterable list"""
    from kyc_service import KYCService
    from kyc_security import log_kyc_security_event
    from datetime import datetime, timedelta
    
    # HTTPS-only check for production
    if app.config.get('ENV') == 'production' and not request.is_secure:
        log_kyc_security_event('insecure_admin_access', current_user.id, 'Attempted admin KYC access over HTTP', severity='WARNING')
        flash('Admin KYC operations require a secure connection (HTTPS).', 'danger')
        return redirect(url_for('admin_dashboard'))
    
    # Get filter parameters
    status_filter = request.args.get('status', 'all')
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    
    # Get KYC statistics
    stats = KYCService.get_kyc_statistics()
    
    # Get KYC list based on filters
    if status_filter == 'all':
        kyc_list = KYCService.get_all_kyc_list()
    else:
        kyc_list = KYCService.get_all_kyc_list(status=status_filter)
    
    # Apply date filters if provided
    date_from_obj = None
    date_to_obj = None
    
    if date_from:
        try:
            date_from_obj = datetime.strptime(date_from, '%Y-%m-%d')
            kyc_list = [kyc for kyc in kyc_list if kyc.created_at >= date_from_obj]
        except ValueError:
            flash('Invalid start date format', 'warning')
    
    if date_to:
        try:
            date_to_obj = datetime.strptime(date_to, '%Y-%m-%d') + timedelta(days=1)
            kyc_list = [kyc for kyc in kyc_list if kyc.created_at < date_to_obj]
        except ValueError:
            flash('Invalid end date format', 'warning')
    
    # Prepare chart data based on filters or default to last 30 days
    chart_labels = []
    chart_data = []
    
    if date_from and date_to:
        # Use filtered date range for chart
        try:
            start_date = datetime.strptime(date_from, '%Y-%m-%d').date()
            end_date = datetime.strptime(date_to, '%Y-%m-%d').date()
            
            # Calculate date range
            date_diff = (end_date - start_date).days
            
            # Query submissions in the filtered date range
            from models import SellerKYC
            from sqlalchemy import func
            submissions_by_date = db.session.query(
                func.date(SellerKYC.created_at).label('date'),
                func.count(SellerKYC.id).label('count')
            ).filter(
                SellerKYC.created_at >= start_date,
                SellerKYC.created_at < end_date + timedelta(days=1)
            ).group_by(
                func.date(SellerKYC.created_at)
            ).all()
            
            # Create dict for quick lookup
            submissions_dict = {str(row.date): row.count for row in submissions_by_date}
            
            # For large date ranges (>90 days), show only days with submissions
            if date_diff > 90:
                # Show only dates with actual submissions
                for date_str, count in sorted(submissions_dict.items()):
                    date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
                    chart_labels.append(date_obj.strftime('%b %d, %Y'))
                    chart_data.append(count)
                
                if not chart_data:
                    # If no submissions, show message
                    chart_labels = []
                    chart_data = []
            else:
                # For smaller ranges, show all days
                current_date = start_date
                while current_date <= end_date:
                    chart_labels.append(current_date.strftime('%b %d'))
                    chart_data.append(submissions_dict.get(str(current_date), 0))
                    current_date += timedelta(days=1)
                
        except Exception as e:
            flash(f'Error generating chart data: {str(e)}', 'danger')
            # Fall back to last 30 days
            date_from = ''
            date_to = ''
    
    # Default to last 30 days if no filters or no data found in filtered range
    if not chart_labels or not chart_data or (isinstance(chart_data, list) and len(chart_data) == 0):
        # Only use last 30 days if no filters were applied
        if not date_from and not date_to:
            chart_labels = []
            chart_data = []
            today = datetime.utcnow().date()
            for i in range(29, -1, -1):
                date = today - timedelta(days=i)
                chart_labels.append(date.strftime('%b %d'))
                
                # Find count for this date
                count = 0
                for submission in stats['submissions_last_30_days']:
                    if submission['date'] == str(date):
                        count = submission['count']
                        break
                chart_data.append(count)
        # If filters were applied but no data, keep empty lists to show "no data" message
        else:
            chart_labels = []
            chart_data = []
    
    return render_template('admin/kyc_dashboard.html',
                         stats=stats,
                         kyc_list=kyc_list,
                         status_filter=status_filter,
                         date_from=date_from,
                         date_to=date_to,
                         chart_labels=chart_labels,
                         chart_data=chart_data)


@app.route('/admin/kyc-verification/<int:kyc_id>')
@login_required
@admin_required
def admin_kyc_detail(kyc_id):
    """View detailed KYC information for review"""
    from kyc_service import KYCService
    from kyc_security import log_kyc_security_event
    
    # HTTPS-only check for production
    if app.config.get('ENV') == 'production' and not request.is_secure:
        log_kyc_security_event('insecure_admin_access', current_user.id, f'Attempted KYC detail access over HTTP for KYC ID: {kyc_id}', severity='WARNING')
        flash('Admin KYC operations require a secure connection (HTTPS).', 'danger')
        return redirect(url_for('admin_dashboard'))
    
    # Log admin access to KYC details
    log_kyc_security_event('admin_kyc_detail_view', current_user.id, f'KYC ID: {kyc_id}', severity='INFO')
    
    # Get KYC record
    kyc_record = KYCService.get_kyc_by_id(kyc_id)
    if not kyc_record:
        flash('KYC record not found', 'danger')
        return redirect(url_for('admin_kyc_verification'))
    
    # Get decrypted KYC data for admin view
    decrypted_data = KYCService.get_decrypted_kyc_data(kyc_record)
    
    # Get audit logs for this KYC record
    audit_logs = kyc_record.audit_logs
    
    return render_template('admin/kyc_detail.html',
                         kyc=kyc_record,
                         decrypted_data=decrypted_data,
                         audit_logs=audit_logs)


@app.route('/admin/kyc-verification/<int:kyc_id>/approve', methods=['POST'])
@login_required
@admin_required
def admin_kyc_approve(kyc_id):
    """Approve a KYC application"""
    from kyc_service import KYCService
    from kyc_security import log_kyc_security_event
    
    # Log approval attempt
    log_kyc_security_event('kyc_approval_attempt', current_user.id, f'KYC ID: {kyc_id}', severity='INFO')
    
    # Approve KYC
    success, message = KYCService.approve_kyc(kyc_id, current_user.id)
    
    if success:
        flash(message, 'success')
        
        # Send approval email notification
        try:
            kyc_record = KYCService.get_kyc_by_id(kyc_id)
            if kyc_record:
                from email_service import EmailService
                email_service = EmailService()
                # TODO: Implement send_kyc_approval_notification method
                # email_service.send_kyc_approval_notification(kyc_record.user)
        except Exception as e:
            app.logger.error(f"Failed to send KYC approval email: {str(e)}")
    else:
        flash(message, 'danger')
    
    return redirect(url_for('admin_kyc_detail', kyc_id=kyc_id))


@app.route('/admin/kyc-verification/<int:kyc_id>/reject', methods=['POST'])
@login_required
@admin_required
def admin_kyc_reject(kyc_id):
    """Reject a KYC application with reason"""
    from kyc_service import KYCService
    from kyc_security import log_kyc_security_event, sanitize_kyc_input
    
    # Log rejection attempt
    log_kyc_security_event('kyc_rejection_attempt', current_user.id, f'KYC ID: {kyc_id}', severity='INFO')
    
    # Get rejection reason from form and sanitize
    rejection_reason = request.form.get('rejection_reason', '').strip()
    rejection_reason = sanitize_kyc_input({'reason': rejection_reason})['reason']
    
    if not rejection_reason or len(rejection_reason) < 10:
        flash('Rejection reason must be at least 10 characters', 'danger')
        return redirect(url_for('admin_kyc_detail', kyc_id=kyc_id))
    
    # Reject KYC
    success, message = KYCService.reject_kyc(kyc_id, current_user.id, rejection_reason)
    
    if success:
        flash(message, 'success')
        
        # Send rejection email notification
        try:
            kyc_record = KYCService.get_kyc_by_id(kyc_id)
            if kyc_record:
                from email_service import EmailService
                email_service = EmailService()
                # TODO: Implement send_kyc_rejection_notification method
                # email_service.send_kyc_rejection_notification(kyc_record.user, rejection_reason)
        except Exception as e:
            app.logger.error(f"Failed to send KYC rejection email: {str(e)}")
    else:
        flash(message, 'danger')
    
    return redirect(url_for('admin_kyc_detail', kyc_id=kyc_id))


@app.route('/admin/kyc-verification/<int:kyc_id>/document/<doc_type>/view')
@login_required
@admin_required
def admin_kyc_document_view(kyc_id, doc_type):
    """Secure document view for admin (opens in browser)"""
    from kyc_service import KYCService
    from kyc_file_service import KYCFileService
    from kyc_security import validate_document_path, log_kyc_security_event
    from flask import send_file
    
    # Log admin document access
    log_kyc_security_event('admin_document_view', current_user.id, f'KYC ID: {kyc_id}, Doc Type: {doc_type}', severity='INFO')
    
    # Get KYC record
    kyc_record = KYCService.get_kyc_by_id(kyc_id)
    if not kyc_record:
        log_kyc_security_event('invalid_kyc_access', current_user.id, f'KYC ID: {kyc_id} not found', severity='WARNING')
        flash('KYC record not found', 'danger')
        return redirect(url_for('admin_kyc_verification'))
    
    # Get document path from KYC record
    document_paths = kyc_record.document_paths or {}
    if not document_paths or doc_type not in document_paths:
        log_kyc_security_event('invalid_document_type', current_user.id, f'KYC ID: {kyc_id}, Doc Type: {doc_type}', severity='WARNING')
        flash('Document not found', 'danger')
        return redirect(url_for('admin_kyc_detail', kyc_id=kyc_id))
    
    # Validate document path to prevent directory traversal
    doc_path = document_paths[doc_type]
    if not validate_document_path(doc_path):
        log_kyc_security_event('path_traversal_attempt', current_user.id, f'KYC ID: {kyc_id}, Path: {doc_path}', severity='ERROR')
        flash('Invalid document path', 'danger')
        return redirect(url_for('admin_kyc_detail', kyc_id=kyc_id))
    
    # Get absolute file path
    file_service = KYCFileService()
    file_path = file_service.get_document_path(doc_path)
    
    # Debug logging
    app.logger.info(f"Document path from DB: {doc_path}")
    app.logger.info(f"Resolved file path: {file_path}")
    
    if not file_path:
        log_kyc_security_event('document_not_found', current_user.id, f'KYC ID: {kyc_id}, Path: {doc_path}', severity='WARNING')
        flash('Document file not found on server', 'danger')
        return redirect(url_for('admin_kyc_detail', kyc_id=kyc_id))
    
    # Check if file actually exists and log file size
    import os
    if os.path.exists(file_path):
        file_size = os.path.getsize(file_path)
        app.logger.info(f"File exists. Size: {file_size} bytes")
    else:
        app.logger.error(f"File does not exist at path: {file_path}")
    
    # Send file for viewing in browser (not as attachment)
    try:
        # Detect MIME type for proper rendering
        import mimetypes
        mime_type, _ = mimetypes.guess_type(file_path)
        app.logger.info(f"Detected MIME type: {mime_type}")
        
        return send_file(
            file_path, 
            as_attachment=False,
            mimetype=mime_type
        )
    except Exception as e:
        app.logger.error(f"Error viewing document file: {str(e)}")
        log_kyc_security_event('document_view_error', current_user.id, f'KYC ID: {kyc_id}, Error: {str(e)}', severity='ERROR')
        flash('Error viewing document', 'danger')
        return redirect(url_for('admin_kyc_detail', kyc_id=kyc_id))


@app.route('/admin/kyc-verification/<int:kyc_id>/document/<doc_type>/download')
@login_required
@admin_required
def admin_kyc_document(kyc_id, doc_type):
    """Secure document download for admin"""
    from kyc_service import KYCService
    from kyc_file_service import KYCFileService
    from kyc_security import validate_document_path, log_kyc_security_event
    from flask import send_file
    
    # Log admin document access
    log_kyc_security_event('admin_document_download', current_user.id, f'KYC ID: {kyc_id}, Doc Type: {doc_type}', severity='INFO')
    
    # Get KYC record
    kyc_record = KYCService.get_kyc_by_id(kyc_id)
    if not kyc_record:
        log_kyc_security_event('invalid_kyc_access', current_user.id, f'KYC ID: {kyc_id} not found', severity='WARNING')
        flash('KYC record not found', 'danger')
        return redirect(url_for('admin_kyc_verification'))
    
    # Get document path from KYC record
    document_paths = kyc_record.document_paths or {}
    if not document_paths or doc_type not in document_paths:
        log_kyc_security_event('invalid_document_type', current_user.id, f'KYC ID: {kyc_id}, Doc Type: {doc_type}', severity='WARNING')
        flash('Document not found', 'danger')
        return redirect(url_for('admin_kyc_detail', kyc_id=kyc_id))
    
    # Validate document path to prevent directory traversal
    doc_path = document_paths[doc_type]
    if not validate_document_path(doc_path):
        log_kyc_security_event('path_traversal_attempt', current_user.id, f'KYC ID: {kyc_id}, Path: {doc_path}', severity='ERROR')
        flash('Invalid document path', 'danger')
        return redirect(url_for('admin_kyc_detail', kyc_id=kyc_id))
    
    # Get absolute file path
    file_service = KYCFileService()
    file_path = file_service.get_document_path(doc_path)
    
    if not file_path:
        log_kyc_security_event('document_not_found', current_user.id, f'KYC ID: {kyc_id}, Path: {doc_path}', severity='WARNING')
        flash('Document file not found on server', 'danger')
        return redirect(url_for('admin_kyc_detail', kyc_id=kyc_id))
    
    # Send file for download
    try:
        return send_file(file_path, as_attachment=True, download_name=f"{doc_type}_{kyc_id}.{file_path.split('.')[-1]}")
    except Exception as e:
        app.logger.error(f"Error sending document file: {str(e)}")
        log_kyc_security_event('document_download_error', current_user.id, f'KYC ID: {kyc_id}, Error: {str(e)}', severity='ERROR')
        flash('Error downloading document', 'danger')
        return redirect(url_for('admin_kyc_detail', kyc_id=kyc_id))


@app.route('/admin/kyc-verification/export/csv')
@login_required
@admin_required
def admin_kyc_export_csv():
    """Export KYC data to CSV format"""
    from kyc_service import KYCService
    from encryption_service import get_encryption_service
    import io
    import csv
    from flask import send_file
    
    try:
        # Get filter parameters (same as dashboard)
        status_filter = request.args.get('status', 'all')
        date_from = request.args.get('date_from', '')
        date_to = request.args.get('date_to', '')
        
        # Get KYC list based on filters
        if status_filter == 'all':
            kyc_list = KYCService.get_all_kyc_list()
        else:
            kyc_list = KYCService.get_all_kyc_list(status=status_filter)
        
        # Apply date filters if provided
        if date_from:
            try:
                date_from_obj = datetime.strptime(date_from, '%Y-%m-%d')
                kyc_list = [kyc for kyc in kyc_list if kyc.created_at >= date_from_obj]
            except ValueError:
                pass
        
        if date_to:
            try:
                from datetime import timedelta
                date_to_obj = datetime.strptime(date_to, '%Y-%m-%d') + timedelta(days=1)
                kyc_list = [kyc for kyc in kyc_list if kyc.created_at < date_to_obj]
            except ValueError:
                pass
        
        # Create CSV in memory
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write header
        writer.writerow([
            'KYC ID',
            'User ID',
            'Seller Name',
            'Username',
            'Email',
            'Phone',
            'Aadhaar (Masked)',
            'PAN',
            'Bank Account (Masked)',
            'IFSC Code',
            'Status',
            'Rejection Reason',
            'Submitted Date',
            'Verified Date',
            'Verified By',
            'Days to Verify',
            'Is Archived'
        ])
        
        # Get encryption service for masking
        encryption_service = get_encryption_service()
        
        # Write data rows
        for kyc in kyc_list:
            # Decrypt and mask sensitive data
            try:
                aadhaar = encryption_service.decrypt(kyc.aadhaar_no_encrypted)
                aadhaar_masked = encryption_service.mask_aadhaar(aadhaar)
                pan = encryption_service.decrypt(kyc.pan_no_encrypted)
                bank_account = encryption_service.decrypt(kyc.bank_account_encrypted)
                bank_account_masked = encryption_service.mask_bank_account(bank_account)
            except Exception as e:
                app.logger.error(f"Error decrypting KYC data for record {kyc.id}: {str(e)}")
                aadhaar_masked = 'ERROR'
                pan = 'ERROR'
                bank_account_masked = 'ERROR'
            
            # Calculate days to verify
            days_to_verify = ''
            if kyc.verified_at and kyc.created_at:
                time_diff = kyc.verified_at - kyc.created_at
                days_to_verify = str(round(time_diff.total_seconds() / 3600 / 24, 2))
            
            writer.writerow([
                kyc.id,
                kyc.user_id,
                kyc.user.full_name or '',
                kyc.user.username,
                kyc.user.email,
                kyc.user.phone or '',
                aadhaar_masked,
                pan,
                bank_account_masked,
                kyc.ifsc,
                kyc.status,
                kyc.rejection_reason or '',
                kyc.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                kyc.verified_at.strftime('%Y-%m-%d %H:%M:%S') if kyc.verified_at else '',
                kyc.verifier.full_name if kyc.verifier else '',
                days_to_verify,
                'Yes' if kyc.is_archived else 'No'
            ])
        
        # Prepare file for download
        output.seek(0)
        filename = f'kyc_data_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
        
        return send_file(
            io.BytesIO(output.getvalue().encode('utf-8-sig')),  # utf-8-sig for Excel compatibility
            mimetype='text/csv',
            as_attachment=True,
            download_name=filename
        )
        
    except Exception as e:
        app.logger.error(f"Error exporting KYC data to CSV: {str(e)}")
        flash('Error exporting KYC data. Please try again.', 'danger')
        return redirect(url_for('admin_kyc_verification'))


@app.route('/admin/kyc-verification/export/excel')
@login_required
@admin_required
def admin_kyc_export_excel():
    """Export KYC data to Excel format"""
    from kyc_service import KYCService
    from encryption_service import get_encryption_service
    import io
    from flask import send_file
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    
    try:
        # Get filter parameters
        status_filter = request.args.get('status', 'all')
        date_from = request.args.get('date_from', '')
        date_to = request.args.get('date_to', '')
        
        # Get KYC list based on filters
        if status_filter == 'all':
            kyc_list = KYCService.get_all_kyc_list()
        else:
            kyc_list = KYCService.get_all_kyc_list(status=status_filter)
        
        # Apply date filters
        if date_from:
            try:
                date_from_obj = datetime.strptime(date_from, '%Y-%m-%d')
                kyc_list = [kyc for kyc in kyc_list if kyc.created_at >= date_from_obj]
            except ValueError:
                pass
        
        if date_to:
            try:
                from datetime import timedelta
                date_to_obj = datetime.strptime(date_to, '%Y-%m-%d') + timedelta(days=1)
                kyc_list = [kyc for kyc in kyc_list if kyc.created_at < date_to_obj]
            except ValueError:
                pass
        
        # Create workbook
        wb = Workbook()
        ws = wb.active
        ws.title = "KYC Data"
        
        # Define styles
        header_font = Font(bold=True, color="FFFFFF", size=12)
        header_fill = PatternFill(start_color="28a745", end_color="28a745", fill_type="solid")
        header_alignment = Alignment(horizontal="center", vertical="center")
        border = Border(
            left=Side(style='thin'),
            right=Side(style='thin'),
            top=Side(style='thin'),
            bottom=Side(style='thin')
        )
        
        # Write header
        headers = [
            'KYC ID', 'User ID', 'Seller Name', 'Username', 'Email', 'Phone',
            'Aadhaar (Masked)', 'PAN', 'Bank Account (Masked)', 'IFSC Code',
            'Status', 'Rejection Reason', 'Submitted Date', 'Verified Date',
            'Verified By', 'Days to Verify', 'Is Archived'
        ]
        
        for col_num, header in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col_num, value=header)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = header_alignment
            cell.border = border
        
        # Get encryption service
        encryption_service = get_encryption_service()
        
        # Write data rows
        for row_num, kyc in enumerate(kyc_list, 2):
            try:
                aadhaar = encryption_service.decrypt(kyc.aadhaar_no_encrypted)
                aadhaar_masked = encryption_service.mask_aadhaar(aadhaar)
                pan = encryption_service.decrypt(kyc.pan_no_encrypted)
                bank_account = encryption_service.decrypt(kyc.bank_account_encrypted)
                bank_account_masked = encryption_service.mask_bank_account(bank_account)
            except Exception as e:
                app.logger.error(f"Error decrypting KYC data for record {kyc.id}: {str(e)}")
                aadhaar_masked = 'ERROR'
                pan = 'ERROR'
                bank_account_masked = 'ERROR'
            
            days_to_verify = ''
            if kyc.verified_at and kyc.created_at:
                time_diff = kyc.verified_at - kyc.created_at
                days_to_verify = round(time_diff.total_seconds() / 3600 / 24, 2)
            
            row_data = [
                kyc.id,
                kyc.user_id,
                kyc.user.full_name or '',
                kyc.user.username,
                kyc.user.email,
                kyc.user.phone or '',
                aadhaar_masked,
                pan,
                bank_account_masked,
                kyc.ifsc,
                kyc.status,
                kyc.rejection_reason or '',
                kyc.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                kyc.verified_at.strftime('%Y-%m-%d %H:%M:%S') if kyc.verified_at else '',
                kyc.verifier.full_name if kyc.verifier else '',
                days_to_verify,
                'Yes' if kyc.is_archived else 'No'
            ]
            
            for col_num, value in enumerate(row_data, 1):
                cell = ws.cell(row=row_num, column=col_num, value=value)
                cell.border = border
                cell.alignment = Alignment(vertical="center")
        
        # Auto-adjust column widths
        for column in ws.columns:
            max_length = 0
            column_letter = column[0].column_letter
            for cell in column:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
            adjusted_width = min(max_length + 2, 50)
            ws.column_dimensions[column_letter].width = adjusted_width
        
        # Save to BytesIO
        output = io.BytesIO()
        wb.save(output)
        output.seek(0)
        
        filename = f'kyc_data_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
        
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=filename
        )
        
    except Exception as e:
        app.logger.error(f"Error exporting KYC data to Excel: {str(e)}")
        flash('Error exporting KYC data. Please try again.', 'danger')
        return redirect(url_for('admin_kyc_verification'))


@app.route('/admin/kyc-verification/export/pdf')
@login_required
@admin_required
def admin_kyc_export_pdf():
    """Export KYC data to PDF format"""
    from kyc_service import KYCService
    from encryption_service import get_encryption_service
    import io
    from flask import send_file
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    
    try:
        # Get filter parameters
        status_filter = request.args.get('status', 'all')
        date_from = request.args.get('date_from', '')
        date_to = request.args.get('date_to', '')
        
        # Get KYC list based on filters
        if status_filter == 'all':
            kyc_list = KYCService.get_all_kyc_list()
        else:
            kyc_list = KYCService.get_all_kyc_list(status=status_filter)
        
        # Apply date filters
        if date_from:
            try:
                date_from_obj = datetime.strptime(date_from, '%Y-%m-%d')
                kyc_list = [kyc for kyc in kyc_list if kyc.created_at >= date_from_obj]
            except ValueError:
                pass
        
        if date_to:
            try:
                from datetime import timedelta
                date_to_obj = datetime.strptime(date_to, '%Y-%m-%d') + timedelta(days=1)
                kyc_list = [kyc for kyc in kyc_list if kyc.created_at < date_to_obj]
            except ValueError:
                pass
        
        # Create PDF in memory
        output = io.BytesIO()
        doc = SimpleDocTemplate(output, pagesize=landscape(A4), rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=18)
        
        # Container for PDF elements
        elements = []
        
        # Styles
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=18,
            textColor=colors.HexColor('#28a745'),
            spaceAfter=30,
            alignment=1  # Center
        )
        
        # Add title
        title = Paragraph("KYC Verification Report", title_style)
        elements.append(title)
        
        # Add metadata
        metadata_style = styles['Normal']
        metadata = Paragraph(
            f"<b>Generated:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}<br/>"
            f"<b>Status Filter:</b> {status_filter.title()}<br/>"
            f"<b>Total Records:</b> {len(kyc_list)}",
            metadata_style
        )
        elements.append(metadata)
        elements.append(Spacer(1, 20))
        
        # Prepare table data
        table_data = [[
            'ID', 'Seller Name', 'Email', 'Phone', 'PAN', 'Status', 'Submitted', 'Verified By'
        ]]
        
        # Get encryption service
        encryption_service = get_encryption_service()
        
        # Add data rows
        for kyc in kyc_list:
            try:
                pan = encryption_service.decrypt(kyc.pan_no_encrypted)
            except:
                pan = 'ERROR'
            
            table_data.append([
                str(kyc.id),
                kyc.user.full_name[:20] if kyc.user.full_name else '',
                kyc.user.email[:25],
                kyc.user.phone[:15] if kyc.user.phone else '',
                pan,
                kyc.status.upper(),
                kyc.created_at.strftime('%Y-%m-%d'),
                kyc.verifier.full_name[:15] if kyc.verifier else 'N/A'
            ])
        
        # Create table
        table = Table(table_data, repeatRows=1)
        table.setStyle(TableStyle([
            # Header styling
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#28a745')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            
            # Data styling
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 1, colors.grey),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f9fa')]),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        
        elements.append(table)
        
        # Build PDF
        doc.build(elements)
        output.seek(0)
        
        filename = f'kyc_report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.pdf'
        
        return send_file(
            output,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=filename
        )
        
    except Exception as e:
        app.logger.error(f"Error exporting KYC data to PDF: {str(e)}")
        flash('Error exporting KYC data. Please try again.', 'danger')
        return redirect(url_for('admin_kyc_verification'))


# =============================================================================
# EMAIL VERIFICATION ROUTES
# =============================================================================

@app.route('/verify-email/<int:user_id>', methods=['GET', 'POST'])
def verify_email(user_id):
    """Email verification page"""
    user = User.query.get_or_404(user_id)
    
    # If already verified, redirect to login
    if user.email_verified:
        flash('Your email is already verified. Please login.', 'info')
        return redirect(url_for('login'))
    
    # If no OTP exists (old users), generate and send one automatically
    if not user.verification_otp or not user.otp_generated_at:
        try:
            otp_service.send_verification_otp(user)
            logging.info(f"OTP sent to existing user: {user.email}")
        except Exception as e:
            logging.error(f"Failed to send OTP to existing user {user.email}: {str(e)}")
            flash('Failed to send verification code. Please try again later.', 'danger')
            return redirect(url_for('login'))
    
    form = OTPVerificationForm()
    
    if form.validate_on_submit():
        provided_otp = form.otp.data
        
        # Verify OTP
        if otp_service.verify_otp(user, provided_otp):
            user.email_verified = True
            user.verification_otp = None  # Clear OTP after verification
            user.otp_generated_at = None
            db.session.commit()
            
            # Send welcome email
            try:
                from email_service import EmailService
                email_service = EmailService()
                email_service.send_welcome_email(user)
            except Exception as e:
                logging.error(f"Failed to send welcome email: {str(e)}")
            
            flash('Email verified successfully! You can now login.', 'success')
            return redirect(url_for('login'))
        else:
            flash('Invalid or expired verification code. Please try again.', 'danger')
    
    return render_template('auth/verify_email.html', form=form, user=user)

@app.route('/resend-verification/<int:user_id>', methods=['POST'])
def resend_verification(user_id):
    """Resend verification OTP"""
    user = User.query.get_or_404(user_id)
    
    # Check if already verified
    if user.email_verified:
        flash('Your email is already verified.', 'info')
        return redirect(url_for('login'))
    
    # Rate limiting: Check if OTP was sent recently (within 1 minute)
    if user.otp_generated_at:
        time_since_last_otp = datetime.utcnow() - user.otp_generated_at
        if time_since_last_otp.total_seconds() < 60:
            remaining_seconds = 60 - int(time_since_last_otp.total_seconds())
            flash(f'Please wait {remaining_seconds} seconds before requesting a new code.', 'warning')
            return redirect(url_for('verify_email', user_id=user_id))
    
    # Send new OTP
    try:
        otp_service.send_verification_otp(user)
        flash('A new verification code has been sent to your email.', 'success')
    except Exception as e:
        logging.error(f"Failed to resend verification email: {str(e)}")
        flash('Failed to send verification code. Please try again later.', 'danger')
    
    return redirect(url_for('verify_email', user_id=user_id))

@app.route('/verification-status')
@login_required
def verification_status():
    """Show verification status page for logged-in users"""
    if current_user.email_verified:
        flash('Your account is already verified.', 'info')
        return redirect(url_for('dashboard'))
    
    return render_template('auth/verification_status.html', user=current_user)

@app.route('/admin/verify-user/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def admin_verify_user(user_id):
    """Admin route to manually verify a user's email"""
    user = User.query.get_or_404(user_id)
    
    if user.email_verified:
        flash(f'User {user.username} is already verified.', 'info')
    else:
        user.email_verified = True
        user.verification_otp = None
        user.otp_generated_at = None
        db.session.commit()
        
        # Send welcome email
        try:
            from email_service import EmailService
            email_service = EmailService()
            email_service.send_welcome_email(user)
        except Exception as e:
            logging.error(f"Failed to send welcome email: {str(e)}")
        
        flash(f'User {user.username} has been manually verified.', 'success')
    
    return redirect(request.referrer or url_for('admin_users'))

@app.errorhandler(404)
def not_found_error(error):
    return render_template('errors/404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return render_template('errors/500.html'), 500

# Import advanced routes
from advanced_routes import *

