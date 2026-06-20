"""
KYC File Storage Service
Handles secure file upload, validation, and storage for KYC documents
"""

import os
import uuid
import sys
from werkzeug.utils import secure_filename
from flask import current_app, url_for
import cloudinary
import cloudinary.uploader

# Import magic with fallback for Windows
try:
    import magic
except ImportError:
    # Fallback for systems without libmagic
    magic = None


class KYCFileService:
    """Service for handling KYC file uploads and storage"""
    
    ALLOWED_EXTENSIONS = {'jpg', 'jpeg', 'png', 'pdf'}
    ALLOWED_MIME_TYPES = {
        'image/jpeg',
        'image/png',
        'application/pdf'
    }
    MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB in bytes
    
    @staticmethod
    def _get_upload_dir(user_id):
        """Get the upload directory path for a specific user"""
        base_dir = current_app.config.get('KYC_UPLOAD_DIR', 'static/uploads/kyc')
        user_dir = os.path.join(base_dir, str(user_id))
        return user_dir
    
    @staticmethod
    def _validate_file_type(file):
        """
        Validate file type using magic numbers (not just extension)
        Returns: (is_valid: bool, mime_type: str)
        """
        try:
            # Read first 2048 bytes for magic number detection
            file.seek(0)
            file_header = file.read(2048)
            file.seek(0)
            
            if magic is not None:
                # Detect MIME type using python-magic
                mime = magic.from_buffer(file_header, mime=True)
            else:
                # Fallback: Basic validation using file signatures
                mime = KYCFileService._detect_mime_from_signature(file_header)
            
            is_valid = mime in KYCFileService.ALLOWED_MIME_TYPES
            return is_valid, mime
        except Exception as e:
            current_app.logger.error(f"Error validating file type: {str(e)}")
            return False, None
    
    @staticmethod
    def _detect_mime_from_signature(file_header):
        """
        Fallback method to detect MIME type from file signature (magic numbers)
        Returns: MIME type string or None
        """
        # JPEG signature
        if file_header.startswith(b'\xFF\xD8\xFF'):
            return 'image/jpeg'
        
        # PNG signature
        if file_header.startswith(b'\x89PNG\r\n\x1a\n'):
            return 'image/png'
        
        # PDF signature
        if file_header.startswith(b'%PDF'):
            return 'application/pdf'
        
        return None
    
    @staticmethod
    def _validate_file_size(file):
        """
        Validate file size (max 5MB)
        Returns: (is_valid: bool, size: int)
        """
        try:
            file.seek(0, 2)  # Seek to end
            size = file.tell()
            file.seek(0)  # Reset to beginning
            
            is_valid = size <= KYCFileService.MAX_FILE_SIZE
            return is_valid, size
        except Exception as e:
            current_app.logger.error(f"Error validating file size: {str(e)}")
            return False, 0
    
    @staticmethod
    def save_kyc_document(file, user_id, doc_type):
        """
        Save uploaded KYC document with validation
        
        Args:
            file: FileStorage object from request.files
            user_id: User ID for directory organization
            doc_type: Type of document (e.g., 'aadhaar_front', 'pan_card')
        
        Returns:
            str: Relative file path if successful, None if failed
        """
        if not file or not file.filename:
            current_app.logger.error("No file provided")
            return None
        
        # Validate file size
        is_valid_size, size = KYCFileService._validate_file_size(file)
        if not is_valid_size:
            current_app.logger.error(f"File size {size} exceeds maximum {KYCFileService.MAX_FILE_SIZE}")
            return None
        
        # Validate file type using magic numbers
        is_valid_type, mime_type = KYCFileService._validate_file_type(file)
        if not is_valid_type:
            current_app.logger.error(f"Invalid file type: {mime_type}")
            return None
        
        # Get file extension
        original_filename = secure_filename(file.filename)
        file_ext = original_filename.rsplit('.', 1)[1].lower() if '.' in original_filename else ''
        
        if file_ext not in KYCFileService.ALLOWED_EXTENSIONS:
            current_app.logger.error(f"Invalid file extension: {file_ext}")
            return None
        
        # Generate unique filename with UUID
        unique_filename = f"{doc_type}_{uuid.uuid4().hex}.{file_ext}"
        
        # Save file
        try:
            # Try Cloudinary First
            try:
                # Seek to beginning in case it was read during validation
                file.seek(0)
                result = cloudinary.uploader.upload(
                    file,
                    folder='farmlink/kyc',
                    public_id=unique_filename.rsplit('.', 1)[0],
                    resource_type='auto'
                )
                image_url = result.get('secure_url')
                current_app.logger.info(f"✅ Successfully uploaded KYC document to Cloudinary: {image_url}")
                return image_url
            except Exception as cloudinary_error:
                current_app.logger.warning(f"⚠️ Cloudinary upload failed: {cloudinary_error}")
                current_app.logger.info("📁 Falling back to local storage...")
            
            # Local fallback
            user_dir = KYCFileService._get_upload_dir(user_id)
            if os.environ.get('VERCEL') != '1':
                try:
                    os.makedirs(user_dir, mode=0o750, exist_ok=True)
                except Exception as e:
                    current_app.logger.error(f"Error creating directory {user_dir}: {str(e)}")
                    return None
                    
            file_path = os.path.join(user_dir, unique_filename)
            file.seek(0)
            file.save(file_path)
            current_app.logger.info(f"Saved KYC document locally: {file_path}")
            
            # Set file permissions to 640 (rw-r-----)
            os.chmod(file_path, 0o640)
            
            # Return relative path for database storage
            relative_path = os.path.join('static/uploads/kyc', str(user_id), unique_filename)
            # Normalize path to use forward slashes
            return relative_path.replace('\\', '/')
        except Exception as e:
            current_app.logger.error(f"Error saving file {file_path}: {str(e)}")
            return None
    
    @staticmethod
    def delete_kyc_documents(user_id):
        """
        Delete all KYC documents for a user
        
        Args:
            user_id: User ID whose documents should be deleted
        
        Returns:
            bool: True if successful, False otherwise
        """
        user_dir = KYCFileService._get_upload_dir(user_id)
        
        if not os.path.exists(user_dir):
            current_app.logger.warning(f"Directory does not exist: {user_dir}")
            return True  # Nothing to delete
        
        try:
            # Delete all files in the directory
            for filename in os.listdir(user_dir):
                file_path = os.path.join(user_dir, filename)
                if os.path.isfile(file_path):
                    os.remove(file_path)
                    current_app.logger.info(f"Deleted file: {file_path}")
            
            # Remove the directory
            os.rmdir(user_dir)
            current_app.logger.info(f"Deleted directory: {user_dir}")
            return True
        except Exception as e:
            current_app.logger.error(f"Error deleting KYC documents for user {user_id}: {str(e)}")
            return False
    
    @staticmethod
    def get_document_url(file_path, kyc_id):
        """
        Get secure URL for document access (admin only)
        
        Args:
            file_path: Relative file path from database
            kyc_id: KYC record ID for URL generation
        
        Returns:
            str: URL for secure document download
        """
        if not file_path:
            return None
        
        # Extract document type from filename
        filename = os.path.basename(file_path)
        doc_type = filename.split('_')[0] if '_' in filename else 'document'
        
        # Generate URL for admin document download route
        # This will be handled by a route like /admin/kyc-verification/<kyc_id>/document/<doc_type>
        try:
            url = url_for('admin_kyc_document', kyc_id=kyc_id, doc_type=doc_type, _external=False)
            return url
        except Exception as e:
            current_app.logger.error(f"Error generating document URL: {str(e)}")
            return None
    
    @staticmethod
    def get_document_path(file_path):
        """
        Get absolute file path for serving documents
        
        Args:
            file_path: Relative file path from database
        
        Returns:
            str: Absolute file path or None if not found
        """
        if not file_path:
            return None
        
        # Normalize path separators to OS-specific format
        normalized_path = file_path.replace('\\', os.sep).replace('/', os.sep)
        
        # Convert relative path to absolute path
        abs_path = os.path.join(current_app.root_path, normalized_path)
        
        # Verify file exists
        if os.path.exists(abs_path) and os.path.isfile(abs_path):
            return abs_path
        else:
            current_app.logger.error(f"File not found: {abs_path}")
            return None
    
    @staticmethod
    def validate_file(file):
        """
        Validate file before upload (for form validation)
        
        Args:
            file: FileStorage object from request.files
        
        Returns:
            tuple: (is_valid: bool, error_message: str or None)
        """
        if not file or not file.filename:
            return False, "No file provided"
        
        # Validate file size
        is_valid_size, size = KYCFileService._validate_file_size(file)
        if not is_valid_size:
            size_mb = size / (1024 * 1024)
            return False, f"File size ({size_mb:.2f}MB) exceeds maximum 5MB"
        
        # Validate file type
        is_valid_type, mime_type = KYCFileService._validate_file_type(file)
        if not is_valid_type:
            return False, f"Invalid file type. Only JPG, PNG, and PDF files are allowed"
        
        # Validate file extension
        original_filename = secure_filename(file.filename)
        file_ext = original_filename.rsplit('.', 1)[1].lower() if '.' in original_filename else ''
        
        if file_ext not in KYCFileService.ALLOWED_EXTENSIONS:
            return False, f"Invalid file extension. Only JPG, PNG, and PDF files are allowed"
        
        return True, None
