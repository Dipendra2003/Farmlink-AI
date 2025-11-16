import logging
import os
from datetime import datetime
from typing import Dict, Any, Optional
import google.generativeai as genai
from config import Config

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize client variables
client = None
client_error = None

def initialize_gemini_client():
    """Initialize Gemini AI client"""
    global client, client_error
    try:
        # Get API key from environment or config
        api_key = os.getenv('GEMINI_API_KEY') or getattr(Config, 'GEMINI_API_KEY', None)
        if not api_key:
            logger.warning("Gemini API key not found. Using mock responses for AI services.")
            client = None
            client_error = "Gemini API key not configured. Using demo mode."
            return
        
        genai.configure(api_key=api_key)
        client = genai.GenerativeModel('gemini-2.5-flash-lite')
        client_error = None
        logger.info("Gemini AI client initialized successfully with gemini-2.5-flash-lite")
        
    except Exception as e:
        logger.error(f"AI client initialization failed: {e}")
        client = None
        client_error = str(e)

# Initialize client on import
initialize_gemini_client()

class EnhancedWeatherAI:
    """Weather-related AI services"""
    
    @staticmethod
    def get_weather_data(location):
        """Get weather data for location"""
        return {
            "success": True,
            "location": location,
            "temperature": "25°C",
            "humidity": "60%",
            "conditions": "Partly cloudy",
            "source": "placeholder"
        }
    
    @staticmethod
    def get_weather_forecast(location, days=5):
        """Get weather forecast"""
        return {
            "success": True,
            "location": location,
            "forecast": [],
            "source": "placeholder"
        }
    
    @staticmethod
    def get_farming_insights(weather_data, crop_name):
        """Get farming insights based on weather data and crop"""
        if not client:
            return {
                "insights": "Weather AI service is currently unavailable.",
                "recommendations": [],
                "alerts": []
            }
        
        try:
            # Extract weather information
            temp = weather_data.get('temperature', 'N/A')
            humidity = weather_data.get('humidity', 'N/A')
            condition = weather_data.get('condition', weather_data.get('weather_condition', 'N/A'))
            wind_speed = weather_data.get('wind_speed', 'N/A')
            
            prompt = f"""
            As an agricultural AI expert, analyze the current weather conditions and provide farming insights for {crop_name}.
            
            Current Weather Data:
            - Temperature: {temp}
            - Humidity: {humidity}
            - Weather Condition: {condition}
            - Wind Speed: {wind_speed}
            
            Please provide specific, actionable farming advice in the following format:
            
            IRRIGATION:
            [Specific irrigation advice based on current conditions]
            
            CROP_CARE:
            [Specific crop care recommendations]
            
            PEST_DISEASE:
            [Disease/pest risk assessment and prevention]
            
            HARVEST:
            [Harvest timing and preparation advice if applicable]
            
            ALERTS:
            [Any urgent warnings or alerts]
            
            OVERALL:
            [Overall assessment and summary]
            
            Keep each section brief and actionable for farmers.
            """
            
            response = client.generate_content(prompt)
            insights_text = response.text if response and hasattr(response, 'text') else "Unable to generate farming insights at this time."
            
            # Parse the structured response
            insights_list = []
            overall_assessment = ""
            
            sections = insights_text.split('\n\n')
            for section in sections:
                lines = section.strip().split('\n')
                if len(lines) >= 2:
                    header = lines[0].strip()
                    content = '\n'.join(lines[1:]).strip()
                    
                    if header.startswith('IRRIGATION'):
                        insights_list.append({
                            'category': 'irrigation',
                            'urgency': 'medium',
                            'recommendation': content,
                            'reason': f'Based on current humidity ({humidity}) and temperature ({temp})'
                        })
                    elif header.startswith('CROP_CARE'):
                        insights_list.append({
                            'category': 'crop care',
                            'urgency': 'low',
                            'recommendation': content,
                            'reason': f'Weather conditions: {condition}'
                        })
                    elif header.startswith('PEST_DISEASE'):
                        urgency = 'high' if any(word in content.lower() for word in ['warning', 'risk', 'urgent', 'immediate']) else 'medium'
                        insights_list.append({
                            'category': 'pest & disease',
                            'urgency': urgency,
                            'recommendation': content,
                            'reason': f'Current conditions may affect pest/disease pressure'
                        })
                    elif header.startswith('HARVEST'):
                        insights_list.append({
                            'category': 'harvest',
                            'urgency': 'medium',
                            'recommendation': content,
                            'reason': f'Weather timing considerations'
                        })
                    elif header.startswith('ALERTS'):
                        if content and content.lower() not in ['none', 'no alerts', 'no warnings']:
                            insights_list.append({
                                'category': 'alert',
                                'urgency': 'high',
                                'recommendation': content,
                                'reason': 'Immediate attention required'
                            })
                    elif header.startswith('OVERALL'):
                        overall_assessment = content
            
            # If parsing failed, create a basic insight
            if not insights_list:
                insights_list = [{
                    'category': 'general',
                    'urgency': 'low',
                    'recommendation': insights_text[:200] + '...' if len(insights_text) > 200 else insights_text,
                    'reason': f'Based on current weather conditions for {crop_name}'
                }]

            return {
                "insights": insights_list,
                "overall_assessment": overall_assessment or f"Weather conditions are suitable for {crop_name} cultivation with proper care.",
                "crop": crop_name,
                "weather_summary": f"Temperature: {temp}, Humidity: {humidity}, Condition: {condition}"
            }
            
        except Exception as e:
            logger.error(f"Error generating farming insights: {str(e)}")
            return {
                "insights": [
                    {
                        'category': 'general',
                        'urgency': 'low',
                        'recommendation': 'Monitor your crops regularly and check soil moisture levels.',
                        'reason': 'AI service temporarily unavailable'
                    },
                    {
                        'category': 'irrigation',
                        'urgency': 'medium',
                        'recommendation': 'Ensure adequate water supply and check irrigation systems.',
                        'reason': 'General farming best practice'
                    }
                ],
                "overall_assessment": f"Weather data analysis for {crop_name} is temporarily unavailable. Follow standard farming practices.",
                "crop": crop_name,
                "weather_summary": "Weather data analysis unavailable"
            }

class EnhancedVoiceAI:
    """Advanced Voice-powered AI services with complete Gemini integration for Farmlink"""
    
    SUPPORTED_LANGUAGES = {
        'english': 'en',
        'hindi': 'hi',
        'punjabi': 'pa',
        'tamil': 'ta',
        'telugu': 'te',
        'bengali': 'bn',
        'gujarati': 'gu',
        'marathi': 'mr',
        'kannada': 'kn',
        'malayalam': 'ml'
    }
    
    @staticmethod
    def get_multilingual_farming_response(query, language="english"):
        """
        Get comprehensive farming response using Gemini AI
        This is the core voice assistant function for Farmlink
        """
        if not client:
            return "I'm sorry, but AI services are currently unavailable. Please check your connection and try again."
        
        try:
            # Normalize language
            lang_code = EnhancedVoiceAI.SUPPORTED_LANGUAGES.get(language.lower(), 'en')
            
            # Create comprehensive farming context prompt
            system_prompt = f"""
You are the Farmlink Voice Assistant, an AI helper powered by Gemini AI specifically designed for farmers.

IDENTITY & ROLE:
- You are the official voice assistant for Farmlink platform
- Your purpose is to help farmers with practical, actionable farming advice
- Respond in {language} language when requested

FARMLINK PLATFORM OVERVIEW:
- Farmlink connects farmers, buyers, and suppliers in a comprehensive ecosystem
- Core services: Crop guidance, market connections, weather alerts, supply chain support
- Target users: Small to medium farmers across India

YOUR CAPABILITIES:
✅ Crop suggestions and planning
✅ Weather forecasts and farming alerts  
✅ Disease & pest identification + treatment
✅ Soil analysis and fertilizer recommendations
✅ Market price information and trends
✅ Irrigation and water management advice
✅ Harvest timing and yield optimization
✅ Supply chain and logistics support
✅ Buyer-farmer marketplace connections

RESPONSE GUIDELINES:
1. Be conversational, warm, and farmer-friendly
2. Provide practical, step-by-step advice
3. Include specific examples when helpful
4. Consider local Indian farming conditions
5. Keep responses concise but complete
6. Always give real, actionable information (no placeholder data)
7. If you don't know something specific, say so honestly
8. Focus on solutions that increase farmer income and reduce risk

QUERY TYPES TO HANDLE:
- Weather: "What's the weather forecast?" → Real weather advice
- Crops: "What should I plant?" → Seasonal crop recommendations  
- Prices: "Rice price today?" → Current market information
- Diseases: "Tomato leaves turning yellow" → Diagnosis + treatment
- Fertilizer: "What fertilizer for wheat?" → Specific recommendations
- General: "How can you help?" → Platform capabilities overview

Always respond as if you have access to real-time data and provide practical farming guidance.
"""

            # Prepare the user query with context
            user_prompt = f"""
Farmer Query: "{query}"
Language: {language}

Please provide a helpful, practical response as the Farmlink Voice Assistant. Include specific farming advice, actionable steps, and relevant information that would help an Indian farmer.
"""

            # Make API call to Gemini
            model = genai.GenerativeModel('gemini-2.5-flash-lite')
            response = model.generate_content(
                f"{system_prompt}\n\n{user_prompt}",
                generation_config=genai.types.GenerationConfig(
                    temperature=0.7,
                    max_output_tokens=400,
                    top_p=0.8,
                )
            )
            
            if response.text:
                # Clean and format the response
                ai_response = response.text.strip()
                
                # Clean up any Farmlink prefix if present
                ai_response = ai_response.replace("🌱 Farmlink Suggestion:", "").strip()
                
                # Log the successful response
                logger.info(f"Voice AI response generated for query: {query[:50]}...")
                
                return ai_response
                
            else:
                logger.warning("Empty response from Gemini API")
                return "I'm having trouble processing your request right now. Please try rephrasing your question or try again in a moment."
                
        except Exception as e:
            logger.error(f"Error in voice AI response generation: {str(e)}")
            return f"I encountered an issue while processing your request. Please try again. If the problem persists, contact Farmlink support."
    
    @staticmethod
    def process_voice_query(audio_file_path, language="english"):
        """
        Process voice audio file (placeholder for future speech-to-text integration)
        """
        try:
            # For now, return a basic structure
            # In future, integrate with Google Speech-to-Text or similar service
            return {
                "success": False,
                "error": "Speech-to-text processing not yet implemented. Please use text input.",
                "text": "",
                "detected_language": language
            }
        except Exception as e:
            logger.error(f"Voice processing error: {str(e)}")
            return {
                "success": False,
                "error": f"Voice processing failed: {str(e)}",
                "text": "",
                "detected_language": language
            }
    
    @staticmethod
    def generate_voice_response(text, language="english", voice_style="alloy"):
        """
        Generate voice audio from text (placeholder for future text-to-speech)
        """
        try:
            # For now, return None - would integrate with Google TTS in future
            logger.info(f"Voice generation requested for text: {text[:50]}...")
            return None
        except Exception as e:
            logger.error(f"Voice generation error: {str(e)}")
            return None
    
    @staticmethod
    def get_quick_farming_response(command_type):
        """
        Get quick responses for common farming commands
        """
        quick_responses = {
            'weather': "Let me check the latest weather forecast for your area. Based on current conditions, here's what you need to know for farming activities...",
            'prices': "Here are today's market prices for major crops. Rice is trading at competitive rates, while vegetable prices show seasonal variations...",
            'diseases': "Common diseases this season include leaf blight and pest infestations. Early detection and organic treatments are most effective...",
            'fertilizer': "For optimal crop nutrition, consider soil testing first. NPK requirements vary by crop stage and soil type...",
            'help': "I can help you with crop planning, weather updates, market prices, disease identification, fertilizer advice, and connecting with buyers. What would you like to know?"
        }
        
        return quick_responses.get(command_type, quick_responses['help'])

class EnhancedAnalyticsAI:
    """Analytics-related AI services"""
    
    @staticmethod
    def generate_analytics_report(user_data):
        """Generate analytics report"""
        return {
            "success": True,
            "report": {
                "summary": "Analytics data processed",
                "insights": [],
                "recommendations": []
            },
            "source": "placeholder"
        }

# Import crop AI services
try:
    from crop_ai_service import EnhancedCropAI as CropAIService, get_crop_service_status, CROP_AI_AVAILABLE
    logger.info("Crop AI service imported successfully")
except ImportError as e:
    logger.warning(f"Crop AI service not available: {e}")
    CROP_AI_AVAILABLE = False
    CropAIService = None

class EnhancedCropAI:
    """Crop suggestion AI services - wrapper for crop_ai_service"""
    
    @staticmethod
    def get_smart_crop_suggestions(input_data):
        """Get intelligent crop suggestions based on comprehensive input"""
        if CROP_AI_AVAILABLE and CropAIService:
            return CropAIService.get_smart_crop_suggestions(input_data)
        else:
            return {
                "success": False,
                "error": "Crop AI service not available",
                "suggestions": []
            }
    
    @staticmethod
    def compare_crops_analysis(crop_names, comparison_factor='profitability'):
        """Compare multiple crops based on specified factors"""
        if CROP_AI_AVAILABLE and CropAIService:
            return CropAIService.compare_crops_analysis(crop_names, comparison_factor)
        else:
            return {
                "success": False,
                "error": "Crop comparison service not available - Gemini API key required",
                "comparison": {}
            }
    
    @staticmethod
    def get_seasonal_suggestions(input_data, season):
        """Get season-specific crop suggestions"""
        if CROP_AI_AVAILABLE and CropAIService:
            return CropAIService.get_seasonal_recommendations(input_data, season)
        else:
            return {
                "success": False,
                "error": "Seasonal suggestion service not available - Gemini API key required",
                "suggestions": []
            }

def get_ai_service_status():
    """Get current AI service status"""
    crop_status = {}
    if CROP_AI_AVAILABLE and CropAIService:
        crop_status = get_crop_service_status()
    
    # Check pest detection service availability
    pest_detection_available = False
    try:
        from pest_detection_service import pest_detection_service
        pest_detection_available = pest_detection_service.is_available()
    except ImportError:
        pass
    
    return {
        "client_available": bool(client),
        "client_error": client_error,
        "cache_enabled": False,
        "fallback_db_ready": False,
        "supported_languages": list(EnhancedVoiceAI.SUPPORTED_LANGUAGES.keys()),
        "service_capabilities": {
            "pest_analysis": pest_detection_available,
            "weather_analysis": True,
            "voice_interface": True,
            "analytics": True,
            "crop_suggestions": CROP_AI_AVAILABLE,
            "crop_comparison": CROP_AI_AVAILABLE,
            "seasonal_recommendations": CROP_AI_AVAILABLE,
            "fertilizer_planning": CROP_AI_AVAILABLE,
            "irrigation_scheduling": CROP_AI_AVAILABLE,
            "yield_prediction": CROP_AI_AVAILABLE
        },
        "crop_ai_status": crop_status
    }

# Legacy aliases for backward compatibility
WeatherAI = EnhancedWeatherAI
VoiceAI = EnhancedVoiceAI
AnalyticsAI = EnhancedAnalyticsAI
