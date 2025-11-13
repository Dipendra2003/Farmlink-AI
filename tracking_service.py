"""
Tracking Service Module
Handles shipment tracking operations and courier API integration
"""
from datetime import datetime, date
from typing import Dict, Any, Optional
import random
import string
import logging
from extensions import db
from models import Order, ShipmentStatusHistory, CourierAPILog

logger = logging.getLogger(__name__)


class TrackingService:
    """Main service for shipment tracking operations"""
    
    @staticmethod
    def generate_tracking_number(order_id: int) -> str:
        """
        Generate unique tracking number in format TRK-{YYYYMMDD}-{RANDOM6}
        
        Args:
            order_id: Order ID for reference
            
        Returns:
            Unique tracking number string
            
        Raises:
            ValueError: If unable to generate unique tracking number after max attempts
        """
        max_attempts = 10
        
        for attempt in range(max_attempts):
            # Generate date part
            date_part = datetime.utcnow().strftime('%Y%m%d')
            
            # Generate random 6-character alphanumeric string
            random_part = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
            
            # Combine to create tracking number
            tracking_number = f"TRK-{date_part}-{random_part}"
            
            # Validate uniqueness by checking database
            existing_order = Order.query.filter_by(tracking_number=tracking_number).first()
            
            if not existing_order:
                logger.info(f"Generated unique tracking number {tracking_number} for order {order_id}")
                return tracking_number
            
            logger.warning(f"Tracking number {tracking_number} already exists, retrying... (attempt {attempt + 1}/{max_attempts})")
        
        # If we couldn't generate a unique number after max attempts
        error_msg = f"Failed to generate unique tracking number after {max_attempts} attempts for order {order_id}"
        logger.error(error_msg)
        raise ValueError(error_msg)
    
    @staticmethod
    def get_shipment_status(tracking_number: str, courier_name: str) -> Dict[str, Any]:
        """
        Fetch current shipment status from courier API
        
        Args:
            tracking_number: Tracking number
            courier_name: Courier service name (shiprocket, india_post)
            
        Returns:
            Dict with current status, last_update, estimated_delivery, tracking_history
            
        Raises:
            ValueError: If tracking_number or courier_name is invalid
            RuntimeError: If API call fails
        """
        if not tracking_number:
            raise ValueError("Tracking number is required")
        
        if not courier_name:
            raise ValueError("Courier name is required")
        
        # Find the order with this tracking number
        order = Order.query.filter_by(tracking_number=tracking_number).first()
        
        if not order:
            error_msg = f"No order found with tracking number {tracking_number}"
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        try:
            # Import courier adapter dynamically to avoid circular imports
            from courier_adapters import get_courier_adapter
            
            # Get the appropriate courier adapter
            adapter = get_courier_adapter(courier_name)
            
            if not adapter:
                error_msg = f"No adapter found for courier: {courier_name}"
                logger.error(error_msg)
                raise ValueError(error_msg)
            
            # Authenticate with courier API
            if not adapter.authenticate():
                error_msg = f"Failed to authenticate with {courier_name} API"
                logger.error(error_msg)
                raise RuntimeError(error_msg)
            
            # Fetch tracking status from courier API
            courier_order_id = order.courier_order_id or tracking_number
            status_data = adapter.get_tracking_status(courier_order_id)
            
            # Get tracking history from database
            history = ShipmentStatusHistory.query.filter_by(
                tracking_number=tracking_number
            ).order_by(ShipmentStatusHistory.created_at.desc()).all()
            
            tracking_history = [
                {
                    'status': h.new_status,
                    'description': h.status_description,
                    'location': h.location,
                    'timestamp': h.courier_timestamp or h.created_at,
                    'source': h.updated_by_source
                }
                for h in history
            ]
            
            result = {
                'success': True,
                'tracking_number': tracking_number,
                'courier_name': courier_name,
                'current_status': status_data.get('status', order.shipment_status),
                'last_update': status_data.get('last_update', order.last_api_sync),
                'estimated_delivery': status_data.get('estimated_delivery', order.estimated_delivery_date),
                'tracking_history': tracking_history,
                'courier_data': status_data
            }
            
            logger.info(f"Successfully fetched status for tracking number {tracking_number}")
            return result
            
        except ImportError as e:
            error_msg = f"Courier adapter module not found: {str(e)}"
            logger.error(error_msg)
            raise RuntimeError(error_msg)
        
        except Exception as e:
            error_msg = f"Error fetching shipment status for {tracking_number}: {str(e)}"
            logger.error(error_msg, exc_info=True)
            raise RuntimeError(error_msg)
    
    @staticmethod
    def create_shipment(order_id: int, shipment_data: Dict) -> Dict[str, Any]:
        """
        Create shipment via courier API
        
        Args:
            order_id: Order ID
            shipment_data: Dict containing:
                - pickup_address: str
                - package_weight: float (kg)
                - package_length: float (cm)
                - package_width: float (cm)
                - package_height: float (cm)
                - courier_preference: str (shiprocket, india_post)
            
        Returns:
            Dict with success status, tracking_number, awb_code, courier_name, tracking_url
            
        Raises:
            ValueError: If validation fails
            RuntimeError: If API call fails
        """
        # Validate order exists
        order = Order.query.get(order_id)
        if not order:
            raise ValueError(f"Order {order_id} not found")
        
        # Validate order is in correct state
        if order.payment_status != 'paid':
            raise ValueError(f"Order {order_id} payment status must be 'paid' (current: {order.payment_status})")
        
        # Validate shipment data
        errors = TrackingService._validate_shipment_data(shipment_data)
        if errors:
            raise ValueError(f"Shipment data validation failed: {', '.join(errors)}")
        
        try:
            # Import courier adapter
            from courier_adapters import get_courier_adapter
            
            courier_name = shipment_data.get('courier_preference', 'shiprocket')
            adapter = get_courier_adapter(courier_name)
            
            if not adapter:
                raise ValueError(f"No adapter found for courier: {courier_name}")
            
            # Authenticate with courier API
            if not adapter.authenticate():
                raise RuntimeError(f"Failed to authenticate with {courier_name} API")
            
            # Generate tracking number
            tracking_number = TrackingService.generate_tracking_number(order_id)
            
            # Prepare shipment data for courier API
            courier_shipment_data = {
                'order_id': order_id,
                'tracking_number': tracking_number,
                'pickup_address': shipment_data['pickup_address'],
                'delivery_address': order.delivery_address,
                'package_weight': shipment_data['package_weight'],
                'package_length': shipment_data['package_length'],
                'package_width': shipment_data['package_width'],
                'package_height': shipment_data['package_height'],
                'buyer_name': order.buyer.full_name,
                'buyer_phone': order.buyer.phone,
                'buyer_email': order.buyer.email,
                'order_amount': order.total_amount,
                'payment_method': 'prepaid'  # Since payment_status is 'paid'
            }
            
            # Create shipment via courier API
            logger.info(f"Creating shipment for order {order_id} via {courier_name}")
            api_response = adapter.create_shipment(courier_shipment_data)
            
            if not api_response.get('success'):
                error_msg = api_response.get('error', 'Unknown error from courier API')
                raise RuntimeError(f"Courier API error: {error_msg}")
            
            # Update order with shipment details
            order.tracking_number = tracking_number
            order.awb_code = api_response.get('awb_code')
            order.courier_name = courier_name
            order.courier_tracking_url = api_response.get('tracking_url')
            order.courier_order_id = api_response.get('courier_order_id')
            order.shipment_created_at = datetime.utcnow()
            order.pickup_address = shipment_data['pickup_address']
            order.package_weight = shipment_data['package_weight']
            order.package_length = shipment_data['package_length']
            order.package_width = shipment_data['package_width']
            order.package_height = shipment_data['package_height']
            order.shipment_status = 'packed'
            order.estimated_delivery_date = api_response.get('estimated_delivery_date')
            order.api_sync_status = 'synced'
            order.last_api_sync = datetime.utcnow()
            
            # Update order status to processing, then shipped
            old_status = order.status
            order.status = 'processing'
            db.session.flush()
            
            # Create status history entry for processing
            from models import OrderStatusHistory
            status_history = OrderStatusHistory(
                order_id=order_id,
                old_status=old_status,
                new_status='processing',
                notes='Shipment created via courier API',
                changed_by_id=order.farmer_id
            )
            db.session.add(status_history)
            db.session.flush()
            
            # Update to shipped
            order.status = 'shipped'
            order.shipped_at = datetime.utcnow()
            
            # Create status history entry for shipped
            status_history_shipped = OrderStatusHistory(
                order_id=order_id,
                old_status='processing',
                new_status='shipped',
                notes=f'Shipment dispatched via {courier_name}',
                changed_by_id=order.farmer_id
            )
            db.session.add(status_history_shipped)
            
            # Create shipment status history entry
            shipment_history = ShipmentStatusHistory(
                order_id=order_id,
                tracking_number=tracking_number,
                old_status=None,
                new_status='packed',
                status_description='Shipment created and packed',
                location=shipment_data['pickup_address'],
                updated_by_source='api',
                courier_timestamp=datetime.utcnow()
            )
            db.session.add(shipment_history)
            
            # Commit all changes
            db.session.commit()
            
            logger.info(f"Successfully created shipment for order {order_id}: {tracking_number}")
            
            return {
                'success': True,
                'tracking_number': tracking_number,
                'awb_code': order.awb_code,
                'courier_name': courier_name,
                'tracking_url': order.courier_tracking_url,
                'courier_order_id': order.courier_order_id,
                'estimated_delivery_date': order.estimated_delivery_date,
                'message': 'Shipment created successfully'
            }
            
        except ImportError as e:
            db.session.rollback()
            error_msg = f"Courier adapter module not found: {str(e)}"
            logger.error(error_msg)
            raise RuntimeError(error_msg)
        
        except Exception as e:
            db.session.rollback()
            error_msg = f"Error creating shipment for order {order_id}: {str(e)}"
            logger.error(error_msg, exc_info=True)
            raise RuntimeError(error_msg)
    
    @staticmethod
    def _validate_shipment_data(shipment_data: Dict) -> list:
        """
        Validate shipment data
        
        Args:
            shipment_data: Shipment data dictionary
            
        Returns:
            List of error messages (empty if valid)
        """
        errors = []
        
        # Validate required fields
        required_fields = ['pickup_address', 'package_weight', 'package_length', 
                          'package_width', 'package_height', 'courier_preference']
        
        for field in required_fields:
            if field not in shipment_data or not shipment_data[field]:
                errors.append(f"{field} is required")
        
        # Validate package weight
        if 'package_weight' in shipment_data:
            try:
                weight = float(shipment_data['package_weight'])
                if weight <= 0:
                    errors.append("package_weight must be greater than 0")
                elif weight >= 1000:
                    errors.append("package_weight must be less than 1000 kg")
            except (ValueError, TypeError):
                errors.append("package_weight must be a valid number")
        
        # Validate package dimensions
        dimension_fields = ['package_length', 'package_width', 'package_height']
        for field in dimension_fields:
            if field in shipment_data:
                try:
                    dimension = float(shipment_data[field])
                    if dimension <= 0:
                        errors.append(f"{field} must be greater than 0")
                except (ValueError, TypeError):
                    errors.append(f"{field} must be a valid number")
        
        return errors
    
    @staticmethod
    def cancel_shipment(tracking_number: str, courier_name: str, reason: str = None) -> Dict[str, Any]:
        """
        Cancel shipment via courier API
        
        Args:
            tracking_number: Tracking number
            courier_name: Courier service name
            reason: Cancellation reason (optional)
            
        Returns:
            Dict with success status and message
            
        Raises:
            ValueError: If validation fails
            RuntimeError: If API call fails
        """
        if not tracking_number:
            raise ValueError("Tracking number is required")
        
        if not courier_name:
            raise ValueError("Courier name is required")
        
        # Find the order
        order = Order.query.filter_by(tracking_number=tracking_number).first()
        
        if not order:
            raise ValueError(f"No order found with tracking number {tracking_number}")
        
        # Validate that shipment can be cancelled (only active shipments)
        non_cancellable_statuses = ['delivered', 'cancelled', 'returned']
        if order.shipment_status in non_cancellable_statuses:
            raise ValueError(f"Cannot cancel shipment with status '{order.shipment_status}'")
        
        try:
            # Import courier adapter
            from courier_adapters import get_courier_adapter
            
            adapter = get_courier_adapter(courier_name)
            
            if not adapter:
                raise ValueError(f"No adapter found for courier: {courier_name}")
            
            # Authenticate with courier API
            if not adapter.authenticate():
                raise RuntimeError(f"Failed to authenticate with {courier_name} API")
            
            # Cancel shipment via courier API
            courier_order_id = order.courier_order_id or tracking_number
            logger.info(f"Cancelling shipment {tracking_number} via {courier_name}")
            api_response = adapter.cancel_shipment(courier_order_id)
            
            if not api_response.get('success'):
                error_msg = api_response.get('error', 'Unknown error from courier API')
                raise RuntimeError(f"Courier API error: {error_msg}")
            
            # Update order status
            old_status = order.status
            old_shipment_status = order.shipment_status
            
            order.status = 'cancelled'
            order.shipment_status = 'cancelled'
            order.cancelled_at = datetime.utcnow()
            order.cancellation_reason = reason or 'Shipment cancelled'
            order.last_api_sync = datetime.utcnow()
            
            # Create order status history entry
            from models import OrderStatusHistory
            status_history = OrderStatusHistory(
                order_id=order.id,
                old_status=old_status,
                new_status='cancelled',
                notes=f'Shipment cancelled: {reason or "No reason provided"}',
                changed_by_id=order.farmer_id
            )
            db.session.add(status_history)
            
            # Create shipment status history entry
            shipment_history = ShipmentStatusHistory(
                order_id=order.id,
                tracking_number=tracking_number,
                old_status=old_shipment_status,
                new_status='cancelled',
                status_description=f'Shipment cancelled: {reason or "No reason provided"}',
                location=None,
                updated_by_source='api',
                courier_timestamp=datetime.utcnow()
            )
            db.session.add(shipment_history)
            
            # Commit changes
            db.session.commit()
            
            logger.info(f"Successfully cancelled shipment {tracking_number}")
            
            return {
                'success': True,
                'tracking_number': tracking_number,
                'message': 'Shipment cancelled successfully',
                'cancelled_at': order.cancelled_at
            }
            
        except ImportError as e:
            db.session.rollback()
            error_msg = f"Courier adapter module not found: {str(e)}"
            logger.error(error_msg)
            raise RuntimeError(error_msg)
        
        except Exception as e:
            db.session.rollback()
            error_msg = f"Error cancelling shipment {tracking_number}: {str(e)}"
            logger.error(error_msg, exc_info=True)
            raise RuntimeError(error_msg)
    
    @staticmethod
    def schedule_redelivery(tracking_number: str, courier_name: str, delivery_date: date) -> Dict[str, Any]:
        """
        Schedule re-delivery attempt
        
        Args:
            tracking_number: Tracking number
            courier_name: Courier service name
            delivery_date: Requested delivery date
            
        Returns:
            Dict with success status and new delivery date
            
        Raises:
            ValueError: If validation fails
            RuntimeError: If API call fails
        """
        if not tracking_number:
            raise ValueError("Tracking number is required")
        
        if not courier_name:
            raise ValueError("Courier name is required")
        
        if not delivery_date:
            raise ValueError("Delivery date is required")
        
        # Validate delivery date is in the future
        if delivery_date < date.today():
            raise ValueError("Delivery date must be in the future")
        
        # Find the order
        order = Order.query.filter_by(tracking_number=tracking_number).first()
        
        if not order:
            raise ValueError(f"No order found with tracking number {tracking_number}")
        
        # Validate that redelivery is applicable (typically for failed deliveries)
        if order.shipment_status not in ['failed', 'returned']:
            raise ValueError(f"Cannot schedule redelivery for shipment with status '{order.shipment_status}'")
        
        try:
            # Import courier adapter
            from courier_adapters import get_courier_adapter
            
            adapter = get_courier_adapter(courier_name)
            
            if not adapter:
                raise ValueError(f"No adapter found for courier: {courier_name}")
            
            # Authenticate with courier API
            if not adapter.authenticate():
                raise RuntimeError(f"Failed to authenticate with {courier_name} API")
            
            # Schedule redelivery via courier API (if supported)
            courier_order_id = order.courier_order_id or tracking_number
            logger.info(f"Scheduling redelivery for {tracking_number} on {delivery_date}")
            
            # Note: Not all courier APIs support redelivery scheduling
            # This is a placeholder for the API call
            redelivery_data = {
                'courier_order_id': courier_order_id,
                'delivery_date': delivery_date.isoformat()
            }
            
            # For now, we'll update the order locally
            # In a real implementation, this would call adapter.schedule_redelivery()
            
            # Update order
            old_shipment_status = order.shipment_status
            order.shipment_status = 'in_transit'
            order.estimated_delivery_date = delivery_date
            order.delivery_attempts += 1
            order.last_api_sync = datetime.utcnow()
            
            # Create shipment status history entry
            shipment_history = ShipmentStatusHistory(
                order_id=order.id,
                tracking_number=tracking_number,
                old_status=old_shipment_status,
                new_status='in_transit',
                status_description=f'Redelivery scheduled for {delivery_date}',
                location=None,
                updated_by_source='manual',
                courier_timestamp=datetime.utcnow()
            )
            db.session.add(shipment_history)
            
            # Commit changes
            db.session.commit()
            
            logger.info(f"Successfully scheduled redelivery for {tracking_number}")
            
            return {
                'success': True,
                'tracking_number': tracking_number,
                'new_delivery_date': delivery_date,
                'delivery_attempts': order.delivery_attempts,
                'message': f'Redelivery scheduled for {delivery_date}'
            }
            
        except ImportError as e:
            db.session.rollback()
            error_msg = f"Courier adapter module not found: {str(e)}"
            logger.error(error_msg)
            raise RuntimeError(error_msg)
        
        except Exception as e:
            db.session.rollback()
            error_msg = f"Error scheduling redelivery for {tracking_number}: {str(e)}"
            logger.error(error_msg, exc_info=True)
            raise RuntimeError(error_msg)
