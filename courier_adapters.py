"""
Courier API Adapters Module
Provides abstract base class and concrete implementations for courier API integrations
"""
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
import os
import time
import logging
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import json

from extensions import db
from models import CourierAPILog

logger = logging.getLogger(__name__)


class CircuitBreakerOpenError(Exception):
    """Exception raised when circuit breaker is open"""
    pass


class CircuitBreaker:
    """Circuit breaker for API calls to prevent cascading failures"""
    
    def __init__(self, failure_threshold: int = 5, timeout: int = 300):
        """
        Initialize circuit breaker
        
        Args:
            failure_threshold: Number of failures before opening circuit
            timeout: Seconds to wait before attempting half-open state
        """
        self.failure_count = 0
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.last_failure_time = None
        self.state = 'closed'  # closed, open, half_open
        
        logger.info(f"Circuit breaker initialized with threshold={failure_threshold}, timeout={timeout}s")
    
    def call(self, func, *args, **kwargs):
        """
        Execute function with circuit breaker protection
        
        Args:
            func: Function to execute
            *args: Positional arguments for function
            **kwargs: Keyword arguments for function
            
        Returns:
            Function result
            
        Raises:
            CircuitBreakerOpenError: If circuit is open
        """
        if self.state == 'open':
            if time.time() - self.last_failure_time > self.timeout:
                logger.info("Circuit breaker transitioning to half_open state")
                self.state = 'half_open'
            else:
                time_remaining = int(self.timeout - (time.time() - self.last_failure_time))
                error_msg = f"Circuit breaker is open. Retry in {time_remaining} seconds"
                logger.warning(error_msg)
                raise CircuitBreakerOpenError(error_msg)
        
        try:
            result = func(*args, **kwargs)
            self.on_success()
            return result
        except Exception as e:
            self.on_failure()
            raise e
    
    def on_success(self):
        """Reset circuit breaker on successful call"""
        if self.state == 'half_open':
            logger.info("Circuit breaker transitioning to closed state after successful call")
        self.failure_count = 0
        self.state = 'closed'
    
    def on_failure(self):
        """Increment failure count and open circuit if threshold reached"""
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        if self.failure_count >= self.failure_threshold:
            logger.error(f"Circuit breaker opening after {self.failure_count} failures")
            self.state = 'open'
        else:
            logger.warning(f"Circuit breaker failure count: {self.failure_count}/{self.failure_threshold}")


class CourierAPIAdapter(ABC):
    """Abstract base class for courier API adapters"""
    
    def __init__(self):
        """Initialize adapter with common configuration"""
        self.circuit_breaker = CircuitBreaker(failure_threshold=5, timeout=300)
        self.session = self._create_session()
        self.base_url = None
        self.authenticated = False
        
    def _create_session(self) -> requests.Session:
        """
        Create requests session with retry logic
        
        Returns:
            Configured requests.Session
        """
        session = requests.Session()
        
        # Configure retry strategy with exponential backoff (1s, 2s, 4s)
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,  # Will create delays of 1s, 2s, 4s
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "POST", "PUT", "DELETE", "OPTIONS", "TRACE"]
        )
        
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        
        return session
    
    def _log_api_call(self, order_id: Optional[int], endpoint: str, method: str,
                     request_payload: Optional[Dict], response_status: Optional[int],
                     response_payload: Optional[Dict], error_message: Optional[str],
                     execution_time_ms: int):
        """
        Log API call to CourierAPILog table
        
        Args:
            order_id: Order ID (if applicable)
            endpoint: API endpoint
            method: HTTP method
            request_payload: Request data
            response_status: HTTP response status code
            response_payload: Response data
            error_message: Error message (if any)
            execution_time_ms: Execution time in milliseconds
        """
        try:
            log_entry = CourierAPILog(
                order_id=order_id,
                courier_name=self.__class__.__name__.replace('Adapter', '').lower(),
                api_endpoint=endpoint,
                http_method=method,
                request_payload=json.dumps(request_payload) if request_payload else None,
                response_status_code=response_status,
                response_payload=json.dumps(response_payload) if response_payload else None,
                error_message=error_message,
                execution_time_ms=execution_time_ms
            )
            db.session.add(log_entry)
            db.session.commit()
        except Exception as e:
            logger.error(f"Failed to log API call: {str(e)}")
            db.session.rollback()
    
    def _make_request(self, method: str, endpoint: str, order_id: Optional[int] = None,
                     **kwargs) -> Dict[str, Any]:
        """
        Make HTTP request with error handling and logging
        
        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint
            order_id: Order ID for logging
            **kwargs: Additional arguments for requests
            
        Returns:
            Response data dictionary
            
        Raises:
            RuntimeError: If request fails
        """
        start_time = time.time()
        request_payload = kwargs.get('json') or kwargs.get('data')
        response_status = None
        response_payload = None
        error_message = None
        
        try:
            # Make request through circuit breaker
            def make_call():
                return self.session.request(method, endpoint, timeout=30, **kwargs)
            
            response = self.circuit_breaker.call(make_call)
            response_status = response.status_code
            
            # Calculate execution time
            execution_time_ms = int((time.time() - start_time) * 1000)
            
            # Parse response
            try:
                response_payload = response.json()
            except ValueError:
                response_payload = {'text': response.text}
            
            # Check for HTTP errors
            response.raise_for_status()
            
            # Log successful request
            self._log_api_call(
                order_id=order_id,
                endpoint=endpoint,
                method=method,
                request_payload=request_payload,
                response_status=response_status,
                response_payload=response_payload,
                error_message=None,
                execution_time_ms=execution_time_ms
            )
            
            return response_payload
            
        except CircuitBreakerOpenError as e:
            error_message = str(e)
            logger.error(f"Circuit breaker open for {endpoint}: {error_message}")
            raise RuntimeError(error_message)
            
        except requests.exceptions.Timeout as e:
            execution_time_ms = int((time.time() - start_time) * 1000)
            error_message = f"Request timeout: {str(e)}"
            logger.error(f"Timeout calling {endpoint}: {error_message}")
            
            self._log_api_call(
                order_id=order_id,
                endpoint=endpoint,
                method=method,
                request_payload=request_payload,
                response_status=response_status,
                response_payload=response_payload,
                error_message=error_message,
                execution_time_ms=execution_time_ms
            )
            
            raise RuntimeError(error_message)
            
        except requests.exceptions.RequestException as e:
            execution_time_ms = int((time.time() - start_time) * 1000)
            error_message = f"Request failed: {str(e)}"
            logger.error(f"Error calling {endpoint}: {error_message}")
            
            self._log_api_call(
                order_id=order_id,
                endpoint=endpoint,
                method=method,
                request_payload=request_payload,
                response_status=response_status,
                response_payload=response_payload,
                error_message=error_message,
                execution_time_ms=execution_time_ms
            )
            
            raise RuntimeError(error_message)
            
        except Exception as e:
            execution_time_ms = int((time.time() - start_time) * 1000)
            error_message = f"Unexpected error: {str(e)}"
            logger.error(f"Unexpected error calling {endpoint}: {error_message}", exc_info=True)
            
            self._log_api_call(
                order_id=order_id,
                endpoint=endpoint,
                method=method,
                request_payload=request_payload,
                response_status=response_status,
                response_payload=response_payload,
                error_message=error_message,
                execution_time_ms=execution_time_ms
            )
            
            raise RuntimeError(error_message)
    
    @abstractmethod
    def authenticate(self) -> bool:
        """
        Authenticate with courier API
        
        Returns:
            True if authentication successful
        """
        pass
    
    @abstractmethod
    def create_shipment(self, shipment_data: Dict) -> Dict[str, Any]:
        """
        Create shipment via courier API
        
        Args:
            shipment_data: Shipment information
            
        Returns:
            Dict with success status and shipment details
        """
        pass
    
    @abstractmethod
    def get_tracking_status(self, tracking_id: str) -> Dict[str, Any]:
        """
        Get tracking status from courier API
        
        Args:
            tracking_id: Tracking identifier
            
        Returns:
            Dict with tracking status information
        """
        pass
    
    @abstractmethod
    def cancel_shipment(self, tracking_id: str) -> Dict[str, Any]:
        """
        Cancel shipment via courier API
        
        Args:
            tracking_id: Tracking identifier
            
        Returns:
            Dict with success status
        """
        pass


def get_courier_adapter(courier_name: str) -> Optional[CourierAPIAdapter]:
    """
    Factory function to get courier adapter instance
    
    Args:
        courier_name: Name of courier service
        
    Returns:
        CourierAPIAdapter instance or None
    """
    courier_name_lower = courier_name.lower()
    
    if courier_name_lower == 'shiprocket':
        return ShiprocketAdapter()
    elif courier_name_lower == 'india_post' or courier_name_lower == 'indiapost':
        return IndiaPostAdapter()
    else:
        logger.error(f"Unknown courier name: {courier_name}")
        return None



class ShiprocketAdapter(CourierAPIAdapter):
    """Shiprocket API implementation"""
    
    BASE_URL = "https://apiv2.shiprocket.in/v1/external"
    
    def __init__(self):
        """Initialize Shiprocket adapter"""
        super().__init__()
        self.base_url = self.BASE_URL
        self.email = os.getenv('SHIPROCKET_EMAIL')
        self.password = os.getenv('SHIPROCKET_PASSWORD')
        self.token = None
        self.token_expires = None
        
        if not self.email or not self.password:
            logger.warning("Shiprocket credentials not found in environment variables")
    
    def authenticate(self) -> bool:
        """
        Authenticate with Shiprocket API and get access token
        
        Returns:
            True if authentication successful
        """
        # Check if token is still valid
        if self.token and self.token_expires and datetime.now() < self.token_expires:
            logger.debug("Using existing valid Shiprocket token")
            return True
        
        if not self.email or not self.password:
            logger.error("Shiprocket credentials not configured")
            return False
        
        try:
            endpoint = f"{self.base_url}/auth/login"
            payload = {
                "email": self.email,
                "password": self.password
            }
            
            logger.info("Authenticating with Shiprocket API")
            response = self._make_request('POST', endpoint, json=payload)
            
            if response.get('token'):
                self.token = response['token']
                # Token typically expires in 10 days, set expiry to 9 days to be safe
                self.token_expires = datetime.now() + timedelta(days=9)
                self.authenticated = True
                logger.info("Shiprocket authentication successful")
                return True
            else:
                logger.error("Shiprocket authentication failed: No token in response")
                return False
                
        except Exception as e:
            logger.error(f"Shiprocket authentication error: {str(e)}")
            self.authenticated = False
            return False
    
    def _get_headers(self) -> Dict[str, str]:
        """
        Get headers with authentication token
        
        Returns:
            Headers dictionary
        """
        if not self.token:
            raise RuntimeError("Not authenticated. Call authenticate() first.")
        
        return {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {self.token}'
        }
    
    def create_shipment(self, shipment_data: Dict) -> Dict[str, Any]:
        """
        Create shipment on Shiprocket
        
        Args:
            shipment_data: Dict containing:
                - order_id: FarmLink order ID
                - order_date: Order date
                - pickup_address: Pickup address details
                - delivery_address: Delivery address details
                - buyer_name: Buyer name
                - buyer_phone: Buyer phone
                - buyer_email: Buyer email
                - package_weight: Weight in kg
                - package_length: Length in cm
                - package_width: Width in cm
                - package_height: Height in cm
                - order_items: List of items
                - payment_method: Payment method
                - sub_total: Order subtotal
                
        Returns:
            Dict with success, awb_code, courier_name, tracking_url, courier_order_id
        """
        # Ensure authenticated
        if not self.authenticate():
            return {
                'success': False,
                'error': 'Authentication failed'
            }
        
        try:
            order_id = shipment_data.get('order_id')
            endpoint = f"{self.base_url}/orders/create/adhoc"
            
            # Map FarmLink data to Shiprocket format
            payload = {
                "order_id": f"FARMLINK-{order_id}",
                "order_date": shipment_data.get('order_date', datetime.now().strftime('%Y-%m-%d %H:%M')),
                "pickup_location": shipment_data.get('pickup_location', 'Primary'),
                "billing_customer_name": shipment_data.get('buyer_name'),
                "billing_last_name": "",
                "billing_address": shipment_data.get('delivery_address', {}).get('address', ''),
                "billing_city": shipment_data.get('delivery_address', {}).get('city', ''),
                "billing_pincode": shipment_data.get('delivery_address', {}).get('pincode', ''),
                "billing_state": shipment_data.get('delivery_address', {}).get('state', ''),
                "billing_country": shipment_data.get('delivery_address', {}).get('country', 'India'),
                "billing_email": shipment_data.get('buyer_email', ''),
                "billing_phone": shipment_data.get('buyer_phone', ''),
                "shipping_is_billing": True,
                "order_items": shipment_data.get('order_items', []),
                "payment_method": shipment_data.get('payment_method', 'Prepaid'),
                "sub_total": shipment_data.get('sub_total', 0),
                "length": shipment_data.get('package_length', 10),
                "breadth": shipment_data.get('package_width', 10),
                "height": shipment_data.get('package_height', 10),
                "weight": shipment_data.get('package_weight', 0.5)
            }
            
            logger.info(f"Creating Shiprocket shipment for order {order_id}")
            response = self._make_request(
                'POST',
                endpoint,
                order_id=order_id,
                json=payload,
                headers=self._get_headers()
            )
            
            # Parse response
            if response.get('order_id'):
                shipment_id = response.get('shipment_id')
                return {
                    'success': True,
                    'courier_order_id': str(response.get('order_id')),
                    'shipment_id': str(shipment_id) if shipment_id else None,
                    'awb_code': response.get('awb_code'),
                    'courier_name': 'Shiprocket',
                    'tracking_url': f"https://shiprocket.co/tracking/{response.get('awb_code')}" if response.get('awb_code') else None,
                    'status': response.get('status', 'created')
                }
            else:
                error_msg = response.get('message', 'Unknown error')
                logger.error(f"Shiprocket shipment creation failed: {error_msg}")
                return {
                    'success': False,
                    'error': error_msg
                }
                
        except Exception as e:
            logger.error(f"Error creating Shiprocket shipment: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def get_tracking_status(self, tracking_id: str) -> Dict[str, Any]:
        """
        Get tracking status from Shiprocket
        
        Args:
            tracking_id: Shiprocket order ID or AWB code
            
        Returns:
            Dict with status, tracking_history, estimated_delivery
        """
        # Ensure authenticated
        if not self.authenticate():
            return {
                'success': False,
                'error': 'Authentication failed'
            }
        
        try:
            endpoint = f"{self.base_url}/courier/track/shipment/{tracking_id}"
            
            logger.info(f"Getting Shiprocket tracking status for {tracking_id}")
            response = self._make_request(
                'GET',
                endpoint,
                headers=self._get_headers()
            )
            
            # Parse tracking data
            tracking_data = response.get('tracking_data', {})
            shipment_track = tracking_data.get('shipment_track', [])
            
            # Map Shiprocket status to system status
            current_status = tracking_data.get('shipment_status', '')
            system_status = self._map_status_to_system(current_status)
            
            # Build tracking history
            tracking_history = []
            for track in shipment_track:
                tracking_history.append({
                    'status': track.get('current_status', ''),
                    'location': track.get('location', ''),
                    'timestamp': track.get('date', ''),
                    'description': track.get('activity', '')
                })
            
            return {
                'success': True,
                'status': system_status,
                'courier_status': current_status,
                'tracking_history': tracking_history,
                'estimated_delivery': tracking_data.get('edd'),
                'awb_code': tracking_data.get('awb_code'),
                'courier_name': tracking_data.get('courier_name')
            }
            
        except Exception as e:
            logger.error(f"Error getting Shiprocket tracking status: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def cancel_shipment(self, tracking_id: str) -> Dict[str, Any]:
        """
        Cancel shipment on Shiprocket
        
        Args:
            tracking_id: Shiprocket order ID
            
        Returns:
            Dict with success status
        """
        # Ensure authenticated
        if not self.authenticate():
            return {
                'success': False,
                'error': 'Authentication failed'
            }
        
        try:
            endpoint = f"{self.base_url}/orders/cancel"
            payload = {
                "ids": [tracking_id]
            }
            
            logger.info(f"Cancelling Shiprocket shipment {tracking_id}")
            response = self._make_request(
                'POST',
                endpoint,
                json=payload,
                headers=self._get_headers()
            )
            
            if response.get('message') == 'Order cancelled successfully':
                return {
                    'success': True,
                    'message': 'Shipment cancelled successfully'
                }
            else:
                return {
                    'success': False,
                    'error': response.get('message', 'Cancellation failed')
                }
                
        except Exception as e:
            logger.error(f"Error cancelling Shiprocket shipment: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def _map_status_to_system(self, shiprocket_status: str) -> str:
        """
        Map Shiprocket status codes to system status values
        
        Args:
            shiprocket_status: Shiprocket status string
            
        Returns:
            System status string
        """
        status_mapping = {
            'NEW': 'placed',
            'PICKUP SCHEDULED': 'packed',
            'PICKED UP': 'shipped',
            'IN TRANSIT': 'in_transit',
            'OUT FOR DELIVERY': 'out_for_delivery',
            'DELIVERED': 'delivered',
            'RTO INITIATED': 'failed',
            'RTO DELIVERED': 'returned',
            'CANCELLED': 'cancelled',
            'LOST': 'failed',
            'DAMAGED': 'failed'
        }
        
        return status_mapping.get(shiprocket_status.upper(), 'in_transit')
      



class IndiaPostAdapter(CourierAPIAdapter):
    """India Post API implementation"""
    
    BASE_URL = "https://api.indiapost.gov.in/api/v1"
    
    def __init__(self):
        """Initialize India Post adapter"""
        super().__init__()
        self.base_url = self.BASE_URL
        self.api_key = os.getenv('INDIA_POST_API_KEY')
        self.client_id = os.getenv('INDIA_POST_CLIENT_ID')
        
        if not self.api_key or not self.client_id:
            logger.warning("India Post credentials not found in environment variables")
    
    def authenticate(self) -> bool:
        """
        Authenticate with India Post API
        
        Returns:
            True if authentication successful
        """
        if not self.api_key or not self.client_id:
            logger.error("India Post credentials not configured")
            return False
        
        # India Post uses API key authentication, no separate auth call needed
        self.authenticated = True
        logger.info("India Post authentication configured")
        return True
    
    def _get_headers(self) -> Dict[str, str]:
        """
        Get headers with authentication
        
        Returns:
            Headers dictionary
        """
        if not self.api_key or not self.client_id:
            raise RuntimeError("Not authenticated. API credentials missing.")
        
        return {
            'Content-Type': 'application/json',
            'X-API-Key': self.api_key,
            'X-Client-ID': self.client_id
        }
    
    def create_shipment(self, shipment_data: Dict) -> Dict[str, Any]:
        """
        Create shipment on India Post
        
        Args:
            shipment_data: Dict containing:
                - order_id: FarmLink order ID
                - pickup_address: Pickup address details
                - delivery_address: Delivery address details
                - buyer_name: Buyer name
                - buyer_phone: Buyer phone
                - package_weight: Weight in kg
                - package_length: Length in cm
                - package_width: Width in cm
                - package_height: Height in cm
                - declared_value: Declared value
                
        Returns:
            Dict with success, awb_code, courier_name, tracking_url, consignment_number
        """
        # Ensure authenticated
        if not self.authenticate():
            return {
                'success': False,
                'error': 'Authentication failed'
            }
        
        try:
            order_id = shipment_data.get('order_id')
            endpoint = f"{self.base_url}/booking"
            
            # Map FarmLink data to India Post format
            payload = {
                "reference_number": f"FARMLINK-{order_id}",
                "service_type": "PARCEL",
                "sender": {
                    "name": shipment_data.get('pickup_address', {}).get('name', ''),
                    "address": shipment_data.get('pickup_address', {}).get('address', ''),
                    "city": shipment_data.get('pickup_address', {}).get('city', ''),
                    "state": shipment_data.get('pickup_address', {}).get('state', ''),
                    "pincode": shipment_data.get('pickup_address', {}).get('pincode', ''),
                    "phone": shipment_data.get('pickup_address', {}).get('phone', '')
                },
                "recipient": {
                    "name": shipment_data.get('buyer_name', ''),
                    "address": shipment_data.get('delivery_address', {}).get('address', ''),
                    "city": shipment_data.get('delivery_address', {}).get('city', ''),
                    "state": shipment_data.get('delivery_address', {}).get('state', ''),
                    "pincode": shipment_data.get('delivery_address', {}).get('pincode', ''),
                    "phone": shipment_data.get('buyer_phone', '')
                },
                "package": {
                    "weight": shipment_data.get('package_weight', 0.5),
                    "length": shipment_data.get('package_length', 10),
                    "width": shipment_data.get('package_width', 10),
                    "height": shipment_data.get('package_height', 10),
                    "declared_value": shipment_data.get('declared_value', 0)
                }
            }
            
            logger.info(f"Creating India Post shipment for order {order_id}")
            response = self._make_request(
                'POST',
                endpoint,
                order_id=order_id,
                json=payload,
                headers=self._get_headers()
            )
            
            # Parse response
            if response.get('status') == 'success' or response.get('consignment_number'):
                consignment_number = response.get('consignment_number')
                return {
                    'success': True,
                    'courier_order_id': consignment_number,
                    'awb_code': consignment_number,
                    'courier_name': 'India Post',
                    'tracking_url': f"https://www.indiapost.gov.in/_layouts/15/dop.portal.tracking/trackconsignment.aspx?consignmentno={consignment_number}" if consignment_number else None,
                    'status': 'created'
                }
            else:
                error_msg = response.get('message', 'Unknown error')
                logger.error(f"India Post shipment creation failed: {error_msg}")
                return {
                    'success': False,
                    'error': error_msg
                }
                
        except Exception as e:
            logger.error(f"Error creating India Post shipment: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def get_tracking_status(self, tracking_id: str) -> Dict[str, Any]:
        """
        Get tracking status from India Post
        
        Args:
            tracking_id: India Post consignment number
            
        Returns:
            Dict with status, tracking_history, estimated_delivery
        """
        # Ensure authenticated
        if not self.authenticate():
            return {
                'success': False,
                'error': 'Authentication failed'
            }
        
        try:
            endpoint = f"{self.base_url}/track/{tracking_id}"
            
            logger.info(f"Getting India Post tracking status for {tracking_id}")
            response = self._make_request(
                'GET',
                endpoint,
                headers=self._get_headers()
            )
            
            # Parse tracking data
            tracking_info = response.get('tracking_info', {})
            events = tracking_info.get('events', [])
            
            # Map India Post status to system status
            current_status = tracking_info.get('status', '')
            system_status = self._map_status_to_system(current_status)
            
            # Build tracking history
            tracking_history = []
            for event in events:
                tracking_history.append({
                    'status': event.get('status', ''),
                    'location': event.get('location', ''),
                    'timestamp': event.get('timestamp', ''),
                    'description': event.get('description', '')
                })
            
            return {
                'success': True,
                'status': system_status,
                'courier_status': current_status,
                'tracking_history': tracking_history,
                'estimated_delivery': tracking_info.get('estimated_delivery'),
                'awb_code': tracking_id,
                'courier_name': 'India Post'
            }
            
        except Exception as e:
            logger.error(f"Error getting India Post tracking status: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def cancel_shipment(self, tracking_id: str) -> Dict[str, Any]:
        """
        Cancel shipment on India Post
        
        Note: India Post may not support cancellation via API.
        This method attempts cancellation but may return not supported.
        
        Args:
            tracking_id: India Post consignment number
            
        Returns:
            Dict with success status
        """
        # Ensure authenticated
        if not self.authenticate():
            return {
                'success': False,
                'error': 'Authentication failed'
            }
        
        try:
            endpoint = f"{self.base_url}/cancel/{tracking_id}"
            
            logger.info(f"Attempting to cancel India Post shipment {tracking_id}")
            response = self._make_request(
                'POST',
                endpoint,
                headers=self._get_headers()
            )
            
            if response.get('status') == 'success':
                return {
                    'success': True,
                    'message': 'Shipment cancelled successfully'
                }
            elif response.get('status') == 'not_supported':
                return {
                    'success': False,
                    'error': 'Cancellation not supported by India Post. Please contact India Post directly.'
                }
            else:
                return {
                    'success': False,
                    'error': response.get('message', 'Cancellation failed')
                }
                
        except Exception as e:
            # If endpoint doesn't exist, assume cancellation not supported
            if '404' in str(e) or 'Not Found' in str(e):
                logger.warning("India Post cancellation endpoint not found")
                return {
                    'success': False,
                    'error': 'Cancellation not supported by India Post. Please contact India Post directly.'
                }
            
            logger.error(f"Error cancelling India Post shipment: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def _map_status_to_system(self, indiapost_status: str) -> str:
        """
        Map India Post status codes to system status values
        
        Args:
            indiapost_status: India Post status string
            
        Returns:
            System status string
        """
        status_mapping = {
            'BOOKED': 'placed',
            'ACCEPTED': 'packed',
            'DISPATCHED': 'shipped',
            'IN TRANSIT': 'in_transit',
            'ARRIVED': 'in_transit',
            'OUT FOR DELIVERY': 'out_for_delivery',
            'DELIVERED': 'delivered',
            'RETURNED': 'returned',
            'UNDELIVERED': 'failed',
            'CANCELLED': 'cancelled'
        }
        
        return status_mapping.get(indiapost_status.upper(), 'in_transit')
