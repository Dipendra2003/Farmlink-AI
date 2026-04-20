import os
import logging
from werkzeug.utils import secure_filename
from PIL import Image
from datetime import datetime
import uuid
import io
import cloudinary
import cloudinary.uploader
import cloudinary.api
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure Cloudinary
cloudinary.config(
    cloud_name=os.environ.get('CLOUDINARY_CLOUD_NAME'),
    api_key=os.environ.get('CLOUDINARY_API_KEY'),
    api_secret=os.environ.get('CLOUDINARY_API_SECRET'),
    secure=True
)

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
MAX_IMAGE_SIZE = (800, 800)  # Maximum dimensions for uploaded images
MAX_PROFILE_SIZE = (400, 400)  # Maximum dimensions for profile pictures

# Cloudinary folders
CROP_FOLDER = 'farmlink/crops'
PROFILE_FOLDER = 'farmlink/profiles'
PEST_FOLDER = 'farmlink/pest_analysis'
KYC_FOLDER = 'farmlink/kyc'

def allowed_file(filename):
    """Check if file extension is allowed"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def optimize_image(file, max_size=MAX_IMAGE_SIZE, quality=85):
    """
    Optimize image before uploading
    Returns: BytesIO object with optimized image
    """
    try:
        # Open and validate image
        with Image.open(file) as image:
            # Verify it's a valid image
            image.verify()
        
        # Reopen for processing
        file.seek(0)
        with Image.open(file) as image:
            # Convert to RGB if needed
            if image.mode in ('RGBA', 'LA') or (image.mode == 'P' and 'transparency' in image.info):
                background = Image.new('RGB', image.size, 'white')
                if image.mode == 'P':
                    image = image.convert('RGBA')
                background.paste(image, mask=image.split()[3])
                image = background
            else:
                image = image.convert('RGB')
            
            # Resize if too large
            if image.size[0] > max_size[0] or image.size[1] > max_size[1]:
                image.thumbnail(max_size, Image.Resampling.LANCZOS)
            
            # Save to BytesIO
            output = io.BytesIO()
            image.save(output, format='JPEG', optimize=True, quality=quality)
            output.seek(0)
            return output
            
    except Exception as e:
        logging.error(f"Error optimizing image: {e}")
        return None

def save_image(file, folder=CROP_FOLDER):
    """
    Save an uploaded image file to Cloudinary
    
    Args:
        file: FileStorage object from Flask
        folder: Cloudinary folder path
        
    Returns:
        str: Cloudinary URL or None if failed
    """
    if not file:
        logging.warning("No file provided for upload")
        return None
        
    if not allowed_file(file.filename):
        logging.warning(f"Invalid file type for {file.filename}")
        return None
    
    try:
        # Generate unique public_id
        filename = secure_filename(file.filename)
        ext = filename.rsplit('.', 1)[1].lower()
        unique_id = f"{uuid.uuid4().hex}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        # Optimize image
        optimized_image = optimize_image(file, MAX_IMAGE_SIZE, quality=85)
        if not optimized_image:
            logging.error("Failed to optimize image")
            return None
        
        # Upload to Cloudinary
        result = cloudinary.uploader.upload(
            optimized_image,
            folder=folder,
            public_id=unique_id,
            resource_type='image',
            format='jpg',
            transformation=[
                {'quality': 'auto:good'},
                {'fetch_format': 'auto'}
            ]
        )
        
        # Return secure URL
        image_url = result.get('secure_url')
        logging.info(f"Successfully uploaded image to Cloudinary: {image_url}")
        return image_url
        
    except Exception as e:
        logging.error(f"Error uploading to Cloudinary: {e}")
        return None

def save_profile_image(file):
    """
    Save an uploaded profile image to Cloudinary
    
    Args:
        file: FileStorage object from Flask
        
    Returns:
        str: Cloudinary URL or None if failed
    """
    if not file:
        logging.warning("No file provided for profile upload")
        return None
        
    if not allowed_file(file.filename):
        logging.warning(f"Invalid file type for {file.filename}")
        return None
    
    try:
        # Generate unique public_id
        filename = secure_filename(file.filename)
        unique_id = f"profile_{uuid.uuid4().hex}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        # Open and process image
        file.seek(0)
        with Image.open(file) as image:
            # Verify image
            image.verify()
        
        # Reopen for processing
        file.seek(0)
        with Image.open(file) as image:
            # Convert to RGB
            if image.mode in ('RGBA', 'LA') or (image.mode == 'P' and 'transparency' in image.info):
                background = Image.new('RGB', image.size, 'white')
                if image.mode == 'P':
                    image = image.convert('RGBA')
                background.paste(image, mask=image.split()[3])
                image = background
            else:
                image = image.convert('RGB')
            
            # Crop to square
            width, height = image.size
            min_dimension = min(width, height)
            left = (width - min_dimension) // 2
            top = (height - min_dimension) // 2
            right = left + min_dimension
            bottom = top + min_dimension
            image = image.crop((left, top, right, bottom))
            
            # Resize
            if image.size[0] > MAX_PROFILE_SIZE[0]:
                image.thumbnail(MAX_PROFILE_SIZE, Image.Resampling.LANCZOS)
            
            # Save to BytesIO
            output = io.BytesIO()
            image.save(output, format='JPEG', optimize=True, quality=90)
            output.seek(0)
            
            # Upload to Cloudinary
            result = cloudinary.uploader.upload(
                output,
                folder=PROFILE_FOLDER,
                public_id=unique_id,
                resource_type='image',
                format='jpg',
                transformation=[
                    {'width': 400, 'height': 400, 'crop': 'fill', 'gravity': 'face'},
                    {'quality': 'auto:good'},
                    {'fetch_format': 'auto'}
                ]
            )
            
            # Return secure URL
            image_url = result.get('secure_url')
            logging.info(f"Successfully uploaded profile image to Cloudinary: {image_url}")
            return image_url
            
    except Exception as e:
        logging.error(f"Error uploading profile image to Cloudinary: {e}")
        return None

def delete_image(image_url):
    """
    Delete an image from Cloudinary
    
    Args:
        image_url: Cloudinary URL or public_id
        
    Returns:
        bool: True if deleted successfully
    """
    if not image_url:
        return False
    
    try:
        # Extract public_id from URL
        if 'cloudinary.com' in image_url:
            # Extract public_id from URL
            # Format: https://res.cloudinary.com/cloud_name/image/upload/v123456/folder/public_id.jpg
            parts = image_url.split('/')
            # Find the index after 'upload'
            upload_index = parts.index('upload')
            # Get everything after version number
            public_id_parts = parts[upload_index + 2:]  # Skip version
            public_id = '/'.join(public_id_parts).rsplit('.', 1)[0]  # Remove extension
        else:
            public_id = image_url
        
        # Delete from Cloudinary
        result = cloudinary.uploader.destroy(public_id)
        
        if result.get('result') == 'ok':
            logging.info(f"Successfully deleted image from Cloudinary: {public_id}")
            return True
        else:
            logging.warning(f"Failed to delete image from Cloudinary: {result}")
            return False
            
    except Exception as e:
        logging.error(f"Error deleting image from Cloudinary: {e}")
        return False

def delete_profile_image(image_url):
    """
    Delete a profile image from Cloudinary
    
    Args:
        image_url: Cloudinary URL
        
    Returns:
        bool: True if deleted successfully
    """
    # Don't delete default profile image
    if not image_url or 'default' in image_url.lower():
        return False
    
    return delete_image(image_url)

def get_default_crop_image():
    """Get default crop image URL"""
    return "https://via.placeholder.com/800x800/f0f0f0/666666?text=No+Image"

def get_default_profile_image():
    """Get default profile image URL"""
    return "https://via.placeholder.com/400x400/e0e0e0/666666?text=Profile"

def ensure_default_crop_image():
    """Placeholder for compatibility - not needed with Cloudinary"""
    pass

def ensure_default_profile_image():
    """Placeholder for compatibility - not needed with Cloudinary"""
    pass

# Test Cloudinary connection on import
try:
    cloudinary.api.ping()
    logging.info("✅ Cloudinary connection successful!")
except Exception as e:
    logging.error(f"❌ Cloudinary connection failed: {e}")
    logging.error("Please check your CLOUDINARY credentials in .env file")
