"""
REST API Routes for FarmLink AI
Provides API endpoints for mobile and third-party integrations
"""

import os
import json
import logging
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify, url_for
from werkzeug.utils import secure_filename
from flask_login import login_required
from app import app, db
from models import PestDiseaseAnalysis, Crop, User, Order
from pest_detection_service import PestDiseaseDetectionService
from api_utils import (
    api_token_required, rate_limit, validate_base64_image,
    save_base64_image, format_analysis_response, get_image_url
)
from role_hierarchy import admin_required

logger = logging.getLogger(__name__)

# Initialize pest detection service
pest_service = PestDiseaseDetectionService()


# =============================================================================
# API v1 - Pest & Disease Detection Endpoints
# =============================================================================

@app.route('/api/v1/pest-analysis', methods=['POST'])
@api_token_required
@rate_limit(max_requests=20, window_seconds=3600)  # 20 requests per hour
def api_pest_analysis_submit():
    """
    Submit pest and disease analysis request via API
    
    Request Body (JSON):
    {
        "crop_type": "tomato",
        "image": "base64_encoded_image_string",  // optional
        "symptoms": "leaves turning yellow...",  // optional
        "plant_stage": "flowering",  // optional
        "urgency": "high",  // optional: low, medium, high, critical
        "location": "Bihar, India",  // optional
        "crop_id": 123  // optional: link to existing crop
    }
    
    Response:
    {
        "success": true,
        "analysis_id": 456,
        "identified_issue": "Late Blight",
        "issue_type": "disease",
        "confidence_score": 87.5,
        "severity_level": "high",
        "treatment_recommendations": {...},
        "preventive_measures": [...],
        ...
    }
    """
    try:
        # Get user from request context (set by api_token_required)
        user = request.api_user
        
        # Parse JSON request
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'error': 'Invalid request',
                'message': 'Request body must be valid JSON'
            }), 400
        
        # Validate required fields
        crop_type = data.get('crop_type')
        if not crop_type:
            return jsonify({
                'success': False,
                'error': 'Missing required field',
                'message': 'crop_type is required'
            }), 400
        
        # Get optional fields
        image_base64 = data.get('image')
        symptoms = data.get('symptoms', '')
        plant_stage = data.get('plant_stage', '')
        urgency = data.get('urgency', 'medium')
        location = data.get('location', user.location or 'Not specified')
        crop_id = data.get('crop_id')
        
        # Validate that at least image or symptoms is provided
        if not image_base64 and not symptoms:
            return jsonify({
                'success': False,
                'error': 'Insufficient data',
                'message': 'Please provide either an image or symptom description (or both)'
            }), 400
        
        # Validate crop_id if provided
        if crop_id:
            crop = Crop.query.filter_by(id=crop_id, farmer_id=user.id).first()
            if not crop:
                return jsonify({
                    'success': False,
                    'error': 'Invalid crop_id',
                    'message': 'Crop not found or does not belong to your account'
                }), 400
        
        # Process image if provided
        image_path = None
        if image_base64:
            success, result = validate_base64_image(image_base64)
            if not success:
                return jsonify({
                    'success': False,
                    'error': 'Invalid image',
                    'message': result
                }), 400
            
            # Save image
            image_data = result
            image_path = save_base64_image(image_data, filename_prefix=f'api_user{user.id}')
            logger.info(f"API: Saved image to {image_path} for user {user.id}")
        
        # Prepare context for analysis
        context = {
            'location': location,
            'plant_stage': plant_stage,
            'urgency': urgency,
            'season': datetime.now().strftime('%B')
        }
        
        # Determine analysis mode and perform analysis
        analysis_result = None
        
        if image_path and symptoms:
            # Combined analysis
            logger.info(f"API: Performing combined analysis for user {user.id}")
            analysis_result = pest_service.combined_analysis(
                image_path, crop_type, symptoms, context
            )
        elif image_path:
            # Image-only analysis
            logger.info(f"API: Performing image analysis for user {user.id}")
            analysis_result = pest_service.analyze_image(
                image_path, crop_type, context
            )
        elif symptoms:
            # Symptoms-only analysis
            logger.info(f"API: Performing symptom analysis for user {user.id}")
            analysis_result = pest_service.analyze_symptoms(
                crop_type, symptoms, context
            )
        
        # Check if analysis was successful
        if not analysis_result or not analysis_result.get('success'):
            error_msg = analysis_result.get('error', 'Analysis failed') if analysis_result else 'Analysis service unavailable'
            return jsonify({
                'success': False,
                'error': 'Analysis failed',
                'message': error_msg
            }), 500
        
        # Adjust for urgency
        analysis_result = pest_service.adjust_for_urgency(analysis_result, urgency)
        
        # Generate treatment recommendations
        treatment_result = pest_service.generate_treatment_recommendations(
            analysis_result.get('identified_issue', ''),
            crop_type,
            analysis_result.get('severity_level', 'medium'),
            context
        )
        
        if treatment_result.get('success'):
            analysis_result['treatment_recommendations'] = treatment_result.get('treatment_recommendations', {})
            analysis_result['preventive_measures'] = treatment_result.get('preventive_measures', [])
        
        # Save to database
        try:
            pest_analysis = PestDiseaseAnalysis(
                user_id=user.id,
                crop_id=crop_id,
                crop_type=crop_type,
                symptoms_description=symptoms if symptoms else None,
                plant_stage=plant_stage if plant_stage else None,
                urgency_level=urgency,
                location=location,
                image_path=image_path,
                identified_issue=analysis_result.get('identified_issue'),
                issue_type=analysis_result.get('issue_type'),
                confidence_score=analysis_result.get('confidence_score'),
                severity_level=analysis_result.get('severity_level'),
                treatment_recommendations=json.dumps(analysis_result.get('treatment_recommendations', {})),
                preventive_measures=json.dumps(analysis_result.get('preventive_measures', [])),
                additional_diagnoses=json.dumps(analysis_result.get('alternative_diagnoses', [])),
                analysis_mode=analysis_result.get('analysis_mode', 'api'),
                ai_model_used=pest_service.model_name,
                analysis_status='completed'
            )
            
            db.session.add(pest_analysis)
            db.session.commit()
            
            logger.info(f"API: Saved analysis {pest_analysis.id} for user {user.id}")
            
            # Format response
            response = format_analysis_response(pest_analysis, include_full_details=True)
            response['success'] = True
            response['message'] = 'Analysis completed successfully'
            
            # Add image URL if image was provided
            if image_path:
                response['image_url'] = get_image_url(image_path)
            
            return jsonify(response), 200
            
        except Exception as db_error:
            logger.error(f"API: Database error saving analysis: {str(db_error)}")
            db.session.rollback()
            
            # Return analysis result even if save failed
            response = format_analysis_response(analysis_result, include_full_details=True)
            response['success'] = True
            response['warning'] = 'Analysis completed but could not be saved to history'
            
            return jsonify(response), 200
        
    except Exception as e:
        logger.error(f"API: Error in pest analysis endpoint: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'error': 'Internal server error',
            'message': 'An unexpected error occurred during analysis'
        }), 500


@app.route('/api/v1/pest-analysis', methods=['GET'])
@api_token_required
@rate_limit(max_requests=100, window_seconds=3600)  # 100 requests per hour
def api_pest_analysis_history():
    """
    Get pest and disease analysis history for authenticated user
    
    Query Parameters:
    - page: Page number (default: 1)
    - per_page: Results per page (default: 20, max: 100)
    - crop_type: Filter by crop type
    - severity: Filter by severity level (low, medium, high, critical)
    - date_from: Filter by start date (ISO format: YYYY-MM-DD)
    - date_to: Filter by end date (ISO format: YYYY-MM-DD)
    - crop_id: Filter by specific crop ID
    
    Response:
    {
        "success": true,
        "analyses": [...],
        "pagination": {
            "page": 1,
            "per_page": 20,
            "total": 45,
            "pages": 3
        }
    }
    """
    try:
        # Get user from request context
        user = request.api_user
        
        # Parse query parameters
        page = request.args.get('page', 1, type=int)
        per_page = min(request.args.get('per_page', 20, type=int), 100)  # Max 100 per page
        crop_type = request.args.get('crop_type')
        severity = request.args.get('severity')
        date_from = request.args.get('date_from')
        date_to = request.args.get('date_to')
        crop_id = request.args.get('crop_id', type=int)
        
        # Build query
        query = PestDiseaseAnalysis.query.filter_by(user_id=user.id)
        
        # Apply filters
        if crop_type:
            query = query.filter(PestDiseaseAnalysis.crop_type.ilike(f'%{crop_type}%'))
        
        if severity:
            query = query.filter_by(severity_level=severity.lower())
        
        if crop_id:
            query = query.filter_by(crop_id=crop_id)
        
        if date_from:
            try:
                date_from_obj = datetime.fromisoformat(date_from)
                query = query.filter(PestDiseaseAnalysis.created_at >= date_from_obj)
            except ValueError:
                return jsonify({
                    'success': False,
                    'error': 'Invalid date_from format',
                    'message': 'date_from must be in ISO format (YYYY-MM-DD)'
                }), 400
        
        if date_to:
            try:
                date_to_obj = datetime.fromisoformat(date_to)
                # Add one day to include the entire end date
                date_to_obj = date_to_obj.replace(hour=23, minute=59, second=59)
                query = query.filter(PestDiseaseAnalysis.created_at <= date_to_obj)
            except ValueError:
                return jsonify({
                    'success': False,
                    'error': 'Invalid date_to format',
                    'message': 'date_to must be in ISO format (YYYY-MM-DD)'
                }), 400
        
        # Order by most recent first
        query = query.order_by(PestDiseaseAnalysis.created_at.desc())
        
        # Paginate
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        
        # Format results
        analyses = []
        for analysis in pagination.items:
            analysis_data = {
                'id': analysis.id,
                'crop_type': analysis.crop_type,
                'crop_id': analysis.crop_id,
                'identified_issue': analysis.identified_issue,
                'issue_type': analysis.issue_type,
                'confidence_score': analysis.confidence_score,
                'severity_level': analysis.severity_level,
                'analysis_mode': analysis.analysis_mode,
                'urgency_level': analysis.urgency_level,
                'location': analysis.location,
                'plant_stage': analysis.plant_stage,
                'created_at': analysis.created_at.isoformat() if analysis.created_at else None,
                'image_url': get_image_url(analysis.image_path) if analysis.image_path else None
            }
            analyses.append(analysis_data)
        
        # Build response
        response = {
            'success': True,
            'analyses': analyses,
            'pagination': {
                'page': pagination.page,
                'per_page': pagination.per_page,
                'total': pagination.total,
                'pages': pagination.pages,
                'has_next': pagination.has_next,
                'has_prev': pagination.has_prev
            }
        }
        
        return jsonify(response), 200
        
    except Exception as e:
        logger.error(f"API: Error in pest analysis history endpoint: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'error': 'Internal server error',
            'message': 'An unexpected error occurred while fetching history'
        }), 500


@app.route('/api/v1/pest-analysis/<int:analysis_id>', methods=['GET'])
@api_token_required
@rate_limit(max_requests=100, window_seconds=3600)  # 100 requests per hour
def api_pest_analysis_detail(analysis_id):
    """
    Get detailed information about a specific analysis
    
    Response:
    {
        "success": true,
        "analysis": {
            "id": 123,
            "crop_type": "tomato",
            "identified_issue": "Late Blight",
            "treatment_recommendations": {...},
            "preventive_measures": [...],
            ...
        }
    }
    """
    try:
        # Get user from request context
        user = request.api_user
        
        # Get analysis
        analysis = PestDiseaseAnalysis.query.filter_by(
            id=analysis_id,
            user_id=user.id
        ).first()
        
        if not analysis:
            return jsonify({
                'success': False,
                'error': 'Not found',
                'message': 'Analysis not found or does not belong to your account'
            }), 404
        
        # Format response with full details
        response = {
            'success': True,
            'analysis': format_analysis_response(analysis, include_full_details=True)
        }
        
        # Add image URL
        if analysis.image_path:
            response['analysis']['image_url'] = get_image_url(analysis.image_path)
        
        return jsonify(response), 200
        
    except Exception as e:
        logger.error(f"API: Error in pest analysis detail endpoint: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'error': 'Internal server error',
            'message': 'An unexpected error occurred while fetching analysis details'
        }), 500


# =============================================================================
# API Token Management Endpoints
# =============================================================================

@app.route('/api/v1/token/generate', methods=['POST'])
def api_generate_token():
    """
    Generate a new API token for authenticated user
    Requires username and password authentication
    
    Request Body (JSON):
    {
        "username": "farmer123",
        "password": "password123",
        "expires_in_days": 365  // optional, default: 365
    }
    
    Response:
    {
        "success": true,
        "api_token": "abc123...",
        "expires_at": "2025-10-30T00:00:00",
        "message": "API token generated successfully"
    }
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'error': 'Invalid request',
                'message': 'Request body must be valid JSON'
            }), 400
        
        username = data.get('username')
        password = data.get('password')
        expires_in_days = data.get('expires_in_days', 365)
        
        if not username or not password:
            return jsonify({
                'success': False,
                'error': 'Missing credentials',
                'message': 'username and password are required'
            }), 400
        
        # Authenticate user
        user = User.query.filter_by(username=username, active=True).first()
        
        if not user or not user.check_password(password):
            return jsonify({
                'success': False,
                'error': 'Authentication failed',
                'message': 'Invalid username or password'
            }), 401
        
        # Generate new token
        from api_utils import generate_api_token
        
        new_token = generate_api_token()
        user.api_token = new_token
        user.api_token_created = datetime.utcnow()
        user.api_token_expires = datetime.utcnow() + timedelta(days=expires_in_days)
        
        db.session.commit()
        
        logger.info(f"API: Generated new token for user {user.id}")
        
        return jsonify({
            'success': True,
            'api_token': new_token,
            'expires_at': user.api_token_expires.isoformat(),
            'message': 'API token generated successfully. Keep this token secure!'
        }), 200
        
    except Exception as e:
        logger.error(f"API: Error generating token: {str(e)}", exc_info=True)
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': 'Internal server error',
            'message': 'Failed to generate API token'
        }), 500


@app.route('/api/v1/token/revoke', methods=['POST'])
@api_token_required
def api_revoke_token():
    """
    Revoke the current API token
    
    Response:
    {
        "success": true,
        "message": "API token revoked successfully"
    }
    """
    try:
        user = request.api_user
        
        # Revoke token
        user.api_token = None
        user.api_token_created = None
        user.api_token_expires = None
        
        db.session.commit()
        
        logger.info(f"API: Revoked token for user {user.id}")
        
        return jsonify({
            'success': True,
            'message': 'API token revoked successfully'
        }), 200
        
    except Exception as e:
        logger.error(f"API: Error revoking token: {str(e)}", exc_info=True)
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': 'Internal server error',
            'message': 'Failed to revoke API token'
        }), 500


# =============================================================================
# API Status and Documentation Endpoints
# =============================================================================

@app.route('/api/v1/status', methods=['GET'])
def api_status():
    """
    Get API status and service availability
    
    Response:
    {
        "status": "operational",
        "version": "1.0",
        "services": {
            "pest_detection": "available",
            "database": "available"
        }
    }
    """
    try:
        # Check pest detection service
        pest_status = 'available' if pest_service.is_available() else 'unavailable'
        
        # Check database
        try:
            db.session.execute('SELECT 1')
            db_status = 'available'
        except:
            db_status = 'unavailable'
        
        return jsonify({
            'status': 'operational' if pest_status == 'available' and db_status == 'available' else 'degraded',
            'version': '1.0',
            'services': {
                'pest_detection': pest_status,
                'database': db_status
            },
            'timestamp': datetime.utcnow().isoformat()
        }), 200
        
    except Exception as e:
        logger.error(f"API: Error checking status: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': 'Failed to check service status'
        }), 500


# =============================================================================
# API v1 - Product Rating Endpoints
# =============================================================================

@app.route('/api/v1/products/<int:product_id>/ratings', methods=['GET'])
@api_token_required
@rate_limit(max_requests=100, window_seconds=3600)  # 100 requests per hour
def api_get_product_ratings(product_id):
    """
    Get ratings for a product (paginated)
    
    Query Parameters:
    - page: Page number (default: 1)
    - per_page: Results per page (default: 20, max: 100)
    - sort: Sort order (recent, helpful, highest, lowest) (default: recent)
    - min_rating: Filter by minimum rating (1-5)
    - max_rating: Filter by maximum rating (1-5)
    
    Response:
    {
        "success": true,
        "product_id": 123,
        "average_rating": 4.5,
        "total_ratings": 45,
        "ratings": [...],
        "pagination": {
            "page": 1,
            "per_page": 20,
            "total": 45,
            "pages": 3
        }
    }
    """
    try:
        from models import ProductRating, Crop
        
        # Verify product exists
        product = Crop.query.get(product_id)
        if not product:
            return jsonify({
                'success': False,
                'error': 'Not found',
                'message': 'Product not found'
            }), 404
        
        # Parse query parameters
        page = request.args.get('page', 1, type=int)
        per_page = min(request.args.get('per_page', 20, type=int), 100)
        sort = request.args.get('sort', 'recent')
        min_rating = request.args.get('min_rating', type=int)
        max_rating = request.args.get('max_rating', type=int)
        
        # Build query - only show non-hidden ratings
        query = ProductRating.query.filter_by(
            product_id=product_id,
            is_hidden=False
        )
        
        # Apply rating filters
        if min_rating:
            query = query.filter(ProductRating.rating >= min_rating)
        if max_rating:
            query = query.filter(ProductRating.rating <= max_rating)
        
        # Apply sorting
        if sort == 'helpful':
            query = query.order_by(ProductRating.helpful_count.desc())
        elif sort == 'highest':
            query = query.order_by(ProductRating.rating.desc(), ProductRating.created_at.desc())
        elif sort == 'lowest':
            query = query.order_by(ProductRating.rating.asc(), ProductRating.created_at.desc())
        else:  # recent (default)
            query = query.order_by(ProductRating.created_at.desc())
        
        # Paginate
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        
        # Calculate average rating and total count
        from sqlalchemy import func
        stats = db.session.query(
            func.avg(ProductRating.rating).label('avg_rating'),
            func.count(ProductRating.id).label('total_count')
        ).filter_by(
            product_id=product_id,
            is_hidden=False
        ).first()
        
        average_rating = round(float(stats.avg_rating), 1) if stats.avg_rating else 0.0
        total_ratings = stats.total_count or 0
        
        # Format ratings
        ratings = []
        for rating in pagination.items:
            rating_data = {
                'id': rating.id,
                'rating': rating.rating,
                'review_text': rating.review_text,
                'is_verified_purchase': rating.is_verified_purchase,
                'helpful_count': rating.helpful_count,
                'created_at': rating.created_at.isoformat() if rating.created_at else None,
                'edited_at': rating.edited_at.isoformat() if rating.edited_at else None,
                'buyer': {
                    'id': rating.buyer.id,
                    'username': rating.buyer.username,
                    'full_name': rating.buyer.full_name
                }
            }
            
            # Include seller response if exists
            if rating.seller_response:
                rating_data['seller_response'] = {
                    'response_text': rating.seller_response.response_text,
                    'created_at': rating.seller_response.created_at.isoformat()
                }
            
            ratings.append(rating_data)
        
        # Build response
        response = {
            'success': True,
            'product_id': product_id,
            'average_rating': average_rating,
            'total_ratings': total_ratings,
            'ratings': ratings,
            'pagination': {
                'page': pagination.page,
                'per_page': pagination.per_page,
                'total': pagination.total,
                'pages': pagination.pages,
                'has_next': pagination.has_next,
                'has_prev': pagination.has_prev
            }
        }
        
        return jsonify(response), 200
        
    except Exception as e:
        logger.error(f"API: Error in get product ratings endpoint: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'error': 'Internal server error',
            'message': 'An unexpected error occurred while fetching ratings'
        }), 500


@app.route('/api/v1/orders/<int:order_id>/rate', methods=['POST'])
@api_token_required
@rate_limit(max_requests=10, window_seconds=3600)  # 10 ratings per hour
def api_submit_rating(order_id):
    """
    Submit a product rating via API
    
    Request Body (JSON):
    {
        "rating": 5,  // required: 1-5
        "review_text": "Great product!"  // optional: 10-1000 chars
    }
    
    Response:
    {
        "success": true,
        "rating_id": 123,
        "message": "Rating submitted successfully"
    }
    """
    try:
        from rating_service import RatingService
        
        # Get user from request context
        user = request.api_user
        
        # Parse JSON request
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'error': 'Invalid request',
                'message': 'Request body must be valid JSON'
            }), 400
        
        # Validate required fields
        rating = data.get('rating')
        if rating is None:
            return jsonify({
                'success': False,
                'error': 'Missing required field',
                'message': 'rating is required'
            }), 400
        
        # Validate rating value
        try:
            rating = int(rating)
            if rating < 1 or rating > 5:
                raise ValueError()
        except (ValueError, TypeError):
            return jsonify({
                'success': False,
                'error': 'Invalid rating',
                'message': 'rating must be an integer between 1 and 5'
            }), 400
        
        # Get optional review text
        review_text = data.get('review_text')
        
        # Validate review text length if provided
        if review_text:
            if len(review_text) < 10:
                return jsonify({
                    'success': False,
                    'error': 'Invalid review text',
                    'message': 'review_text must be at least 10 characters'
                }), 400
            if len(review_text) > 1000:
                return jsonify({
                    'success': False,
                    'error': 'Invalid review text',
                    'message': 'review_text cannot exceed 1000 characters'
                }), 400
        
        # Create rating using service
        try:
            new_rating = RatingService.create_rating(
                buyer_id=user.id,
                order_id=order_id,
                rating=rating,
                review_text=review_text
            )
            
            logger.info(f"API: Created rating {new_rating.id} for order {order_id} by user {user.id}")
            
            return jsonify({
                'success': True,
                'rating_id': new_rating.id,
                'message': 'Rating submitted successfully',
                'rating': {
                    'id': new_rating.id,
                    'rating': new_rating.rating,
                    'review_text': new_rating.review_text,
                    'product_id': new_rating.product_id,
                    'created_at': new_rating.created_at.isoformat()
                }
            }), 201
            
        except ValueError as ve:
            # Business logic validation errors
            return jsonify({
                'success': False,
                'error': 'Validation error',
                'message': str(ve)
            }), 422
        
    except Exception as e:
        logger.error(f"API: Error in submit rating endpoint: {str(e)}", exc_info=True)
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': 'Internal server error',
            'message': 'An unexpected error occurred while submitting rating'
        }), 500


@app.route('/api/v1/ratings/<int:rating_id>', methods=['PUT'])
@api_token_required
@rate_limit(max_requests=20, window_seconds=3600)  # 20 updates per hour
def api_update_rating(rating_id):
    """
    Update a rating via API
    
    Request Body (JSON):
    {
        "rating": 4,  // required: 1-5
        "review_text": "Updated review"  // optional: 10-1000 chars
    }
    
    Response:
    {
        "success": true,
        "message": "Rating updated successfully"
    }
    """
    try:
        from rating_service import RatingService
        
        # Get user from request context
        user = request.api_user
        
        # Parse JSON request
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'error': 'Invalid request',
                'message': 'Request body must be valid JSON'
            }), 400
        
        # Validate required fields
        new_rating = data.get('rating')
        if new_rating is None:
            return jsonify({
                'success': False,
                'error': 'Missing required field',
                'message': 'rating is required'
            }), 400
        
        # Validate rating value
        try:
            new_rating = int(new_rating)
            if new_rating < 1 or new_rating > 5:
                raise ValueError()
        except (ValueError, TypeError):
            return jsonify({
                'success': False,
                'error': 'Invalid rating',
                'message': 'rating must be an integer between 1 and 5'
            }), 400
        
        # Get optional review text
        new_review_text = data.get('review_text')
        
        # Validate review text length if provided
        if new_review_text:
            if len(new_review_text) < 10:
                return jsonify({
                    'success': False,
                    'error': 'Invalid review text',
                    'message': 'review_text must be at least 10 characters'
                }), 400
            if len(new_review_text) > 1000:
                return jsonify({
                    'success': False,
                    'error': 'Invalid review text',
                    'message': 'review_text cannot exceed 1000 characters'
                }), 400
        
        # Update rating using service
        try:
            updated_rating = RatingService.update_rating(
                rating_id=rating_id,
                user_id=user.id,
                new_rating=new_rating,
                new_review_text=new_review_text
            )
            
            logger.info(f"API: Updated rating {rating_id} by user {user.id}")
            
            return jsonify({
                'success': True,
                'message': 'Rating updated successfully',
                'rating': {
                    'id': updated_rating.id,
                    'rating': updated_rating.rating,
                    'review_text': updated_rating.review_text,
                    'edited_at': updated_rating.edited_at.isoformat() if updated_rating.edited_at else None
                }
            }), 200
            
        except ValueError as ve:
            # Business logic validation errors
            return jsonify({
                'success': False,
                'error': 'Validation error',
                'message': str(ve)
            }), 422
        
    except Exception as e:
        logger.error(f"API: Error in update rating endpoint: {str(e)}", exc_info=True)
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': 'Internal server error',
            'message': 'An unexpected error occurred while updating rating'
        }), 500


@app.route('/api/v1/ratings/<int:rating_id>', methods=['DELETE'])
@api_token_required
@rate_limit(max_requests=20, window_seconds=3600)  # 20 deletes per hour
def api_delete_rating(rating_id):
    """
    Delete a rating via API
    
    Response:
    {
        "success": true,
        "message": "Rating deleted successfully"
    }
    """
    try:
        from rating_service import RatingService
        
        # Get user from request context
        user = request.api_user
        
        # Delete rating using service
        try:
            RatingService.delete_rating(
                rating_id=rating_id,
                user_id=user.id
            )
            
            logger.info(f"API: Deleted rating {rating_id} by user {user.id}")
            
            return jsonify({
                'success': True,
                'message': 'Rating deleted successfully'
            }), 200
            
        except ValueError as ve:
            # Business logic validation errors
            return jsonify({
                'success': False,
                'error': 'Validation error',
                'message': str(ve)
            }), 422
        
    except Exception as e:
        logger.error(f"API: Error in delete rating endpoint: {str(e)}", exc_info=True)
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': 'Internal server error',
            'message': 'An unexpected error occurred while deleting rating'
        }), 500


@app.route('/api/v1/sellers/<int:seller_id>/reputation', methods=['GET'])
@api_token_required
@rate_limit(max_requests=100, window_seconds=3600)  # 100 requests per hour
def api_get_seller_reputation(seller_id):
    """
    Get seller reputation data
    
    Response:
    {
        "success": true,
        "seller_id": 123,
        "reputation": {
            "average_rating": 4.52,
            "total_ratings": 45,
            "rating_distribution": {
                "5": 25,
                "4": 15,
                "3": 3,
                "2": 1,
                "1": 1
            },
            "last_updated": "2025-10-30T12:00:00"
        }
    }
    """
    try:
        from models import SellerReputation, User
        
        # Verify seller exists
        seller = User.query.get(seller_id)
        if not seller:
            return jsonify({
                'success': False,
                'error': 'Not found',
                'message': 'Seller not found'
            }), 404
        
        # Get reputation data
        reputation = SellerReputation.query.filter_by(seller_id=seller_id).first()
        
        if not reputation:
            # No reputation data yet - return defaults
            return jsonify({
                'success': True,
                'seller_id': seller_id,
                'reputation': {
                    'average_rating': 0.0,
                    'total_ratings': 0,
                    'rating_distribution': {
                        '5': 0,
                        '4': 0,
                        '3': 0,
                        '2': 0,
                        '1': 0
                    },
                    'last_updated': None
                }
            }), 200
        
        # Build response
        response = {
            'success': True,
            'seller_id': seller_id,
            'seller': {
                'username': seller.username,
                'full_name': seller.full_name
            },
            'reputation': {
                'average_rating': round(reputation.average_rating, 2),
                'total_ratings': reputation.total_ratings,
                'rating_distribution': {
                    '5': reputation.five_star_count,
                    '4': reputation.four_star_count,
                    '3': reputation.three_star_count,
                    '2': reputation.two_star_count,
                    '1': reputation.one_star_count
                },
                'last_updated': reputation.last_updated.isoformat() if reputation.last_updated else None
            }
        }
        
        return jsonify(response), 200
        
    except Exception as e:
        logger.error(f"API: Error in get seller reputation endpoint: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'error': 'Internal server error',
            'message': 'An unexpected error occurred while fetching seller reputation'
        }), 500


logger.info("API routes loaded successfully")


# =============================================================================
# Admin Dashboard API Endpoints
# =============================================================================

@app.route('/api/admin/dashboard/stats', methods=['GET'])
@login_required
@admin_required
def api_admin_dashboard_stats():
    """
    Get real-time dashboard statistics
    Returns JSON with current system stats for auto-refresh
    """
    try:
        # Get system statistics
        total_users = User.query.count()
        total_farmers = User.query.filter_by(role='farmer').count()
        total_buyers = User.query.filter_by(role='buyer').count()
        total_crops = Crop.query.count()
        total_orders = Order.query.count()
        pending_orders = Order.query.filter(Order.status.in_(['pending', 'paid'])).count()
        
        # Get recent activity
        recent_users = User.query.order_by(User.created_at.desc()).limit(5).all()
        recent_crops = Crop.query.order_by(Crop.created_at.desc()).limit(5).all()
        recent_orders = Order.query.order_by(Order.created_at.desc()).limit(5).all()
        
        return jsonify({
            'success': True,
            'stats': {
                'total_users': total_users,
                'total_farmers': total_farmers,
                'total_buyers': total_buyers,
                'total_crops': total_crops,
                'total_orders': total_orders,
                'pending_orders': pending_orders
            },
            'recent_users': [{
                'id': user.id,
                'full_name': user.full_name,
                'email': user.email,
                'role': user.role,
                'is_active': user.is_active
            } for user in recent_users],
            'recent_crops': [{
                'id': crop.id,
                'name': crop.name,
                'price_per_unit': float(crop.price_per_unit),
                'unit': crop.unit,
                'status': crop.status,
                'farmer_name': crop.farmer.full_name,
                'image_url': crop.image_url
            } for crop in recent_crops],
            'recent_orders': [{
                'id': order.id,
                'crop_name': order.crop.name,
                'buyer_name': order.buyer.full_name,
                'farmer_name': order.farmer_user.full_name,
                'total_amount': float(order.total_amount),
                'quantity_requested': float(order.quantity_requested),
                'unit': order.crop.unit,
                'status': order.status
            } for order in recent_orders],
            'timestamp': datetime.utcnow().isoformat()
        })
    except Exception as e:
        logger.error(f"Error fetching dashboard stats: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'Failed to fetch dashboard statistics'
        }), 500
