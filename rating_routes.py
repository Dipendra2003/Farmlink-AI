"""Rating Routes - Web routes for product rating system"""
from flask import Blueprint, request, jsonify, flash, redirect, url_for, render_template
from flask_login import login_required, current_user
from extensions import db, limiter
from sqlalchemy import func, case
from models import ProductRating, RatingHelpfulVote, Order, Crop, User, SellerReputation
from rating_service import RatingService
from datetime import datetime, timedelta
import logging
from utils import sanitize_text

rating_bp = Blueprint('rating', __name__)
logger = logging.getLogger(__name__)


def _handle_response(success, message, status_code=200, redirect_url=None, flash_category=None, extra_data=None):
    """Unified response handler for JSON and HTML requests"""
    if request.is_json:
        response_data = {'success': success, 'message': message}
        if extra_data:
            response_data.update(extra_data)
        return jsonify(response_data), status_code
    
    if not flash_category:
        flash_category = 'success' if success else 'error'
    flash(message, flash_category)
    return redirect(redirect_url or request.referrer or url_for('marketplace'))


def _check_admin_access():
    """Check if current user has admin access"""
    if current_user.role != 'admin':
        raise PermissionError('Access denied. Admin privileges required.')


@rating_bp.route('/order/<int:order_id>/rate', methods=['GET', 'POST'])
@login_required
@limiter.limit("10 per hour")
def rate_product(order_id):
    from forms import ProductRatingForm
    
    try:
        can_rate, error_msg = RatingService.can_rate_order(current_user.id, order_id)
        if not can_rate:
            flash(error_msg, 'error')
            return redirect(url_for('marketplace'))

        order = Order.query.get_or_404(order_id)
        form = ProductRatingForm()
        
        # Pre-populate order_id for GET requests
        if request.method == 'GET':
            form.order_id.data = order_id

        if form.validate_on_submit():
            try:
                new_rating = RatingService.create_rating(
                    buyer_id=current_user.id,
                    order_id=order_id,
                    rating=int(form.rating.data),
                    review_text=form.review_text.data if form.review_text.data else None
                )
                logger.info(f'User {current_user.id} created rating {new_rating.id} for order {order_id}')
                flash('Thank you for your rating! Your feedback helps other buyers.', 'success')
                return redirect(url_for('order_detail', order_id=order_id))
            except ValueError as e:
                logger.error(f'ValueError in rating creation: {str(e)}')
                flash(str(e), 'error')
            except Exception as e:
                logger.error(f'Exception in rating creation: {str(e)}')
                db.session.rollback()
                flash('Failed to submit rating. Please try again.', 'error')
        else:
            # Log form validation errors
            if form.errors:
                logger.error(f'Form validation errors: {form.errors}')
                for field, errors in form.errors.items():
                    for error in errors:
                        flash(f'{field}: {error}', 'error')

        return render_template('ratings/rate_product.html', form=form, order=order)

    except Exception as e:
        db.session.rollback()
        logger.error(f'Error in rate_product: {str(e)}')
        flash('An error occurred. Please try again.', 'error')
        return redirect(url_for('marketplace'))


@rating_bp.route('/rating/<int:rating_id>/helpful', methods=['POST'])
@login_required
def mark_helpful(rating_id):
    """Mark a rating as helpful
    Requirements: 6.1, 6.2, 6.3, 6.4, 10.2"""
    try:
        rating = ProductRating.query.get(rating_id)
        if not rating:
            return _handle_response(False, 'Rating not found', 404)

        if rating.buyer_id == current_user.id:
            return _handle_response(False, 'You cannot mark your own rating as helpful', 403)

        existing_vote = RatingHelpfulVote.query.filter_by(
            rating_id=rating_id,
            user_id=current_user.id
        ).first()

        if existing_vote:
            return _handle_response(False, 'You have already marked this rating as helpful', 400, 
                                   redirect_url=url_for('rating.view_product_ratings', product_id=rating.product_id),
                                   flash_category='info')

        helpful_vote = RatingHelpfulVote(
            rating_id=rating_id,
            user_id=current_user.id,
            created_at=datetime.utcnow()
        )
        db.session.add(helpful_vote)
        rating.helpful_count += 1
        rating.updated_at = datetime.utcnow()
        db.session.commit()

        if rating.helpful_count == 5:
            try:
                from rating_notification_service import rating_notification_service
                rating_notification_service.notify_buyer_helpful_milestone(rating_id, milestone=5)
            except Exception as notify_err:
                logger.warning(f'Failed to send helpful milestone notification: {str(notify_err)}')

        logger.info(f'User {current_user.id} marked rating {rating_id} as helpful. Total: {rating.helpful_count}')

        if request.is_json:
            return jsonify({'success': True, 'message': 'Rating marked as helpful', 'helpful_count': rating.helpful_count}), 200

        flash('Thank you for your feedback!', 'success')
        return redirect(request.referrer or url_for('rating.view_product_ratings', product_id=rating.product_id))

    except Exception as e:
        db.session.rollback()
        logger.error(f'Error marking rating as helpful: {str(e)}')
        return _handle_response(False, 'An error occurred. Please try again.', 500)


@rating_bp.route('/rating/<int:rating_id>/respond', methods=['GET', 'POST'])
@login_required
def respond_to_rating(rating_id):
    """Seller responds to a rating
    Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 10.1"""
    from forms import SellerResponseForm
    from models import SellerResponse

    try:
        rating = ProductRating.query.get_or_404(rating_id)

        if rating.product.farmer_id != current_user.id:
            flash('You can only respond to ratings on your own products', 'error')
            return redirect(url_for('rating.view_product_ratings', product_id=rating.product_id))

        if SellerResponse.query.filter_by(rating_id=rating_id).first():
            flash('You have already responded to this rating', 'info')
            return redirect(url_for('rating.view_product_ratings', product_id=rating.product_id))

        form = SellerResponseForm()
        
        # Pre-populate rating_id for GET requests
        if request.method == 'GET':
            form.rating_id.data = rating_id

        if form.validate_on_submit():
            sanitized_response = sanitize_text(form.response_text.data.strip())
            
            seller_response = SellerResponse(
                rating_id=rating_id,
                seller_id=current_user.id,
                response_text=sanitized_response,
                created_at=datetime.utcnow()
            )
            db.session.add(seller_response)
            db.session.commit()

            try:
                from rating_notification_service import rating_notification_service
                rating_notification_service.notify_buyer_seller_response(rating_id)
            except Exception as notify_err:
                logger.warning(f'Failed to send seller response notification: {str(notify_err)}')

            logger.info(f'Seller {current_user.id} responded to rating {rating_id}')
            flash('Your response has been posted successfully', 'success')
            return redirect(url_for('rating.view_product_ratings', product_id=rating.product_id))

        return render_template('ratings/respond_to_rating.html', rating=rating, form=form)

    except Exception as e:
        db.session.rollback()
        logger.error(f'Error responding to rating: {str(e)}')
        flash('An error occurred. Please try again.', 'error')
        return redirect(url_for('marketplace'))


@rating_bp.route('/seller/<int:seller_id>/reputation')
def view_seller_reputation(seller_id):
    """View seller's reputation dashboard
    Requirements: 3.1, 3.2, 3.3, 3.4, 7.1, 7.3, 7.4, 7.5"""
    try:
        seller = User.query.get_or_404(seller_id)

        if seller.role not in ['farmer', 'manager_farmer']:
            flash('This user is not a seller', 'error')
            return redirect(url_for('marketplace'))

        reputation = SellerReputation.query.filter_by(seller_id=seller_id).first()

        if not reputation:
            reputation = SellerReputation(
                seller_id=seller_id,
                average_rating=0.0,
                total_ratings=0,
                five_star_count=0,
                four_star_count=0,
                three_star_count=0,
                two_star_count=0,
                one_star_count=0
            )

        avg_rating = round(reputation.average_rating, 2)
        total_ratings = reputation.total_ratings
        rating_distribution = {
            5: reputation.five_star_count,
            4: reputation.four_star_count,
            3: reputation.three_star_count,
            2: reputation.two_star_count,
            1: reputation.one_star_count
        }

        rating_percentages = {
            stars: (count / total_ratings * 100) if total_ratings > 0 else 0
            for stars, count in rating_distribution.items()
        }

        recent_ratings = db.session.query(ProductRating).join(
            Crop, ProductRating.product_id == Crop.id
        ).filter(
            Crop.farmer_id == seller_id,
            ProductRating.is_hidden == False
        ).order_by(ProductRating.created_at.desc()).limit(10).all()

        products = Crop.query.filter_by(farmer_id=seller_id).all()

        return render_template('ratings/seller_reputation.html',
                             seller=seller,
                             reputation=reputation,
                             avg_rating=avg_rating,
                             total_ratings=total_ratings,
                             rating_distribution=rating_distribution,
                             rating_percentages=rating_percentages,
                             recent_ratings=recent_ratings,
                             products=products)

    except Exception as e:
        logger.error(f'Error viewing seller reputation: {str(e)}')
        flash('An error occurred while loading seller reputation', 'error')
        return redirect(url_for('marketplace'))


@rating_bp.route('/rating/<int:rating_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_rating(rating_id):
    """Edit an existing rating
    Requirements: 2.1, 2.2, 2.3, 2.4, 11.1, 11.2"""
    from forms import ProductRatingForm
    
    try:
        rating = ProductRating.query.get_or_404(rating_id)

        if rating.buyer_id != current_user.id:
            flash('You can only edit your own ratings', 'error')
            return redirect(url_for('rating.view_product_ratings', product_id=rating.product_id))

        days_since_creation = (datetime.utcnow() - rating.created_at).days
        if days_since_creation > RatingService.RATING_EDIT_WINDOW_DAYS:
            flash(f'Edit window expired. You can only edit ratings within {RatingService.RATING_EDIT_WINDOW_DAYS} days of submission', 'error')
            return redirect(url_for('rating.view_product_ratings', product_id=rating.product_id))

        form = ProductRatingForm()

        if form.validate_on_submit():
            try:
                RatingService.update_rating(
                    rating_id=rating_id,
                    user_id=current_user.id,
                    new_rating=int(form.rating.data),
                    new_review_text=form.review_text.data if form.review_text.data else None
                )
                logger.info(f'User {current_user.id} updated rating {rating_id}')
                flash('Your rating has been updated successfully', 'success')
                return redirect(url_for('rating.view_product_ratings', product_id=rating.product_id))
            except ValueError as e:
                flash(str(e), 'error')

        if request.method == 'GET':
            form.rating.data = rating.rating
            form.review_text.data = rating.review_text
            form.order_id.data = rating.order_id

        return render_template('ratings/edit_rating.html', form=form, rating=rating)

    except Exception as e:
        db.session.rollback()
        logger.error(f'Error editing rating: {str(e)}')
        flash('An error occurred. Please try again.', 'error')
        return redirect(url_for('marketplace'))


@rating_bp.route('/rating/<int:rating_id>/delete', methods=['POST'])
@login_required
def delete_rating(rating_id):
    """Delete a rating
    Requirements: 2.1, 2.2, 2.3, 11.1, 11.2"""
    try:
        rating = ProductRating.query.get(rating_id)
        if not rating:
            return _handle_response(False, 'Rating not found', 404)

        product_id = rating.product_id

        if rating.buyer_id != current_user.id:
            return _handle_response(False, 'You can only delete your own ratings', 403,
                                   redirect_url=url_for('rating.view_product_ratings', product_id=product_id))

        days_since_creation = (datetime.utcnow() - rating.created_at).days
        if days_since_creation > RatingService.RATING_DELETE_WINDOW_DAYS:
            message = f'Delete window expired. You can only delete ratings within {RatingService.RATING_DELETE_WINDOW_DAYS} days of submission'
            return _handle_response(False, message, 400,
                                   redirect_url=url_for('rating.view_product_ratings', product_id=product_id))

        RatingService.delete_rating(rating_id, current_user.id)
        logger.info(f'User {current_user.id} deleted rating {rating_id}')

        return _handle_response(True, 'Rating deleted successfully', 200,
                               redirect_url=url_for('rating.view_product_ratings', product_id=product_id))

    except ValueError as e:
        return _handle_response(False, str(e), 400)
    except Exception as e:
        db.session.rollback()
        logger.error(f'Error deleting rating: {str(e)}')
        return _handle_response(False, 'An error occurred. Please try again.', 500)


@rating_bp.route('/rating/<int:rating_id>/flag', methods=['GET', 'POST'])
@login_required
def flag_rating(rating_id):
    """Flag a rating for moderation
    Requirements: 8.1, 8.2, 11.1"""
    from forms import RatingFlagForm
    from moderation_service import ModerationService
    
    try:
        rating = ProductRating.query.get_or_404(rating_id)

        if rating.buyer_id == current_user.id:
            flash('You cannot flag your own rating', 'error')
            return redirect(url_for('rating.view_product_ratings', product_id=rating.product_id))

        form = RatingFlagForm()

        if form.validate_on_submit():
            try:
                ModerationService.flag_rating(
                    rating_id=rating_id,
                    flagger_id=current_user.id,
                    reason=form.reason.data,
                    description=form.description.data if form.description.data else None
                )
                logger.info(f'User {current_user.id} flagged rating {rating_id} for reason: {form.reason.data}')
                flash('Thank you for reporting this review. Our moderation team will review it shortly.', 'success')
                return redirect(url_for('rating.view_product_ratings', product_id=rating.product_id))
            except ValueError as e:
                flash(str(e), 'error')

        if request.method == 'GET':
            form.rating_id.data = rating_id

        return render_template('ratings/flag_rating.html', form=form, rating=rating)

    except Exception as e:
        db.session.rollback()
        logger.error(f'Error flagging rating: {str(e)}')
        flash('An error occurred. Please try again.', 'error')
        return redirect(url_for('marketplace'))


@rating_bp.route('/product/<int:product_id>/ratings')
def view_product_ratings(product_id):
    """View all ratings for a product with filtering, sorting, and pagination
    Requirements: 3.1, 3.2, 3.3, 3.4, 5.1, 5.2, 5.3, 5.4, 5.5"""
    try:
        product = Crop.query.get_or_404(product_id)

        star_filter = request.args.get('stars', type=int)
        sort_by = request.args.get('sort', 'recent')
        page = request.args.get('page', 1, type=int)
        per_page = 20

        query = ProductRating.query.filter_by(product_id=product_id, is_hidden=False)

        if star_filter and 1 <= star_filter <= 5:
            query = query.filter_by(rating=star_filter)

        sort_options = {
            'helpful': [ProductRating.helpful_count.desc(), ProductRating.created_at.desc()],
            'highest': [ProductRating.rating.desc(), ProductRating.created_at.desc()],
            'lowest': [ProductRating.rating.asc(), ProductRating.created_at.desc()],
            'recent': [ProductRating.created_at.desc()]
        }
        query = query.order_by(*sort_options.get(sort_by, sort_options['recent']))

        from models import SellerResponse
        query = query.options(
            db.joinedload(ProductRating.buyer),
            db.joinedload(ProductRating.seller_response).joinedload(SellerResponse.seller),
            db.joinedload(ProductRating.helpful_votes)
        )

        ratings_pagination = query.paginate(page=page, per_page=per_page, error_out=False)

        rating_stats = db.session.query(
            func.avg(ProductRating.rating).label('avg_rating'),
            func.count(ProductRating.id).label('total_count'),
            func.sum(case((ProductRating.rating == 5, 1), else_=0)).label('five_star'),
            func.sum(case((ProductRating.rating == 4, 1), else_=0)).label('four_star'),
            func.sum(case((ProductRating.rating == 3, 1), else_=0)).label('three_star'),
            func.sum(case((ProductRating.rating == 2, 1), else_=0)).label('two_star'),
            func.sum(case((ProductRating.rating == 1, 1), else_=0)).label('one_star')
        ).filter(
            ProductRating.product_id == product_id,
            ProductRating.is_hidden == False
        ).first()

        avg_rating = float(rating_stats.avg_rating) if rating_stats.avg_rating else 0.0
        total_ratings = rating_stats.total_count or 0

        rating_distribution = {
            5: rating_stats.five_star or 0,
            4: rating_stats.four_star or 0,
            3: rating_stats.three_star or 0,
            2: rating_stats.two_star or 0,
            1: rating_stats.one_star or 0
        }

        rating_percentages = {
            stars: (count / total_ratings * 100) if total_ratings > 0 else 0
            for stars, count in rating_distribution.items()
        }

        user_helpful_votes = set()
        if current_user.is_authenticated:
            votes = RatingHelpfulVote.query.filter(
                RatingHelpfulVote.user_id == current_user.id,
                RatingHelpfulVote.rating_id.in_([r.id for r in ratings_pagination.items])
            ).all()
            user_helpful_votes = {vote.rating_id for vote in votes}

        return render_template('ratings/product_ratings.html',
                             product=product,
                             ratings=ratings_pagination.items,
                             pagination=ratings_pagination,
                             avg_rating=avg_rating,
                             total_ratings=total_ratings,
                             rating_distribution=rating_distribution,
                             rating_percentages=rating_percentages,
                             star_filter=star_filter,
                             sort_by=sort_by,
                             user_helpful_votes=user_helpful_votes)

    except Exception as e:
        logger.error(f'Error viewing product ratings: {str(e)}')
        flash('An error occurred while loading ratings', 'error')
        return redirect(url_for('marketplace'))


# ============================================================================
# ADMIN MODERATION ROUTES
# ============================================================================

@rating_bp.route('/admin/moderation-queue')
@login_required
def moderation_queue():
    """Display all flagged ratings for admin review
    Requirements: 8.1, 8.2, 8.3, 8.4"""
    from moderation_service import ModerationService
    
    try:
        _check_admin_access()
    except PermissionError as e:
        flash(str(e), 'error')
        return redirect(url_for('index'))
    
    try:
        status = request.args.get('status', 'pending')
        page = request.args.get('page', 1, type=int)
        per_page = 20

        queue_data = ModerationService.get_moderation_queue(status=status, page=page, per_page=per_page)
        stats = ModerationService.get_flag_statistics()

        logger.info(f'Admin {current_user.id} accessed moderation queue (status: {status}, page: {page})')

        return render_template('ratings/moderation_queue.html',
                             flags=queue_data['flags'],
                             total=queue_data['total'],
                             page=queue_data['page'],
                             per_page=queue_data['per_page'],
                             pages=queue_data['pages'],
                             has_next=queue_data['has_next'],
                             has_prev=queue_data['has_prev'],
                             status=status,
                             stats=stats)

    except Exception as e:
        logger.error(f'Error loading moderation queue: {str(e)}')
        flash('An error occurred while loading the moderation queue', 'error')
        return redirect(url_for('index'))


@rating_bp.route('/admin/moderate/<int:flag_id>', methods=['POST'])
@login_required
def moderate_rating(flag_id):
    """Take moderation action on a flagged rating
    Requirements: 8.3, 8.4"""
    from moderation_service import ModerationService
    
    try:
        _check_admin_access()
    except PermissionError as e:
        return _handle_response(False, str(e), 403, redirect_url=url_for('index'))
    
    try:
        action = request.form.get('action')
        notes = request.form.get('notes', '').strip()

        if action not in ['approve', 'hide', 'delete']:
            return _handle_response(False, 'Invalid action', 400, redirect_url=url_for('rating.moderation_queue'))

        result = ModerationService.moderate_rating(
            flag_id=flag_id,
            moderator_id=current_user.id,
            action=action,
            notes=notes if notes else None
        )

        logger.info(f'Admin {current_user.id} {action}d rating via flag {flag_id}')

        if request.is_json:
            return jsonify(result), 200

        action_messages = {
            'approve': 'Rating approved and flag resolved',
            'hide': 'Rating hidden from public view',
            'delete': 'Rating permanently deleted'
        }
        flash(action_messages.get(action, 'Action completed'), 'success')
        return redirect(url_for('rating.moderation_queue'))

    except ValueError as e:
        logger.warning(f'Moderation validation error: {str(e)}')
        return _handle_response(False, str(e), 400, redirect_url=url_for('rating.moderation_queue'))
    except Exception as e:
        db.session.rollback()
        logger.error(f'Error moderating rating: {str(e)}')
        return _handle_response(False, 'An error occurred', 500, redirect_url=url_for('rating.moderation_queue'))


@rating_bp.route('/admin/rating-analytics')
@login_required
def rating_analytics():
    """Display system-wide rating statistics and analytics
    Requirements: 8.1, 8.2"""
    from moderation_service import ModerationService
    
    try:
        _check_admin_access()
    except PermissionError as e:
        flash(str(e), 'error')
        return redirect(url_for('index'))
    
    try:
        period = request.args.get('period', '30')
        date_threshold = datetime.min if period == 'all' else datetime.utcnow() - timedelta(days=int(period))

        total_ratings = ProductRating.query.filter(ProductRating.created_at >= date_threshold).count()
        visible_ratings = ProductRating.query.filter(ProductRating.created_at >= date_threshold, ProductRating.is_hidden == False).count()
        hidden_ratings = ProductRating.query.filter(ProductRating.created_at >= date_threshold, ProductRating.is_hidden == True).count()
        flagged_ratings = ProductRating.query.filter(ProductRating.created_at >= date_threshold, ProductRating.is_flagged == True).count()

        avg_rating_result = db.session.query(func.avg(ProductRating.rating)).filter(
            ProductRating.created_at >= date_threshold,
            ProductRating.is_hidden == False
        ).scalar()
        platform_avg_rating = float(avg_rating_result) if avg_rating_result else 0.0

        rating_distribution = db.session.query(
            ProductRating.rating,
            func.count(ProductRating.id).label('count')
        ).filter(
            ProductRating.created_at >= date_threshold,
            ProductRating.is_hidden == False
        ).group_by(ProductRating.rating).all()

        distribution_dict = {i: 0 for i in range(1, 6)}
        for rating, count in rating_distribution:
            distribution_dict[rating] = count

        with_reviews = ProductRating.query.filter(
            ProductRating.created_at >= date_threshold,
            ProductRating.review_text.isnot(None),
            ProductRating.review_text != ''
        ).count()
        without_reviews = total_ratings - with_reviews

        responded_ratings = db.session.query(ProductRating).join('seller_response').filter(
            ProductRating.created_at >= date_threshold
        ).count()
        response_rate = (responded_ratings / total_ratings * 100) if total_ratings > 0 else 0

        total_helpful_votes = db.session.query(func.sum(ProductRating.helpful_count)).filter(
            ProductRating.created_at >= date_threshold
        ).scalar() or 0
        avg_helpful_per_rating = (total_helpful_votes / visible_ratings) if visible_ratings > 0 else 0

        top_sellers = db.session.query(SellerReputation, User).join(
            User, SellerReputation.seller_id == User.id
        ).filter(
            SellerReputation.total_ratings >= 5
        ).order_by(
            SellerReputation.average_rating.desc(),
            SellerReputation.total_ratings.desc()
        ).limit(10).all()

        recent_activity = db.session.query(
            func.date(ProductRating.created_at).label('date'),
            func.count(ProductRating.id).label('count')
        ).filter(
            ProductRating.created_at >= datetime.utcnow() - timedelta(days=7)
        ).group_by(func.date(ProductRating.created_at)).order_by('date').all()

        moderation_stats = ModerationService.get_flag_statistics()

        top_products = db.session.query(
            Crop,
            func.count(ProductRating.id).label('rating_count'),
            func.avg(ProductRating.rating).label('avg_rating')
        ).join(ProductRating, Crop.id == ProductRating.product_id).filter(
            ProductRating.created_at >= date_threshold,
            ProductRating.is_hidden == False
        ).group_by(Crop.id).order_by(func.count(ProductRating.id).desc()).limit(10).all()

        logger.info(f'Admin {current_user.id} accessed rating analytics (period: {period} days)')

        return render_template('ratings/rating_analytics.html',
                             period=period,
                             total_ratings=total_ratings,
                             visible_ratings=visible_ratings,
                             hidden_ratings=hidden_ratings,
                             flagged_ratings=flagged_ratings,
                             platform_avg_rating=platform_avg_rating,
                             rating_distribution=distribution_dict,
                             with_reviews=with_reviews,
                             without_reviews=without_reviews,
                             response_rate=response_rate,
                             total_helpful_votes=total_helpful_votes,
                             avg_helpful_per_rating=avg_helpful_per_rating,
                             top_sellers=top_sellers,
                             recent_activity=recent_activity,
                             moderation_stats=moderation_stats,
                             top_products=top_products)

    except Exception as e:
        logger.error(f'Error loading rating analytics: {str(e)}')
        flash('An error occurred while loading analytics', 'error')
        return redirect(url_for('index'))
