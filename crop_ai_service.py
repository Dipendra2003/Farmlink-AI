import json
import logging
import os
import re
from datetime import datetime
from typing import Dict, List, Any, Optional
import google.generativeai as genai
from config import Config

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class EnhancedCropAI:
    """Enhanced AI service for comprehensive crop suggestions - GEMINI AI ONLY"""
    
    def __init__(self, strict_mode=None):
        """
        Initialize the Gemini AI client
        
        Args:
            strict_mode: If True, reject crops with quality score < 70.
                        If None, reads from Config.CROP_AI_STRICT_MODE (default: True)
        """
        self.client = None
        self.model = None
        # Read from config if not explicitly provided
        if strict_mode is None:
            self.strict_mode = getattr(Config, 'CROP_AI_STRICT_MODE', True)
        else:
            self.strict_mode = strict_mode
        self.initialize_client()
    
    def initialize_client(self):
        """Initialize Gemini AI client - REQUIRED for all operations"""
        try:
            # Get API key from environment or config
            api_key = os.getenv('GEMINI_API_KEY') or getattr(Config, 'GEMINI_API_KEY', None)
            if not api_key:
                logger.error("CRITICAL: Gemini API key not found. Service will not work without it.")
                raise ValueError("Gemini API key is required for crop suggestions service")
            
            genai.configure(api_key=api_key)
            self.model = genai.GenerativeModel('gemini-2.5-flash-lite')
            logger.info("Gemini AI client initialized successfully with gemini-2.5-flash-lite model")
            
        except Exception as e:
            logger.error(f"CRITICAL: Failed to initialize Gemini AI client: {e}")
            raise e
    
    @staticmethod
    def get_smart_crop_suggestions(input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Get comprehensive crop suggestions using ONLY Gemini AI
        
        Args:
            input_data: Dictionary containing all input parameters
            
        Returns:
            Dictionary with crop suggestions and detailed insights from Gemini AI
        """
        max_retries = 2
        retry_count = 0
        last_error = None
        
        while retry_count <= max_retries:
            try:
                service = EnhancedCropAI()
                if not service.model:
                    logger.error("Gemini AI model not available - cannot provide suggestions")
                    return {
                        'success': False,
                        'error': 'AI service is not configured. Please contact support.',
                        'error_type': 'no_api_key',
                        'service_status': {
                            'gemini_available': False,
                            'api_key_configured': False
                        }
                    }
                
                # Create comprehensive prompt for Gemini AI
                prompt = service._create_comprehensive_prompt(input_data)
                
                # Get AI response with timeout handling
                logger.info(f"Requesting crop suggestions from Gemini AI (attempt {retry_count + 1}/{max_retries + 1})")
                response = service.model.generate_content(
                    prompt,
                    generation_config=genai.types.GenerationConfig(
                        temperature=0.7,
                        top_p=0.8,
                        top_k=40,
                        max_output_tokens=4096,
                    )
                )
                
                # Parse and structure the response
                suggestions = service._parse_ai_response(response.text)
                
                # Check if we got any valid suggestions
                if not suggestions:
                    logger.error("AI response parsing failed - no valid crop data extracted")
                    return {
                        'success': False,
                        'error': 'AI response could not be processed. Our team has been notified.',
                        'error_type': 'parsing_error',
                        'service_status': {
                            'gemini_available': True,
                            'api_key_configured': True
                        }
                    }
                
                # Add additional insights and metadata
                enhanced_suggestions = service._enhance_suggestions(suggestions, input_data)
                
                # Calculate data quality metrics
                quality_scores = [s.get('data_quality_score', 0) for s in enhanced_suggestions]
                min_quality_score = getattr(Config, 'CROP_AI_MIN_QUALITY_SCORE', 70)
                crops_with_complete_data = sum(1 for score in quality_scores if score >= min_quality_score)
                crops_with_partial_data = len(quality_scores) - crops_with_complete_data
                average_quality_score = round(sum(quality_scores) / len(quality_scores), 1) if quality_scores else 0
                
                logger.info(f"Successfully generated {len(enhanced_suggestions)} crop suggestions with average quality score {average_quality_score}")
                
                # Log retry success if this was a retry attempt
                if retry_count > 0:
                    logger.info(f"Request succeeded after {retry_count} retry attempt(s)")
                
                return {
                    'success': True,
                    'suggestions': enhanced_suggestions,
                    'input_summary': input_data,
                    'generated_at': datetime.now().isoformat(),
                    'total_suggestions': len(enhanced_suggestions),
                    'ai_model': 'Farmlnk AI',
                    'source': 'Farmlink AI - Real-time Analysis',
                    'data_quality_metrics': {
                        'average_quality_score': average_quality_score,
                        'crops_with_complete_data': crops_with_complete_data,
                        'crops_with_partial_data': crops_with_partial_data
                    }
                }
                
            except Exception as e:
                last_error = e
                error_msg = str(e)
                error_type = type(e).__name__
                
                # Check for timeout indicators: 504 status, timeout keywords, deadline exceeded
                is_timeout_error = (
                    '504' in error_msg or 
                    'timeout' in error_msg.lower() or
                    'deadline exceeded' in error_msg.lower() or
                    'timed out' in error_msg.lower()
                )
                
                # Log detailed error information
                logger.error(f"Error on attempt {retry_count + 1}/{max_retries + 1}: {error_type}: {error_msg}")
                
                if is_timeout_error:
                    # Timeout error - retry if we haven't exceeded max retries
                    retry_count += 1
                    if retry_count <= max_retries:
                        logger.warning(f"Timeout error detected (type: {error_type}). Retrying... (attempt {retry_count + 1}/{max_retries + 1})")
                        logger.debug(f"Timeout error details: {error_msg}")
                        continue
                    else:
                        logger.error(f"Max retries ({max_retries}) reached after timeout errors")
                        logger.error(f"All retry attempts failed with timeout. Last error: {error_type}: {error_msg}")
                        return {
                            'success': False,
                            'error': 'Request timed out. The AI service is experiencing high load. Please try again.',
                            'error_type': 'timeout',
                            'service_status': {
                                'gemini_available': True,
                                'api_key_configured': True
                            }
                        }
                else:
                    # Non-timeout error - don't retry, return immediately
                    logger.error(f"Non-timeout error detected (type: {error_type}). Not retrying.")
                    logger.error(f"Error details: {error_msg}")
                    logger.info(f"Skipping retry for non-timeout error type: {error_type}")
                    return {
                        'success': False,
                        'error': 'AI service is temporarily unavailable. Please try again in a few minutes.',
                        'error_type': 'api_unavailable',
                        'service_status': {
                            'gemini_available': False,
                            'api_key_configured': True
                        }
                    }
        
        # Should not reach here, but just in case
        logger.error(f"Unexpected exit from retry loop. Last error: {last_error}")
        return {
            'success': False,
            'error': 'Unexpected error occurred. Please try again.',
            'error_type': 'api_unavailable',
            'service_status': {
                'gemini_available': False,
                'api_key_configured': False
            }
        }

    def _create_comprehensive_prompt(self, input_data: Dict[str, Any]) -> str:
        """Create a comprehensive prompt for Gemini AI - Enhanced for Indian Agriculture with Real Data Analysis"""
        
        # Extract and validate input parameters
        location = input_data.get('location', 'Not specified')
        soil_type = input_data.get('soil_type', 'Not specified')
        soil_ph = input_data.get('soil_ph', 'Not specified')
        water_source = input_data.get('water_source', 'Not specified')
        temperature = input_data.get('temperature_range', 'Not specified')
        rainfall = input_data.get('rainfall_range', 'Not specified')
        humidity = input_data.get('humidity_level', 'Not specified')
        season = input_data.get('season', 'Not specified')
        fertilizer = input_data.get('fertilizer_availability', 'Not specified')
        budget = input_data.get('budget_preference', 'Not specified')
        farm_size = input_data.get('farm_size', 'Not specified')
        market = input_data.get('market_preference', 'Not specified')
        experience = input_data.get('experience_level', 'Not specified')
        
        prompt = f"""
You are an expert agricultural scientist and agronomist with 20+ years of experience in Indian farming systems. Analyze the following REAL farming conditions and provide SCIENTIFICALLY ACCURATE crop recommendations based on actual agricultural data, soil science, climate patterns, and current market economics.

CRITICAL INSTRUCTION: Base ALL recommendations on REAL agricultural science, actual crop requirements, genuine market data, and proven farming practices. DO NOT provide generic or placeholder responses.

═══════════════════════════════════════════════════════════════
ACTUAL FARMING CONDITIONS TO ANALYZE:
═══════════════════════════════════════════════════════════════

📍 LOCATION: {location}
   → Analyze regional climate patterns, local market access, and state-specific agricultural practices

🌱 SOIL TYPE: {soil_type}
   → Consider actual soil characteristics: drainage, nutrient retention, texture, organic matter content
   → Match crops that ACTUALLY thrive in this specific soil type

⚗️ SOIL pH: {soil_ph}
   → Use REAL pH requirements for crops (e.g., rice: 5.5-7.0, wheat: 6.0-7.5, cotton: 6.0-8.0)
   → Recommend only crops that can genuinely grow in this pH range

💧 WATER SOURCE: {water_source}
   → Match water availability with ACTUAL crop water requirements
   → Consider irrigation efficiency and water stress tolerance

🌡️ TEMPERATURE: {temperature}
   → Use REAL temperature requirements (e.g., rice: 20-35°C, wheat: 10-25°C)
   → Consider heat/cold tolerance of recommended crops

🌧️ RAINFALL: {rainfall}
   → Match with ACTUAL rainfall requirements of crops
   → Consider drought tolerance and waterlogging sensitivity

💨 HUMIDITY: {humidity}
   → Factor in disease susceptibility based on humidity levels
   → Recommend crops with appropriate humidity tolerance

📅 SEASON: {season}
   → Recommend ONLY season-appropriate crops (Kharif/Rabi/Zaid)
   → Consider actual planting and harvesting windows

🧪 FERTILIZER: {fertilizer}
   → Provide REAL NPK requirements (e.g., rice: 120:60:40 kg/ha)
   → Include actual fertilizer costs and application schedules

💰 BUDGET: {budget}
   → Use REAL cost data for seeds, inputs, labor, and equipment
   → Provide accurate ROI calculations based on current market prices

📏 FARM SIZE: {farm_size} acres
   → Consider economies of scale and mechanization feasibility
   → Recommend crops suitable for this farm size

🎯 MARKET: {market}
   → Analyze REAL market demand and current prices
   → Consider transportation, storage, and market access

👨‍🌾 EXPERIENCE: {experience}
   → Match crop complexity with farmer's skill level
   → Recommend appropriate technical support needs

═══════════════════════════════════════════════════════════════
REQUIRED OUTPUT FORMAT:
═══════════════════════════════════════════════════════════════

Provide 8-12 crops ranked by ACTUAL suitability. Each crop MUST include:

1. REAL yield data (not "variable" - give actual ranges like "25-30 quintals/hectare")
2. ACTUAL cost estimates based on current Indian market prices
3. GENUINE revenue projections using current mandi prices
4. SPECIFIC fertilizer requirements (actual NPK ratios)
5. REAL water requirements (in mm or liters/hectare)
6. ACCURATE time to harvest (specific days, not ranges like "90-120")
7. ACTUAL market prices and demand analysis
8. SPECIFIC pest/disease risks for the given conditions

JSON FORMAT (return ONLY valid JSON array):
[
  {{
    "crop_name": "Specific variety name (e.g., 'Basmati Rice - Pusa 1121' not just 'Rice')",
    "suitability_score": <1-100 based on ACTUAL match with conditions>,
    "suitability_category": "Highly Suitable|Moderately Suitable|Less Suitable",
    "expected_yield": "Specific yield with units (e.g., '28-32 quintals/hectare' not 'Variable')",
    "time_to_harvest": "Exact days (e.g., '125 days' not '90-120 days')",
    "profitability": "Very High|High|Medium|Low",
    "water_requirements": "Specific amount (e.g., '1200-1400 mm' not just 'High')",
    "fertilizer_needs": "Actual NPK ratio and amounts (e.g., 'NPK 120:60:40 kg/ha, apply in 3 splits')",
    "pesticide_recommendations": "Specific products and application timing for common pests in this region",
    "irrigation_schedule": "Actual schedule (e.g., 'Irrigate every 7 days during vegetative stage, 5 days during flowering')",
    "disease_resistance": "High|Medium|Low with specific diseases mentioned",
    "market_demand": "Current market analysis with actual price range (e.g., 'High demand, ₹2500-3000/quintal in local mandis')",
    "growing_tips": ["Specific, actionable tip 1", "Specific, actionable tip 2", "Specific, actionable tip 3"],
    "estimated_cost": "Actual cost breakdown (e.g., '₹35,000-40,000/hectare including seeds ₹8000, fertilizer ₹12000, labor ₹15000')",
    "estimated_revenue": "Based on current market prices (e.g., '₹85,000-95,000/hectare at ₹3000/quintal')",
    "risk_factors": ["Specific risk 1 with probability", "Specific risk 2 with mitigation", "Specific risk 3"],
    "best_practices": ["Specific practice 1", "Specific practice 2", "Specific practice 3"],
    "yield_prediction": "Factors affecting yield with specific impacts (e.g., 'Good soil pH will increase yield by 15%, adequate water will add 20%')",
    "soil_health_impact": "Specific impact (e.g., 'Adds 2-3 tons organic matter/ha, fixes 40-50 kg N/ha if legume')",
    "climate_resilience": "Specific tolerance levels (e.g., 'Tolerates up to 42°C, drought resistant for 15 days')",
    "government_schemes": "Actual schemes (e.g., 'PM-KISAN ₹6000/year, Crop Insurance under PMFBY, MSP ₹2203/quintal')"
  }}
]

═══════════════════════════════════════════════════════════════
CRITICAL REQUIREMENTS:
═══════════════════════════════════════════════════════════════

✓ Use REAL agricultural data from Indian Council of Agricultural Research (ICAR)
✓ Include ACTUAL current market prices from major mandis
✓ Provide SPECIFIC variety names (not generic crop names)
✓ Calculate REAL ROI based on actual costs and revenues
✓ Consider ACTUAL seasonal timing for the specified season
✓ Include REAL government schemes and MSP (Minimum Support Price) where applicable
✓ Provide SPECIFIC pest/disease management for the region
✓ Use ACTUAL water requirements based on crop evapotranspiration data
✓ Include REAL fertilizer recommendations based on soil test values
✓ Consider ACTUAL labor requirements and mechanization needs

✗ NO generic responses like "Variable based on conditions"
✗ NO placeholder data or dummy values
✗ NO vague recommendations without specific numbers
✗ NO crops unsuitable for the given soil pH, temperature, or season
✗ NO outdated market prices or cost estimates

Return ONLY the JSON array. No markdown, no explanations, no additional text.
"""
        
        return prompt

    def _parse_ai_response(self, response_text: str) -> List[Dict[str, Any]]:
        """Parse AI response and extract structured data - JSON only, no fallback"""
        try:
            # Clean the response text
            cleaned_text = response_text.strip()
            
            # Remove markdown code blocks if present
            if '```json' in cleaned_text:
                cleaned_text = re.sub(r'```json\s*', '', cleaned_text)
                cleaned_text = re.sub(r'```\s*$', '', cleaned_text)
            elif '```' in cleaned_text:
                cleaned_text = re.sub(r'```\s*', '', cleaned_text)
            
            # Find JSON array in the response
            json_pattern = r'\[[\s\S]*\]'
            json_match = re.search(json_pattern, cleaned_text)
            
            if json_match:
                json_str = json_match.group(0)
                
                # Additional JSON cleaning to fix common issues
                # Fix trailing commas before closing brackets/braces
                json_str = re.sub(r',(\s*[}\]])', r'\1', json_str)
                # Fix missing commas between array elements (common AI mistake)
                json_str = re.sub(r'}\s*{', r'},{', json_str)
                # Remove any control characters that might break JSON
                json_str = ''.join(char for char in json_str if ord(char) >= 32 or char in '\n\r\t')
                
                try:
                    crops_data = json.loads(json_str)
                except json.JSONDecodeError as json_err:
                    # Log the problematic JSON for debugging
                    logger.error(f"JSON decode error at position {json_err.pos}: {json_err.msg}")
                    logger.debug(f"Problematic JSON snippet: {json_str[max(0, json_err.pos-100):min(len(json_str), json_err.pos+100)]}")
                    
                    # Try to salvage partial data by finding complete objects
                    logger.info("Attempting to salvage partial JSON data...")
                    crops_data = self._salvage_partial_json(json_str)
                    
                    if not crops_data:
                        logger.error("Could not salvage any valid crop data from malformed JSON")
                        return []
                
                # Validate and clean each crop entry
                validated_crops = []
                for crop in crops_data:
                    if isinstance(crop, dict) and 'crop_name' in crop:
                        validated_crop = self._validate_crop_data(crop)
                        if validated_crop:  # Only add if validation passed
                            validated_crops.append(validated_crop)
                
                if validated_crops:
                    logger.info(f"Successfully parsed {len(validated_crops)} crops from Gemini AI")
                    return validated_crops
                else:
                    logger.warning("No valid crops after validation")
                    return []
            
            # If JSON parsing fails, return empty list - no fallback to text parsing
            logger.error("JSON parsing failed - no valid JSON array found in AI response")
            return []
            
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error: {e}")
            return []
        except Exception as e:
            logger.error(f"Error parsing AI response: {e}")
            return []
    
    def _salvage_partial_json(self, json_str: str) -> List[Dict[str, Any]]:
        """
        Attempt to extract valid crop objects from malformed JSON.
        This is a fallback when the main JSON parsing fails.
        """
        crops = []
        try:
            # Find all complete object patterns that look like crop entries
            # Pattern: { ... "crop_name": "..." ... }
            object_pattern = r'\{[^{}]*"crop_name"\s*:\s*"[^"]*"[^{}]*\}'
            
            # Find all potential crop objects
            potential_objects = re.finditer(object_pattern, json_str, re.DOTALL)
            
            for match in potential_objects:
                obj_str = match.group(0)
                try:
                    # Try to parse this individual object
                    crop_obj = json.loads(obj_str)
                    if isinstance(crop_obj, dict) and 'crop_name' in crop_obj:
                        crops.append(crop_obj)
                        logger.debug(f"Salvaged crop object: {crop_obj.get('crop_name')}")
                except json.JSONDecodeError:
                    # This object is also malformed, skip it
                    continue
            
            if crops:
                logger.info(f"Salvaged {len(crops)} crop objects from malformed JSON")
            
            return crops
            
        except Exception as e:
            logger.error(f"Error during JSON salvage operation: {e}")
            return []
    
    def _validate_crop_data(self, crop: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Validate and standardize crop data from AI response - Strict validation, no fallback values"""
        
        # Define placeholder patterns to detect and reject
        PLACEHOLDER_PATTERNS = [
            'variable', 'based on conditions', 'not available',
            'not specified', 'x kg', 'x quintals', 'consult',
            'check local', 'data not available', 'varies',
            'depends on', 'to be determined', 'tbd', 'n/a'
        ]
        
        # Validate crop name
        crop_name = str(crop.get('crop_name', ''))
        if not crop_name.strip():
            logger.warning("Rejecting crop with empty crop name")
            return None
        
        # Reject generic crop names
        GENERIC_CROP_NAMES = [
            'rice', 'wheat', 'cotton', 'maize', 'corn',
            'unknown crop', 'crop', 'unknown', 'not specified',
            'barley', 'millet', 'sorghum', 'sugarcane',
            'pulses', 'vegetables', 'fruits'
        ]
        
        crop_name_lower = crop_name.lower().strip()
        
        # Check if crop name is exactly a generic name (not a variety)
        if crop_name_lower in GENERIC_CROP_NAMES:
            logger.warning(f"Rejecting crop with generic name: '{crop_name}'. Crop names must include specific varieties.")
            return None
        
        # Ensure crop name is properly capitalized and formatted
        # Capitalize first letter of each word for proper formatting
        crop_name = ' '.join(word.capitalize() for word in crop_name.split())
        crop['crop_name'] = crop_name
        
        # Log warning if crop name seems too short or generic
        if len(crop_name) < 4:
            logger.warning(f"Crop name '{crop_name}' is very short and may not be specific enough")
        
        # Check if crop name contains variety information (e.g., "Basmati Rice - Pusa 1121")
        # This is a quality indicator but not a rejection criterion
        if '-' not in crop_name and len(crop_name.split()) < 2:
            logger.warning(f"Crop name '{crop_name}' may lack variety information. Specific varieties are preferred.")
        
        # Build validated crop data - no default/fallback values
        validated = {
            'crop_name': crop_name,
            'suitability_score': max(1, min(100, int(crop.get('suitability_score', 0)))) if crop.get('suitability_score') else 0,
            'suitability_category': crop.get('suitability_category', ''),
            'expected_yield': crop.get('expected_yield', ''),
            'time_to_harvest': crop.get('time_to_harvest', ''),
            'profitability': crop.get('profitability', ''),
            'water_requirements': crop.get('water_requirements', ''),
            'fertilizer_needs': crop.get('fertilizer_needs', ''),
            'pesticide_recommendations': crop.get('pesticide_recommendations', ''),
            'irrigation_schedule': crop.get('irrigation_schedule', ''),
            'disease_resistance': crop.get('disease_resistance', ''),
            'market_demand': crop.get('market_demand', ''),
            'growing_tips': crop.get('growing_tips', []) if isinstance(crop.get('growing_tips'), list) else [],
            'estimated_cost': crop.get('estimated_cost', ''),
            'estimated_revenue': crop.get('estimated_revenue', ''),
            'risk_factors': crop.get('risk_factors', []) if isinstance(crop.get('risk_factors'), list) else [],
            'best_practices': crop.get('best_practices', []) if isinstance(crop.get('best_practices'), list) else [],
            'yield_prediction': crop.get('yield_prediction', ''),
            'soil_health_impact': crop.get('soil_health_impact', ''),
            'climate_resilience': crop.get('climate_resilience', ''),
            'government_schemes': crop.get('government_schemes', '')
        }
        
        # Check critical fields for placeholder patterns
        critical_fields = {
            'expected_yield': validated['expected_yield'],
            'estimated_cost': validated['estimated_cost'],
            'estimated_revenue': validated['estimated_revenue'],
            'fertilizer_needs': validated['fertilizer_needs'],
            'market_demand': validated['market_demand']
        }
        
        # Log warnings when placeholder patterns are detected
        for field_name, field_value in critical_fields.items():
            field_value_lower = str(field_value).lower()
            for pattern in PLACEHOLDER_PATTERNS:
                if pattern in field_value_lower:
                    logger.warning(f"Placeholder pattern '{pattern}' detected in {field_name} for crop {crop_name}: {field_value}")
                    break
        
        # Calculate ROI from parsed data (no fallback estimates)
        validated['roi_percentage'] = 0
        try:
            cost_str = str(validated['estimated_cost']).replace('₹', '').replace(',', '').replace('/hectare', '').replace('/acre', '').split('-')[0].strip()
            revenue_str = str(validated['estimated_revenue']).replace('₹', '').replace(',', '').replace('/hectare', '').replace('/acre', '').split('-')[0].strip()
            
            # Extract numbers more robustly
            cost_match = re.search(r'(\d+(?:\.\d+)?)', cost_str)
            revenue_match = re.search(r'(\d+(?:\.\d+)?)', revenue_str)
            
            if cost_match and revenue_match:
                cost = float(cost_match.group(1))
                revenue = float(revenue_match.group(1))
                
                if cost > 0:
                    roi = ((revenue - cost) / cost) * 100
                    validated['roi_percentage'] = round(roi, 1)
                    logger.debug(f"ROI calculated for {crop_name}: {validated['roi_percentage']}% (cost: ₹{cost}, revenue: ₹{revenue})")
                else:
                    logger.warning(f"ROI calculation failed for {crop_name}: cost is zero or negative (cost: {cost})")
            else:
                logger.warning(f"ROI calculation failed for {crop_name}: could not parse cost/revenue data (cost: '{cost_str}', revenue: '{revenue_str}')")
                
        except (ValueError, ZeroDivisionError, AttributeError) as e:
            logger.warning(f"ROI calculation failed for {crop_name}: {type(e).__name__}: {e} (cost: '{validated['estimated_cost']}', revenue: '{validated['estimated_revenue']}')")
        
        # Calculate data quality score using the new algorithm
        validated['data_quality_score'] = self._calculate_data_quality_score(validated, PLACEHOLDER_PATTERNS)
        
        # Get minimum quality score threshold from config
        min_quality_score = getattr(Config, 'CROP_AI_MIN_QUALITY_SCORE', 70)
        
        # Log warning if quality score is below threshold
        if validated['data_quality_score'] < min_quality_score:
            logger.warning(f"Low data quality score ({validated['data_quality_score']}) for crop {crop_name}")
            
            # In strict mode, reject crops with quality score below threshold
            if self.strict_mode:
                logger.warning(f"Rejecting crop {crop_name} due to low quality score ({validated['data_quality_score']} < {min_quality_score}) in strict mode")
                return None
        
        return validated
    
    def _calculate_data_quality_score(self, crop_data: Dict[str, Any], placeholder_patterns: List[str]) -> int:
        """
        Calculate quality score based on data completeness and specificity.
        
        Scoring:
        - Start with 100 points
        - Deduct points for each quality issue
        
        Args:
            crop_data: Validated crop data dictionary
            placeholder_patterns: List of placeholder patterns to check for
            
        Returns:
            Quality score from 0-100
        """
        score = 100
        crop_name = crop_data.get('crop_name', '')
        
        # Check for placeholder patterns in critical fields (-30 points each)
        critical_fields = [
            'expected_yield',
            'estimated_cost',
            'estimated_revenue',
            'fertilizer_needs',
            'market_demand'
        ]
        
        for field in critical_fields:
            value = str(crop_data.get(field, '')).lower()
            for pattern in placeholder_patterns:
                if pattern in value:
                    score -= 30
                    break  # Only deduct once per field
        
        # Check for empty lists (-10 points each)
        list_fields = ['growing_tips', 'risk_factors', 'best_practices']
        for field in list_fields:
            if not crop_data.get(field):
                score -= 10
        
        # Check for zero ROI (-10 points)
        if crop_data.get('roi_percentage', 0) == 0:
            score -= 10
        
        # Check for generic crop names (-20 points for borderline cases)
        generic_names = [
            'rice', 'wheat', 'cotton', 'maize', 'corn',
            'unknown crop', 'crop', 'unknown', 'barley',
            'millet', 'sorghum', 'sugarcane', 'pulses',
            'vegetables', 'fruits'
        ]
        crop_name_lower = crop_name.lower().strip()
        if crop_name_lower in generic_names:
            score -= 20
        
        # Check if crop name lacks variety information (-10 points)
        if '-' not in crop_name and len(crop_name.split()) < 2:
            score -= 10
        
        return max(0, score)



    def _enhance_suggestions(self, suggestions: List[Dict[str, Any]], input_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Enhance suggestions with additional calculations and insights"""
        enhanced = []
        
        for i, crop in enumerate(suggestions):
            enhanced_crop = crop.copy()
            
            # Add ranking
            enhanced_crop['rank'] = i + 1
            
            # Ensure ROI is present (0 indicates missing/invalid data)
            if 'roi_percentage' not in enhanced_crop:
                enhanced_crop['roi_percentage'] = 0
                logger.warning(f"ROI not found for {crop.get('crop_name', 'unknown crop')} - setting to 0")
            
            # Add suitability factors based on input
            enhanced_crop['suitability_factors'] = self._calculate_suitability_factors(crop, input_data)
            
            # Add seasonal appropriateness
            enhanced_crop['seasonal_match'] = self._check_seasonal_match(crop, input_data.get('season'))
            
            # Add sustainability score
            enhanced_crop['sustainability_score'] = self._calculate_sustainability_score(crop, input_data)
            
            enhanced.append(enhanced_crop)
        
        # Sort by suitability score
        enhanced.sort(key=lambda x: x.get('suitability_score', 0), reverse=True)
        
        return enhanced
    
    def _calculate_suitability_factors(self, crop: Dict[str, Any], input_data: Dict[str, Any]) -> Dict[str, str]:
        """Calculate specific suitability factors"""
        factors = {}
        
        # Soil compatibility
        soil_type = input_data.get('soil_type', '').lower()
        crop_name = crop.get('crop_name', '').lower()
        
        # Enhanced soil compatibility logic
        if 'rice' in crop_name:
            if soil_type in ['clay', 'loamy', 'alluvial']:
                factors['soil_compatibility'] = 'Excellent'
            elif soil_type in ['black', 'red']:
                factors['soil_compatibility'] = 'Good'
            else:
                factors['soil_compatibility'] = 'Moderate'
        elif 'wheat' in crop_name:
            if soil_type in ['loamy', 'black', 'alluvial']:
                factors['soil_compatibility'] = 'Excellent'
            else:
                factors['soil_compatibility'] = 'Good'
        elif 'cotton' in crop_name:
            if soil_type in ['black', 'red']:
                factors['soil_compatibility'] = 'Excellent'
            else:
                factors['soil_compatibility'] = 'Moderate'
        else:
            factors['soil_compatibility'] = 'Good'  # Default
        
        # Water compatibility
        water_source = input_data.get('water_source', '').lower()
        water_req = crop.get('water_requirements', '').lower()
        
        if 'high' in water_req or 'very high' in water_req:
            if 'irrigated' in water_source or 'drip' in water_source:
                factors['water_compatibility'] = 'Excellent'
            elif 'groundwater_high' in water_source:
                factors['water_compatibility'] = 'Good'
            else:
                factors['water_compatibility'] = 'Poor'
        elif 'low' in water_req:
            if 'rainfed' in water_source:
                factors['water_compatibility'] = 'Excellent'
            else:
                factors['water_compatibility'] = 'Good'
        else:
            factors['water_compatibility'] = 'Good'
        
        # Climate compatibility
        temperature = input_data.get('temperature_range', '')
        rainfall = input_data.get('rainfall_range', '')
        
        if 'moderate' in temperature and 'moderate' in rainfall:
            factors['climate_compatibility'] = 'Excellent'
        elif 'warm' in temperature or 'high' in rainfall:
            factors['climate_compatibility'] = 'Good'
        else:
            factors['climate_compatibility'] = 'Moderate'
        
        return factors
    
    def _check_seasonal_match(self, crop: Dict[str, Any], season: str) -> str:
        """Check if crop matches the season"""
        if not season:
            return 'Unknown'
        
        crop_name = crop.get('crop_name', '').lower()
        season = season.lower()
        
        # Kharif crops (monsoon season)
        kharif_crops = ['rice', 'cotton', 'sugarcane', 'maize', 'bajra', 'jowar', 'groundnut', 'soybean']
        
        # Rabi crops (winter season)
        rabi_crops = ['wheat', 'barley', 'peas', 'mustard', 'gram', 'chana', 'masoor', 'rapeseed']
        
        # Zaid crops (summer season)
        zaid_crops = ['watermelon', 'cucumber', 'fodder', 'green fodder', 'moong']
        
        # Year-round crops
        perennial_crops = ['sugarcane', 'banana', 'coconut', 'mango', 'vegetables']
        
        if season == 'kharif' and any(kc in crop_name for kc in kharif_crops):
            return 'Perfect Match'
        elif season == 'rabi' and any(rc in crop_name for rc in rabi_crops):
            return 'Perfect Match'
        elif season == 'zaid' and any(zc in crop_name for zc in zaid_crops):
            return 'Perfect Match'
        elif season == 'year_round' or any(pc in crop_name for pc in perennial_crops):
            return 'Suitable'
        else:
            return 'Moderate Match'
    
    def _calculate_sustainability_score(self, crop: Dict[str, Any], input_data: Dict[str, Any]) -> int:
        """Calculate sustainability score based on various factors"""
        score = 50  # Base score
        
        # Water efficiency
        water_req = crop.get('water_requirements', '').lower()
        if 'low' in water_req:
            score += 15
        elif 'medium' in water_req:
            score += 10
        elif 'high' in water_req:
            score += 5
        
        # Soil health impact
        soil_impact = crop.get('soil_health_impact', '').lower()
        if 'improves' in soil_impact or 'enriches' in soil_impact:
            score += 15
        elif 'maintains' in soil_impact:
            score += 10
        elif 'neutral' in soil_impact:
            score += 5
        
        # Climate resilience
        climate_resilience = crop.get('climate_resilience', '').lower()
        if 'high' in climate_resilience:
            score += 10
        elif 'moderate' in climate_resilience:
            score += 5
        
        # Organic potential
        fertilizer_type = input_data.get('fertilizer_availability', '').lower()
        if 'organic' in fertilizer_type:
            score += 10
        
        return min(100, max(0, score))
    
    @staticmethod
    def compare_crops_analysis(crop_names: List[str], comparison_factor: str = 'profitability') -> Dict[str, Any]:
        """
        Compare multiple crops using Gemini AI analysis
        """
        try:
            service = EnhancedCropAI()
            if not service.model:
                return {
                    'success': False,
                    'error': 'AI service not available',
                    'comparison': {}
                }
            
            # Create comparison prompt
            prompt = f"""
You are an agricultural expert specializing in Indian agriculture. Compare the following crops based on {comparison_factor}:

Crops to compare: {', '.join(crop_names)}
Comparison factor: {comparison_factor}

IMPORTANT: Use Indian Rupee (₹) for ALL monetary values. DO NOT use dollar signs ($) or any other currency.

Provide a detailed comparison with the following structure:
{{
  "comparison_factor": "{comparison_factor}",
  "crop_analysis": [
    {{
      "crop_name": "crop name",
      "score": numeric_score_1_to_100,
      "advantages": ["advantage1", "advantage2"],
      "disadvantages": ["disadvantage1", "disadvantage2"],
      "key_metrics": {{
        "yield_potential": "description with specific numbers",
        "investment_required": "amount in Indian Rupees (₹) - e.g., ₹1,000 - ₹5,000+ per acre",
        "market_price": "price range in Indian Rupees (₹) - e.g., ₹0.20 - ₹1.50+ per pound",
        "risk_level": "High/Medium/Low"
      }},
      "recommendation": "detailed recommendation"
    }}
  ],
  "overall_recommendation": "which crop is best and why",
  "market_insights": "current market analysis with Indian Rupee (₹) prices",
  "risk_assessment": "comparative risk analysis"
}}

CRITICAL: All prices and costs MUST be in Indian Rupees (₹). Never use $ or USD.

Return only valid JSON, no additional text.
"""
            
            response = service.model.generate_content(
                prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=0.6,
                    top_p=0.8,
                    max_output_tokens=4096,
                )
            )
            
            # Parse response
            try:
                # Clean the response text
                response_text = response.text.strip()
                
                # Try to extract JSON if response contains extra text
                if '```json' in response_text:
                    start = response_text.find('```json') + 7
                    end = response_text.find('```', start)
                    if end != -1:
                        response_text = response_text[start:end].strip()
                elif '{' in response_text:
                    # Extract JSON from the first { to last }
                    start = response_text.find('{')
                    end = response_text.rfind('}') + 1
                    response_text = response_text[start:end]
                
                comparison_data = json.loads(response_text)
                
                # Validate the response structure
                if not isinstance(comparison_data, dict):
                    raise ValueError("Response is not a valid dictionary")
                
                # Ensure required fields exist
                if 'crop_analysis' not in comparison_data:
                    comparison_data['crop_analysis'] = []
                
                return {
                    'success': True,
                    'comparison': comparison_data,
                    'generated_at': datetime.now().isoformat(),
                    'ai_model': 'gemini-2.5-flash-lite'
                }
            except (json.JSONDecodeError, ValueError) as e:
                logger.error(f"JSON parsing error: {e}")
                logger.error(f"Raw response: {response.text[:500]}")
                return {
                    'success': False,
                    'error': 'Failed to parse AI comparison response. The AI response was malformed.',
                    'comparison': {},
                    'raw_response': response.text[:200]  # First 200 chars for debugging
                }
                
        except Exception as e:
            logger.error(f"Error in crop comparison: {e}")
            return {
                'success': False,
                'error': str(e),
                'comparison': {}
            }
    
    @staticmethod
    def get_fertilizer_recommendations(crop_name, soil_data):
        """Get detailed fertilizer recommendations for a specific crop"""
        try:
            prompt = f"""
            As an expert agricultural consultant, provide comprehensive fertilizer recommendations for {crop_name} cultivation.
            
            Soil Information:
            - Soil Type: {soil_data.get('soil_type', 'Not specified')}
            - Soil pH: {soil_data.get('soil_ph', 'Not specified')}
            - Organic Matter: {soil_data.get('organic_matter', 'Not specified')}
            - Nutrient Status: {soil_data.get('nutrient_status', 'Not specified')}
            - Location: {soil_data.get('location', 'India')}
            
            Provide detailed recommendations in JSON format:
            {{
                "success": true,
                "crop_name": "{crop_name}",
                "recommendations": {{
                    "primary_nutrients": {{
                        "nitrogen": {{"amount": "X kg/hectare", "timing": "schedule", "source": "fertilizer type"}},
                        "phosphorus": {{"amount": "X kg/hectare", "timing": "schedule", "source": "fertilizer type"}},
                        "potassium": {{"amount": "X kg/hectare", "timing": "schedule", "source": "fertilizer type"}}
                    }},
                    "secondary_nutrients": {{
                        "calcium": {{"amount": "X kg/hectare", "source": "fertilizer type"}},
                        "magnesium": {{"amount": "X kg/hectare", "source": "fertilizer type"}},
                        "sulfur": {{"amount": "X kg/hectare", "source": "fertilizer type"}}
                    }},
                    "micronutrients": [
                        {{"nutrient": "Iron", "amount": "X kg/hectare", "source": "fertilizer type"}},
                        {{"nutrient": "Zinc", "amount": "X kg/hectare", "source": "fertilizer type"}}
                    ],
                    "organic_options": [
                        {{"type": "compost", "amount": "X tons/hectare", "benefits": "description"}},
                        {{"type": "bio-fertilizers", "amount": "X kg/hectare", "benefits": "description"}}
                    ],
                    "application_schedule": [
                        {{"stage": "pre-planting", "fertilizers": ["list"], "timing": "when to apply"}},
                        {{"stage": "vegetative", "fertilizers": ["list"], "timing": "when to apply"}},
                        {{"stage": "flowering", "fertilizers": ["list"], "timing": "when to apply"}},
                        {{"stage": "fruiting", "fertilizers": ["list"], "timing": "when to apply"}}
                    ],
                    "cost_estimate": {{
                        "total_cost_per_hectare": "₹X",
                        "cost_breakdown": [
                            {{"item": "fertilizer name", "cost": "₹X"}}
                        ]
                    }},
                    "sustainability_tips": [
                        "tip 1 for sustainable fertilizer use",
                        "tip 2 for soil health improvement"
                    ]
                }}
            }}
            
            Make recommendations specific to Indian agricultural conditions and include both chemical and organic options.
            """
            
            model = genai.GenerativeModel('gemini-2.5-flash-lite')
            response = model.generate_content(prompt)
            
            # Try to parse JSON response
            try:
                result = json.loads(response.text)
                return result
            except json.JSONDecodeError:
                # Fallback to text parsing if JSON fails
                return {
                    "success": True,
                    "crop_name": crop_name,
                    "recommendations": {
                        "text_response": response.text,
                        "note": "Detailed fertilizer recommendations provided"
                    }
                }
        
        except Exception as e:
            logger.error(f"Error in fertilizer recommendations: {str(e)}")
            return {
                "success": False,
                "error": f"Failed to get fertilizer recommendations: {str(e)}"
            }
    
    @staticmethod
    def get_irrigation_schedule(crop_name, climate_data):
        """Get detailed irrigation schedule for a specific crop"""
        try:
            prompt = f"""
            As an expert irrigation specialist, create a comprehensive irrigation schedule for {crop_name} cultivation.
            
            Climate and Farm Information:
            - Location: {climate_data.get('location', 'India')}
            - Season: {climate_data.get('season', 'Not specified')}
            - Water Source: {climate_data.get('water_source', 'Not specified')}
            - Soil Type: {climate_data.get('soil_type', 'Not specified')}
            - Farm Size: {climate_data.get('farm_size', 'Not specified')}
            - Irrigation Method: {climate_data.get('irrigation_method', 'Not specified')}
            
            Provide detailed irrigation schedule in JSON format:
            {{
                "success": true,
                "crop_name": "{crop_name}",
                "schedule": {{
                    "crop_duration": "X days/months",
                    "total_water_requirement": "X mm or liters/hectare",
                    "growth_stages": [
                        {{
                            "stage": "germination",
                            "duration": "X days",
                            "water_frequency": "every X days",
                            "water_amount": "X mm per irrigation",
                            "critical_notes": "special requirements"
                        }},
                        {{
                            "stage": "vegetative",
                            "duration": "X days",
                            "water_frequency": "every X days",
                            "water_amount": "X mm per irrigation",
                            "critical_notes": "special requirements"
                        }},
                        {{
                            "stage": "flowering",
                            "duration": "X days",
                            "water_frequency": "every X days",
                            "water_amount": "X mm per irrigation",
                            "critical_notes": "special requirements"
                        }},
                        {{
                            "stage": "maturity",
                            "duration": "X days",
                            "water_frequency": "every X days",
                            "water_amount": "X mm per irrigation",
                            "critical_notes": "special requirements"
                        }}
                    ],
                    "irrigation_methods": [
                        {{"method": "drip irrigation", "efficiency": "X%", "suitability": "high/medium/low"}},
                        {{"method": "sprinkler", "efficiency": "X%", "suitability": "high/medium/low"}},
                        {{"method": "furrow", "efficiency": "X%", "suitability": "high/medium/low"}}
                    ],
                    "water_conservation": [
                        "tip 1 for water conservation",
                        "tip 2 for efficient water use"
                    ],
                    "monitoring_indicators": [
                        "soil moisture levels",
                        "plant stress signs",
                        "weather conditions"
                    ],
                    "seasonal_adjustments": {{
                        "monsoon": "adjustments during rainy season",
                        "summer": "adjustments during hot season",
                        "winter": "adjustments during cool season"
                    }},
                    "cost_estimate": {{
                        "setup_cost": "₹X per hectare",
                        "operational_cost": "₹X per season",
                        "water_cost": "₹X per season"
                    }}
                }}
            }}
            
            Focus on Indian agricultural conditions and include water-efficient practices.
            """
            
            model = genai.GenerativeModel('gemini-2.5-flash-lite')
            response = model.generate_content(prompt)
            
            # Try to parse JSON response
            try:
                result = json.loads(response.text)
                return result
            except json.JSONDecodeError:
                # Fallback to text parsing if JSON fails
                return {
                    "success": True,
                    "crop_name": crop_name,
                    "schedule": {
                        "text_response": response.text,
                        "note": "Detailed irrigation schedule provided"
                    }
                }
        
        except Exception as e:
            logger.error(f"Error in irrigation schedule: {str(e)}")
            return {
                "success": False,
                "error": f"Failed to get irrigation schedule: {str(e)}"
            }
    
    @staticmethod
    def predict_yield(crop_name, farming_conditions):
        """Predict crop yield based on farming conditions"""
        try:
            prompt = f"""
            As an expert agricultural analyst, predict the yield for {crop_name} based on the given farming conditions.
            
            Farming Conditions:
            - Location: {farming_conditions.get('location', 'India')}
            - Soil Type: {farming_conditions.get('soil_type', 'Not specified')}
            - Soil pH: {farming_conditions.get('soil_ph', 'Not specified')}
            - Water Source: {farming_conditions.get('water_source', 'Not specified')}
            - Fertilizer Availability: {farming_conditions.get('fertilizer_availability', 'Not specified')}
            - Season: {farming_conditions.get('season', 'Not specified')}
            - Farm Size: {farming_conditions.get('farm_size', 'Not specified')}
            - Farming Experience: {farming_conditions.get('experience', 'Not specified')}
            - Budget: {farming_conditions.get('budget_preference', 'Not specified')}
            
            Provide yield prediction in JSON format:
            {{
                "success": true,
                "crop_name": "{crop_name}",
                "prediction": {{
                    "expected_yield": {{
                        "minimum": "X quintals/hectare",
                        "average": "X quintals/hectare",
                        "maximum": "X quintals/hectare",
                        "confidence_level": "X%"
                    }},
                    "yield_factors": [
                        {{"factor": "soil quality", "impact": "positive/negative", "importance": "high/medium/low"}},
                        {{"factor": "water availability", "impact": "positive/negative", "importance": "high/medium/low"}},
                        {{"factor": "fertilizer use", "impact": "positive/negative", "importance": "high/medium/low"}},
                        {{"factor": "climate conditions", "impact": "positive/negative", "importance": "high/medium/low"}}
                    ],
                    "improvement_suggestions": [
                        {{"area": "soil management", "suggestion": "specific recommendation", "potential_increase": "X%"}},
                        {{"area": "irrigation", "suggestion": "specific recommendation", "potential_increase": "X%"}},
                        {{"area": "fertilization", "suggestion": "specific recommendation", "potential_increase": "X%"}}
                    ],
                    "risk_factors": [
                        {{"risk": "drought", "probability": "high/medium/low", "mitigation": "how to reduce risk"}},
                        {{"risk": "pests", "probability": "high/medium/low", "mitigation": "how to reduce risk"}},
                        {{"risk": "diseases", "probability": "high/medium/low", "mitigation": "how to reduce risk"}}
                    ],
                    "economic_analysis": {{
                        "production_cost": "₹X per hectare",
                        "expected_revenue": {{
                            "minimum": "₹X per hectare",
                            "average": "₹X per hectare",
                            "maximum": "₹X per hectare"
                        }},
                        "profit_margin": {{
                            "minimum": "₹X per hectare",
                            "average": "₹X per hectare",
                            "maximum": "₹X per hectare"
                        }},
                        "roi_percentage": "X%"
                    }},
                    "market_insights": {{
                        "current_price": "₹X per quintal",
                        "price_trend": "increasing/stable/decreasing",
                        "demand_outlook": "high/medium/low",
                        "best_selling_time": "month/season"
                    }},
                    "recommendations": [
                        "key recommendation 1 for maximizing yield",
                        "key recommendation 2 for profit optimization"
                    ]
                }}
            }}
            
            Base predictions on Indian agricultural data and current market conditions.
            """
            
            model = genai.GenerativeModel('gemini-2.5-flash-lite')
            response = model.generate_content(prompt)
            
            # Try to parse JSON response
            try:
                result = json.loads(response.text)
                return result
            except json.JSONDecodeError:
                # Fallback to text parsing if JSON fails
                return {
                    "success": True,
                    "crop_name": crop_name,
                    "prediction": {
                        "text_response": response.text,
                        "note": "Detailed yield prediction provided"
                    }
                }
        
        except Exception as e:
            logger.error(f"Error in yield prediction: {str(e)}")
            return {
                "success": False,
                "error": f"Failed to predict yield: {str(e)}"
            }
    
    @staticmethod
    def get_seasonal_recommendations(input_data, season):
        """Get season-specific crop recommendations"""
        try:
            prompt = f"""
            As an expert agricultural consultant, provide season-specific crop recommendations for {season} season.
            
            Farm Information:
            - Location: {input_data.get('location', 'India')}
            - Soil Type: {input_data.get('soil_type', 'Not specified')}
            - Soil pH: {input_data.get('soil_ph', 'Not specified')}
            - Water Source: {input_data.get('water_source', 'Not specified')}
            - Fertilizer Availability: {input_data.get('fertilizer_availability', 'Not specified')}
            - Budget Preference: {input_data.get('budget_preference', 'Not specified')}
            
            Provide seasonal recommendations in JSON format:
            {{
                "success": true,
                "season": "{season}",
                "recommendations": {{
                    "top_crops": [
                        {{
                            "crop_name": "crop 1",
                            "suitability_score": "X/10",
                            "planting_time": "specific months",
                            "harvest_time": "specific months",
                            "expected_yield": "X quintals/hectare",
                            "market_demand": "high/medium/low",
                            "profit_potential": "₹X per hectare",
                            "key_benefits": ["benefit 1", "benefit 2"]
                        }}
                    ],
                    "seasonal_advantages": [
                        "advantage 1 of this season",
                        "advantage 2 of this season"
                    ],
                    "seasonal_challenges": [
                        "challenge 1 and mitigation",
                        "challenge 2 and mitigation"
                    ],
                    "preparation_timeline": [
                        {{"activity": "land preparation", "timing": "X weeks before planting"}},
                        {{"activity": "seed procurement", "timing": "X weeks before planting"}},
                        {{"activity": "irrigation setup", "timing": "X weeks before planting"}}
                    ],
                    "resource_requirements": {{
                        "seeds": "X kg/hectare",
                        "fertilizers": "specific types and quantities",
                        "water": "X mm total requirement",
                        "labor": "X person-days"
                    }},
                    "success_tips": [
                        "tip 1 for successful cultivation",
                        "tip 2 for maximizing profits"
                    ]
                }}
            }}
            
            Focus on crops suitable for Indian climate and {season} season conditions.
            """
            
            model = genai.GenerativeModel('gemini-2.5-flash-lite')
            response = model.generate_content(prompt)
            
            # Try to parse JSON response
            try:
                result = json.loads(response.text)
                return result
            except json.JSONDecodeError:
                # Fallback to text parsing if JSON fails
                return {
                    "success": True,
                    "season": season,
                    "recommendations": {
                        "text_response": response.text,
                        "note": f"Seasonal recommendations for {season} provided"
                    }
                }
        
        except Exception as e:
            logger.error(f"Error in seasonal recommendations: {str(e)}")
            return {
                "success": False,
                "error": f"Failed to get seasonal recommendations: {str(e)}"
            }

def get_crop_service_status() -> Dict[str, Any]:
    """Get the status of crop AI service"""
    try:
        service = EnhancedCropAI()
        return {
            'service_available': service.model is not None,
            'model_name': 'gemini-2.5-flash-lite',
            'capabilities': [
                'crop_suggestions',
                'crop_comparison', 
                'seasonal_recommendations',
                'fertilizer_planning',
                'irrigation_scheduling',
                'yield_prediction'
            ],
            'last_checked': datetime.now().isoformat()
        }
    except Exception as e:
        return {
            'service_available': False,
            'error': str(e),
            'last_checked': datetime.now().isoformat()
        }

# Main service instance
CROP_AI_AVAILABLE = True
try:
    enhanced_crop_ai = EnhancedCropAI()
    logger.info("Enhanced Crop AI service initialized successfully")
except Exception as e:
    CROP_AI_AVAILABLE = False
    enhanced_crop_ai = None
    logger.error(f"Enhanced Crop AI service initialization failed: {e}")
