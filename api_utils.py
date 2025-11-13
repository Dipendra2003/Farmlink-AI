"""
API Utilities for FarmLink AI
Provides authentication, rate limiting, and helper functions for REST API endpoints
"""

import secrets
import logging
from functools import wraps
from datetime import datetime, timedelta
from flask import request, jsonify
from flask_login import current_user
from collections import defaultdict
import threading

logger = logging.getLogger(__name__)

# In-memory rate limiting storage (for production, use Redis)
rate_limit_storage = defaultdict(list)
rate_limit_lock = threading.Lock()


def generate_api_token():
    """Generate a secure API token"""
    return secrets.token_urlsafe(32)


def api_token_required(f):
    """
    Decorator to require API token authentication
    Checks for Bearer token in Authorization header
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Import here to avoid circular imports
        from models import User, db
        
        # Get token from Authorization header
        auth_header = request.headers.get('Authorization', '')
        
        if not auth_header:
            return jsonify({
                'success': False,
                'error': 'Missing Authorization header',
                'message': 'Please provide an API token in the Authorization header as "Bearer <token>"'
            }), 401
        
        # Parse Bearer token
        parts = auth_header.split()
        if len(parts) != 2 or parts[0].lower() != 'bearer':
            return jsonify({
                'success': False,
                'error': 'Invalid Authorization header format',
                'message': 'Authorization header must be in format: "Bearer <token>"'
            }), 401
        
        token = parts[1]
        
        # Validate token
        user = User.query.filter_by(api_token=token, active=True).first()
        
        if not user:
            return jsonify({
                'success': False,
                'error': 'Invalid or expired API token',
                'message': 'The provided API token is invalid or has been revoked'
            }), 401
        
        # Check if token is expired
        if user.api_token_expires and user.api_token_expires < datetime.utcnow():
            return jsonify({
                'success': False,
                'error': 'Expired API token',
                'message': 'Your API token has expired. Please generate a new one.'
            }), 401
        
        # Update last API usage
        user.last_api_usage = datetime.utcnow()
        db.session.commit()
        
        # Store user in request context
        request.api_user = user
        
        return f(*args, **kwargs)
    
    return decorated_function


def rate_limit(max_requests=10, window_seconds=60):
    """
    Decorator to implement rate limiting per user
    
    Args:
        max_requests: Maximum number of requests allowed in the time window
        window_seconds: Time window in seconds
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Get user from request context (set by api_token_required)
            user = getattr(request, 'api_user', None)
            
            if not user:
                # If no user, apply rate limit by IP address
                identifier = request.remote_addr
            else:
                identifier = f"user_{user.id}"
            
            current_time = datetime.utcnow()
            cutoff_time = current_time - timedelta(seconds=window_seconds)
            
            with rate_limit_lock:
                # Clean up old requests
                rate_limit_storage[identifier] = [
                    req_time for req_time in rate_limit_storage[identifier]
                    if req_time > cutoff_time
                ]
                
                # Check if rate limit exceeded
                if len(rate_limit_storage[identifier]) >= max_requests:
                    oldest_request = min(rate_limit_storage[identifier])
                    retry_after = int((oldest_request + timedelta(seconds=window_seconds) - current_time).total_seconds())
                    
                    return jsonify({
                        'success': False,
                        'error': 'Rate limit exceeded',
                        'message': f'Too many requests. Maximum {max_requests} requests per {window_seconds} seconds.',
                        'retry_after': max(retry_after, 1)
                    }), 429
                
                # Add current request
                rate_limit_storage[identifier].append(current_time)
            
            return f(*args, **kwargs)
        
        return decorated_function
    return decorator


def validate_base64_image(base64_string):
    """
    Validate and decode base64 image string
    
    Args:
        base64_string: Base64 encoded image string
        
    Returns:
        tuple: (success, image_data or error_message)
    """
    import base64
    import io
    from PIL import Image
    
    try:
        # Remove data URL prefix if present
        if ',' in base64_string:
            base64_string = base64_string.split(',')[1]
        
        # Decode base64
        image_data = base64.b64decode(base64_string)
        
        # Validate it's a valid image
        try:
            image = Image.open(io.BytesIO(image_data))
            image.verify()
            
            # Check file size (max 10MB)
            if len(image_data) > 10 * 1024 * 1024:
                return False, 'Image size exceeds 10MB limit'
            
            return True, image_data
            
        except Exception as img_error:
            return False, f'Invalid image data: {str(img_error)}'
            
    except Exception as e:
        return False, f'Failed to decode base64 image: {str(e)}'


def save_base64_image(image_data, filename_prefix='api'):
    """
    Save base64 decoded image data to file
    
    Args:
        image_data: Binary image data
        filename_prefix: Prefix for the filename
        
    Returns:
        str: Path to saved image file
    """
    import os
    from werkzeug.utils import secure_filename
    from app import app
    
    # Generate unique filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    random_suffix = secrets.token_hex(4)
    filename = f"{filename_prefix}_{timestamp}_{random_suffix}.jpg"
    
    # Create upload directory
    upload_path = os.path.join(
        app.config.get('UPLOAD_FOLDER', 'static/uploads'),
        'pest_analysis'
    )
    os.makedirs(upload_path, exist_ok=True)
    
    # Save file
    file_path = os.path.join(upload_path, filename)
    with open(file_path, 'wb') as f:
        f.write(image_data)
    
    return file_path


def format_analysis_response(analysis, include_full_details=True):
    """
    Format analysis result for API response
    
    Args:
        analysis: PestDiseaseAnalysis model instance or dict
        include_full_details: Whether to include full treatment details
        
    Returns:
        dict: Formatted response
    """
    from models import PestDiseaseAnalysis
    
    # Handle both model instances and dicts
    if isinstance(analysis, PestDiseaseAnalysis):
        response = {
            'id': analysis.id,
            'crop_type': analysis.crop_type,
            'identified_issue': analysis.identified_issue,
            'issue_type': analysis.issue_type,
            'confidence_score': analysis.confidence_score,
            'severity_level': analysis.severity_level,
            'analysis_mode': analysis.analysis_mode,
            'created_at': analysis.created_at.isoformat() if analysis.created_at else None,
        }
        
        if include_full_details:
            response.update({
                'symptoms_description': analysis.symptoms_description,
                'plant_stage': analysis.plant_stage,
                'urgency_level': analysis.urgency_level,
                'location': analysis.location,
                'treatment_recommendations': analysis.get_treatment_recommendations(),
                'preventive_measures': analysis.get_preventive_measures(),
                'additional_diagnoses': analysis.get_additional_diagnoses(),
                'ai_model_used': analysis.ai_model_used,
            })
    else:
        # Handle dict format (from service)
        response = {
            'identified_issue': analysis.get('identified_issue'),
            'issue_type': analysis.get('issue_type'),
            'confidence_score': analysis.get('confidence_score'),
            'severity_level': analysis.get('severity_level'),
            'analysis_mode': analysis.get('analysis_mode'),
        }
        
        if include_full_details:
            response.update({
                'description': analysis.get('description'),
                'symptoms_observed': analysis.get('symptoms_observed', []),
                'treatment_recommendations': analysis.get('treatment_recommendations', {}),
                'preventive_measures': analysis.get('preventive_measures', []),
                'additional_diagnoses': analysis.get('alternative_diagnoses', []),
                'regional_context': analysis.get('regional_context'),
                'seasonal_factors': analysis.get('seasonal_factors'),
            })
    
    return response


def get_image_url(image_path):
    """
    Convert local image path to accessible URL
    
    Args:
        image_path: Local file path
        
    Returns:
        str: URL to access the image
    """
    from flask import url_for
    import os
    
    if not image_path:
        return None
    
    # Extract relative path from full path
    if 'static' in image_path:
        # Get path relative to static folder
        parts = image_path.split('static')
        if len(parts) > 1:
            relative_path = parts[1].lstrip('/\\').replace('\\', '/')
            return url_for('static', filename=relative_path, _external=True)
    
    return None
