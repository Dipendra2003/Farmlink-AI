import os
from werkzeug.utils import secure_filename
from PIL import Image
from datetime import datetime
import uuid
import logging

UPLOAD_FOLDER = os.path.join('static', 'uploads', 'crops')
PROFILE_UPLOAD_FOLDER = os.path.join('static', 'uploads', 'profiles')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
MAX_IMAGE_SIZE = (800, 800)  # Maximum dimensions for uploaded images
MAX_PROFILE_SIZE = (400, 400)  # Maximum dimensions for profile pictures

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def save_image(file):
    """Save an uploaded image file with proper validation and optimization"""
    if not file:
        logging.warning("No file provided for upload")
        return None
        
    if not allowed_file(file.filename):
        logging.warning(f"Invalid file type for {file.filename}")
        return None
        
    try:
        # Create unique filename with timestamp
        filename = secure_filename(file.filename)
        ext = filename.rsplit('.', 1)[1].lower()
        unique_filename = f"{uuid.uuid4().hex}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{ext}"
        
        # Ensure upload directory exists
        os.makedirs(UPLOAD_FOLDER, exist_ok=True)
        
        filepath = os.path.join(UPLOAD_FOLDER, unique_filename)
        
        # Open and validate image
        try:
            with Image.open(file) as image:
                # Verify it's a valid image file
                image.verify()
        except Exception as e:
            logging.error(f"Invalid image file: {e}")
            return None
        
        # Reopen image for processing (needed after verify)
        file.seek(0)  # Reset file pointer
        with Image.open(file) as image:
            # Process image
            if image.mode in ('RGBA', 'LA') or (image.mode == 'P' and 'transparency' in image.info):
                # Convert RGBA to RGB with white background
                background = Image.new('RGB', image.size, 'white')
                if image.mode == 'P':
                    image = image.convert('RGBA')
                background.paste(image, mask=image.split()[3])
                image = background
            else:
                image = image.convert('RGB')
            
            # Resize if too large while maintaining aspect ratio
            if image.size[0] > MAX_IMAGE_SIZE[0] or image.size[1] > MAX_IMAGE_SIZE[1]:
                image.thumbnail(MAX_IMAGE_SIZE, Image.Resampling.LANCZOS)
            
            # Save optimized image
            image.save(
                filepath,
                'JPEG',
                optimize=True,
                quality=85
            )
        
        # Return relative path for database (starting from static/)
        relative_path = os.path.join('uploads', 'crops', unique_filename).replace('\\', '/')
        logging.info(f"Successfully saved image: {relative_path}")
        return relative_path
            
    except Exception as e:
        logging.error(f"Error saving image: {e}")
        return None

def delete_image(image_path):
    if image_path:
        try:
            full_path = os.path.join('static', image_path)
            if os.path.exists(full_path):
                os.remove(full_path)
                return True
        except Exception as e:
            logging.error(f"Error deleting image: {e}")
    return False

def ensure_default_crop_image():
    default_image_path = os.path.join('static', 'uploads', 'crops', 'default-crop.jpg')
    if not os.path.exists(default_image_path):
        try:
            # Create a simple default image
            img = Image.new('RGB', (800, 800), color='#f0f0f0')
            img.save(default_image_path, 'JPEG', quality=85)
        except Exception as e:
            logging.error(f"Error creating default crop image: {e}")

def save_profile_image(file):
    """Save an uploaded profile image with proper validation and optimization"""
    if not file:
        logging.warning("No file provided for profile upload")
        return None
        
    if not allowed_file(file.filename):
        logging.warning(f"Invalid file type for {file.filename}")
        return None
        
    try:
        # Create unique filename with timestamp
        filename = secure_filename(file.filename)
        ext = filename.rsplit('.', 1)[1].lower()
        unique_filename = f"profile_{uuid.uuid4().hex}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{ext}"
        
        # Ensure upload directory exists
        os.makedirs(PROFILE_UPLOAD_FOLDER, exist_ok=True)
        
        filepath = os.path.join(PROFILE_UPLOAD_FOLDER, unique_filename)
        
        # Open and validate image
        try:
            with Image.open(file) as image:
                # Verify it's a valid image file
                image.verify()
        except Exception as e:
            logging.error(f"Invalid image file: {e}")
            return None
        
        # Reopen image for processing (needed after verify)
        file.seek(0)  # Reset file pointer
        with Image.open(file) as image:
            # Process image
            if image.mode in ('RGBA', 'LA') or (image.mode == 'P' and 'transparency' in image.info):
                # Convert RGBA to RGB with white background
                background = Image.new('RGB', image.size, 'white')
                if image.mode == 'P':
                    image = image.convert('RGBA')
                background.paste(image, mask=image.split()[3])
                image = background
            else:
                image = image.convert('RGB')
            
            # Resize to square profile picture while maintaining aspect ratio
            # Crop to square first
            width, height = image.size
            min_dimension = min(width, height)
            left = (width - min_dimension) // 2
            top = (height - min_dimension) // 2
            right = left + min_dimension
            bottom = top + min_dimension
            image = image.crop((left, top, right, bottom))
            
            # Resize to max profile size
            if image.size[0] > MAX_PROFILE_SIZE[0] or image.size[1] > MAX_PROFILE_SIZE[1]:
                image.thumbnail(MAX_PROFILE_SIZE, Image.Resampling.LANCZOS)
            
            # Save optimized image
            image.save(
                filepath,
                'JPEG',
                optimize=True,
                quality=90
            )
        
        # Return relative path for database (starting from static/)
        relative_path = os.path.join('uploads', 'profiles', unique_filename).replace('\\', '/')
        logging.info(f"Successfully saved profile image: {relative_path}")
        return relative_path
            
    except Exception as e:
        logging.error(f"Error saving profile image: {e}")
        return None

def delete_profile_image(image_path):
    """Delete a profile image file"""
    if image_path and image_path != 'default.jpg':
        try:
            full_path = os.path.join('static', image_path)
            if os.path.exists(full_path):
                os.remove(full_path)
                logging.info(f"Successfully deleted profile image: {image_path}")
                return True
        except Exception as e:
            logging.error(f"Error deleting profile image: {e}")
    return False

def ensure_default_profile_image():
    """Ensure default profile image exists"""
    default_image_path = os.path.join('static', 'uploads', 'profiles', 'default.jpg')
    if not os.path.exists(default_image_path):
        try:
            os.makedirs(PROFILE_UPLOAD_FOLDER, exist_ok=True)
            # Create a simple default profile image
            img = Image.new('RGB', (400, 400), color='#e0e0e0')
            img.save(default_image_path, 'JPEG', quality=90)
            logging.info("Created default profile image")
        except Exception as e:
            logging.error(f"Error creating default profile image: {e}")

# Create default images when module is imported
ensure_default_crop_image()
ensure_default_profile_image()
