from functools import wraps
from flask import flash, redirect, url_for, request, abort
from flask_login import current_user
import requests
import os
import logging
from datetime import datetime, timedelta
from pytz import timezone

logger = logging.getLogger(__name__)

def format_datetime(dt, format='%B %d, %Y at %I:%M %p'):
    """
    Convert UTC datetime to Indian timezone and format it
    """
    if not dt:
        return ''
    indian_tz = timezone('Asia/Kolkata')
    if dt.tzinfo is None:  # If datetime is naive, assume it's UTC
        dt = dt.replace(tzinfo=timezone('UTC'))
    local_dt = dt.astimezone(indian_tz)
    return local_dt.strftime(format)

def extract_location(text):
    """Extract location from text, with fallback when spaCy is not available"""
    if not text:
        return None
        
    try:
        # Try using spaCy if available
        import spacy
        # Disable spaCy's logging to avoid conflicts
        import warnings
        warnings.filterwarnings("ignore", category=UserWarning)
        
        nlp = spacy.load('en_core_web_sm')
        doc = nlp(text)
        
        # Look for GPE (geo-political entity) or LOC (location) entities
        for ent in doc.ents:
            if ent.label_ in ['GPE', 'LOC']:
                return ent.text
        
        # If no GPE/LOC found, return the original text
        return text.strip()
    except (ImportError, OSError, AttributeError, Exception) as e:
        # Silently fallback for common errors like missing models or logging conflicts
        if not isinstance(e, (ImportError, OSError)):
            logger.debug(f"Location extraction using fallback: {type(e).__name__}")
        
        # Fallback: Simple text cleaning for location
        location = text.strip()
        
        # Remove common prefixes and suffixes
        prefixes_to_remove = ['weather in', 'weather for', 'temperature in', 'temperature for', 'in', 'at']
        for prefix in prefixes_to_remove:
            if location.lower().startswith(prefix.lower()):
                location = location[len(prefix):].strip()
        
        # Basic validation - return None if it looks invalid
        if not location or len(location) < 2 or location.lower() in ['the', 'a', 'an', 'this', 'that']:
            return None
            
        return location

def get_weather_data(location):
    """
    Get weather data for a given location.
    Returns cached data if available and recent, otherwise fetches from API.
    """
    from models import WeatherData
    
    if not location:
        return get_default_weather("Unknown Location", "missing_location")
        
    # Extract location from natural language input
    extracted_location = extract_location(location)
    
    # If extraction failed, use original location or default
    if not extracted_location:
        if isinstance(location, str) and location.strip():
            extracted_location = location.strip()
        else:
            return get_default_weather("Unknown Location", "location_extraction_failed")
    
    location = extracted_location
        
    # Check if we have recent weather data for this location
    recent_weather = WeatherData.query.filter_by(location=location).filter(
        WeatherData.recorded_at > datetime.utcnow() - timedelta(hours=1)
    ).first()
    
    if recent_weather:
        return {
            'location': recent_weather.location,
            'temperature': recent_weather.temperature,
            'humidity': recent_weather.humidity,
            'condition': recent_weather.weather_condition,
            'wind_speed': recent_weather.wind_speed,
            'precipitation': recent_weather.precipitation,
            'last_updated': recent_weather.recorded_at
        }
    
    # Try to fetch from OpenWeatherMap API
    api_key = os.environ.get('WEATHER_API_KEY')
    if not api_key:
        logger.warning("Weather API key not found in environment variables")
        return get_default_weather(location, "missing_api_key")
    
    try:
        # Format location for API call
        formatted_location = location.strip()
        
        # Handle Indian city names
        if any(state.lower() in formatted_location.lower() for state in [
            'bihar', 'uttar pradesh', 'madhya pradesh', 'tamil nadu', 
            'andhra pradesh', 'west bengal', 'maharashtra', 'karnataka'
        ]):
            # If state is included, assume it's an Indian location
            formatted_location = formatted_location.replace(" ", ",")
        elif "," not in formatted_location:
            # For single city names, assume Indian location
            formatted_location += ",IN"
        
        # Make API call to OpenWeatherMap
        url = f"https://api.openweathermap.org/data/2.5/weather?q={formatted_location}&appid={api_key}&units=metric"
        headers = {
            'User-Agent': 'FarmLinkAI/1.0',
            'Accept': 'application/json'
        }
        
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()  # Raise an error for bad status codes
        
        data = response.json()
        
        # Extract and process weather data
        weather_data = {
            'location': location,
            'temperature': round(float(data['main']['temp']), 1),
            'humidity': int(data['main']['humidity']),
            'condition': data['weather'][0]['description'].title(),
            'wind_speed': round(float(data['wind']['speed']), 1),  # Keep in m/s to match template
            'pressure': int(data['main']['pressure']),  # Add pressure
            'visibility': round(float(data.get('visibility', 0)) / 1000, 1),  # Convert to km
            'precipitation': float(data.get('rain', {}).get('1h', 0) or data.get('snow', {}).get('1h', 0) or 0),
            'last_updated': datetime.utcnow()
        }
        
        try:
            # Save to database
            weather_record = WeatherData(
                location=location,
                temperature=weather_data['temperature'],
                humidity=weather_data['humidity'],
                weather_condition=weather_data['condition'],  # Use consistent field name
                wind_speed=weather_data['wind_speed'],
                precipitation=weather_data['precipitation'],
                pressure=weather_data['pressure'],
                visibility=weather_data['visibility'],
                recorded_at=datetime.utcnow()
            )
            
            from app import db
            db.session.add(weather_record)
            db.session.commit()
            logger.info(f"Weather data saved successfully for {location}")
        except Exception as db_error:
            logger.error(f"Database error while saving weather data: {str(db_error)}")
            # Continue even if database save fails
        
        return weather_data
    except requests.HTTPError as http_err:
        error_response = None
        if 'response' in locals():
            try:
                error_response = response.json()
                error_message = error_response.get('message', str(http_err))
            except:
                error_message = str(http_err)
        else:
            error_message = str(http_err)
            
        logger.error(f"HTTP error occurred: {error_message}")
        error_type = response.status_code if 'response' in locals() else None
        
        # Special handling for common OpenWeatherMap errors
        if error_type == 404:
            return get_default_weather(location, "location_not_found")
        elif error_type == 401:
            return get_default_weather(location, "invalid_api_key")
        elif error_type == 429:
            return get_default_weather(location, "rate_limit_exceeded")
        else:
            return get_default_weather(location, error_type)
            
    except requests.ConnectionError as conn_err:
        logger.error(f"Connection error occurred: {conn_err}")
        return get_default_weather(location, "connection_error")
        
    except requests.Timeout as timeout_err:
        logger.error(f"Timeout error occurred: {timeout_err}")
        return get_default_weather(location, "timeout")
        
    except Exception as e:
        logger.error(f"Unexpected error occurred while fetching weather: {str(e)}")
        return get_default_weather(location, "unexpected_error")

def get_default_weather(location, error_type=None):
    """Return default weather data when API is unavailable"""
    error_messages = {
        "location_not_found": f"Location '{location}' not found. Try using the city's English name or add state/country (e.g., 'Patna, Bihar' or 'Mumbai, IN').",
        "invalid_api_key": "Weather service configuration error. Please contact support.",
        "rate_limit_exceeded": "Too many requests. Please try again in a few minutes.",
        "connection_error": "Unable to connect to weather service. Please check your internet connection.",
        "timeout": "Weather service request timed out. Please try again.",
        "missing_location": "Please enter a location to get weather information.",
        "missing_api_key": "Weather service is not properly configured. Please contact support.",
        "location_extraction_failed": "Unable to understand the location. Please try entering just the city name (e.g., 'Delhi', 'Mumbai', 'Kolkata').",
        404: f"Location '{location}' not found. Try using the city's English name (e.g., 'Mumbai' instead of 'Bombay').",
        401: "Weather service authentication failed. Please contact support.",
        429: "Weather service rate limit exceeded. Please try again later.",
    }
    
    error_msg = error_messages.get(error_type, "Weather service temporarily unavailable. Please try again later.")

    return {
        'location': location,
        'temperature': None,
        'humidity': None,
        'condition': error_msg,
        'wind_speed': None,
        'precipitation': None,
        'last_updated': datetime.utcnow(),
        'error': True,
        'error_type': error_type
    }

def format_currency(amount):
    """Format amount as Indian currency"""
    if amount is None:
        return "₹0"
    return f"₹{amount:,.2f}"

def get_crop_categories():
    """Get list of crop categories"""
    return [
        ('grains', 'Grains & Cereals'),
        ('vegetables', 'Vegetables'),
        ('fruits', 'Fruits'),
        ('pulses', 'Pulses'),
        ('spices', 'Spices'),
        ('others', 'Others')
    ]

def get_order_status_badge_class(status):
    """Get Bootstrap badge class for order status"""
    status_classes = {
        'pending': 'bg-warning text-dark',
        'confirmed': 'bg-info text-white',
        'processing': 'bg-primary',
        'shipped': 'bg-purple',
        'delivered': 'bg-success',
        'rejected': 'bg-danger',
        'cancelled': 'bg-secondary',
        'accepted': 'bg-info',  # Legacy support
        'completed': 'bg-success'  # Legacy support
    }
    return status_classes.get(status, 'bg-secondary')

def get_shipment_status_badge_class(status):
    """Get Bootstrap badge class for shipment status"""
    status_classes = {
        'pending': 'bg-status-pending',
        'packed': 'bg-status-packed',
        'shipped': 'bg-status-shipped',
        'in_transit': 'bg-status-in_transit',
        'out_for_delivery': 'bg-status-out_for_delivery',
        'delivered': 'bg-status-delivered',
        'failed': 'bg-status-failed',
        'returned': 'bg-status-returned'
    }
    return status_classes.get(status, 'bg-status-pending')

def get_weather_forecast(location, days=5):
    """
    Get weather forecast for a given location.
    Returns forecast data for the specified number of days.
    """
    if not location:
        return {
            'location': 'Unknown Location',
            'forecast': [],
            'error': True,
            'error_message': 'Location not provided'
        }
        
    # Extract location from natural language input
    extracted_location = extract_location(location)
    
    # If extraction failed, use original location or return error
    if not extracted_location:
        if isinstance(location, str) and location.strip():
            extracted_location = location.strip()
        else:
            return {
                'location': 'Unknown Location',
                'forecast': [],
                'error': True,
                'error_message': 'Unable to extract location'
            }
    
    location = extracted_location
    
    # Try to fetch from OpenWeatherMap API
    api_key = os.environ.get('WEATHER_API_KEY')
    if not api_key:
        logger.warning("Weather API key not found for forecast")
        return {
            'location': location,
            'forecast': [],
            'error': True,
            'error_message': 'Weather service not configured'
        }
    
    try:
        # Format location for API call
        formatted_location = location.strip()
        
        # Handle Indian city names
        if any(state.lower() in formatted_location.lower() for state in [
            'bihar', 'uttar pradesh', 'madhya pradesh', 'tamil nadu', 
            'andhra pradesh', 'west bengal', 'maharashtra', 'karnataka'
        ]):
            formatted_location = formatted_location.replace(" ", ",")
        elif "," not in formatted_location:
            formatted_location += ",IN"
        
        # Make API call to OpenWeatherMap forecast endpoint
        url = f"https://api.openweathermap.org/data/2.5/forecast?q={formatted_location}&appid={api_key}&units=metric"
        headers = {
            'User-Agent': 'FarmLinkAI/1.0',
            'Accept': 'application/json'
        }
        
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        
        # Process forecast data
        forecast_list = []
        processed_dates = set()
        
        for item in data['list'][:days * 8]:  # 8 forecasts per day (every 3 hours)
            forecast_date = datetime.fromtimestamp(item['dt']).date()
            
            # Take one forecast per day (around noon time)
            forecast_hour = datetime.fromtimestamp(item['dt']).hour
            if forecast_date not in processed_dates and 10 <= forecast_hour <= 14:
                forecast_item = {
                    'date': forecast_date.strftime('%Y-%m-%d'),
                    'day': forecast_date.strftime('%A'),
                    'temperature_max': round(float(item['main']['temp_max']), 1),
                    'temperature_min': round(float(item['main']['temp_min']), 1),
                    'temperature': round(float(item['main']['temp']), 1),
                    'humidity': int(item['main']['humidity']),
                    'weather_condition': item['weather'][0]['description'].title(),
                    'icon': item['weather'][0]['icon'],
                    'wind_speed': round(float(item['wind']['speed']), 1),
                    'precipitation': float(item.get('rain', {}).get('3h', 0) or item.get('snow', {}).get('3h', 0) or 0)
                }
                forecast_list.append(forecast_item)
                processed_dates.add(forecast_date)
                
                if len(forecast_list) >= days:
                    break
        
        return {
            'location': location,
            'forecast': forecast_list,
            'error': False,
            'last_updated': datetime.utcnow()
        }
        
    except requests.HTTPError as http_err:
        logger.error(f"HTTP error occurred during forecast fetch: {str(http_err)}")
        return {
            'location': location,
            'forecast': [],
            'error': True,
            'error_message': 'Unable to fetch weather forecast'
        }
    except Exception as e:
        logger.error(f"Error fetching weather forecast: {str(e)}")
        return {
            'location': location,
            'forecast': [],
            'error': True,
            'error_message': 'Weather forecast service temporarily unavailable'
        }

def get_weather_history(limit=10):
    """Get recent weather history"""
    try:
        from app import db
        from models import WeatherData
        history = WeatherData.query.order_by(WeatherData.recorded_at.desc()).limit(limit).all()
        return [{
            'date': format_datetime(record.recorded_at),
            'location': record.location,
            'temperature': record.temperature,
            'humidity': record.humidity,
            'condition': record.weather_condition,
            'wind_speed': record.wind_speed,
            'pressure': record.pressure,
            'visibility': record.visibility,
            'precipitation': record.precipitation
        } for record in history]
    except Exception as e:
        logger.error(f"Error fetching weather history: {str(e)}")
        return []

# Add utility functions to Jinja2 global functions
# Note: This is done in app.py to avoid circular imports
# The functions are registered after app initialization


def get_crop_health_trends(crop_id):
    """
    Analyze crop health trends based on pest and disease analysis history
    
    Args:
        crop_id: ID of the crop to analyze
        
    Returns:
        dict: Analysis results with trends, patterns, and recommendations
    """
    from models import PestDiseaseAnalysis, Crop
    from collections import Counter
    from datetime import datetime, timedelta
    import json
    
    try:
        # Get the crop
        crop = Crop.query.get(crop_id)
        if not crop:
            return {
                'success': False,
                'error': 'Crop not found'
            }
        
        # Get all analyses for this crop
        analyses = PestDiseaseAnalysis.query.filter_by(
            crop_id=crop_id
        ).order_by(
            PestDiseaseAnalysis.created_at.asc()
        ).all()
        
        if not analyses:
            return {
                'success': True,
                'has_data': False,
                'message': 'No pest or disease analyses found for this crop yet.'
            }
        
        # Initialize trend data
        trend_data = {
            'success': True,
            'has_data': True,
            'total_analyses': len(analyses),
            'crop_name': crop.name,
            'crop_type': crop.category,
            'analysis_period': {
                'start': analyses[0].created_at,
                'end': analyses[-1].created_at,
                'days': (analyses[-1].created_at - analyses[0].created_at).days
            },
            'issues_identified': [],
            'severity_distribution': Counter(),
            'issue_type_distribution': Counter(),
            'recurring_issues': [],
            'severity_trend': [],
            'confidence_trend': [],
            'recommendations': []
        }
        
        # Analyze each record
        issue_occurrences = Counter()
        monthly_severity = {}
        
        for analysis in analyses:
            # Track issues
            if analysis.identified_issue:
                issue_occurrences[analysis.identified_issue] += 1
                trend_data['issues_identified'].append({
                    'date': analysis.created_at,
                    'issue': analysis.identified_issue,
                    'severity': analysis.severity_level,
                    'confidence': analysis.confidence_score
                })
            
            # Track severity distribution
            if analysis.severity_level:
                trend_data['severity_distribution'][analysis.severity_level] += 1
            
            # Track issue type distribution
            if analysis.issue_type:
                trend_data['issue_type_distribution'][analysis.issue_type] += 1
            
            # Track severity trend over time
            trend_data['severity_trend'].append({
                'date': analysis.created_at.strftime('%Y-%m-%d'),
                'severity': analysis.severity_level,
                'severity_score': {
                    'critical': 4,
                    'high': 3,
                    'medium': 2,
                    'low': 1
                }.get(analysis.severity_level, 0)
            })
            
            # Track confidence trend
            if analysis.confidence_score:
                trend_data['confidence_trend'].append({
                    'date': analysis.created_at.strftime('%Y-%m-%d'),
                    'confidence': analysis.confidence_score
                })
            
            # Track monthly severity
            month_key = analysis.created_at.strftime('%Y-%m')
            if month_key not in monthly_severity:
                monthly_severity[month_key] = []
            if analysis.severity_level:
                monthly_severity[month_key].append(analysis.severity_level)
        
        # Identify recurring issues (appeared more than once)
        for issue, count in issue_occurrences.items():
            if count > 1:
                trend_data['recurring_issues'].append({
                    'issue': issue,
                    'occurrences': count,
                    'frequency': f"{count}/{len(analyses)}"
                })
        
        # Sort recurring issues by frequency
        trend_data['recurring_issues'].sort(key=lambda x: x['occurrences'], reverse=True)
        
        # Generate recommendations based on trends
        recommendations = []
        
        # Check for recurring issues
        if trend_data['recurring_issues']:
            top_recurring = trend_data['recurring_issues'][0]
            recommendations.append({
                'type': 'recurring_issue',
                'priority': 'high',
                'message': f"'{top_recurring['issue']}' has occurred {top_recurring['occurrences']} times. Consider implementing preventive measures to break this cycle."
            })
        
        # Check severity trend
        if len(trend_data['severity_trend']) >= 2:
            recent_severities = [s['severity_score'] for s in trend_data['severity_trend'][-3:]]
            if len(recent_severities) >= 2 and all(recent_severities[i] <= recent_severities[i+1] for i in range(len(recent_severities)-1)):
                recommendations.append({
                    'type': 'increasing_severity',
                    'priority': 'critical',
                    'message': 'Severity levels are increasing over time. Immediate intervention recommended to prevent crop loss.'
                })
        
        # Check for high severity concentration
        critical_count = trend_data['severity_distribution'].get('critical', 0)
        high_count = trend_data['severity_distribution'].get('high', 0)
        if (critical_count + high_count) / len(analyses) > 0.5:
            recommendations.append({
                'type': 'high_severity_rate',
                'priority': 'high',
                'message': 'More than 50% of analyses show high or critical severity. Consider consulting an agricultural expert for comprehensive crop health assessment.'
            })
        
        # Check for pest vs disease pattern
        pest_count = trend_data['issue_type_distribution'].get('pest', 0)
        disease_count = trend_data['issue_type_distribution'].get('disease', 0)
        if pest_count > disease_count * 2:
            recommendations.append({
                'type': 'pest_dominant',
                'priority': 'medium',
                'message': 'Pest issues are more common than diseases. Focus on integrated pest management strategies and regular monitoring.'
            })
        elif disease_count > pest_count * 2:
            recommendations.append({
                'type': 'disease_dominant',
                'priority': 'medium',
                'message': 'Disease issues are more common than pests. Improve drainage, air circulation, and consider disease-resistant varieties.'
            })
        
        # Check analysis frequency
        if trend_data['analysis_period']['days'] > 30 and len(analyses) < 3:
            recommendations.append({
                'type': 'low_monitoring',
                'priority': 'low',
                'message': 'Regular monitoring is recommended. Consider analyzing your crop weekly during critical growth stages.'
            })
        
        # Add general recommendations
        if not recommendations:
            recommendations.append({
                'type': 'general',
                'priority': 'low',
                'message': 'Continue regular monitoring and maintain good agricultural practices to keep your crop healthy.'
            })
        
        trend_data['recommendations'] = recommendations
        
        # Calculate health score (0-100)
        health_score = 100
        
        # Deduct for critical issues
        health_score -= critical_count * 15
        health_score -= high_count * 10
        health_score -= len(trend_data['recurring_issues']) * 5
        
        # Ensure score is within bounds
        health_score = max(0, min(100, health_score))
        
        trend_data['health_score'] = health_score
        trend_data['health_status'] = (
            'Excellent' if health_score >= 80 else
            'Good' if health_score >= 60 else
            'Fair' if health_score >= 40 else
            'Poor'
        )
        
        return trend_data
        
    except Exception as e:
        logger.error(f"Error analyzing crop health trends: {str(e)}")
        return {
            'success': False,
            'error': str(e)
        }
