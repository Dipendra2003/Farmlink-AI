from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import StringField, TextAreaField, FloatField, SelectField, DateField, PasswordField, SubmitField, HiddenField, BooleanField, IntegerField, DecimalField
from wtforms.validators import DataRequired, Email, Length, NumberRange, EqualTo, ValidationError, Optional
from models import User
from flask_login import current_user

class AdminCredentialsForm(FlaskForm):
    current_password = PasswordField('Current Password', validators=[
        DataRequired(message='Current password is required')
    ])
    new_username = StringField('New Username', validators=[
        DataRequired(message='New username is required'),
        Length(min=4, max=30, message='Username must be between 4 and 30 characters')
    ])
    new_password = PasswordField('New Password', validators=[
        DataRequired(message='New password is required'),
        Length(min=8, message='Password must be at least 8 characters long')
    ])
    confirm_password = PasswordField('Confirm New Password', validators=[
        DataRequired(),
        EqualTo('new_password', message='Passwords must match')
    ])
    submit = SubmitField('Update Credentials')

    def validate_current_password(self, field):
        if not current_user.check_password(field.data):
            raise ValidationError('Current password is incorrect')

class OrderForm(FlaskForm):
    quantity_requested = FloatField('Quantity', 
        validators=[DataRequired(), NumberRange(min=0.1)],
        render_kw={"placeholder": "Enter quantity"}
    )
    delivery_address = TextAreaField('Delivery Address',
        validators=[DataRequired()],
        render_kw={"placeholder": "Enter complete delivery address"}
    )
    delivery_method = SelectField('Delivery Method',
        choices=[
            ('standard', 'Standard Delivery (3-5 days)'),
            ('express', 'Express Delivery (1-2 days)')
        ],
        validators=[DataRequired()]
    )
    notes = TextAreaField('Additional Notes',
        validators=[Optional()],
        render_kw={"placeholder": "Any special instructions for delivery?"}
    )
    submit = SubmitField('Place Order')

# ContactForm moved to line 218 - this is a duplicate, removing

class RegistrationForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=4, max=20)])
    email = StringField('Email', validators=[DataRequired(), Email()])
    full_name = StringField('Full Name', validators=[DataRequired(), Length(min=2, max=100)])
    phone = StringField('Phone Number', validators=[DataRequired(), Length(min=10, max=15)])
    location = StringField('Location', validators=[DataRequired(), Length(min=2, max=100)])
    role = SelectField('I am a', choices=[('farmer', 'Farmer'), ('buyer', 'Buyer')], validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=6)])
    password2 = PasswordField('Confirm Password', validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField('Register')
    
    def validate_username(self, username):
        user = User.query.filter_by(username=username.data).first()
        if user:
            raise ValidationError('Username already exists. Please choose a different one.')
    
    def validate_email(self, email):
        user = User.query.filter_by(email=email.data).first()
        if user:
            raise ValidationError('Email already registered. Please use a different email.')

class LoginForm(FlaskForm):
    identifier = StringField('Username / Email / Phone', validators=[
        DataRequired(message='Please enter your username, email, or phone number')
    ])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Sign In')

from flask_wtf.file import FileField, FileAllowed

class CropForm(FlaskForm):
    name = StringField('Crop Name', validators=[DataRequired(), Length(min=2, max=100)])
    category = SelectField('Category', choices=[], validators=[DataRequired()])
    
    def __init__(self, *args, **kwargs):
        super(CropForm, self).__init__(*args, **kwargs)
        from category_config import get_crop_categories
        self.category.choices = get_crop_categories()
    description = TextAreaField('Description', validators=[Length(max=500)])
    quantity = FloatField('Quantity', validators=[DataRequired(), NumberRange(min=0.1)])
    unit = SelectField('Unit', choices=[
        ('kg', 'Kilograms'),
        ('tonnes', 'Tonnes'),
        ('quintal', 'Quintal'),
        ('bags', 'Bags')
    ], validators=[DataRequired()])
    price_per_unit = FloatField('Price per Unit (₹)', validators=[DataRequired(), NumberRange(min=0.01)])
    harvest_date = DateField('Harvest Date')
    location = StringField('Location', validators=[DataRequired(), Length(min=2, max=100)])
    image = FileField('Crop Image', 
        validators=[
            FileAllowed(['jpg', 'jpeg', 'png', 'gif', 'webp'], 'Only image files are allowed!')
        ],
        description="Upload a clear, high-quality image of your crop"
    )
    submit = SubmitField('Save Crop')

class MessageForm(FlaskForm):
    """Form for sending messages between users"""
    recipient_id = HiddenField('Recipient ID', validators=[DataRequired()])
    subject = StringField('Subject', validators=[
        DataRequired(message='Subject is required'),
        Length(min=2, max=200, message='Subject must be between 2 and 200 characters')
    ])
    content = TextAreaField('Message', validators=[
        DataRequired(message='Message content is required'),
        Length(min=10, max=5000, message='Message must be between 10 and 5000 characters')
    ])
    submit = SubmitField('Send Message')

class ProfileForm(FlaskForm):
    full_name = StringField('Full Name', validators=[DataRequired(), Length(min=2, max=100)])
    phone = StringField('Phone Number', validators=[DataRequired(), Length(min=10, max=15)])
    location = StringField('Location', validators=[DataRequired(), Length(min=2, max=100)])
    profile_picture = FileField('Profile Picture', validators=[
        FileAllowed(['jpg', 'jpeg', 'png', 'gif'], 'Only image files are allowed!')
    ])
    submit = SubmitField('Update Profile')

class SearchForm(FlaskForm):
    query = StringField('Search', validators=[Length(max=100)])
    category = SelectField('Category', choices=[
        ('all', 'All Categories'),
        ('grains', 'Grains & Cereals'),
        ('vegetables', 'Vegetables'),
        ('fruits', 'Fruits'),
        ('pulses', 'Pulses'),
        ('spices', 'Spices'),
        ('others', 'Others')
    ])
    location = StringField('Location', validators=[Length(max=100)])
    min_price = FloatField('Min Price (₹)', validators=[NumberRange(min=0)])
    max_price = FloatField('Max Price (₹)', validators=[NumberRange(min=0)])
    submit = SubmitField('Search')

# New Advanced Forms
class ExpertPostForm(FlaskForm):
    title = StringField('Title', validators=[DataRequired(), Length(min=5, max=200)])
    content = TextAreaField('Content', validators=[DataRequired(), Length(min=20, max=5000)])
    main_category = SelectField('Main Category', choices=[], validators=[DataRequired()])
    subcategory = SelectField('Subcategory', choices=[], validators=[DataRequired()])
    tags = StringField('Tags (comma separated)', validators=[Length(max=200)])
    is_question = BooleanField('This is a question')
    submit = SubmitField('Post')
    
    def __init__(self, *args, **kwargs):
        super(ExpertPostForm, self).__init__(*args, **kwargs)
        from category_config import get_main_categories
        self.main_category.choices = [('', 'Select Main Category')] + get_main_categories()
        self.subcategory.choices = [('', 'Select Subcategory')]

class ReportContentForm(FlaskForm):
    reason = SelectField('Reason for Report', choices=[
        ('spam', 'Spam'),
        ('inappropriate', 'Inappropriate Content'),
        ('harassment', 'Harassment'),
        ('misinformation', 'Misinformation'),
        ('off-topic', 'Off-topic'),
        ('other', 'Other')
    ], validators=[DataRequired()])
    details = TextAreaField('Additional Details (optional)', validators=[Length(max=500)])
    submit = SubmitField('Submit Report')

class RatingForm(FlaskForm):
    rating = IntegerField('Rating (1-5 stars)', validators=[DataRequired(), NumberRange(min=1, max=5)])
    feedback = TextAreaField('Feedback', validators=[Length(max=500)])
    submit = SubmitField('Submit Rating')

class ForgotPasswordForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    reset_method = SelectField('Reset Method', 
                             choices=[('link', 'Reset via Email Link'), 
                                    ('otp', 'Reset via OTP Code')],
                             validators=[DataRequired()])
    submit = SubmitField('Continue')

class ResetPasswordForm(FlaskForm):
    password = PasswordField('New Password', validators=[DataRequired(), Length(min=6)])
    password2 = PasswordField('Confirm Password', validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField('Reset Password')

class ChangePasswordForm(FlaskForm):
    old_password = PasswordField('Current Password', validators=[DataRequired()])
    new_password = PasswordField('New Password', validators=[
        DataRequired(),
        Length(min=8, message='Password must be at least 8 characters long')
    ])
    confirm_password = PasswordField('Confirm New Password', validators=[
        DataRequired(),
        EqualTo('new_password', message='Passwords must match')
    ])
    submit = SubmitField('Change Password')

class OTPVerificationForm(FlaskForm):
    otp = StringField('Verification Code', validators=[DataRequired(), Length(min=6, max=6)])
    submit = SubmitField('Verify')

class ContactForm(FlaskForm):
    name = StringField('Your Name', validators=[
        DataRequired(message="Please enter your name"),
        Length(min=2, max=100, message="Name must be between 2 and 100 characters")
    ])
    email = StringField('Email Address', validators=[
        DataRequired(message="Please enter your email address"),
        Email(message="Please enter a valid email address")
    ])
    subject = StringField('Subject', validators=[
        DataRequired(message="Please enter a subject"),
        Length(min=5, max=200, message="Subject must be between 5 and 200 characters")
    ])
    message = TextAreaField('Message', validators=[
        DataRequired(message="Please enter your message"),
        Length(min=10, max=2000, message="Message must be between 10 and 2000 characters")
    ])
    submit = SubmitField('Send Message')
    
class ExpertReplyForm(FlaskForm):
    content = TextAreaField('Your Reply', validators=[
        DataRequired(),
        Length(min=20, max=2000, message='Reply must be between 20 and 2000 characters')
    ])
    expertise = StringField('Your Expertise/Credentials (optional)', validators=[
        Length(max=200)
    ])
    submit = SubmitField('Post Reply')

class PostDraftForm(FlaskForm):
    """Form for saving post drafts"""
    title = StringField('Title', validators=[
        Length(max=200)
    ])
    content = TextAreaField('Content')
    main_category = SelectField('Main Category', choices=[])
    subcategory = SelectField('Subcategory', choices=[])
    tags = StringField('Tags (comma separated)')
    is_question = BooleanField('This is a question')
    submit = SubmitField('Save Draft')
    
    def __init__(self, *args, **kwargs):
        super(PostDraftForm, self).__init__(*args, **kwargs)
        from category_config import get_main_categories
        self.main_category.choices = [('', 'Select Main Category')] + get_main_categories()
        self.subcategory.choices = [('', 'Select Subcategory')]

class AdvancedSearchForm(FlaskForm):
    """Advanced search form for expert forum"""
    query = StringField('Search Keywords')
    main_category = SelectField('Main Category', choices=[])
    subcategory = SelectField('Subcategory', choices=[])
    post_type = SelectField('Post Type', choices=[
        ('all', 'All Posts'),
        ('questions', 'Questions Only'),
        ('discussions', 'Discussions Only'),
        ('answered', 'Answered Questions'),
        ('unanswered', 'Unanswered Questions')
    ])
    date_range = SelectField('Date Range', choices=[
        ('all', 'All Time'),
        ('today', 'Today'),
        ('week', 'This Week'),
        ('month', 'This Month'),
        ('year', 'This Year')
    ])
    sort_by = SelectField('Sort By', choices=[
        ('recent', 'Most Recent'),
        ('popular', 'Most Popular'),
        ('views', 'Most Viewed'),
        ('replies', 'Most Replies')
    ])
    submit = SubmitField('Search')
    
    def __init__(self, *args, **kwargs):
        super(AdvancedSearchForm, self).__init__(*args, **kwargs)
        from category_config import get_main_categories
        self.main_category.choices = [('all', 'All Categories')] + get_main_categories()
        self.subcategory.choices = [('all', 'All Subcategories')]

class NotificationPreferencesForm(FlaskForm):
    """Form for managing notification preferences"""
    email_replies = BooleanField('Email me when someone replies to my posts')
    email_solutions = BooleanField('Email me when my reply is marked as solution')
    email_upvotes = BooleanField('Email me when my posts/replies are upvoted')
    email_follows = BooleanField('Email me when someone follows me')
    email_weekly_digest = BooleanField('Send me weekly digest of trending topics')
    browser_notifications = BooleanField('Enable browser notifications')
    submit = SubmitField('Update Preferences')

class ModerationForm(FlaskForm):
    """Form for content moderation actions"""
    action = SelectField('Action', choices=[
        ('approve', 'Approve Content'),
        ('hide', 'Hide Content'),
        ('delete', 'Delete Content'),
        ('warn_user', 'Warn User'),
        ('suspend_user', 'Suspend User'),
        ('lock_post', 'Lock Post')
    ])
    reason = TextAreaField('Reason', validators=[
        DataRequired(),
        Length(min=10, max=500)
    ])
    duration = SelectField('Duration (for suspensions/locks)', choices=[
        ('1_day', '1 Day'),
        ('3_days', '3 Days'),
        ('1_week', '1 Week'),
        ('1_month', '1 Month'),
        ('permanent', 'Permanent')
    ])
    submit = SubmitField('Take Action')

# ContactForm is defined above at line 218 - this duplicate is incomplete, removing
# class ContactForm(FlaskForm):
#     email = StringField('Email', validators=[DataRequired(), Email()])
#     subject = StringField('Subject', validators=[DataRequired(), Length(min=5, max=200)])
#     message = TextAreaField('Message', validators=[DataRequired(), Length(min=20, max=1000)])
#     submit = SubmitField('Send Message')

class LearningArticleForm(FlaskForm):
    title = StringField('Title', validators=[DataRequired(), Length(min=5, max=200)])
    content = TextAreaField('Content', validators=[DataRequired(), Length(min=50)])
    summary = StringField('Summary', validators=[Length(max=500)])
    category = SelectField('Category', choices=[
        ('farming-basics', 'Farming Basics'),
        ('crop-cultivation', 'Crop Cultivation'),
        ('pest-management', 'Pest Management'),
        ('soil-science', 'Soil Science'),
        ('irrigation-techniques', 'Irrigation Techniques'),
        ('sustainable-farming', 'Sustainable Farming'),
        ('agricultural-technology', 'Agricultural Technology'),
        ('market-trends', 'Market Trends')
    ], validators=[DataRequired()])
    difficulty_level = SelectField('Difficulty Level', choices=[
        ('beginner', 'Beginner'),
        ('intermediate', 'Intermediate'),
        ('advanced', 'Advanced')
    ], validators=[DataRequired()])
    reading_time = IntegerField('Reading Time (minutes)', validators=[NumberRange(min=1, max=60)])
    featured_image = StringField('Featured Image URL', validators=[Length(max=200)])
    tags = StringField('Tags (comma separated)', validators=[Length(max=200)])
    submit = SubmitField('Save Article')

# AI-Related Forms
class PestDiseaseDetectionForm(FlaskForm):
    """Form for AI-based pest and disease detection"""
    # Crop Selection
    crop_id = SelectField('Select Your Crop (Optional)', 
                         coerce=int, 
                         validators=[Optional()],
                         render_kw={'placeholder': 'Select from your registered crops'})
    
    crop_type = StringField('Crop Type', validators=[
        DataRequired(message='Crop type is required')
    ], render_kw={'placeholder': 'e.g., Tomato, Wheat, Rice'})
    
    # Image Upload
    plant_image = FileField('Plant Image', validators=[
        FileAllowed(['jpg', 'jpeg', 'png', 'webp'], 'Only image files are allowed (JPG, JPEG, PNG, WEBP)')
    ])
    
    # Symptom Description - No validators here, custom validation in validate() method
    symptoms_noticed = TextAreaField('Symptoms Noticed', validators=[
        Optional()
    ], render_kw={'placeholder': 'Describe any symptoms you have noticed (e.g., yellow leaves, spots, wilting)'})
    
    # Plant Stage
    plant_stage = SelectField('Plant Growth Stage', choices=[
        ('', 'Select plant stage'),
        ('seedling', 'Seedling'),
        ('vegetative', 'Vegetative Growth'),
        ('flowering', 'Flowering'),
        ('fruiting', 'Fruiting/Grain Formation'),
        ('mature', 'Mature')
    ], validators=[DataRequired(message='Please select plant growth stage')])
    
    # Urgency Level
    urgency = SelectField('Urgency Level', choices=[
        ('low', 'Low - Routine checkup'),
        ('medium', 'Medium - Some concerns'),
        ('high', 'High - Urgent issue'),
        ('critical', 'Critical - Emergency')
    ], default='medium', validators=[DataRequired()])
    
    # Location
    location = StringField('Location (State/District)', validators=[
        Optional(),
        Length(max=200)
    ], render_kw={'placeholder': 'e.g., Punjab, Ludhiana'})
    
    submit = SubmitField('Analyze Plant Health')
    
    def validate_plant_image(self, field):
        """Custom validator to check file size (max 10MB)"""
        if field.data:
            try:
                # Check file size
                field.data.seek(0, 2)  # Seek to end of file
                file_size = field.data.tell()  # Get current position (file size)
                field.data.seek(0)  # Reset to beginning
                
                max_size = 10 * 1024 * 1024  # 10MB in bytes
                if file_size > max_size:
                    raise ValidationError('File size must not exceed 10MB')
            except (AttributeError, IOError, OSError) as e:
                # Handle file operation errors gracefully
                raise ValidationError('Unable to validate file. Please try uploading again.')
            finally:
                # Ensure file pointer is reset even if an error occurs
                try:
                    if field.data and hasattr(field.data, 'seek'):
                        field.data.seek(0)
                except:
                    pass
    
    def validate(self, extra_validators=None):
        """Custom validation to ensure either image or symptoms is provided"""
        # Call parent validate() with extra_validators parameter
        if not super(PestDiseaseDetectionForm, self).validate(extra_validators=extra_validators):
            return False
        
        # Check if at least one of image or symptoms is provided
        has_image = self.plant_image.data is not None and self.plant_image.data
        symptoms_text = self.symptoms_noticed.data.strip() if self.symptoms_noticed.data else ''
        symptoms_length = len(symptoms_text)
        
        # Validate symptoms length if provided
        if symptoms_text and symptoms_length > 0:
            if symptoms_length < 10:
                self.symptoms_noticed.errors.append('Symptoms description must be at least 10 characters')
                if not has_image:
                    return False
            elif symptoms_length > 1000:
                self.symptoms_noticed.errors.append('Symptoms description must not exceed 1000 characters')
                return False
        
        # Check if at least one input method is provided
        has_valid_symptoms = symptoms_length >= 10
        
        if not has_image and not has_valid_symptoms:
            if symptoms_length == 0:
                # No image and no symptoms at all
                self.plant_image.errors.append('Please provide either a plant image or symptom description (minimum 10 characters)')
                self.symptoms_noticed.errors.append('Please provide either a plant image or symptom description (minimum 10 characters)')
            else:
                # Has some symptoms but too short, and no image
                self.plant_image.errors.append('Please provide a plant image since symptoms are too short')
            return False
        
        return True

class VoiceQueryForm(FlaskForm):
    query_text = TextAreaField('Your Question', validators=[Length(max=500)])
    language = SelectField('Language', choices=[
        ('english', 'English'),
        ('hindi', 'हिंदी (Hindi)'),
        ('hinglish', 'Hinglish'),
        ('punjabi', 'ਪੰਜਾਬੀ (Punjabi)'),
        ('bengali', 'বাংলা (Bengali)'),
        ('tamil', 'தமிழ் (Tamil)'),
        ('telugu', 'తెలుగు (Telugu)'),
        ('gujarati', 'ગુજરાતી (Gujarati)'),
        ('marathi', 'मराठी (Marathi)'),
        ('kannada', 'ಕನ್ನಡ (Kannada)'),
        ('urdu', 'اردو (Urdu)')
    ], default='english', validators=[DataRequired()])
    include_audio = BooleanField('Generate Audio Response')
    submit = SubmitField('Ask FarmLink AI')

class CropSuggestionForm(FlaskForm):
    """Comprehensive crop suggestion form"""
    # Location Information
    location = StringField('Location/Region', validators=[
        DataRequired(message='Location is required'),
        Length(min=2, max=200, message='Location must be between 2 and 200 characters')
    ], render_kw={"placeholder": "Enter village, city, state or GPS coordinates"})
    
    # Soil Information
    soil_type = SelectField('Soil Type', choices=[
        ('clay', 'Clay Soil'),
        ('loamy', 'Loamy Soil'),
        ('sandy', 'Sandy Soil'),
        ('black', 'Black Cotton Soil'),
        ('red', 'Red Soil'),
        ('alluvial', 'Alluvial Soil'),
        ('laterite', 'Laterite Soil'),
        ('peat', 'Peat Soil'),
        ('chalky', 'Chalky Soil'),
        ('saline', 'Saline Soil')
    ], validators=[DataRequired()])
    
    soil_ph = FloatField('Soil pH Value', validators=[
        DataRequired(message='Soil pH is required'),
        NumberRange(min=3.0, max=10.0, message='Soil pH must be between 3.0 and 10.0')
    ], render_kw={"placeholder": "Enter pH value (3.0 - 10.0)", "step": "0.1"})
    
    # Water Resources
    water_source = SelectField('Water Source', choices=[
        ('rainfed', 'Rainfed (Natural Rainfall)'),
        ('irrigated', 'Irrigated (Canal/Tube well)'),
        ('groundwater_high', 'Groundwater - High Level'),
        ('groundwater_medium', 'Groundwater - Medium Level'),
        ('groundwater_low', 'Groundwater - Low Level'),
        ('drip_irrigation', 'Drip Irrigation System'),
        ('sprinkler', 'Sprinkler Irrigation'),
        ('mixed', 'Mixed Sources')
    ], validators=[DataRequired()])
    
    # Climate Data
    temperature_range = SelectField('Temperature Range', choices=[
        ('very_cold', 'Very Cold (Below 10°C)'),
        ('cold', 'Cold (10°C - 20°C)'),
        ('moderate', 'Moderate (20°C - 30°C)'),
        ('warm', 'Warm (30°C - 35°C)'),
        ('hot', 'Hot (Above 35°C)')
    ], validators=[DataRequired()])
    
    rainfall_range = SelectField('Annual Rainfall', choices=[
        ('very_low', 'Very Low (Below 250mm)'),
        ('low', 'Low (250mm - 500mm)'),
        ('moderate', 'Moderate (500mm - 1000mm)'),
        ('high', 'High (1000mm - 1500mm)'),
        ('very_high', 'Very High (Above 1500mm)')
    ], validators=[DataRequired()])
    
    humidity_level = SelectField('Humidity Level', choices=[
        ('low', 'Low (Below 40%)'),
        ('moderate', 'Moderate (40% - 60%)'),
        ('high', 'High (60% - 80%)'),
        ('very_high', 'Very High (Above 80%)')
    ], validators=[DataRequired()])
    
    # Season
    season = SelectField('Growing Season', choices=[
        ('kharif', 'Kharif (Monsoon Season - June to October)'),
        ('rabi', 'Rabi (Winter Season - November to April)'),
        ('zaid', 'Zaid (Summer Season - March to June)'),
        ('year_round', 'Year Round Cultivation')
    ], validators=[DataRequired()])
    
    # Resources
    fertilizer_availability = SelectField('Fertilizer/Manure Availability', choices=[
        ('organic_only', 'Organic Only (Compost, Manure)'),
        ('chemical_only', 'Chemical Fertilizers Only'),
        ('mixed', 'Both Organic and Chemical'),
        ('limited', 'Limited Availability'),
        ('none', 'No External Fertilizers')
    ], validators=[DataRequired()])
    
    # Budget and Preferences
    budget_preference = SelectField('Budget & Cost Preference', choices=[
        ('low_cost', 'Low Cost - Budget Friendly'),
        ('moderate_cost', 'Moderate Cost - Balanced Approach'),
        ('high_yield', 'High Yield - Premium Investment'),
        ('organic', 'Organic - Sustainable Farming'),
        ('commercial', 'Commercial - Large Scale'),
        ('subsistence', 'Subsistence - Family Consumption')
    ], validators=[DataRequired()])
    
    # Farm size
    farm_size = FloatField('Farm Size (in acres)', validators=[
        DataRequired(message='Farm size is required'),
        NumberRange(min=0.1, max=10000, message='Farm size must be between 0.1 and 10000 acres')
    ], render_kw={"placeholder": "Enter farm size in acres", "step": "0.1"})
    
    # Additional preferences
    market_preference = SelectField('Market Focus', choices=[
        ('local', 'Local Market'),
        ('regional', 'Regional Market'),
        ('export', 'Export Market'),
        ('processing', 'Processing Industry'),
        ('direct_consumer', 'Direct to Consumer')
    ], validators=[DataRequired()])
    
    experience_level = SelectField('Farming Experience', choices=[
        ('beginner', 'Beginner (0-2 years)'),
        ('intermediate', 'Intermediate (2-5 years)'),
        ('experienced', 'Experienced (5-10 years)'),
        ('expert', 'Expert (10+ years)')
    ], validators=[DataRequired()])
    
    submit = SubmitField('Get Crop Suggestions')

class CropComparisonForm(FlaskForm):
    """Form for comparing multiple crops"""
    crop1 = StringField('First Crop', validators=[DataRequired()], 
                       render_kw={"placeholder": "Enter first crop name"})
    crop2 = StringField('Second Crop', validators=[DataRequired()], 
                       render_kw={"placeholder": "Enter second crop name"})
    crop3 = StringField('Third Crop', validators=[Optional()], 
                       render_kw={"placeholder": "Enter third crop name (optional)"})
    
    comparison_factors = SelectField('Primary Comparison Factor', choices=[
        ('profitability', 'Profitability Analysis'),
        ('yield', 'Yield Potential'),
        ('water_requirement', 'Water Requirements'),
        ('cost_analysis', 'Cost Analysis'),
        ('market_demand', 'Market Demand'),
        ('risk_assessment', 'Risk Assessment')
    ], validators=[DataRequired()])
    
    submit = SubmitField('Compare Crops')


# Product Rating System Forms

class ProductRatingForm(FlaskForm):
    """Form for submitting product ratings"""
    rating = IntegerField('Rating', validators=[
        DataRequired(message='Rating is required'),
        NumberRange(min=1, max=5, message='Rating must be between 1 and 5 stars')
    ])
    review_text = TextAreaField('Review (Optional)', validators=[
        Optional(),
        Length(min=10, max=1000, message='Review must be between 10 and 1000 characters')
    ])
    order_id = HiddenField('Order ID', validators=[DataRequired()])
    submit = SubmitField('Submit Rating')

class SellerResponseForm(FlaskForm):
    """Form for seller responses to ratings"""
    response_text = TextAreaField('Your Response', validators=[
        DataRequired(message='Response is required'),
        Length(min=10, max=500, message='Response must be between 10 and 500 characters')
    ])
    rating_id = HiddenField('Rating ID', validators=[DataRequired()])
    submit = SubmitField('Post Response')

class RatingFlagForm(FlaskForm):
    """Form for flagging inappropriate ratings"""
    reason = SelectField('Reason', choices=[
        ('spam', 'Spam'),
        ('inappropriate', 'Inappropriate Content'),
        ('fake', 'Fake Review'),
        ('offensive', 'Offensive Language'),
        ('other', 'Other')
    ], validators=[DataRequired()])
    description = TextAreaField('Additional Details', validators=[
        Optional(),
        Length(max=500, message='Description cannot exceed 500 characters')
    ])
    rating_id = HiddenField('Rating ID', validators=[DataRequired()])
    submit = SubmitField('Report Review')

class PriceForecastForm(FlaskForm):
    """Simplified form for national price forecast - location-free"""
    commodity = StringField('Commodity Name', validators=[
        DataRequired(message='Please enter a commodity name'),
        Length(min=2, max=100, message='Commodity name must be between 2 and 100 characters')
    ], render_kw={
        'placeholder': 'e.g., Wheat, Rice, Onion, Tomato',
        'autocomplete': 'off',
        'class': 'form-control'
    })
    submit = SubmitField('Get National Forecast')


class CheckoutForm(FlaskForm):
    """Form for checkout with delivery information"""
    delivery_address = TextAreaField('Delivery Address', validators=[
        DataRequired(message='Delivery address is required'),
        Length(min=10, max=500, message='Address must be between 10 and 500 characters')
    ], render_kw={'placeholder': 'Enter complete delivery address with landmarks', 'rows': 3})
    
    delivery_method = SelectField('Delivery Method', choices=[
        ('standard', 'Standard Delivery (3-5 days)'),
        ('express', 'Express Delivery (1-2 days)')
    ], validators=[DataRequired(message='Please select a delivery method')])
    
    contact_phone = StringField('Contact Phone', validators=[
        DataRequired(message='Contact phone is required'),
        Length(min=10, max=15, message='Phone number must be between 10 and 15 digits')
    ], render_kw={"placeholder": "Enter contact number for delivery"})
    
    notes = TextAreaField('Additional Notes (Optional)', validators=[
        Optional(),
        Length(max=500, message='Notes cannot exceed 500 characters')
    ], render_kw={'placeholder': 'Any special instructions for delivery?', 'rows': 2})
    
    submit = SubmitField('Proceed to Payment')
    
    def validate_contact_phone(self, field):
        """Custom validator for phone number format"""
        if field.data:
            # Remove spaces and special characters
            phone = ''.join(filter(str.isdigit, field.data))
            if len(phone) < 10:
                raise ValidationError('Phone number must contain at least 10 digits')


# Shopping Cart and Order Management Forms

class AddToCartForm(FlaskForm):
    """Form for adding items to shopping cart"""
    quantity = FloatField('Quantity', validators=[
        DataRequired(message='Quantity is required'),
        NumberRange(min=0.1, message='Quantity must be at least 0.1')
    ], render_kw={"placeholder": "Enter quantity", "step": "0.1", "min": "0.1"})
    crop_id = HiddenField('Crop ID', validators=[DataRequired()])
    submit = SubmitField('Add to Cart')
    
    def validate_quantity(self, field):
        """Custom validator to ensure quantity is positive"""
        if field.data is not None and field.data <= 0:
            raise ValidationError('Quantity must be greater than zero')

class OrderCancellationForm(FlaskForm):
    """Form for cancelling orders with reason"""
    reason = SelectField('Cancellation Reason', choices=[
        ('changed_mind', 'Changed my mind'),
        ('found_better_price', 'Found better price elsewhere'),
        ('ordered_by_mistake', 'Ordered by mistake'),
        ('delivery_too_long', 'Delivery time too long'),
        ('payment_issues', 'Payment issues'),
        ('quality_concerns', 'Quality concerns'),
        ('other', 'Other reason')
    ], validators=[DataRequired(message='Please select a cancellation reason')])
    
    additional_details = TextAreaField('Additional Details', validators=[
        Optional(),
        Length(min=10, max=500, message='Details must be between 10 and 500 characters if provided')
    ], render_kw={"placeholder": "Please provide more details about your cancellation (Optional)", "rows": "4"})
    
    order_id = HiddenField('Order ID', validators=[DataRequired()])
    submit = SubmitField('Confirm Cancellation')
    
    def validate_additional_details(self, field):
        """Require additional details if 'other' reason is selected"""
        if self.reason.data == 'other' and (not field.data or len(field.data.strip()) < 10):
            raise ValidationError('Please provide additional details for "Other reason" (minimum 10 characters)')

class ShipOrderForm(FlaskForm):
    """Form for farmers to add tracking information when shipping orders"""
    tracking_number = StringField('Tracking Number', validators=[
        DataRequired(message='Tracking number is required'),
        Length(min=5, max=100, message='Tracking number must be between 5 and 100 characters')
    ], render_kw={"placeholder": "Enter courier tracking number"})
    
    courier_service = SelectField('Courier Service', choices=[
        ('india_post', 'India Post'),
        ('dhl', 'DHL'),
        ('fedex', 'FedEx'),
        ('bluedart', 'Blue Dart'),
        ('dtdc', 'DTDC'),
        ('ecom_express', 'Ecom Express'),
        ('delhivery', 'Delhivery'),
        ('xpressbees', 'XpressBees'),
        ('shadowfax', 'Shadowfax'),
        ('ekart', 'Ekart'),
        ('other', 'Other')
    ], validators=[DataRequired(message='Please select courier service')])
    
    estimated_delivery = DateField('Estimated Delivery Date', validators=[
        Optional()
    ], render_kw={"placeholder": "Select estimated delivery date"})
    
    shipping_notes = TextAreaField('Shipping Notes', validators=[
        Optional(),
        Length(max=300, message='Shipping notes cannot exceed 300 characters')
    ], render_kw={"placeholder": "Any special shipping instructions or notes (Optional)", "rows": "3"})
    
    order_id = HiddenField('Order ID', validators=[DataRequired()])
    submit = SubmitField('Mark as Shipped')
    
    def validate_tracking_number(self, field):
        """Custom validator for tracking number format"""
        if field.data:
            # Remove spaces and convert to uppercase
            tracking = field.data.strip().upper()
            # Basic validation - alphanumeric only
            if not tracking.replace('-', '').replace('_', '').isalnum():
                raise ValidationError('Tracking number should contain only letters, numbers, hyphens, and underscores')
    
    def validate_estimated_delivery(self, field):
        """Ensure estimated delivery is in the future"""
        if field.data:
            from datetime import date
            if field.data < date.today():
                raise ValidationError('Estimated delivery date must be today or in the future')


# KYC Verification Forms

class SellerKYCForm(FlaskForm):
    """Form for seller KYC submission"""
    full_name = StringField('Full Name', validators=[
        DataRequired(message='Full name is required'),
        Length(min=2, max=100, message='Full name must be between 2 and 100 characters')
    ], render_kw={"placeholder": "Enter your full name as per documents"})
    
    aadhaar_no = StringField('Aadhaar Number', validators=[
        DataRequired(message='Aadhaar number is required'),
        Length(min=12, max=12, message='Aadhaar number must be exactly 12 digits')
    ], render_kw={"placeholder": "Enter 12-digit Aadhaar number"})
    
    pan_no = StringField('PAN Number', validators=[
        DataRequired(message='PAN number is required'),
        Length(min=10, max=10, message='PAN must be exactly 10 characters')
    ], render_kw={"placeholder": "Enter PAN (e.g., ABCDE1234F)"})
    
    bank_account = StringField('Bank Account Number', validators=[
        DataRequired(message='Bank account number is required'),
        Length(min=9, max=18, message='Bank account must be 9-18 digits')
    ], render_kw={"placeholder": "Enter bank account number"})
    
    ifsc = StringField('IFSC Code', validators=[
        DataRequired(message='IFSC code is required'),
        Length(min=11, max=11, message='IFSC must be exactly 11 characters')
    ], render_kw={"placeholder": "Enter IFSC code (e.g., SBIN0001234)"})
    
    # File uploads
    aadhaar_front = FileField('Aadhaar Front Image', validators=[
        DataRequired(message='Aadhaar front image is required'),
        FileAllowed(['jpg', 'jpeg', 'png', 'pdf'], 'Only JPG, PNG, or PDF files allowed')
    ])
    
    aadhaar_back = FileField('Aadhaar Back Image', validators=[
        DataRequired(message='Aadhaar back image is required'),
        FileAllowed(['jpg', 'jpeg', 'png', 'pdf'], 'Only JPG, PNG, or PDF files allowed')
    ])
    
    pan_card = FileField('PAN Card Image', validators=[
        DataRequired(message='PAN card image is required'),
        FileAllowed(['jpg', 'jpeg', 'png', 'pdf'], 'Only JPG, PNG, or PDF files allowed')
    ])
    
    land_proof = FileField('Land Ownership Proof (Optional)', validators=[
        Optional(),
        FileAllowed(['jpg', 'jpeg', 'png', 'pdf'], 'Only JPG, PNG, or PDF files allowed')
    ])
    
    submit = SubmitField('Submit KYC')
    
    def validate_aadhaar_no(self, field):
        """Validate Aadhaar number format (12 digits, numeric only)"""
        if field.data:
            # Remove spaces and special characters
            aadhaar = ''.join(filter(str.isdigit, field.data))
            if len(aadhaar) != 12:
                raise ValidationError('Aadhaar number must be exactly 12 digits')
            if not aadhaar.isdigit():
                raise ValidationError('Aadhaar number must contain only digits')
            # Update field data with cleaned value
            field.data = aadhaar
    
    def validate_pan_no(self, field):
        """Validate PAN format (10 characters, format ABCDE1234F)"""
        if field.data:
            import re
            pan = field.data.strip().upper()
            # PAN format: 5 letters, 4 digits, 1 letter
            pan_pattern = r'^[A-Z]{5}[0-9]{4}[A-Z]{1}$'
            if not re.match(pan_pattern, pan):
                raise ValidationError('Invalid PAN format. Must be 10 alphanumeric characters (e.g., ABCDE1234F)')
            # Update field data with cleaned value
            field.data = pan
    
    def validate_ifsc(self, field):
        """Validate IFSC code format (11 characters, format ABCD0123456)"""
        if field.data:
            import re
            ifsc = field.data.strip().upper()
            # IFSC format: 4 letters, 0, 6 alphanumeric characters
            ifsc_pattern = r'^[A-Z]{4}0[A-Z0-9]{6}$'
            if not re.match(ifsc_pattern, ifsc):
                raise ValidationError('Invalid IFSC format. Must be 11 characters (e.g., SBIN0001234)')
            # Update field data with cleaned value
            field.data = ifsc
    
    def validate_bank_account(self, field):
        """Validate bank account number (9-18 digits)"""
        if field.data:
            # Remove spaces and special characters
            account = ''.join(filter(str.isdigit, field.data))
            if len(account) < 9 or len(account) > 18:
                raise ValidationError('Bank account must be 9-18 digits')
            if not account.isdigit():
                raise ValidationError('Bank account must contain only digits')
            # Update field data with cleaned value
            field.data = account
    
    def validate_aadhaar_front(self, field):
        """Validate file size (max 5MB)"""
        if field.data:
            try:
                field.data.seek(0, 2)
                size = field.data.tell()
                field.data.seek(0)
                if size > 5 * 1024 * 1024:
                    raise ValidationError('File size must not exceed 5MB')
            except (AttributeError, IOError, OSError):
                raise ValidationError('Unable to validate file. Please try uploading again.')
    
    def validate_aadhaar_back(self, field):
        """Validate file size (max 5MB)"""
        if field.data:
            try:
                field.data.seek(0, 2)
                size = field.data.tell()
                field.data.seek(0)
                if size > 5 * 1024 * 1024:
                    raise ValidationError('File size must not exceed 5MB')
            except (AttributeError, IOError, OSError):
                raise ValidationError('Unable to validate file. Please try uploading again.')
    
    def validate_pan_card(self, field):
        """Validate file size (max 5MB)"""
        if field.data:
            try:
                field.data.seek(0, 2)
                size = field.data.tell()
                field.data.seek(0)
                if size > 5 * 1024 * 1024:
                    raise ValidationError('File size must not exceed 5MB')
            except (AttributeError, IOError, OSError):
                raise ValidationError('Unable to validate file. Please try uploading again.')
    
    def validate_land_proof(self, field):
        """Validate file size (max 5MB) for optional land proof"""
        if field.data:
            try:
                field.data.seek(0, 2)
                size = field.data.tell()
                field.data.seek(0)
                if size > 5 * 1024 * 1024:
                    raise ValidationError('File size must not exceed 5MB')
            except (AttributeError, IOError, OSError):
                raise ValidationError('Unable to validate file. Please try uploading again.')


class KYCReviewForm(FlaskForm):
    """Form for admin KYC review"""
    action = SelectField('Action', choices=[
        ('approve', 'Approve'),
        ('reject', 'Reject')
    ], validators=[DataRequired(message='Please select an action')])
    
    rejection_reason = TextAreaField('Rejection Reason', validators=[
        Optional(),
        Length(min=10, max=500, message='Rejection reason must be 10-500 characters')
    ], render_kw={"placeholder": "Provide detailed reason for rejection (minimum 10 characters)", "rows": "4"})
    
    submit = SubmitField('Submit Review')
    
    def validate_rejection_reason(self, field):
        """Require rejection reason if action is reject"""
        if self.action.data == 'reject':
            if not field.data or len(field.data.strip()) < 10:
                raise ValidationError('Rejection reason is required when rejecting KYC (minimum 10 characters)')
