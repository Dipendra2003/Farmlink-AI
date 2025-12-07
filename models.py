from extensions import db
from flask_login import UserMixin
from datetime import datetime
import json
import logging
from werkzeug.security import generate_password_hash, check_password_hash

logger = logging.getLogger(__name__)

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # farmer, buyer, admin, manager_farmer, manager_buyer, manager_crop
    full_name = db.Column(db.String(100))
    phone = db.Column(db.String(20))
    location = db.Column(db.String(100))
    profile_image = db.Column(db.String(200), default='default.jpg')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    active = db.Column(db.Boolean, default=True)
    email_verified = db.Column(db.Boolean, default=False)
    verification_otp = db.Column(db.String(10))
    otp_generated_at = db.Column(db.DateTime)
    reset_token = db.Column(db.String(100))
    reset_token_expires = db.Column(db.DateTime)
    reset_otp = db.Column(db.String(10))
    reset_otp_expires = db.Column(db.DateTime)
    last_login = db.Column(db.DateTime)
    login_count = db.Column(db.Integer, default=0)
    
    # API Token fields
    api_token = db.Column(db.String(100), unique=True, nullable=True)
    api_token_created = db.Column(db.DateTime, nullable=True)
    api_token_expires = db.Column(db.DateTime, nullable=True)
    last_api_usage = db.Column(db.DateTime, nullable=True)
    
    # Two-Factor Authentication fields
    two_factor_enabled = db.Column(db.Boolean, default=False)
    two_factor_secret = db.Column(db.String(32), nullable=True)
    backup_codes = db.Column(db.Text, nullable=True)  # JSON array of backup codes
    two_factor_verified_at = db.Column(db.DateTime, nullable=True)
    
    @property
    def is_active(self):
        return self.active
    
    # Relationships
    crops = db.relationship('Crop', foreign_keys='Crop.farmer_id', backref='farmer', lazy=True, cascade='all, delete-orphan')
    sent_messages = db.relationship('Message', foreign_keys='Message.sender_id', backref='sender', lazy=True)
    received_messages = db.relationship('Message', foreign_keys='Message.recipient_id', backref='recipient', lazy=True)
    orders_placed = db.relationship('Order', foreign_keys='Order.buyer_id', backref='buyer', lazy=True)
    orders_received = db.relationship('Order', foreign_keys='Order.farmer_id', backref='farmer_user', lazy=True)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password, method='pbkdf2:sha256')
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def is_following(self, user):
        """Check if this user is following another user"""
        return UserFollow.query.filter_by(
            follower_id=self.id, 
            followed_id=user.id
        ).first() is not None
        
    def follow(self, user):
        """Follow another user"""
        if not self.is_following(user) and user.id != self.id:
            follow = UserFollow(follower_id=self.id, followed_id=user.id)
            db.session.add(follow)
            return True
        return False
        
    def unfollow(self, user):
        """Unfollow a user"""
        follow = UserFollow.query.filter_by(
            follower_id=self.id, 
            followed_id=user.id
        ).first()
        if follow:
            db.session.delete(follow)
            return True
        return False
        
    def get_follower_count(self):
        """Get number of followers"""
        return UserFollow.query.filter_by(followed_id=self.id).count()
        
    def get_following_count(self):
        """Get number of users this user is following"""
        return UserFollow.query.filter_by(follower_id=self.id).count()
    
    def get_reputation_weight(self):
        """Calculate vote weight based on reputation"""
        # Import here to avoid circular imports
        from expert_forum_utils import calculate_user_reputation
        reputation = calculate_user_reputation(self.id)
        points = reputation.get('points', 0)
        
        # Weight calculation: higher reputation = higher vote weight
        if points >= 1000:
            return 3.0  # Master Expert
        elif points >= 500:
            return 2.5  # Expert
        elif points >= 200:
            return 2.0  # Advanced
        elif points >= 50:
            return 1.5  # Intermediate
        else:
            return 1.0  # Beginner
    
    @property
    def is_verified(self):
        """Check if user is verified (admin or email verified)"""
        return self.role == 'admin' or self.email_verified
    
    @property
    def is_kyc_verified(self):
        """Check if seller has verified KYC"""
        if self.role not in ['farmer', 'manager_farmer']:
            return True  # Non-sellers don't need KYC
        # Check if user has a verified KYC record (most recent non-archived)
        # Using hasattr to avoid circular import issues
        if hasattr(self, 'kyc_records') and self.kyc_records:
            # Get most recent non-archived KYC record
            active_kyc = [kyc for kyc in self.kyc_records if not kyc.is_archived]
            if active_kyc:
                # Sort by created_at descending and get the first one
                most_recent = sorted(active_kyc, key=lambda x: x.created_at, reverse=True)[0]
                return most_recent.status == 'verified'
        return False
    
    def get(self, key, default=None):
        """Dictionary-style access for template compatibility"""
        if hasattr(self, key):
            return getattr(self, key)
        return default
    
    def __repr__(self):
        return f'<User {self.username}>'

class LoginAttempt(db.Model):
    """Track login attempts for security monitoring"""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    ip_address = db.Column(db.String(45), nullable=False)
    user_agent = db.Column(db.String(255))
    success = db.Column(db.Boolean, default=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<LoginAttempt {self.ip_address} {"Success" if self.success else "Failed"}>'

class Crop(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    category = db.Column(db.String(50), nullable=False)
    description = db.Column(db.Text)
    quantity = db.Column(db.Float, nullable=False)
    unit = db.Column(db.String(20), nullable=False)  # kg, tonnes, etc.
    price_per_unit = db.Column(db.Float, nullable=False)
    harvest_date = db.Column(db.Date)
    location = db.Column(db.String(100))
    status = db.Column(db.String(20), default='available')  # available, sold, reserved
    image_url = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Admin approval workflow fields
    approval_status = db.Column(db.String(20), default='pending')  # pending, approved, rejected
    rejection_reason = db.Column(db.Text)
    approved_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    approved_at = db.Column(db.DateTime)
    
    # Foreign Keys
    farmer_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
    # Relationships
    orders = db.relationship('Order', backref='crop', lazy=True)
    approver = db.relationship('User', foreign_keys=[approved_by], backref='crops_approved', overlaps="crops,farmer")
    
    @property
    def total_value(self):
        return self.quantity * self.price_per_unit
    
    def __repr__(self):
        return f'<Crop {self.name}>'

class Cart(db.Model):
    """Shopping cart for buyers to add multiple crops before checkout"""
    id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Foreign Keys
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
    # Relationships
    user = db.relationship('User', backref='cart')
    items = db.relationship('CartItem', backref='cart', lazy=True, cascade='all, delete-orphan')
    
    # Indexes for frequently queried fields
    __table_args__ = (
        db.Index('idx_cart_user', 'user_id'),
    )
    
    def __repr__(self):
        return f'<Cart {self.id} for user {self.user_id}>'


class CartItem(db.Model):
    """Individual items in a shopping cart"""
    id = db.Column(db.Integer, primary_key=True)
    quantity = db.Column(db.Float, nullable=False)
    price_per_unit = db.Column(db.Float, nullable=False)  # Snapshot at time of adding
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Foreign Keys
    cart_id = db.Column(db.Integer, db.ForeignKey('cart.id'), nullable=False)
    crop_id = db.Column(db.Integer, db.ForeignKey('crop.id'), nullable=False)
    
    # Relationships
    crop = db.relationship('Crop', backref='cart_items')
    
    # Unique constraint to prevent duplicate crops in same cart and indexes
    __table_args__ = (
        db.UniqueConstraint('cart_id', 'crop_id', name='unique_cart_crop'),
        db.Index('idx_cart_item_cart', 'cart_id'),
        db.Index('idx_cart_item_crop', 'crop_id'),
    )
    
    @property
    def subtotal(self):
        """Calculate subtotal for this cart item"""
        return self.quantity * self.price_per_unit
    
    @property
    def is_available(self):
        """Check if the crop is still available and has sufficient quantity"""
        if not self.crop:
            return False
        return (
            self.crop.status == 'available' and
            self.crop.approval_status == 'approved' and
            self.crop.quantity >= self.quantity
        )
    
    def __repr__(self):
        return f'<CartItem {self.id} - {self.quantity} of crop {self.crop_id}>'


class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    quantity_requested = db.Column(db.Float, nullable=False)
    price_per_unit = db.Column(db.Float, nullable=False)
    total_amount = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(20), default='pending')  # pending, confirmed, processing, shipped, delivered, rejected, cancelled
    delivery_address = db.Column(db.Text)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    delivery_method = db.Column(db.String(20), default='standard')  # standard, express
    payment_status = db.Column(db.String(20), default='pending')  # pending, paid, failed, refunded
    invoice_number = db.Column(db.String(50), unique=True, nullable=True)  # Unique invoice number
    razorpay_order_id = db.Column(db.String(200), unique=True, nullable=True)
    razorpay_payment_id = db.Column(db.String(200), unique=True, nullable=True)
    razorpay_signature = db.Column(db.String(500), nullable=True)
    
    # Enhanced tracking fields
    tracking_number = db.Column(db.String(100), nullable=True, index=True)
    shipped_at = db.Column(db.DateTime, nullable=True)
    delivered_at = db.Column(db.DateTime, nullable=True)
    cancelled_at = db.Column(db.DateTime, nullable=True)
    cancellation_reason = db.Column(db.Text, nullable=True)
    
    # Shipment tracking system fields
    awb_code = db.Column(db.String(100), nullable=True)  # Air Waybill code from courier
    courier_name = db.Column(db.String(50), nullable=True, index=True)  # shiprocket, india_post, etc.
    courier_tracking_url = db.Column(db.String(500), nullable=True)
    shipment_created_at = db.Column(db.DateTime, nullable=True)
    pickup_address = db.Column(db.Text, nullable=True)
    package_weight = db.Column(db.Float, nullable=True)  # in kg
    package_length = db.Column(db.Float, nullable=True)  # in cm
    package_width = db.Column(db.Float, nullable=True)  # in cm
    package_height = db.Column(db.Float, nullable=True)  # in cm
    shipment_status = db.Column(db.String(50), nullable=True, index=True)  # packed, shipped, in_transit, out_for_delivery, delivered, failed, returned
    estimated_delivery_date = db.Column(db.Date, nullable=True)
    actual_delivery_date = db.Column(db.DateTime, nullable=True)
    delivery_confirmed_by_buyer = db.Column(db.Boolean, default=False)
    delivery_confirmation_date = db.Column(db.DateTime, nullable=True)
    delivery_attempts = db.Column(db.Integer, default=0)
    delivery_failure_reason = db.Column(db.Text, nullable=True)
    courier_order_id = db.Column(db.String(100), nullable=True)  # External order ID from courier
    last_api_sync = db.Column(db.DateTime, nullable=True)
    api_sync_status = db.Column(db.String(20), default='pending')  # pending, synced, failed
    
    # Foreign Keys
    buyer_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    farmer_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    crop_id = db.Column(db.Integer, db.ForeignKey('crop.id'), nullable=False)
    
    # Indexes for frequently queried fields
    __table_args__ = (
        db.Index('idx_order_buyer', 'buyer_id', 'created_at'),
        db.Index('idx_order_farmer', 'farmer_id', 'created_at'),
        db.Index('idx_order_status', 'status', 'created_at'),
        db.Index('idx_order_payment', 'payment_status', 'created_at'),
        db.Index('idx_order_crop', 'crop_id'),
    )

    def __repr__(self):
        return f'<Order {self.id} - {self.status}>'
        
    def calculate_total(self):
        """Calculate total amount based on quantity and price"""
        self.total_amount = self.quantity_requested * self.price_per_unit
        return self.total_amount


class OrderStatusHistory(db.Model):
    """Track order status changes for audit trail and transparency"""
    __tablename__ = 'order_status_history'
    
    id = db.Column(db.Integer, primary_key=True)
    old_status = db.Column(db.String(20), nullable=True)
    new_status = db.Column(db.String(20), nullable=False)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Foreign Keys
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=False)
    changed_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
    # Relationships
    order = db.relationship('Order', backref='status_history')
    changed_by = db.relationship('User', backref='order_status_changes')
    
    # Indexes for frequently queried fields
    __table_args__ = (
        db.Index('idx_status_history_order', 'order_id', 'created_at'),
        db.Index('idx_status_history_user', 'changed_by_id', 'created_at'),
    )
    
    def __repr__(self):
        return f'<OrderStatusHistory {self.id} - {self.old_status} → {self.new_status}>'


class ShipmentStatusHistory(db.Model):
    """Track all shipment status changes for tracking system"""
    __tablename__ = 'shipment_status_history'
    
    id = db.Column(db.Integer, primary_key=True)
    tracking_number = db.Column(db.String(100), nullable=False, index=True)
    
    # Status information
    old_status = db.Column(db.String(50), nullable=True)
    new_status = db.Column(db.String(50), nullable=False)
    status_description = db.Column(db.Text, nullable=True)
    location = db.Column(db.String(200), nullable=True)  # Current location of package
    
    # Metadata
    updated_by_source = db.Column(db.String(20), nullable=False)  # webhook, polling, manual
    courier_timestamp = db.Column(db.DateTime, nullable=True)  # Timestamp from courier
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Foreign Keys
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=False)
    
    # Relationships
    order = db.relationship('Order', backref='shipment_history')
    
    # Indexes
    __table_args__ = (
        db.Index('idx_shipment_history_order', 'order_id', 'created_at'),
        db.Index('idx_shipment_history_tracking', 'tracking_number', 'created_at'),
    )
    
    def __repr__(self):
        return f'<ShipmentStatusHistory {self.id} - {self.old_status} → {self.new_status}>'


class CourierAPILog(db.Model):
    """Log all courier API interactions for debugging and audit"""
    __tablename__ = 'courier_api_log'
    
    id = db.Column(db.Integer, primary_key=True)
    
    # Request details
    courier_name = db.Column(db.String(50), nullable=False)
    api_endpoint = db.Column(db.String(200), nullable=False)
    http_method = db.Column(db.String(10), nullable=False)
    request_payload = db.Column(db.Text, nullable=True)
    
    # Response details
    response_status_code = db.Column(db.Integer, nullable=True)
    response_payload = db.Column(db.Text, nullable=True)
    error_message = db.Column(db.Text, nullable=True)
    
    # Metadata
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    execution_time_ms = db.Column(db.Integer, nullable=True)
    
    # Foreign Keys
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=True)
    
    # Indexes
    __table_args__ = (
        db.Index('idx_api_log_order', 'order_id', 'created_at'),
        db.Index('idx_api_log_courier', 'courier_name', 'created_at'),
    )
    
    def __repr__(self):
        return f'<CourierAPILog {self.id} - {self.courier_name} {self.http_method} {self.api_endpoint}>'


class Payment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=False)
    razorpay_order_id = db.Column(db.String(200), unique=True)
    razorpay_payment_id = db.Column(db.String(200), unique=True)
    razorpay_signature = db.Column(db.String(500))
    status = db.Column(db.String(20), default='pending')  # pending, completed, failed, refunded
    amount = db.Column(db.Float, nullable=False)
    currency = db.Column(db.String(3), default='INR')
    method = db.Column(db.String(50))  # card, netbanking, upi, wallet
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationship with Order
    order = db.relationship('Order', backref=db.backref('payment', uselist=False))
    
    def __repr__(self):
        return f'<Payment {self.razorpay_order_id}>'

class Message(db.Model):
    """Message model for user-to-user communications"""
    id = db.Column(db.Integer, primary_key=True)
    subject = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    read_at = db.Column(db.DateTime, nullable=True)
    
    # Foreign Keys and Relationships
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    recipient_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
    def mark_as_read(self):
        """Mark message as read and update read timestamp"""
        if not self.is_read:
            self.is_read = True
            self.read_at = datetime.utcnow()
            db.session.add(self)
    
    def to_dict(self):
        """Convert message to dictionary for API responses"""
        return {
            'id': self.id,
            'subject': self.subject,
            'content': self.content,
            'is_read': self.is_read,
            'created_at': self.created_at.isoformat(),
            'read_at': self.read_at.isoformat() if self.read_at else None,
            'sender_id': self.sender_id,
            'recipient_id': self.recipient_id,
            'sender_name': self.sender.full_name,
            'recipient_name': self.recipient.full_name
        }
    
    @property
    def preview(self):
        """Get a preview of the message content"""
        max_length = 100
        if len(self.content) > max_length:
            return self.content[:max_length] + '...'
        return self.content
    
    @property
    def time_ago(self):
        """Get a human-readable time difference"""
        now = datetime.utcnow()
        diff = now - self.created_at
        
        if diff.days > 7:
            return self.created_at.strftime('%B %d, %Y')
        elif diff.days > 0:
            return f'{diff.days} days ago'
        elif diff.seconds > 3600:
            hours = diff.seconds // 3600
            return f'{hours} hours ago'
        elif diff.seconds > 60:
            minutes = diff.seconds // 60
            return f'{minutes} minutes ago'
        else:
            return 'Just now'
    
    def __repr__(self):
        return f'<Message {self.subject}>'

class WeatherData(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    location = db.Column(db.String(100), nullable=False)
    temperature = db.Column(db.Float)
    humidity = db.Column(db.Float)
    weather_condition = db.Column(db.String(50))
    wind_speed = db.Column(db.Float)
    precipitation = db.Column(db.Float)
    pressure = db.Column(db.Float)
    visibility = db.Column(db.Float)
    recorded_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<WeatherData {self.location}>'

class ExpertPost(db.Model):
    """Expert forum posts and Q&A"""
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    category = db.Column(db.String(50), nullable=False)  # Legacy field, kept for backward compatibility
    main_category = db.Column(db.String(50))  # farming-crop-management, soil-environment, etc.
    subcategory = db.Column(db.String(50))  # crop-management, pest-control, etc.
    tags = db.Column(db.String(200))
    is_question = db.Column(db.Boolean, default=False)
    is_answered = db.Column(db.Boolean, default=False)
    upvotes = db.Column(db.Integer, default=0)
    downvotes = db.Column(db.Integer, default=0)
    views = db.Column(db.Integer, default=0)
    is_locked = db.Column(db.Boolean, default=False)
    is_featured = db.Column(db.Boolean, default=False)
    is_deleted = db.Column(db.Boolean, default=False)
    deleted_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Foreign Keys
    author_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    deleted_by_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    
    # Relationships
    replies = db.relationship('ExpertReply', backref='post', lazy=True, cascade='all, delete-orphan')
    author = db.relationship('User', foreign_keys=[author_id], backref='expert_posts')
    deleted_by = db.relationship('User', foreign_keys=[deleted_by_id], backref='posts_deleted')
    
    def __repr__(self):
        return f'<ExpertPost {self.title}>'
        
    @property
    def vote_score(self):
        """Calculate weighted vote score"""
        from sqlalchemy import func
        upvote_sum = db.session.query(func.sum(PostVote.weight)).filter_by(
            post_id=self.id, vote_type='upvote'
        ).scalar() or 0
        downvote_sum = db.session.query(func.sum(PostVote.weight)).filter_by(
            post_id=self.id, vote_type='downvote'
        ).scalar() or 0
        return upvote_sum - downvote_sum
        
    def get_user_vote(self, user_id):
        """Get user's vote on this post"""
        if not user_id:
            return None
        return PostVote.query.filter_by(post_id=self.id, user_id=user_id).first()
        
    @property
    def is_locked_active(self):
        """Check if post is currently locked"""
        if not self.is_locked:
            return False
        active_lock = PostLock.query.filter_by(
            post_id=self.id, 
            is_active=True
        ).first()
        if active_lock and active_lock.expires_at:
            return active_lock.expires_at > datetime.utcnow()
        return bool(active_lock)

class ExpertReply(db.Model):
    """Replies to expert forum posts"""
    __tablename__ = 'expert_reply'
    
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    is_solution = db.Column(db.Boolean, default=False)
    upvotes = db.Column(db.Integer, default=0)
    downvotes = db.Column(db.Integer, default=0)
    expertise = db.Column(db.String(200))  # Author's expertise/credentials
    is_deleted = db.Column(db.Boolean, default=False)
    deleted_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Foreign Keys
    post_id = db.Column(db.Integer, db.ForeignKey('expert_post.id', ondelete='CASCADE'), nullable=False)
    author_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    deleted_by_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    
    # Relationships
    author = db.relationship('User', foreign_keys=[author_id], backref='expert_replies')
    deleted_by = db.relationship('User', foreign_keys=[deleted_by_id], backref='replies_deleted')
    
    def __repr__(self):
        return f'<ExpertReply {self.id}>'
        
    @property
    def vote_score(self):
        """Calculate weighted vote score"""
        from sqlalchemy import func
        upvote_sum = db.session.query(func.sum(ReplyVote.weight)).filter_by(
            reply_id=self.id, vote_type='upvote'
        ).scalar() or 0
        downvote_sum = db.session.query(func.sum(ReplyVote.weight)).filter_by(
            reply_id=self.id, vote_type='downvote'
        ).scalar() or 0
        return upvote_sum - downvote_sum
        
    def get_user_vote(self, user_id):
        """Get user's vote on this reply"""
        if not user_id:
            return None
        return ReplyVote.query.filter_by(reply_id=self.id, user_id=user_id).first()

class LearningArticle(db.Model):
    """Learning hub articles and tutorials"""
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    summary = db.Column(db.String(500))
    category = db.Column(db.String(50), nullable=False)
    crop_type = db.Column(db.String(50))  # specific crop this article is about
    difficulty_level = db.Column(db.String(20), default='beginner')  # beginner, intermediate, advanced
    reading_time = db.Column(db.Integer, default=5)  # minutes
    featured_image = db.Column(db.String(200))
    tags = db.Column(db.String(200))
    is_published = db.Column(db.Boolean, default=True)
    is_draft = db.Column(db.Boolean, default=False)
    scheduled_publish = db.Column(db.DateTime, nullable=True)
    views = db.Column(db.Integer, default=0)
    likes = db.Column(db.Integer, default=0)
    comments_count = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Foreign Keys
    author_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
    # Relationships
    author = db.relationship('User', backref='articles')
    comments = db.relationship('ArticleComment', backref='article', lazy='dynamic', cascade='all, delete-orphan')
    likes_rel = db.relationship('ArticleLike', backref='article', lazy='dynamic', cascade='all, delete-orphan')
    bookmarks = db.relationship('ArticleBookmark', backref='article', lazy='dynamic', cascade='all, delete-orphan')
    
    def get_like_count(self):
        """Get total likes for this article"""
        return ArticleLike.query.filter_by(article_id=self.id).count()
    
    def is_liked_by(self, user_id):
        """Check if user has liked this article"""
        if not user_id:
            return False
        return ArticleLike.query.filter_by(article_id=self.id, user_id=user_id).first() is not None
    
    def is_bookmarked_by(self, user_id):
        """Check if user has bookmarked this article"""
        if not user_id:
            return False
        return ArticleBookmark.query.filter_by(article_id=self.id, user_id=user_id).first() is not None
    
    def __repr__(self):
        return f'<LearningArticle {self.title}>'


class ArticleLike(db.Model):
    """Track article likes"""
    id = db.Column(db.Integer, primary_key=True)
    article_id = db.Column(db.Integer, db.ForeignKey('learning_article.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    __table_args__ = (db.UniqueConstraint('article_id', 'user_id', name='unique_article_like'),)


class ArticleBookmark(db.Model):
    """Track article bookmarks"""
    id = db.Column(db.Integer, primary_key=True)
    article_id = db.Column(db.Integer, db.ForeignKey('learning_article.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    __table_args__ = (db.UniqueConstraint('article_id', 'user_id', name='unique_article_bookmark'),)


class AIConversation(db.Model):
    """Store AI voice assistant conversations"""
    __tablename__ = 'ai_conversation'
    
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Foreign Keys
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
    # Relationships
    user = db.relationship('User', backref='ai_conversations')
    messages = db.relationship('AIMessage', backref='conversation', lazy='dynamic', cascade='all, delete-orphan', order_by='AIMessage.created_at')
    
    def to_dict(self):
        """Convert conversation to dictionary"""
        return {
            'id': self.id,
            'title': self.title,
            'timestamp': int(self.created_at.timestamp() * 1000),
            'messages': [msg.to_dict() for msg in self.messages.all()]
        }
    
    def __repr__(self):
        return f'<AIConversation {self.id} - {self.title}>'


class AIMessage(db.Model):
    """Store individual messages in AI conversations"""
    __tablename__ = 'ai_message'
    
    id = db.Column(db.Integer, primary_key=True)
    type = db.Column(db.String(10), nullable=False)  # 'user' or 'ai'
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Foreign Keys
    conversation_id = db.Column(db.Integer, db.ForeignKey('ai_conversation.id'), nullable=False)
    
    def to_dict(self):
        """Convert message to dictionary"""
        return {
            'type': self.type,
            'content': self.content,
            'timestamp': int(self.created_at.timestamp() * 1000)
        }
    
    def __repr__(self):
        return f'<AIMessage {self.id} - {self.type}>'


class ArticleComment(db.Model):
    """Comments on learning articles"""
    id = db.Column(db.Integer, primary_key=True)
    article_id = db.Column(db.Integer, db.ForeignKey('learning_article.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    parent_id = db.Column(db.Integer, db.ForeignKey('article_comment.id'), nullable=True)  # For nested replies
    is_edited = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = db.relationship('User', backref='article_comments')
    replies = db.relationship('ArticleComment', backref=db.backref('parent', remote_side=[id]), lazy='dynamic')
    
    def __repr__(self):
        return f'<ArticleComment {self.id} on Article {self.article_id}>'


class UserReadingProgress(db.Model):
    """Track user reading progress and history"""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    article_id = db.Column(db.Integer, db.ForeignKey('learning_article.id'), nullable=False)
    completed = db.Column(db.Boolean, default=False)
    progress_percentage = db.Column(db.Integer, default=0)
    last_read_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime, nullable=True)
    time_spent_seconds = db.Column(db.Integer, default=0)  # Track actual reading time
    
    # Relationships
    user = db.relationship('User', backref='reading_progress')
    article = db.relationship('LearningArticle', backref='reading_progress')
    
    __table_args__ = (db.UniqueConstraint('user_id', 'article_id', name='unique_user_article_progress'),)


class UserLearningPreference(db.Model):
    """Track user learning preferences and interests"""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, unique=True)
    preferred_categories = db.Column(db.Text)  # JSON array of category preferences
    skill_level = db.Column(db.String(20), default='beginner')  # beginner, intermediate, advanced
    learning_goals = db.Column(db.Text)  # JSON array of learning goals
    preferred_reading_time = db.Column(db.Integer, default=10)  # Preferred article length in minutes
    interests = db.Column(db.Text)  # JSON array of specific interests/crops
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = db.relationship('User', backref=db.backref('learning_preference', uselist=False))
    
    def __repr__(self):
        return f'<UserLearningPreference user_id={self.user_id}>'


class ArticleRecommendation(db.Model):
    """Store personalized article recommendations for users"""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    article_id = db.Column(db.Integer, db.ForeignKey('learning_article.id'), nullable=False)
    recommendation_score = db.Column(db.Float, default=0.0)  # Relevance score
    recommendation_reason = db.Column(db.String(200))  # Why this article is recommended
    is_viewed = db.Column(db.Boolean, default=False)
    is_dismissed = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    viewed_at = db.Column(db.DateTime, nullable=True)
    
    # Relationships
    user = db.relationship('User', backref='article_recommendations')
    article = db.relationship('LearningArticle', backref='recommendations')
    
    __table_args__ = (
        db.UniqueConstraint('user_id', 'article_id', name='unique_user_article_recommendation'),
        db.Index('idx_recommendation_user_score', 'user_id', 'recommendation_score'),
    )
    
    def __repr__(self):
        return f'<ArticleRecommendation user_id={self.user_id} article_id={self.article_id}>'


class UserAchievement(db.Model):
    """Track user achievements and badges"""
    __tablename__ = 'user_achievement'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    achievement_type = db.Column(db.String(50), nullable=False)  # first_article, bookworm, scholar, etc.
    achievement_name = db.Column(db.String(100), nullable=False)
    achievement_description = db.Column(db.String(200))
    icon = db.Column(db.String(50))  # FontAwesome icon class
    earned_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_notified = db.Column(db.Boolean, default=False)  # Whether user has been notified
    
    # Relationships
    user = db.relationship('User', backref='achievements')
    
    __table_args__ = (
        db.UniqueConstraint('user_id', 'achievement_type', name='unique_user_achievement'),
        db.Index('idx_achievement_user', 'user_id', 'earned_at'),
    )
    
    def __repr__(self):
        return f'<UserAchievement {self.achievement_name} for user {self.user_id}>'


class ContentFlag(db.Model):
    """Track flagged content for moderation"""
    id = db.Column(db.Integer, primary_key=True)
    content_type = db.Column(db.String(20), nullable=False)  # 'comment' or 'article'
    comment_id = db.Column(db.Integer, db.ForeignKey('article_comment.id'), nullable=True)
    article_id = db.Column(db.Integer, db.ForeignKey('learning_article.id'), nullable=True)
    reporter_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    reason = db.Column(db.String(50), nullable=False)  # spam, inappropriate, harassment, etc.
    description = db.Column(db.Text)
    status = db.Column(db.String(20), default='pending')  # pending, approved, removed, dismissed
    moderator_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    moderator_notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    moderated_at = db.Column(db.DateTime, nullable=True)
    
    # Relationships
    reporter = db.relationship('User', foreign_keys=[reporter_id], backref='content_flags')
    moderator = db.relationship('User', foreign_keys=[moderator_id], backref='moderated_flags')
    comment = db.relationship('ArticleComment', backref='flags')
    article = db.relationship('LearningArticle', backref='flags')
    
    def __repr__(self):
        return f'<ContentFlag {self.id} - {self.content_type} - {self.status}>'


class ArticleCategory(db.Model):
    """Categories for learning hub articles"""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    slug = db.Column(db.String(50), unique=True, nullable=False)
    description = db.Column(db.Text)
    icon = db.Column(db.String(50))  # FontAwesome icon class
    color = db.Column(db.String(20), default='#6c757d')  # Hex color code
    display_order = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True)
    article_count = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f'<ArticleCategory {self.name}>'
    
    def to_dict(self):
        """Convert to dictionary"""
        return {
            'id': self.id,
            'name': self.name,
            'slug': self.slug,
            'description': self.description,
            'icon': self.icon,
            'color': self.color,
            'display_order': self.display_order,
            'is_active': self.is_active,
            'article_count': self.article_count
        }


class UserRating(db.Model):
    """User ratings and feedback system"""
    id = db.Column(db.Integer, primary_key=True)
    rating = db.Column(db.Integer, nullable=False)  # 1-5 stars
    feedback = db.Column(db.Text)
    transaction_type = db.Column(db.String(20), nullable=False)  # order, service, etc.
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Foreign Keys
    rater_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    rated_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'))
    
    # Relationships
    rater = db.relationship('User', foreign_keys=[rater_id], backref='ratings_given')
    rated_user = db.relationship('User', foreign_keys=[rated_user_id], backref='ratings_received')
    order = db.relationship('Order', backref='rating')
    
    def __repr__(self):
        return f'<UserRating {self.rating} stars>'

class Analytics(db.Model):
    """Analytics and reports data"""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    metric_type = db.Column(db.String(50), nullable=False)  # revenue, orders, crops, etc.
    metric_value = db.Column(db.Float, nullable=False)
    time_period = db.Column(db.String(20), nullable=False)  # daily, weekly, monthly
    date_recorded = db.Column(db.Date, nullable=False)
    additional_data = db.Column(db.Text)  # JSON string for additional data
    
    # Relationships
    user = db.relationship('User', backref='analytics')
    
    def __repr__(self):
        return f'<Analytics {self.metric_type}: {self.metric_value}>'

class PostVote(db.Model):
    """Voting system for expert forum posts"""
    __tablename__ = 'post_vote'
    __mapper_args__ = {'confirm_deleted_rows': False}
    
    id = db.Column(db.Integer, primary_key=True)
    vote_type = db.Column(db.String(10), nullable=False)  # 'upvote' or 'downvote'
    weight = db.Column(db.Float, default=1.0)  # Vote weight based on user reputation
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Foreign Keys
    post_id = db.Column(db.Integer, db.ForeignKey('expert_post.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
    # Relationships
    post = db.relationship('ExpertPost', backref='votes')
    user = db.relationship('User', backref='post_votes')
    
    # Unique constraint to prevent duplicate votes
    __table_args__ = (db.UniqueConstraint('post_id', 'user_id', name='unique_post_vote'),)
    
    def __repr__(self):
        return f'<PostVote {self.vote_type} on post {self.post_id}>'

class ReplyVote(db.Model):
    """Voting system for expert forum replies"""
    __tablename__ = 'reply_vote'
    __mapper_args__ = {'confirm_deleted_rows': False}
    
    id = db.Column(db.Integer, primary_key=True)
    vote_type = db.Column(db.String(10), nullable=False)  # 'upvote' or 'downvote'
    weight = db.Column(db.Float, default=1.0)  # Vote weight based on user reputation
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Foreign Keys
    reply_id = db.Column(db.Integer, db.ForeignKey('expert_reply.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
    # Relationships
    reply = db.relationship('ExpertReply', backref='votes')
    user = db.relationship('User', backref='reply_votes')
    
    # Unique constraint to prevent duplicate votes
    __table_args__ = (db.UniqueConstraint('reply_id', 'user_id', name='unique_reply_vote'),)
    
    def __repr__(self):
        return f'<ReplyVote {self.vote_type} on reply {self.reply_id}>'

class UserFollow(db.Model):
    """User following system"""
    __tablename__ = 'user_follow'
    __mapper_args__ = {'confirm_deleted_rows': False}
    
    id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Foreign Keys with cascade delete
    follower_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False)
    followed_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False)
    
    # Relationships
    follower = db.relationship('User', foreign_keys=[follower_id], backref='following')
    followed = db.relationship('User', foreign_keys=[followed_id], backref='followers')
    
    # Unique constraint and check constraint to prevent self-follow
    __table_args__ = (
        db.UniqueConstraint('follower_id', 'followed_id', name='unique_follow'),
        db.CheckConstraint('follower_id != followed_id', name='no_self_follow')
    )
    
    def __repr__(self):
        return f'<UserFollow {self.follower_id} -> {self.followed_id}>'

class PostDraft(db.Model):
    """Draft posts for expert forum"""
    __tablename__ = 'post_draft'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200))
    content = db.Column(db.Text)
    category = db.Column(db.String(50))  # Legacy field
    main_category = db.Column(db.String(50))  # farming-crop-management, soil-environment, etc.
    subcategory = db.Column(db.String(50))  # crop-management, pest-control, etc.
    tags = db.Column(db.String(200))
    is_question = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Foreign Keys
    author_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
    # Relationships
    author = db.relationship('User', backref='post_drafts')
    
    def __repr__(self):
        return f'<PostDraft {self.title or "Untitled"}>'

class ContentReport(db.Model):
    """Content reporting system"""
    __tablename__ = 'content_report'
    id = db.Column(db.Integer, primary_key=True)
    content_type = db.Column(db.String(10), nullable=False)  # 'post' or 'reply'
    content_id = db.Column(db.Integer, nullable=False)  # ID of post or reply (deprecated, use post_id/reply_id)
    reason = db.Column(db.String(50), nullable=False)
    description = db.Column(db.Text)
    status = db.Column(db.String(20), default='pending')  # pending, reviewed, resolved, dismissed
    resolution = db.Column(db.String(50))  # approved, locked, removed, dismissed
    moderator_notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    resolved_at = db.Column(db.DateTime)
    
    # Foreign Keys
    reporter_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    moderator_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    resolved_by_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    post_id = db.Column(db.Integer, db.ForeignKey('expert_post.id'))
    reply_id = db.Column(db.Integer, db.ForeignKey('expert_reply.id'))
    
    # Relationships
    reporter = db.relationship('User', foreign_keys=[reporter_id], backref='reports_made')
    moderator = db.relationship('User', foreign_keys=[moderator_id], backref='reports_handled')
    resolved_by = db.relationship('User', foreign_keys=[resolved_by_id], backref='reports_resolved')
    post = db.relationship('ExpertPost', backref='reports')
    reply = db.relationship('ExpertReply', backref='reports')
    
    def __repr__(self):
        return f'<ContentReport {self.content_type} {self.content_id}>'

class EditHistory(db.Model):
    """Track edit history for posts and replies"""
    __tablename__ = 'edit_history'
    id = db.Column(db.Integer, primary_key=True)
    content_type = db.Column(db.String(10), nullable=False)  # 'post' or 'reply'
    content_id = db.Column(db.Integer, nullable=False)  # ID of post or reply
    field_name = db.Column(db.String(50), nullable=False)  # 'title', 'content', etc.
    old_value = db.Column(db.Text)
    new_value = db.Column(db.Text)
    edit_reason = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Foreign Keys
    editor_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
    # Relationships
    editor = db.relationship('User', backref='edit_history')
    
    def __repr__(self):
        return f'<EditHistory {self.content_type} {self.content_id} - {self.field_name}>'

class ForumNotification(db.Model):
    """Notification system for expert forum"""
    __tablename__ = 'forum_notification'
    id = db.Column(db.Integer, primary_key=True)
    notification_type = db.Column(db.String(50), nullable=False)  # reply, solution, upvote, follow, etc.
    title = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text, nullable=False)
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    read_at = db.Column(db.DateTime)
    
    # References to content (optional) with cascade delete
    post_id = db.Column(db.Integer, db.ForeignKey('expert_post.id', ondelete='CASCADE'))
    reply_id = db.Column(db.Integer, db.ForeignKey('expert_reply.id', ondelete='CASCADE'))
    
    # Foreign Keys with cascade delete
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='SET NULL'))
    
    # Relationships
    user = db.relationship('User', foreign_keys=[user_id], backref='notifications')
    sender = db.relationship('User', foreign_keys=[sender_id], backref='sent_notifications')
    post = db.relationship('ExpertPost', backref='notifications')
    reply = db.relationship('ExpertReply', backref='notifications')
    
    def __repr__(self):
        return f'<ForumNotification {self.notification_type} for user {self.user_id}>'

class PostLock(db.Model):
    """Post locking system"""
    __tablename__ = 'post_lock'
    id = db.Column(db.Integer, primary_key=True)
    content_type = db.Column(db.String(10), default='post')  # 'post' or 'reply'
    reason = db.Column(db.String(200), nullable=False)
    lock_reason = db.Column(db.String(200))  # Alias for reason
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    locked_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime)  # Optional expiration
    
    # Foreign Keys
    post_id = db.Column(db.Integer, db.ForeignKey('expert_post.id'), nullable=False)
    moderator_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    locked_by_id = db.Column(db.Integer, db.ForeignKey('user.id'))  # Alias for moderator_id
    
    # Relationships
    post = db.relationship('ExpertPost', backref='locks')
    moderator = db.relationship('User', foreign_keys=[moderator_id], backref='post_locks_created')
    locked_by = db.relationship('User', foreign_keys=[locked_by_id], backref='content_locked')
    
    @property
    def title(self):
        """Get title from locked post"""
        return self.post.title if self.post else 'Unknown'
    
    @property
    def content(self):
        """Get content from locked post"""
        return self.post.content if self.post else ''
    
    def __repr__(self):
        return f'<PostLock post {self.post_id}>'

class CropSuggestionHistory(db.Model):
    """Store user's crop suggestion queries and results"""
    __tablename__ = 'crop_suggestion_history'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
    # Input parameters
    location = db.Column(db.String(200))
    soil_type = db.Column(db.String(100))
    soil_ph = db.Column(db.Float)
    water_source = db.Column(db.String(100))
    climate_data = db.Column(db.Text)  # JSON string
    fertilizer_availability = db.Column(db.String(200))
    budget_preference = db.Column(db.String(100))
    season = db.Column(db.String(50))
    
    # Results
    suggestions = db.Column(db.Text)  # JSON string of all suggestions
    top_suggestion = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    user = db.relationship('User', backref='crop_suggestions')
    
    def __repr__(self):
        return f'<CropSuggestionHistory {self.user_id} - {self.top_suggestion}>'

class CropSuggestionComparison(db.Model):
    """Store crop comparison data"""
    __tablename__ = 'crop_suggestion_comparison'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    history_id = db.Column(db.Integer, db.ForeignKey('crop_suggestion_history.id'), nullable=False)
    
    crop_names = db.Column(db.Text)  # JSON array of crop names being compared
    comparison_data = db.Column(db.Text)  # JSON of detailed comparison
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    user = db.relationship('User', backref='crop_comparisons')
    history = db.relationship('CropSuggestionHistory', backref='comparisons')
    
    def __repr__(self):
        return f'<CropSuggestionComparison {self.user_id}>'

class CropComparisonHistory(db.Model):
    """Store standalone crop comparison history"""
    __tablename__ = 'crop_comparison_history'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
    # Comparison inputs
    crop_names = db.Column(db.Text, nullable=False)  # JSON array of crop names
    comparison_factor = db.Column(db.String(100))  # What factor was used for comparison
    
    # AI Results
    comparison_result = db.Column(db.Text)  # Full JSON comparison result
    best_crop = db.Column(db.String(100))  # Name of the recommended crop
    overall_recommendation = db.Column(db.Text)  # AI's overall recommendation
    
    # Metadata
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = db.relationship('User', backref='comparison_history')
    
    def get_crop_names_list(self):
        """Return crop names as a Python list"""
        try:
            if not self.crop_names:
                return []
            names = json.loads(self.crop_names)
            return names if isinstance(names, list) else []
        except (json.JSONDecodeError, TypeError) as e:
            logger.error(f"Error parsing crop names for comparison {self.id}: {str(e)}")
            return []
    
    def get_comparison_data(self):
        """Return comparison result as Python dict"""
        try:
            if not self.comparison_result:
                return {}
            data = json.loads(self.comparison_result)
            return data if isinstance(data, dict) else {}
        except (json.JSONDecodeError, TypeError) as e:
            app.logger.error(f"Error parsing comparison data for comparison {self.id}: {str(e)}")
            return {}
    
    def __repr__(self):
        return f'<CropComparisonHistory {self.user_id} - {self.best_crop}>'

class PestDiseaseAnalysis(db.Model):
    """Store pest and disease analysis results"""
    __tablename__ = 'pest_disease_analysis'
    
    # Primary Key
    id = db.Column(db.Integer, primary_key=True)
    
    # Foreign Keys
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    crop_id = db.Column(db.Integer, db.ForeignKey('crop.id'), nullable=True)
    
    # Input Data
    crop_type = db.Column(db.String(100), nullable=False)
    symptoms_description = db.Column(db.Text, nullable=True)
    plant_stage = db.Column(db.String(50), nullable=True)
    urgency_level = db.Column(db.String(20), nullable=True)
    location = db.Column(db.String(200), nullable=True)
    image_path = db.Column(db.String(500), nullable=True)
    
    # Analysis Results
    identified_issue = db.Column(db.String(200), nullable=True)
    issue_type = db.Column(db.String(50), nullable=True)  # 'pest', 'disease', 'deficiency', 'unknown'
    confidence_score = db.Column(db.Float, nullable=True)
    severity_level = db.Column(db.String(20), nullable=True)  # 'low', 'medium', 'high', 'critical'
    
    # Recommendations (stored as JSON)
    treatment_recommendations = db.Column(db.Text, nullable=True)  # JSON string
    preventive_measures = db.Column(db.Text, nullable=True)  # JSON string
    additional_diagnoses = db.Column(db.Text, nullable=True)  # JSON array of alternative diagnoses
    
    # Metadata
    analysis_mode = db.Column(db.String(20), nullable=False)  # 'image', 'symptoms', 'combined'
    ai_model_used = db.Column(db.String(50), default='gemini-2.5-flash-lite')
    analysis_status = db.Column(db.String(20), default='completed')  # 'pending', 'completed', 'failed'
    error_message = db.Column(db.Text, nullable=True)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = db.relationship('User', backref='pest_analyses')
    crop = db.relationship('Crop', backref='pest_analyses')
    
    def get_treatment_recommendations(self):
        """Return treatment recommendations as Python dict"""
        try:
            if not self.treatment_recommendations:
                return {}
            data = json.loads(self.treatment_recommendations)
            return data if isinstance(data, dict) else {}
        except (json.JSONDecodeError, TypeError) as e:
            logger.error(f"Error parsing treatment recommendations for analysis {self.id}: {str(e)}")
            return {}
    
    def get_preventive_measures(self):
        """Return preventive measures as Python list"""
        try:
            if not self.preventive_measures:
                return []
            data = json.loads(self.preventive_measures)
            return data if isinstance(data, list) else []
        except (json.JSONDecodeError, TypeError) as e:
            logger.error(f"Error parsing preventive measures for analysis {self.id}: {str(e)}")
            return []
    
    def get_additional_diagnoses(self):
        """Return additional diagnoses as Python list"""
        try:
            if not self.additional_diagnoses:
                return []
            data = json.loads(self.additional_diagnoses)
            return data if isinstance(data, list) else []
        except (json.JSONDecodeError, TypeError) as e:
            logger.error(f"Error parsing additional diagnoses for analysis {self.id}: {str(e)}")
            return []
    
    def __repr__(self):
        return f'<PestDiseaseAnalysis {self.id} - {self.identified_issue}>'


# ============================================================================
# PRODUCT RATING SYSTEM MODELS
# ============================================================================

class ProductRating(db.Model):
    """Product ratings and reviews"""
    __tablename__ = 'product_rating'
    
    # Primary Key
    id = db.Column(db.Integer, primary_key=True)
    
    # Rating Data
    rating = db.Column(db.Integer, nullable=False)  # 1-5 stars
    review_text = db.Column(db.Text, nullable=True)  # Optional review
    
    # Metadata
    is_verified_purchase = db.Column(db.Boolean, default=True)
    helpful_count = db.Column(db.Integer, default=0)
    is_flagged = db.Column(db.Boolean, default=False)
    is_hidden = db.Column(db.Boolean, default=False)  # Admin moderation
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    edited_at = db.Column(db.DateTime, nullable=True)
    
    # Foreign Keys
    buyer_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('crop.id'), nullable=False)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=False)
    
    # Relationships
    buyer = db.relationship('User', foreign_keys=[buyer_id], backref='product_ratings_given')
    product = db.relationship('Crop', backref='ratings')
    order = db.relationship('Order', backref=db.backref('product_rating', uselist=False))
    seller_response = db.relationship('SellerResponse', backref='rating', uselist=False, cascade='all, delete-orphan')
    helpful_votes = db.relationship('RatingHelpfulVote', backref='rating', cascade='all, delete-orphan')
    flags = db.relationship('RatingFlag', backref='rating', cascade='all, delete-orphan')
    audit_logs = db.relationship('RatingAuditLog', backref='rating', cascade='all, delete-orphan')
    
    # Constraints
    __table_args__ = (
        db.UniqueConstraint('order_id', name='unique_rating_per_order'),
        db.CheckConstraint('rating >= 1 AND rating <= 5', name='valid_rating_range'),
        db.Index('idx_product_ratings', 'product_id', 'created_at'),
        db.Index('idx_buyer_ratings', 'buyer_id'),
        db.Index('idx_flagged', 'is_flagged', 'is_hidden'),
    )
    
    def __repr__(self):
        return f'<ProductRating {self.id} - {self.rating} stars>'


class SellerResponse(db.Model):
    """Seller responses to product ratings"""
    __tablename__ = 'seller_response'
    
    id = db.Column(db.Integer, primary_key=True)
    response_text = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Foreign Keys
    rating_id = db.Column(db.Integer, db.ForeignKey('product_rating.id'), nullable=False, unique=True)
    seller_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
    # Relationships
    seller = db.relationship('User', foreign_keys=[seller_id], backref='seller_responses')
    
    def __repr__(self):
        return f'<SellerResponse {self.id} to rating {self.rating_id}>'


class RatingHelpfulVote(db.Model):
    """Track helpful votes on ratings"""
    __tablename__ = 'rating_helpful_vote'
    
    id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Foreign Keys
    rating_id = db.Column(db.Integer, db.ForeignKey('product_rating.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
    # Relationships
    user = db.relationship('User', backref='helpful_votes')
    
    # Constraints
    __table_args__ = (
        db.UniqueConstraint('rating_id', 'user_id', name='unique_helpful_vote'),
    )
    
    def __repr__(self):
        return f'<RatingHelpfulVote {self.id} by user {self.user_id}>'


class RatingFlag(db.Model):
    """Track flagged ratings for moderation"""
    __tablename__ = 'rating_flag'
    
    id = db.Column(db.Integer, primary_key=True)
    reason = db.Column(db.String(50), nullable=False)  # spam, inappropriate, etc.
    description = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), default='pending')  # pending, reviewed, resolved
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    resolved_at = db.Column(db.DateTime, nullable=True)
    
    # Foreign Keys
    rating_id = db.Column(db.Integer, db.ForeignKey('product_rating.id'), nullable=False)
    flagger_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    moderator_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    
    # Relationships
    flagger = db.relationship('User', foreign_keys=[flagger_id], backref='rating_flags_made')
    moderator = db.relationship('User', foreign_keys=[moderator_id], backref='rating_flags_handled')
    
    # Indexes
    __table_args__ = (
        db.Index('idx_pending_flags', 'status', 'created_at'),
    )
    
    def __repr__(self):
        return f'<RatingFlag {self.id} - {self.reason}>'


class SellerReputation(db.Model):
    """Aggregated seller reputation metrics"""
    __tablename__ = 'seller_reputation'
    
    id = db.Column(db.Integer, primary_key=True)
    
    # Reputation Metrics
    average_rating = db.Column(db.Float, default=0.0)
    total_ratings = db.Column(db.Integer, default=0)
    five_star_count = db.Column(db.Integer, default=0)
    four_star_count = db.Column(db.Integer, default=0)
    three_star_count = db.Column(db.Integer, default=0)
    two_star_count = db.Column(db.Integer, default=0)
    one_star_count = db.Column(db.Integer, default=0)
    
    # Timestamps
    last_updated = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Foreign Keys
    seller_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, unique=True)
    
    # Relationships
    seller = db.relationship('User', backref=db.backref('reputation', uselist=False))
    
    # Indexes
    __table_args__ = (
        db.Index('idx_top_sellers', 'average_rating', 'total_ratings'),
    )
    
    def __repr__(self):
        return f'<SellerReputation seller {self.seller_id} - {self.average_rating:.2f}>'


class RatingAuditLog(db.Model):
    """Audit trail for rating operations"""
    __tablename__ = 'rating_audit_log'
    
    id = db.Column(db.Integer, primary_key=True)
    action = db.Column(db.String(50), nullable=False)  # create, update, delete, hide, etc.
    old_value = db.Column(db.Text, nullable=True)
    new_value = db.Column(db.Text, nullable=True)
    ip_address = db.Column(db.String(45), nullable=True)
    user_agent = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Foreign Keys
    rating_id = db.Column(db.Integer, db.ForeignKey('product_rating.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
    # Relationships
    user = db.relationship('User', backref='rating_audit_logs')
    
    # Indexes
    __table_args__ = (
        db.Index('idx_audit_rating', 'rating_id', 'created_at'),
        db.Index('idx_audit_user', 'user_id', 'created_at'),
    )
    
    def __repr__(self):
        return f'<RatingAuditLog {self.action} on rating {self.rating_id}>'


class RatingNotificationPreference(db.Model):
    """
    User preferences for rating notifications
    Requirement 10.4: Allow users to configure notification preferences
    """
    __tablename__ = 'rating_notification_preference'
    
    id = db.Column(db.Integer, primary_key=True)
    
    # Notification preferences
    notify_new_rating = db.Column(db.Boolean, default=True)  # For sellers
    notify_seller_response = db.Column(db.Boolean, default=True)  # For buyers
    notify_helpful_milestone = db.Column(db.Boolean, default=True)  # For buyers
    notify_rating_removed = db.Column(db.Boolean, default=True)  # For all users
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Foreign Keys
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, unique=True)
    
    # Relationships
    user = db.relationship('User', backref=db.backref('rating_notification_preference', uselist=False))
    
    def __repr__(self):
        return f'<RatingNotificationPreference user {self.user_id}>'


# ============================================================================
# ADMIN PANEL ENHANCEMENT MODELS
# ============================================================================

class Feedback(db.Model):
    """User feedback and support requests"""
    __tablename__ = 'feedback'
    
    id = db.Column(db.Integer, primary_key=True)
    subject = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), default='pending')  # pending, responded, resolved
    admin_response = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    responded_at = db.Column(db.DateTime)
    
    # Foreign Keys
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    responded_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    
    # Relationships
    user = db.relationship('User', foreign_keys=[user_id], backref='feedback_submitted')
    responder = db.relationship('User', foreign_keys=[responded_by], backref='feedback_responses')
    
    # Indexes
    __table_args__ = (
        db.Index('idx_feedback_status', 'status', 'created_at'),
        db.Index('idx_feedback_user', 'user_id'),
    )
    
    def __repr__(self):
        return f'<Feedback {self.id} - {self.subject}>'


class AdminNotification(db.Model):
    """Admin announcements and notifications to users"""
    __tablename__ = 'admin_notification'
    
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text, nullable=False)
    target_audience = db.Column(db.String(20), nullable=False)  # all, farmers, buyers
    notification_type = db.Column(db.String(20), default='announcement')  # announcement, alert, info
    is_active = db.Column(db.Boolean, default=True)
    send_email = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime)
    
    # Foreign Keys
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
    # Relationships
    creator = db.relationship('User', backref='admin_notifications_created')
    
    # Indexes
    __table_args__ = (
        db.Index('idx_active_notifications', 'is_active', 'expires_at'),
        db.Index('idx_notification_audience', 'target_audience', 'created_at'),
    )
    
    def __repr__(self):
        return f'<AdminNotification {self.id} - {self.title}>'


class SystemSettings(db.Model):
    """System configuration settings with encryption support"""
    __tablename__ = 'system_settings'
    
    id = db.Column(db.Integer, primary_key=True)
    setting_key = db.Column(db.String(100), unique=True, nullable=False)
    setting_value = db.Column(db.Text)
    setting_type = db.Column(db.String(20), default='string')  # string, integer, boolean, json, encrypted
    description = db.Column(db.String(500))
    is_sensitive = db.Column(db.Boolean, default=False)  # Mark sensitive fields for encryption
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Foreign Keys
    updated_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    
    # Relationships
    updater = db.relationship('User', backref='system_settings_updated')
    
    # Indexes
    __table_args__ = (
        db.Index('idx_setting_key', 'setting_key'),
    )
    
    # Sensitive keys that should be encrypted
    SENSITIVE_KEYS = [
        'razorpay_key_secret',
        'gemini_api_key',
        'weather_api_key',
        'smtp_password',
        'database_password',
        'encryption_key',
        'jwt_secret'
    ]
    
    def get_value(self, decrypt=True):
        """
        Parse and return the setting value based on type
        
        Args:
            decrypt (bool): Whether to decrypt encrypted values
        """
        if not self.setting_value:
            return None
        
        try:
            # Handle encrypted values
            if self.setting_type == 'encrypted' or self.is_sensitive:
                if decrypt:
                    try:
                        from encryption_utils import decrypt_value
                        decrypted = decrypt_value(self.setting_value)
                        return decrypted if decrypted else self.setting_value
                    except:
                        # Return raw value if decryption fails (legacy data)
                        return self.setting_value
                else:
                    return self.setting_value
            
            # Handle other types
            if self.setting_type == 'integer':
                return int(self.setting_value)
            elif self.setting_type == 'boolean':
                return self.setting_value.lower() in ('true', '1', 'yes')
            elif self.setting_type == 'json':
                return json.loads(self.setting_value)
            else:
                return self.setting_value
        except (ValueError, json.JSONDecodeError) as e:
            logger.error(f"Error parsing setting {self.setting_key}: {str(e)}")
            return self.setting_value
    
    def set_value(self, value, encrypt=None):
        """
        Set the setting value with proper type conversion and optional encryption
        
        Args:
            value: Value to set
            encrypt (bool): Whether to encrypt (auto-detects if None)
        """
        # Auto-detect if should encrypt
        if encrypt is None:
            encrypt = self.setting_key in self.SENSITIVE_KEYS or self.is_sensitive
        
        # Encrypt if needed
        if encrypt and value:
            try:
                from encryption_utils import encrypt_value
                self.setting_value = encrypt_value(str(value))
                self.setting_type = 'encrypted'
                self.is_sensitive = True
                return
            except Exception as e:
                logger.error(f"Encryption failed for {self.setting_key}: {str(e)}")
                # Fall through to normal storage
        
        # Normal storage
        if self.setting_type == 'json':
            self.setting_value = json.dumps(value)
        else:
            self.setting_value = str(value)
    
    def __repr__(self):
        return f'<SystemSettings {self.setting_key}>'


class SettingsBackup(db.Model):
    """Backup of system settings for rollback capability"""
    __tablename__ = 'settings_backup'
    
    id = db.Column(db.Integer, primary_key=True)
    description = db.Column(db.String(500))
    backup_data = db.Column(db.Text, nullable=False)  # JSON dump of all settings
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Foreign Keys
    admin_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
    # Relationships
    admin = db.relationship('User', backref='settings_backups')
    
    # Indexes
    __table_args__ = (
        db.Index('idx_backup_created', 'created_at'),
    )
    
    def __repr__(self):
        return f'<SettingsBackup {self.id}: {self.description}>'


class AdminActionLog(db.Model):
    """Audit trail for admin actions"""
    __tablename__ = 'admin_action_log'
    
    id = db.Column(db.Integer, primary_key=True)
    action_type = db.Column(db.String(50), nullable=False)  # approve_crop, reject_crop, update_order, etc.
    target_type = db.Column(db.String(50))  # crop, order, user, feedback, etc.
    target_id = db.Column(db.Integer)
    description = db.Column(db.Text)
    ip_address = db.Column(db.String(45))
    user_agent = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Foreign Keys
    admin_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
    # Relationships
    admin = db.relationship('User', backref='admin_actions')
    
    # Indexes
    __table_args__ = (
        db.Index('idx_admin_actions', 'admin_id', 'created_at'),
        db.Index('idx_action_type', 'action_type', 'created_at'),
        db.Index('idx_target', 'target_type', 'target_id'),
    )
    
    def __repr__(self):
        return f'<AdminActionLog {self.action_type} by admin {self.admin_id}>'


class SellerKYC(db.Model):
    """Model for storing seller KYC verification data"""
    __tablename__ = 'seller_kyc'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
    # Encrypted sensitive fields
    aadhaar_no_encrypted = db.Column(db.LargeBinary, nullable=False)
    pan_no_encrypted = db.Column(db.LargeBinary, nullable=False)
    bank_account_encrypted = db.Column(db.LargeBinary, nullable=False)
    ifsc = db.Column(db.String(11), nullable=False)
    
    # Document storage (JSON array of file paths)
    document_paths = db.Column(db.JSON, nullable=False)
    # Example: {"aadhaar_front": "path/to/file", "aadhaar_back": "path/to/file", "pan": "path/to/file", "land_proof": "path/to/file"}
    
    # Status and verification
    status = db.Column(db.String(20), default='pending', nullable=False)  # pending, verified, rejected
    rejection_reason = db.Column(db.Text, nullable=True)
    
    # Archive flag for resubmissions
    is_archived = db.Column(db.Boolean, default=False, nullable=False)
    
    # Admin tracking
    verified_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    verified_at = db.Column(db.DateTime, nullable=True)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationships
    user = db.relationship('User', foreign_keys=[user_id], backref='kyc_records')
    verifier = db.relationship('User', foreign_keys=[verified_by], backref='kyc_verifications')
    
    # Indexes
    __table_args__ = (
        db.Index('idx_kyc_status', 'status'),
        db.Index('idx_kyc_user', 'user_id'),
        db.Index('idx_kyc_created', 'created_at'),
        db.Index('idx_kyc_archived', 'is_archived'),
        db.Index('idx_kyc_user_archived', 'user_id', 'is_archived'),
    )
    
    def __repr__(self):
        return f'<SellerKYC user_id={self.user_id} status={self.status}>'


class KYCAuditLog(db.Model):
    """Model for auditing KYC actions"""
    __tablename__ = 'kyc_audit_log'
    
    id = db.Column(db.Integer, primary_key=True)
    kyc_id = db.Column(db.Integer, db.ForeignKey('seller_kyc.id'), nullable=False)
    action = db.Column(db.String(50), nullable=False)  # submitted, approved, rejected, resubmitted
    performed_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    old_status = db.Column(db.String(20), nullable=True)
    new_status = db.Column(db.String(20), nullable=False)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    kyc_record = db.relationship('SellerKYC', backref='audit_logs')
    user = db.relationship('User', backref='kyc_actions')
    
    def __repr__(self):
        return f'<KYCAuditLog kyc_id={self.kyc_id} action={self.action}>'
