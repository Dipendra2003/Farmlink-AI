import logging
import os
import json
import re
import time
import hashlib
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Tuple
from PIL import Image, ImageEnhance, ImageStat
import google.generativeai as genai
from config import Config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class PestDiseaseDetectionService:
    
    COMMON_PESTS = {
        'rice': ['brown planthopper', 'stem borer', 'leaf folder', 'gall midge'],
        'wheat': ['aphids', 'armyworm', 'termites', 'rust'],
        'cotton': ['bollworm', 'whitefly', 'aphids', 'jassids'],
        'tomato': ['fruit borer', 'whitefly', 'leaf miner', 'aphids'],
        'potato': ['late blight', 'early blight', 'aphids', 'tuber moth']
    }
    
    COMMON_DISEASES = {
        'rice': ['blast', 'bacterial leaf blight', 'sheath blight', 'tungro'],
        'wheat': ['rust', 'powdery mildew', 'smut', 'bunt'],
        'cotton': ['wilt', 'leaf curl', 'boll rot', 'root rot'],
        'tomato': ['late blight', 'early blight', 'leaf curl', 'bacterial wilt'],
        'potato': ['late blight', 'early blight', 'black scurf', 'common scab']
    }
    
    def __init__(self):
        self.gemini_model = None
        self.client_error = None
        self.model_name = 'gemini-2.5-flash-lite'
        self.analysis_cache = {}
        self.cache_ttl = 3600
        self.max_cache_size = 100
        self.initialize_ai_client()
    
    def _generate_cache_key(self, image_path: str, crop_type: str, context: Optional[Dict[str, Any]] = None) -> str:
        """Generate unique cache key for analysis results"""
        try:
            with open(image_path, 'rb') as f:
                image_hash = hashlib.md5(f.read()).hexdigest()
            
            context_str = json.dumps(context or {}, sort_keys=True)
            cache_str = f"{image_hash}_{crop_type}_{context_str}"
            return hashlib.md5(cache_str.encode()).hexdigest()
        except Exception as e:
            logger.error(f"Cache key generation failed: {str(e)}")
            return None
    
    def _get_cached_analysis(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """Retrieve cached analysis if available and not expired"""
        if not cache_key or cache_key not in self.analysis_cache:
            return None
        
        cached_entry = self.analysis_cache[cache_key]
        cache_time = cached_entry.get('timestamp', 0)
        
        if time.time() - cache_time > self.cache_ttl:
            del self.analysis_cache[cache_key]
            return None
        
        logger.info(f"Cache hit for key: {cache_key[:8]}...")
        return cached_entry.get('result')
    
    def _cache_analysis(self, cache_key: str, result: Dict[str, Any]):
        """Cache analysis result with timestamp"""
        if not cache_key:
            return
        
        if len(self.analysis_cache) >= self.max_cache_size:
            oldest_key = min(self.analysis_cache.keys(), 
                           key=lambda k: self.analysis_cache[k].get('timestamp', 0))
            del self.analysis_cache[oldest_key]
        
        self.analysis_cache[cache_key] = {
            'result': result,
            'timestamp': time.time()
        }
    
    def _assess_image_quality(self, image: Image.Image) -> Dict[str, Any]:
        """Assess image quality for analysis suitability"""
        try:
            width, height = image.size
            total_pixels = width * height
            
            stat = ImageStat.Stat(image)
            brightness = sum(stat.mean) / len(stat.mean)
            
            if image.mode == 'RGB':
                r, g, b = stat.stddev
                sharpness = (r + g + b) / 3
            else:
                sharpness = stat.stddev[0] if stat.stddev else 0
            
            issues = []
            score = 100
            
            if total_pixels < 100000:
                issues.append('Low resolution')
                score -= 30
            
            if brightness < 50:
                issues.append('Too dark')
                score -= 20
            elif brightness > 200:
                issues.append('Too bright')
                score -= 20
            
            if sharpness < 20:
                issues.append('Blurry')
                score -= 25
            
            return {
                'score': max(0, score),
                'resolution': f"{width}x{height}",
                'brightness': round(brightness, 2),
                'sharpness': round(sharpness, 2),
                'issues': issues
            }
        except Exception as e:
            logger.error(f"Image quality assessment failed: {str(e)}")
            return {'score': 50, 'issues': ['Unable to assess']}
    
    def _preprocess_image(self, image: Image.Image) -> Image.Image:
        """Preprocess image for better analysis"""
        try:
            if image.mode != 'RGB':
                image = image.convert('RGB')
            
            width, height = image.size
            max_dimension = 1920
            
            if width > max_dimension or height > max_dimension:
                if width > height:
                    new_width = max_dimension
                    new_height = int(height * (max_dimension / width))
                else:
                    new_height = max_dimension
                    new_width = int(width * (max_dimension / height))
                
                image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
                logger.info(f"Image resized to {new_width}x{new_height}")
            
            stat = ImageStat.Stat(image)
            brightness = sum(stat.mean) / len(stat.mean)
            
            if brightness < 80:
                enhancer = ImageEnhance.Brightness(image)
                image = enhancer.enhance(1.2)
                logger.info("Image brightness enhanced")
            
            if brightness > 180:
                enhancer = ImageEnhance.Brightness(image)
                image = enhancer.enhance(0.9)
                logger.info("Image brightness reduced")
            
            return image
        except Exception as e:
            logger.error(f"Image preprocessing failed: {str(e)}")
            return image
    
    def _get_common_issues(self, crop_type: str, season: str, location: str) -> Dict[str, List[str]]:
        """Get common pests and diseases for crop, season, and location"""
        crop_lower = crop_type.lower()
        
        common_pests = self.COMMON_PESTS.get(crop_lower, [])
        common_diseases = self.COMMON_DISEASES.get(crop_lower, [])
        
        seasonal_factors = []
        if season.lower() in ['june', 'july', 'august', 'september']:
            seasonal_factors.append('High humidity increases fungal disease risk')
            seasonal_factors.append('Monsoon season pest activity')
        elif season.lower() in ['october', 'november', 'december', 'january']:
            seasonal_factors.append('Post-monsoon disease pressure')
            seasonal_factors.append('Winter pest dormancy')
        elif season.lower() in ['february', 'march', 'april', 'may']:
            seasonal_factors.append('Pre-monsoon heat stress')
            seasonal_factors.append('Increased pest activity in warm weather')
        
        return {
            'common_pests': common_pests,
            'common_diseases': common_diseases,
            'seasonal_factors': seasonal_factors
        }
    
    def initialize_ai_client(self):
        try:
            api_key = os.getenv('GEMINI_API_KEY') or getattr(Config, 'GEMINI_API_KEY', None)
            
            if not api_key:
                error_msg = "Gemini API key not found. Pest detection service unavailable."
                logger.warning(error_msg)
                self.gemini_model = None
                self.client_error = error_msg
                return
            
            genai.configure(api_key=api_key)
            self.gemini_model = genai.GenerativeModel(self.model_name)
            self.client_error = None
            logger.info(f"Pest Detection Service initialized with {self.model_name}")
            
        except Exception as e:
            error_msg = f"Failed to initialize Gemini AI: {str(e)}"
            logger.error(error_msg)
            self.gemini_model = None
            self.client_error = error_msg
    
    def is_available(self) -> bool:
        return self.gemini_model is not None
    
    def get_status(self) -> Dict[str, Any]:
        return {
            'available': self.is_available(),
            'model': self.model_name if self.is_available() else None,
            'error': self.client_error
        }

    def analyze_image(self, image_path: str, crop_type: str, 
                     additional_context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        
        if not image_path or not isinstance(image_path, str) or not image_path.strip():
            logger.error("Invalid image_path")
            return {'success': False, 'error': 'Invalid image path', 'error_type': 'invalid_input'}
        
        if not crop_type or not isinstance(crop_type, str) or len(crop_type.strip()) < 2:
            logger.error("Invalid crop_type")
            return {'success': False, 'error': 'Invalid crop type', 'error_type': 'invalid_input'}
        
        if not self.is_available():
            return {'success': False, 'error': self.client_error or 'AI service unavailable', 'error_type': 'service_unavailable'}
        
        try:
            if not os.path.exists(image_path):
                logger.error(f"Image not found: {image_path}")
                return {'success': False, 'error': f'Image not found: {image_path}', 'error_type': 'file_not_found'}
            
            cache_key = self._generate_cache_key(image_path, crop_type, additional_context)
            cached_result = self._get_cached_analysis(cache_key)
            if cached_result:
                logger.info("Returning cached analysis result")
                return cached_result
            
            try:
                image = Image.open(image_path)
                image.verify()
                image = Image.open(image_path)
            except Exception as img_error:
                logger.error(f"Image validation failed: {str(img_error)}")
                return {'success': False, 'error': 'Invalid image file', 'error_type': 'invalid_image'}
            
            image_quality = self._assess_image_quality(image)
            if image_quality['score'] < 30:
                logger.warning(f"Low image quality detected: {image_quality['issues']}")
            
            processed_image = self._preprocess_image(image)
            
            context = additional_context or {}
            location = context.get('location', 'Not specified')
            plant_stage = context.get('plant_stage', 'Not specified')
            season = context.get('season', datetime.now().strftime('%B'))
            urgency = context.get('urgency', 'medium')
            
            common_issues = self._get_common_issues(crop_type, season, location)
            
            common_pests_str = ', '.join(common_issues['common_pests'][:5]) if common_issues['common_pests'] else 'various pests'
            common_diseases_str = ', '.join(common_issues['common_diseases'][:5]) if common_issues['common_diseases'] else 'various diseases'
            
            prompt = f"""
You are an expert agricultural pathologist specializing in {crop_type} crops. Analyze this plant image for pests, diseases, or deficiencies.

CONTEXT:
- Location: {location}
- Plant Stage: {plant_stage}
- Season: {season}
- Urgency: {urgency}
- Common pests in this region: {common_pests_str}
- Common diseases: {common_diseases_str}

ANALYSIS INSTRUCTIONS:
1. Examine leaf color, texture, spots, holes, wilting
2. Check for visible pests, eggs, or pest damage patterns
3. Identify disease symptoms: discoloration, lesions, mold, rot
4. Assess nutrient deficiencies: yellowing, stunting, necrosis
5. Consider environmental stress: drought, waterlogging, heat damage

Provide detailed analysis in JSON format:

{{
    "identified_issue": "Name of pest/disease/problem",
    "issue_type": "pest|disease|deficiency|environmental|unknown",
    "confidence_score": 0-100,
    "severity_level": "low|medium|high|critical",
    "description": "Detailed description",
    "symptoms_observed": ["symptom1", "symptom2"],
    "affected_parts": ["leaves", "stems"],
    "likely_causes": ["cause1"],
    "risk_assessment": "Risk assessment"
}}
"""
            
            logger.info(f"Analyzing image for {crop_type}")
            response = self.gemini_model.generate_content(
                [prompt, image],
                generation_config=genai.types.GenerationConfig(temperature=0.3, max_output_tokens=1500)
            )
            
            if not response or not response.text:
                return {'success': False, 'error': 'Empty AI response', 'error_type': 'empty_response'}
            
            response_text = response.text.strip()
            analysis_data = self._parse_ai_response(response_text)
            
            if not analysis_data:
                return {'success': False, 'error': 'Failed to parse response', 'error_type': 'parse_error', 'raw_response': response_text}
            
            confidence_score = float(analysis_data.get('confidence_score', 0))
            
            if image_quality['score'] < 50:
                confidence_score = confidence_score * 0.8
                logger.info(f"Confidence adjusted for low image quality: {confidence_score}")
            
            result = {
                'success': True,
                'analysis_mode': 'image',
                'identified_issue': analysis_data.get('identified_issue', 'Unknown issue'),
                'issue_type': analysis_data.get('issue_type', 'unknown'),
                'confidence_score': round(confidence_score, 2),
                'severity_level': analysis_data.get('severity_level', 'medium'),
                'description': analysis_data.get('description', ''),
                'symptoms_observed': analysis_data.get('symptoms_observed', []),
                'affected_parts': analysis_data.get('affected_parts', []),
                'likely_causes': analysis_data.get('likely_causes', []),
                'risk_assessment': analysis_data.get('risk_assessment', ''),
                'crop_type': crop_type,
                'location': location,
                'plant_stage': plant_stage,
                'image_quality': image_quality,
                'common_issues': common_issues,
                'ai_model': self.model_name,
                'analysis_timestamp': datetime.utcnow().isoformat()
            }
            
            result = self._validate_and_adjust_confidence(result, 'image')
            
            if cache_key:
                self._cache_analysis(cache_key, result)
            
            logger.info(f"Analysis complete: {result['identified_issue']} ({result['confidence_score']}%)")
            return result
            
        except Exception as e:
            logger.error(f"Image analysis error: {str(e)}", exc_info=True)
            return {'success': False, 'error': f'Analysis failed: {str(e)}', 'error_type': 'analysis_error'}
    
    def _parse_ai_response(self, response_text: str) -> Optional[Dict[str, Any]]:
        if not response_text or not isinstance(response_text, str) or not response_text.strip():
            logger.error("Invalid response_text")
            return None
        
        try:
            original_text = response_text
            
            if '```json' in response_text:
                start = response_text.find('```json') + 7
                end = response_text.find('```', start)
                response_text = response_text[start:end].strip() if end != -1 else response_text[start:].strip()
            elif '```' in response_text:
                start = response_text.find('```') + 3
                end = response_text.find('```', start)
                response_text = response_text[start:end].strip() if end != -1 else response_text[start:].strip()
            
            if not response_text.strip():
                return self._fallback_parse(original_text)
            
            try:
                data = json.loads(response_text)
                if not isinstance(data, dict) or not data:
                    return self._fallback_parse(original_text)
                return data
                
            except json.JSONDecodeError:
                fixed_text = self._attempt_json_fix(response_text)
                if fixed_text != response_text:
                    try:
                        data = json.loads(fixed_text)
                        if isinstance(data, dict) and data:
                            return data
                    except json.JSONDecodeError:
                        pass
                
                return self._fallback_parse(original_text)
            
        except Exception as e:
            logger.error(f"Parse error: {str(e)}", exc_info=True)
            try:
                return self._fallback_parse(response_text)
            except:
                return None
    
    def _attempt_json_fix(self, json_text: str) -> str:
        try:
            fixed = json_text.strip()
            
            if '{' in fixed:
                first_brace = fixed.find('{')
                if first_brace > 0:
                    fixed = fixed[first_brace:]
            
            if '}' in fixed:
                last_brace = fixed.rfind('}')
                if last_brace < len(fixed) - 1:
                    fixed = fixed[:last_brace + 1]
            
            if "'" in fixed and '"' not in fixed:
                fixed = fixed.replace("'", '"')
            
            return fixed
        except:
            return json_text
    
    def _fallback_parse(self, text: str) -> Optional[Dict[str, Any]]:
        try:
            if not text or not isinstance(text, str) or len(text.strip()) < 10:
                return None
            
            result = {
                'identified_issue': 'Analysis completed',
                'issue_type': 'unknown',
                'confidence_score': 50,
                'severity_level': 'medium',
                'description': '',
                'symptoms_observed': [],
                'affected_parts': [],
                'likely_causes': [],
                'risk_assessment': 'Unable to parse detailed analysis'
            }
            
            issue_patterns = [
                r'identified[_\s]issue[:\s]+([^\n,]+)',
                r'disease[:\s]+([^\n,]+)',
                r'pest[:\s]+([^\n,]+)',
                r'problem[:\s]+([^\n,]+)'
            ]
            
            for pattern in issue_patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    issue = re.sub(r'["\']', '', match.group(1).strip()).split('.')[0]
                    if 5 < len(issue) < 200:
                        result['identified_issue'] = issue
                        break
            
            confidence_patterns = [r'confidence[_\s]score[:\s]+(\d+)', r'confidence[:\s]+(\d+)', r'(\d+)%?\s+confidence']
            for pattern in confidence_patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    try:
                        confidence = int(match.group(1))
                        if 0 <= confidence <= 100:
                            result['confidence_score'] = confidence
                            break
                    except:
                        continue
            
            severity_patterns = [r'severity[_\s]level[:\s]+(low|medium|high|critical)', r'severity[:\s]+(low|medium|high|critical)']
            for pattern in severity_patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    result['severity_level'] = match.group(1).lower()
                    break
            
            type_patterns = [r'issue[_\s]type[:\s]+(pest|disease|deficiency|environmental|unknown)', r'type[:\s]+(pest|disease|deficiency|environmental|unknown)']
            for pattern in type_patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    result['issue_type'] = match.group(1).lower()
                    break
            
            desc_patterns = [r'description[:\s]+([^\n]+(?:\n(?!\w+:)[^\n]+)*)']
            for pattern in desc_patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    description = re.sub(r'\s+', ' ', match.group(1).strip())
                    if len(description) > 10:
                        result['description'] = description[:500]
                        break
            
            if not result['description']:
                paragraphs = [p.strip() for p in text.split('\n\n') if len(p.strip()) > 50]
                if paragraphs:
                    result['description'] = paragraphs[0][:500]
            
            symptoms_match = re.search(r'symptoms[_\s]observed[:\s]+\[(.*?)\]', text, re.IGNORECASE | re.DOTALL)
            if symptoms_match:
                symptoms = [s.strip(' "\'') for s in re.split(r'[,\n]', symptoms_match.group(1)) if s.strip()]
                result['symptoms_observed'] = symptoms[:10]
            
            parts_match = re.search(r'affected[_\s]parts[:\s]+\[(.*?)\]', text, re.IGNORECASE | re.DOTALL)
            if parts_match:
                parts = [p.strip(' "\'') for p in re.split(r'[,\n]', parts_match.group(1)) if p.strip()]
                result['affected_parts'] = parts[:10]
            
            return result
            
        except Exception as e:
            logger.error(f"Fallback parse failed: {str(e)}")
            return None

    def analyze_symptoms(self, crop_type: str, symptoms: str,
                        context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        
        if not crop_type or not isinstance(crop_type, str) or len(crop_type.strip()) < 2:
            return {'success': False, 'error': 'Invalid crop type', 'error_type': 'invalid_input'}
        
        if not symptoms or not isinstance(symptoms, str):
            return {'success': False, 'error': 'Symptom description required', 'error_type': 'invalid_input'}
        
        if not self.is_available():
            return {'success': False, 'error': self.client_error or 'AI service unavailable', 'error_type': 'service_unavailable'}
        
        try:
            if len(symptoms.strip()) < 10:
                return {'success': False, 'error': 'Symptom description too short', 'error_type': 'insufficient_data'}
            
            ctx = context or {}
            location = ctx.get('location', 'Not specified')
            plant_stage = ctx.get('plant_stage', 'Not specified')
            season = ctx.get('season', datetime.now().strftime('%B'))
            urgency = ctx.get('urgency', 'medium')
            
            common_issues = self._get_common_issues(crop_type, season, location)
            common_pests_str = ', '.join(common_issues['common_pests'][:5]) if common_issues['common_pests'] else 'various pests'
            common_diseases_str = ', '.join(common_issues['common_diseases'][:5]) if common_issues['common_diseases'] else 'various diseases'
            
            symptom_keywords = self._extract_symptom_keywords(symptoms)
            
            prompt = f"""
You are an expert agricultural pathologist specializing in {crop_type} crops. Analyze the following symptoms for differential diagnosis.

CONTEXT:
- Location: {location}
- Plant Stage: {plant_stage}
- Season: {season}
- Urgency: {urgency}
- Common pests in region: {common_pests_str}
- Common diseases: {common_diseases_str}

FARMER'S SYMPTOMS:
"{symptoms}"

KEY SYMPTOMS DETECTED: {', '.join(symptom_keywords)}

DIAGNOSTIC APPROACH:
1. Match symptoms to known pest/disease patterns
2. Consider regional prevalence and seasonal timing
3. Account for plant growth stage vulnerabilities
4. Provide differential diagnoses ranked by probability
5. Include distinguishing features for each diagnosis

Provide top 3 diagnoses in JSON format:
{{
    "primary_diagnosis": {{
        "identified_issue": "Most likely issue",
        "issue_type": "pest|disease|deficiency|environmental|unknown",
        "confidence_score": 0-100,
        "severity_level": "low|medium|high|critical",
        "description": "Explanation",
        "matching_symptoms": ["symptom1"],
        "reasoning": "Why this diagnosis"
    }},
    "alternative_diagnoses": [
        {{"identified_issue": "Second issue", "issue_type": "pest|disease", "confidence_score": 0-100, "severity_level": "low|medium|high|critical", "description": "Brief explanation", "key_difference": "Distinguishing factor"}}
    ],
    "additional_questions": ["Clarifying question"],
    "regional_context": "Regional info",
    "seasonal_factors": "Seasonal factors"
}}
"""
            
            logger.info(f"Analyzing symptoms for {crop_type}")
            response = self.gemini_model.generate_content(
                prompt,
                generation_config=genai.types.GenerationConfig(temperature=0.4, max_output_tokens=2000)
            )
            
            if not response or not response.text:
                return {'success': False, 'error': 'Empty AI response', 'error_type': 'empty_response'}
            
            response_text = response.text.strip()
            analysis_data = self._parse_ai_response(response_text)
            
            if not analysis_data:
                return {'success': False, 'error': 'Failed to parse response', 'error_type': 'parse_error', 'raw_response': response_text}
            
            primary = analysis_data.get('primary_diagnosis', {})
            alternatives = analysis_data.get('alternative_diagnoses', [])
            
            confidence_score = float(primary.get('confidence_score', 0))
            
            if len(symptoms.strip()) < 50:
                confidence_score = confidence_score * 0.9
                logger.info(f"Confidence adjusted for brief symptoms: {confidence_score}")
            
            result = {
                'success': True,
                'analysis_mode': 'symptoms',
                'identified_issue': primary.get('identified_issue', 'Unknown issue'),
                'issue_type': primary.get('issue_type', 'unknown'),
                'confidence_score': round(confidence_score, 2),
                'severity_level': primary.get('severity_level', 'medium'),
                'description': primary.get('description', ''),
                'matching_symptoms': primary.get('matching_symptoms', []),
                'reasoning': primary.get('reasoning', ''),
                'alternative_diagnoses': alternatives,
                'additional_questions': analysis_data.get('additional_questions', []),
                'regional_context': analysis_data.get('regional_context', ''),
                'seasonal_factors': analysis_data.get('seasonal_factors', ''),
                'symptom_keywords': symptom_keywords,
                'common_issues': common_issues,
                'crop_type': crop_type,
                'location': location,
                'plant_stage': plant_stage,
                'ai_model': self.model_name,
                'analysis_timestamp': datetime.utcnow().isoformat()
            }
            
            result = self._validate_and_adjust_confidence(result, 'symptoms')
            
            logger.info(f"Symptom analysis complete: {result['identified_issue']} ({result['confidence_score']}%)")
            return result
            
        except Exception as e:
            logger.error(f"Symptom analysis error: {str(e)}", exc_info=True)
            return {'success': False, 'error': f'Analysis failed: {str(e)}', 'error_type': 'analysis_error'}

    def combined_analysis(self, image_path: str, crop_type: str,
                         symptoms: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        
        if not image_path or not isinstance(image_path, str) or not image_path.strip():
            return {'success': False, 'error': 'Invalid image path', 'error_type': 'invalid_input'}
        
        if not crop_type or not isinstance(crop_type, str) or len(crop_type.strip()) < 2:
            return {'success': False, 'error': 'Invalid crop type', 'error_type': 'invalid_input'}
        
        if not symptoms or not isinstance(symptoms, str) or len(symptoms.strip()) < 10:
            return {'success': False, 'error': 'Invalid symptom description', 'error_type': 'invalid_input'}
        
        if not os.path.exists(image_path):
            return {'success': False, 'error': f'Image not found: {image_path}', 'error_type': 'file_not_found'}
        
        if not self.is_available():
            return {'success': False, 'error': self.client_error or 'AI service unavailable', 'error_type': 'service_unavailable'}
        
        try:
            image_result = self.analyze_image(image_path, crop_type, context)
            
            if not image_result.get('success'):
                logger.warning("Image analysis failed, using symptom-only")
                return self.analyze_symptoms(crop_type, symptoms, context)
            
            symptom_result = self.analyze_symptoms(crop_type, symptoms, context)
            
            if not symptom_result.get('success'):
                logger.warning("Symptom analysis failed, using image-only")
                image_result['analysis_mode'] = 'image_only'
                return image_result
            
            image_issue = image_result.get('identified_issue', '').lower()
            symptom_issue = symptom_result.get('identified_issue', '').lower()
            image_confidence = image_result.get('confidence_score', 0)
            symptom_confidence = symptom_result.get('confidence_score', 0)
            
            issues_match = self._check_diagnosis_similarity(image_issue, symptom_issue)
            
            if issues_match:
                combined_confidence = min(100, (image_confidence * 0.6 + symptom_confidence * 0.4) * 1.15)
                agreement_status = 'strong_agreement'
                logger.info(f"Diagnoses match: {image_issue} ≈ {symptom_issue}")
            else:
                combined_confidence = (image_confidence * 0.6 + symptom_confidence * 0.4) * 0.85
                agreement_status = 'discrepancy_detected'
                logger.warning(f"Diagnosis mismatch: {image_issue} vs {symptom_issue}")
            
            severity_levels = {'low': 1, 'medium': 2, 'high': 3, 'critical': 4}
            image_severity = severity_levels.get(image_result.get('severity_level', 'medium'), 2)
            symptom_severity = severity_levels.get(symptom_result.get('severity_level', 'medium'), 2)
            combined_severity_value = max(image_severity, symptom_severity)
            combined_severity = [k for k, v in severity_levels.items() if v == combined_severity_value][0]
            
            result = {
                'success': True,
                'analysis_mode': 'combined',
                'agreement_status': agreement_status,
                'identified_issue': image_result.get('identified_issue') if image_confidence >= symptom_confidence else symptom_result.get('identified_issue'),
                'issue_type': image_result.get('issue_type'),
                'confidence_score': round(combined_confidence, 2),
                'severity_level': combined_severity,
                'description': self._merge_descriptions(image_result.get('description', ''), symptom_result.get('description', '')),
                'image_analysis': {
                    'identified_issue': image_result.get('identified_issue'),
                    'confidence_score': image_confidence,
                    'severity_level': image_result.get('severity_level'),
                    'symptoms_observed': image_result.get('symptoms_observed', []),
                    'affected_parts': image_result.get('affected_parts', [])
                },
                'symptom_analysis': {
                    'identified_issue': symptom_result.get('identified_issue'),
                    'confidence_score': symptom_confidence,
                    'severity_level': symptom_result.get('severity_level'),
                    'matching_symptoms': symptom_result.get('matching_symptoms', []),
                    'reasoning': symptom_result.get('reasoning', '')
                },
                'alternative_diagnoses': symptom_result.get('alternative_diagnoses', []),
                'discrepancy_notes': self._generate_discrepancy_notes(image_result, symptom_result) if not issues_match else None,
                'crop_type': crop_type,
                'location': context.get('location') if context else 'Not specified',
                'plant_stage': context.get('plant_stage') if context else 'Not specified',
                'regional_context': symptom_result.get('regional_context', ''),
                'seasonal_factors': symptom_result.get('seasonal_factors', ''),
                'ai_model': self.model_name,
                'analysis_timestamp': datetime.utcnow().isoformat()
            }
            
            result = self._validate_and_adjust_confidence(result, 'combined')
            
            logger.info(f"Combined analysis complete: {result['identified_issue']} ({result['confidence_score']}%, {agreement_status})")
            return result
            
        except Exception as e:
            logger.error(f"Combined analysis error: {str(e)}", exc_info=True)
            return {'success': False, 'error': f'Analysis failed: {str(e)}', 'error_type': 'analysis_error'}
    
    def _check_diagnosis_similarity(self, diagnosis1: str, diagnosis2: str) -> bool:
        """Check if two diagnoses refer to the same or similar issue"""
        if not diagnosis1 or not diagnosis2:
            return False
        
        d1 = diagnosis1.lower().strip()
        d2 = diagnosis2.lower().strip()
        
        if d1 == d2 or d1 in d2 or d2 in d1:
            return True
        
        d1_words = set(d1.split())
        d2_words = set(d2.split())
        
        stopwords = {'the', 'a', 'an', 'of', 'in', 'on', 'at', 'to', 'for', 'and', 'or'}
        d1_words = d1_words - stopwords
        d2_words = d2_words - stopwords
        
        common_words = d1_words.intersection(d2_words)
        
        if len(common_words) >= 2:
            return True
        
        pest_disease_synonyms = {
            'blight': ['leaf blight', 'early blight', 'late blight'],
            'rust': ['leaf rust', 'stem rust', 'stripe rust'],
            'wilt': ['bacterial wilt', 'fusarium wilt', 'verticillium wilt'],
            'borer': ['stem borer', 'fruit borer', 'shoot borer'],
            'aphid': ['aphids', 'plant lice'],
            'whitefly': ['whiteflies', 'white fly']
        }
        
        for key, synonyms in pest_disease_synonyms.items():
            if key in d1 and any(syn in d2 for syn in synonyms):
                return True
            if key in d2 and any(syn in d1 for syn in synonyms):
                return True
        
        return False
    
    def _merge_descriptions(self, image_desc: str, symptom_desc: str) -> str:
        merged = []
        if image_desc:
            merged.append(f"Visual: {image_desc}")
        if symptom_desc:
            merged.append(f"Symptom: {symptom_desc}")
        return " | ".join(merged) if merged else "No description available"
    
    def _generate_discrepancy_notes(self, image_result: Dict, symptom_result: Dict) -> str:
        image_issue = image_result.get('identified_issue', 'Unknown')
        symptom_issue = symptom_result.get('identified_issue', 'Unknown')
        return (f"Image suggests '{image_issue}' while symptoms indicate '{symptom_issue}'. "
                f"This may be due to multiple issues, symptom stage, or similar conditions. "
                f"Consult a local expert for confirmation.")
    
    def _extract_symptom_keywords(self, symptoms: str) -> List[str]:
        """Extract key symptom indicators from description"""
        symptom_indicators = [
            'yellow', 'brown', 'black', 'white', 'spots', 'holes', 'wilting',
            'curling', 'drooping', 'stunted', 'discolored', 'mold', 'rot',
            'lesions', 'blight', 'rust', 'powdery', 'sticky', 'webbing',
            'insects', 'larvae', 'eggs', 'chewed', 'damaged', 'dying'
        ]
        
        symptoms_lower = symptoms.lower()
        found_keywords = []
        
        for indicator in symptom_indicators:
            if indicator in symptoms_lower:
                found_keywords.append(indicator)
        
        return found_keywords[:10]
    
    def _validate_and_adjust_confidence(self, analysis_result: Dict[str, Any], 
                                       analysis_mode: str) -> Dict[str, Any]:
        """Validate analysis results and adjust confidence based on multiple factors"""
        if not analysis_result.get('success'):
            return analysis_result
        
        confidence = analysis_result.get('confidence_score', 0)
        identified_issue = analysis_result.get('identified_issue', '').lower()
        crop_type = analysis_result.get('crop_type', '').lower()
        
        if 'unknown' in identified_issue or 'unclear' in identified_issue:
            confidence = min(confidence, 40)
            logger.info("Confidence capped at 40% for unknown issue")
        
        if analysis_mode == 'image':
            image_quality = analysis_result.get('image_quality', {})
            if image_quality.get('score', 100) < 50:
                confidence *= 0.85
                logger.info(f"Confidence reduced due to image quality: {confidence}")
        
        if analysis_mode == 'symptoms':
            symptom_keywords = analysis_result.get('symptom_keywords', [])
            if len(symptom_keywords) < 3:
                confidence *= 0.9
                logger.info(f"Confidence reduced due to limited symptom keywords: {confidence}")
        
        common_issues = analysis_result.get('common_issues', {})
        if common_issues:
            common_pests = [p.lower() for p in common_issues.get('common_pests', [])]
            common_diseases = [d.lower() for d in common_issues.get('common_diseases', [])]
            
            is_common = any(pest in identified_issue for pest in common_pests) or \
                       any(disease in identified_issue for disease in common_diseases)
            
            if is_common:
                confidence = min(100, confidence * 1.1)
                logger.info(f"Confidence boosted for common regional issue: {confidence}")
        
        analysis_result['confidence_score'] = round(confidence, 2)
        analysis_result['confidence_factors'] = {
            'image_quality_impact': analysis_mode == 'image',
            'symptom_detail_impact': analysis_mode == 'symptoms',
            'regional_prevalence_boost': is_common if 'is_common' in locals() else False
        }
        
        return analysis_result
    
    def get_analysis_statistics(self, user_id: int, days: int = 30) -> Dict[str, Any]:
        """Get analysis statistics for a user over specified period"""
        try:
            from models import PestDiseaseAnalysis
            from datetime import timedelta
            
            cutoff_date = datetime.utcnow() - timedelta(days=days)
            
            analyses = PestDiseaseAnalysis.query.filter(
                PestDiseaseAnalysis.user_id == user_id,
                PestDiseaseAnalysis.created_at >= cutoff_date
            ).all()
            
            if not analyses:
                return {
                    'total_analyses': 0,
                    'period_days': days,
                    'message': 'No analyses found in this period'
                }
            
            total = len(analyses)
            successful = sum(1 for a in analyses if a.analysis_status == 'completed')
            
            issue_types = {}
            severity_counts = {}
            crop_counts = {}
            
            for analysis in analyses:
                if analysis.issue_type:
                    issue_types[analysis.issue_type] = issue_types.get(analysis.issue_type, 0) + 1
                
                if analysis.severity_level:
                    severity_counts[analysis.severity_level] = severity_counts.get(analysis.severity_level, 0) + 1
                
                if analysis.crop_type:
                    crop_counts[analysis.crop_type] = crop_counts.get(analysis.crop_type, 0) + 1
            
            avg_confidence = sum(a.confidence_score for a in analyses if a.confidence_score) / total if total > 0 else 0
            
            return {
                'total_analyses': total,
                'successful_analyses': successful,
                'failed_analyses': total - successful,
                'success_rate': round((successful / total) * 100, 2) if total > 0 else 0,
                'average_confidence': round(avg_confidence, 2),
                'issue_type_distribution': issue_types,
                'severity_distribution': severity_counts,
                'crop_distribution': crop_counts,
                'period_days': days,
                'most_common_issue_type': max(issue_types, key=issue_types.get) if issue_types else None,
                'most_affected_crop': max(crop_counts, key=crop_counts.get) if crop_counts else None
            }
            
        except Exception as e:
            logger.error(f"Error getting analysis statistics: {str(e)}")
            return {'error': str(e)}

    def generate_treatment_recommendations(self, identified_issue: str, crop_type: str,
                                          severity: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        
        if not self.is_available():
            return {'success': False, 'error': self.client_error or 'AI service unavailable'}
        
        try:
            ctx = context or {}
            location = ctx.get('location', 'Not specified')
            plant_stage = ctx.get('plant_stage', 'Not specified')
            urgency = ctx.get('urgency', 'medium')
            
            common_issues = self._get_common_issues(crop_type, ctx.get('season', datetime.now().strftime('%B')), location)
            
            prompt = f"""
You are an agricultural consultant specializing in integrated pest management for {crop_type} crops in India.

PROBLEM DETAILS:
- Identified Issue: {identified_issue}
- Crop: {crop_type}
- Severity: {severity}
- Location: {location}
- Plant Stage: {plant_stage}
- Urgency: {urgency}

TREATMENT REQUIREMENTS:
1. Provide BOTH organic and chemical treatment options
2. Include specific product names available in Indian market
3. Specify exact dosages, application methods, and timing
4. Rank by effectiveness, cost, and environmental impact
5. Include preventive measures for long-term management
6. Provide realistic cost estimates in Indian Rupees (₹)
7. Consider farmer safety and environmental sustainability

Provide comprehensive recommendations in JSON format:
{{
    "immediate_actions": ["Action 1", "Action 2"],
    "organic_treatments": [{{"name": "Treatment", "active_ingredient": "Ingredient", "application": "Method", "dosage": "Amount", "timing": "Schedule", "effectiveness": "high|medium|low", "cost_estimate": "₹X-Y/acre", "availability": "Availability", "precautions": "Safety notes"}}],
    "chemical_treatments": [{{"name": "Product", "active_ingredient": "Chemical", "application": "Method", "dosage": "Amount", "timing": "Schedule", "effectiveness": "high|medium|low", "cost_estimate": "₹X-Y/acre", "availability": "Availability", "precautions": "Safety warnings", "pre_harvest_interval": "Days"}}],
    "preventive_measures": ["Prevention 1"],
    "cultural_practices": ["Practice 1"],
    "monitoring_schedule": "Check frequency",
    "expected_recovery_time": "Timeline",
    "regional_notes": "Regional info",
    "government_schemes": ["Subsidy program"],
    "expert_consultation": {{"recommended": true|false, "reason": "Why", "contact": "Contact info"}}
}}
"""
            
            logger.info(f"Generating treatment for {identified_issue}")
            response = self.gemini_model.generate_content(
                prompt,
                generation_config=genai.types.GenerationConfig(temperature=0.5, max_output_tokens=2500)
            )
            
            if not response or not response.text:
                return {'success': False, 'error': 'Empty AI response'}
            
            response_text = response.text.strip()
            recommendations = self._parse_ai_response(response_text)
            
            if not recommendations:
                return {'success': False, 'error': 'Failed to parse recommendations', 'raw_response': response_text}
            
            if 'organic_treatments' in recommendations:
                recommendations['organic_treatments'] = self._rank_treatments(recommendations['organic_treatments'])
            
            if 'chemical_treatments' in recommendations:
                recommendations['chemical_treatments'] = self._rank_treatments(recommendations['chemical_treatments'])
            
            result = {
                'success': True,
                'treatment_recommendations': recommendations,
                'generated_at': datetime.utcnow().isoformat()
            }
            
            logger.info("Treatment recommendations generated")
            return result
            
        except Exception as e:
            logger.error(f"Treatment generation error: {str(e)}", exc_info=True)
            return {'success': False, 'error': f'Failed to generate recommendations: {str(e)}'}
    
    def _rank_treatments(self, treatments: List[Dict]) -> List[Dict]:
        """Rank treatments by effectiveness, cost, and safety"""
        if not treatments:
            return []
        
        effectiveness_weight = {'high': 3, 'medium': 2, 'low': 1}
        
        for treatment in treatments:
            effectiveness = treatment.get('effectiveness', 'medium')
            score = effectiveness_weight.get(effectiveness, 2)
            
            cost_str = treatment.get('cost_estimate', '')
            if '₹' in cost_str:
                try:
                    cost_parts = cost_str.replace('₹', '').replace(',', '').split('-')
                    avg_cost = sum(float(p.split('/')[0]) for p in cost_parts) / len(cost_parts)
                    if avg_cost < 500:
                        score += 0.5
                    elif avg_cost > 2000:
                        score -= 0.3
                except:
                    pass
            
            availability = treatment.get('availability', '').lower()
            if 'widely' in availability or 'common' in availability:
                score += 0.3
            
            treatment['_rank_score'] = score
        
        ranked = sorted(treatments, key=lambda x: x.get('_rank_score', 0), reverse=True)
        
        for treatment in ranked:
            treatment.pop('_rank_score', None)
        
        return ranked

    def adjust_for_urgency(self, analysis_result: Dict[str, Any], urgency: str) -> Dict[str, Any]:
        if not analysis_result.get('success'):
            return analysis_result
        
        urgency = urgency.lower() if urgency else 'medium'
        analysis_result['urgency_level'] = urgency
        
        if urgency in ['high', 'critical']:
            analysis_result['emergency_actions'] = self._get_emergency_actions(
                analysis_result.get('identified_issue', ''),
                analysis_result.get('crop_type', ''),
                urgency
            )
            
            if urgency == 'critical':
                analysis_result['emergency_contacts'] = self._get_emergency_contacts(
                    analysis_result.get('location', '')
                )
        
        if 'treatment_recommendations' in analysis_result:
            recommendations = analysis_result['treatment_recommendations']
            
            if urgency in ['high', 'critical']:
                if 'immediate_actions' in recommendations:
                    immediate = recommendations['immediate_actions']
                    recommendations['immediate_actions'] = [f"⚠️ URGENT: {action}" for action in immediate]
                
                recommendations['urgency_note'] = (
                    f"{urgency.upper()} urgency. Immediate action required. Begin treatment within 24 hours."
                )
            else:
                recommendations['urgency_note'] = (
                    f"{urgency} urgency. Address promptly and focus on prevention."
                )
        
        return analysis_result
    
    def _get_emergency_actions(self, issue: str, crop_type: str, urgency: str) -> List[str]:
        actions = [
            f"Isolate affected {crop_type} plants immediately",
            "Document damage with photos",
            "Contact local agricultural extension officer within 24 hours"
        ]
        
        if urgency == 'critical':
            actions.insert(0, "⚠️ CRITICAL: Stop irrigation and fertilization until diagnosis confirmed")
            actions.append("Consider emergency crop protection measures")
            actions.append("Prepare for potential crop loss and insurance claim")
        
        return actions
    
    def _get_emergency_contacts(self, location: str) -> Dict[str, Any]:
        return {
            'krishi_vigyan_kendra': {
                'name': 'Krishi Vigyan Kendra (KVK)',
                'phone': '1800-180-1551',
                'note': f'Search for KVK nearest to {location}'
            },
            'kisan_call_center': {
                'name': 'Kisan Call Center',
                'phone': '1800-180-1551',
                'description': '24/7 toll-free helpline',
                'languages': '22 languages'
            },
            'online_resources': {
                'websites': ['https://farmer.gov.in', 'https://mkisan.gov.in']
            }
        }

    def save_analysis(self, user_id: int, analysis_data: Dict[str, Any]) -> Optional[int]:
        if not user_id or not isinstance(user_id, int):
            logger.error(f"Invalid user_id: {user_id}")
            return None
        
        if not analysis_data or not isinstance(analysis_data, dict):
            logger.error(f"Invalid analysis_data: {type(analysis_data)}")
            return None
        
        try:
            from extensions import db
            from models import PestDiseaseAnalysis
            
            analysis_mode = analysis_data.get('analysis_mode', 'unknown')
            
            treatment_json = None
            try:
                treatment_recommendations = analysis_data.get('treatment_recommendations', {})
                if treatment_recommendations:
                    if isinstance(treatment_recommendations, dict):
                        treatment_json = json.dumps(treatment_recommendations)
                    elif isinstance(treatment_recommendations, str):
                        json.loads(treatment_recommendations)
                        treatment_json = treatment_recommendations
            except Exception as e:
                logger.error(f"Failed to serialize treatment_recommendations: {str(e)}")
            
            preventive_json = None
            try:
                preventive_measures = []
                if 'treatment_recommendations' in analysis_data:
                    treatment_rec = analysis_data['treatment_recommendations']
                    if isinstance(treatment_rec, dict):
                        preventive_measures = treatment_rec.get('preventive_measures', [])
                elif 'preventive_measures' in analysis_data:
                    preventive_measures = analysis_data['preventive_measures']
                
                if preventive_measures:
                    if isinstance(preventive_measures, list):
                        preventive_json = json.dumps(preventive_measures)
                    elif isinstance(preventive_measures, str):
                        json.loads(preventive_measures)
                        preventive_json = preventive_measures
            except Exception as e:
                logger.error(f"Failed to serialize preventive_measures: {str(e)}")
            
            additional_json = None
            try:
                additional_diagnoses = analysis_data.get('alternative_diagnoses', [])
                if additional_diagnoses:
                    if isinstance(additional_diagnoses, list):
                        additional_json = json.dumps(additional_diagnoses)
                    elif isinstance(additional_diagnoses, str):
                        json.loads(additional_diagnoses)
                        additional_json = additional_diagnoses
            except Exception as e:
                logger.error(f"Failed to serialize additional_diagnoses: {str(e)}")
            
            status = 'completed' if analysis_data.get('success') else 'failed'
            error_message = None if analysis_data.get('success') else analysis_data.get('error', 'Unknown error')
            
            try:
                analysis_record = PestDiseaseAnalysis(
                    user_id=user_id,
                    crop_id=analysis_data.get('crop_id'),
                    crop_type=analysis_data.get('crop_type', 'Unknown'),
                    symptoms_description=analysis_data.get('symptoms_description'),
                    plant_stage=analysis_data.get('plant_stage'),
                    urgency_level=analysis_data.get('urgency_level'),
                    location=analysis_data.get('location'),
                    image_path=analysis_data.get('image_path'),
                    identified_issue=analysis_data.get('identified_issue'),
                    issue_type=analysis_data.get('issue_type'),
                    confidence_score=analysis_data.get('confidence_score'),
                    severity_level=analysis_data.get('severity_level'),
                    treatment_recommendations=treatment_json,
                    preventive_measures=preventive_json,
                    additional_diagnoses=additional_json,
                    analysis_mode=analysis_mode,
                    ai_model_used=analysis_data.get('ai_model', self.model_name),
                    analysis_status=status,
                    error_message=error_message
                )
            except Exception as e:
                logger.error(f"Failed to create record: {str(e)}", exc_info=True)
                return None
            
            try:
                db.session.add(analysis_record)
                db.session.commit()
                logger.info(f"Analysis saved: ID {analysis_record.id}, user {user_id}")
                return analysis_record.id
            except Exception as db_error:
                logger.error(f"DB commit failed: {str(db_error)}", exc_info=True)
                try:
                    db.session.rollback()
                except:
                    pass
                return None
            
        except ImportError as e:
            logger.error(f"Import failed: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Save analysis error: {str(e)}", exc_info=True)
            try:
                from extensions import db
                db.session.rollback()
            except:
                pass
            return None
    
    def get_analysis_by_id(self, analysis_id: int):
        try:
            from models import PestDiseaseAnalysis
            return PestDiseaseAnalysis.query.get(analysis_id)
        except Exception as e:
            logger.error(f"Error retrieving analysis {analysis_id}: {str(e)}")
            return None
    
    def get_user_analyses(self, user_id: int, limit: int = 20, offset: int = 0):
        try:
            from models import PestDiseaseAnalysis
            return PestDiseaseAnalysis.query.filter_by(user_id=user_id)\
                .order_by(PestDiseaseAnalysis.created_at.desc())\
                .limit(limit)\
                .offset(offset)\
                .all()
        except Exception as e:
            logger.error(f"Error retrieving user analyses: {str(e)}")
            return []

    def analyze_with_retry(self, analysis_function, *args, max_retries: int = 2, **kwargs) -> Dict[str, Any]:
        last_error = None
        
        for attempt in range(max_retries + 1):
            try:
                result = analysis_function(*args, **kwargs)
                
                if result.get('success'):
                    if attempt > 0:
                        logger.info(f"Succeeded on attempt {attempt + 1}")
                    return result
                
                error_type = result.get('error_type', '')
                if error_type in ['rate_limit', 'insufficient_data', 'invalid_image']:
                    return result
                
                last_error = result.get('error', 'Unknown error')
                
            except TimeoutError as e:
                last_error = f"Timeout: {str(e)}"
                logger.warning(f"Timeout on attempt {attempt + 1}/{max_retries + 1}")
                
                if attempt < max_retries:
                    wait_time = 2 ** attempt
                    logger.info(f"Retrying in {wait_time}s...")
                    time.sleep(wait_time)
                    continue
                
            except Exception as e:
                last_error = f"Error: {str(e)}"
                logger.error(f"Error on attempt {attempt + 1}/{max_retries + 1}: {last_error}")
                
                if attempt < max_retries:
                    wait_time = 2 ** attempt
                    time.sleep(wait_time)
                    continue
        
        logger.error(f"Failed after {max_retries + 1} attempts: {last_error}")
        return {
            'success': False,
            'error': f'Failed after {max_retries + 1} attempts. Last error: {last_error}',
            'error_type': 'max_retries_exceeded'
        }
    
    def handle_analysis_error(self, error: Exception, context: Dict[str, Any]) -> Dict[str, Any]:
        error_str = str(error).lower()
        
        if 'rate limit' in error_str or 'quota' in error_str:
            return {'success': False, 'error': 'Analysis limit reached. Try again in a few minutes.', 'error_type': 'rate_limit', 'retry_after': 300}
        
        if 'timeout' in error_str or 'timed out' in error_str:
            return {'success': False, 'error': 'Analysis timeout. Please try again.', 'error_type': 'timeout', 'suggestion': 'Try a smaller image or simpler description.'}
        
        if 'image' in error_str and any(word in error_str for word in ['invalid', 'corrupt', 'format']):
            return {'success': False, 'error': 'Invalid image format. Use JPEG, PNG, or WebP.', 'error_type': 'image_quality', 'suggestion': 'Capture in good lighting and ensure focus.'}
        
        if 'unavailable' in error_str or 'connection' in error_str:
            return {'success': False, 'error': 'AI service temporarily unavailable.', 'error_type': 'service_unavailable', 'suggestion': 'Check internet connection.'}
        
        if 'insufficient' in error_str or 'not enough' in error_str:
            return {
                'success': False,
                'error': 'Insufficient information for diagnosis.',
                'error_type': 'insufficient_data',
                'suggestion': 'Provide more details or consult local expert.',
                'expert_consultation': {'recommended': True, 'reason': 'More information needed', 'contact': 'Kisan Call Center: 1800-180-1551'}
            }
        
        logger.error(f"Unhandled error: {error}", exc_info=True)
        return {'success': False, 'error': 'Unexpected error. Please try again or contact support.', 'error_type': 'unknown_error', 'suggestion': 'Contact FarmLink support if problem persists.'}
    
    def validate_analysis_input(self, image_path: Optional[str] = None, 
                               symptoms: Optional[str] = None,
                               crop_type: Optional[str] = None) -> Dict[str, Any]:
        errors = []
        
        if not image_path and not symptoms:
            errors.append('Provide either image or symptom description.')
        
        if not crop_type or len(crop_type.strip()) < 2:
            errors.append('Specify valid crop type.')
        
        if image_path:
            if not os.path.exists(image_path):
                errors.append(f'Image not found: {image_path}')
            else:
                file_size = os.path.getsize(image_path)
                max_size = 10 * 1024 * 1024
                if file_size > max_size:
                    errors.append(f'Image too large ({file_size / 1024 / 1024:.1f}MB). Max 10MB.')
                
                valid_extensions = ['.jpg', '.jpeg', '.png', '.webp']
                file_ext = os.path.splitext(image_path)[1].lower()
                if file_ext not in valid_extensions:
                    errors.append('Invalid format. Use JPEG, PNG, or WebP.')
        
        if symptoms:
            if len(symptoms.strip()) < 10:
                errors.append('Symptom description too short (min 10 chars).')
            elif len(symptoms.strip()) > 2000:
                errors.append('Symptom description too long (max 2000 chars).')
        
        if errors:
            return {'success': False, 'errors': errors, 'error': ' '.join(errors)}
        
        return {'success': True}


pest_detection_service = PestDiseaseDetectionService()
