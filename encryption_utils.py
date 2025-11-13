"""
Encryption Utilities for Sensitive Data
Provides encryption/decryption for sensitive database values
"""

import os
import base64
import logging
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.backends import default_backend

logger = logging.getLogger(__name__)


class EncryptionManager:
    """
    Manages encryption and decryption of sensitive data
    Uses Fernet (symmetric encryption) with key derivation
    """
    
    _instance = None
    _cipher = None
    
    def __new__(cls):
        """Singleton pattern to ensure one encryption key"""
        if cls._instance is None:
            cls._instance = super(EncryptionManager, cls).__new__(cls)
            cls._instance._initialize()
        return cls._instance
    
    def _initialize(self):
        """Initialize encryption cipher"""
        try:
            # Get encryption key from environment or generate
            encryption_key = os.environ.get('ENCRYPTION_KEY')
            
            if not encryption_key:
                logger.warning(
                    "ENCRYPTION_KEY not found in environment. "
                    "Generating temporary key. Set ENCRYPTION_KEY in .env for production!"
                )
                # Generate a key (should be stored in .env in production)
                encryption_key = Fernet.generate_key().decode()
                logger.warning(f"Generated key: {encryption_key}")
                logger.warning("Add this to your .env file: ENCRYPTION_KEY={encryption_key}")
            
            # If key is a password, derive a proper key
            if len(encryption_key) < 32:
                encryption_key = self._derive_key(encryption_key)
            
            # Ensure key is bytes
            if isinstance(encryption_key, str):
                encryption_key = encryption_key.encode()
            
            self._cipher = Fernet(encryption_key)
            logger.info("Encryption manager initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize encryption: {str(e)}")
            raise
    
    def _derive_key(self, password):
        """
        Derive a proper encryption key from a password
        Uses PBKDF2 with SHA256
        """
        # Use a fixed salt (in production, store this securely)
        salt = os.environ.get('ENCRYPTION_SALT', 'farmlink-ai-salt-2025').encode()
        
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
            backend=default_backend()
        )
        
        key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
        return key
    
    def encrypt(self, plaintext):
        """
        Encrypt plaintext data
        
        Args:
            plaintext (str): Data to encrypt
        
        Returns:
            str: Base64-encoded encrypted data
        """
        if not plaintext:
            return None
        
        try:
            # Convert to bytes if string
            if isinstance(plaintext, str):
                plaintext = plaintext.encode()
            
            # Encrypt
            encrypted = self._cipher.encrypt(plaintext)
            
            # Return as base64 string for database storage
            return base64.urlsafe_b64encode(encrypted).decode()
            
        except Exception as e:
            logger.error(f"Encryption failed: {str(e)}")
            raise
    
    def decrypt(self, encrypted_data):
        """
        Decrypt encrypted data
        
        Args:
            encrypted_data (str): Base64-encoded encrypted data
        
        Returns:
            str: Decrypted plaintext
        """
        if not encrypted_data:
            return None
        
        try:
            # Decode from base64
            encrypted_bytes = base64.urlsafe_b64decode(encrypted_data.encode())
            
            # Decrypt
            decrypted = self._cipher.decrypt(encrypted_bytes)
            
            # Return as string
            return decrypted.decode()
            
        except Exception as e:
            logger.error(f"Decryption failed: {str(e)}")
            # Return None instead of raising to handle legacy unencrypted data
            return None
    
    def is_encrypted(self, data):
        """
        Check if data appears to be encrypted
        
        Args:
            data (str): Data to check
        
        Returns:
            bool: True if data appears encrypted
        """
        if not data:
            return False
        
        try:
            # Try to decrypt - if it works, it's encrypted
            self.decrypt(data)
            return True
        except:
            return False


# Global encryption manager instance
encryption_manager = EncryptionManager()


def encrypt_value(value):
    """
    Convenience function to encrypt a value
    
    Args:
        value (str): Value to encrypt
    
    Returns:
        str: Encrypted value
    """
    return encryption_manager.encrypt(value)


def decrypt_value(encrypted_value):
    """
    Convenience function to decrypt a value
    
    Args:
        encrypted_value (str): Encrypted value
    
    Returns:
        str: Decrypted value
    """
    return encryption_manager.decrypt(encrypted_value)


# ============================================================================
# SENSITIVE FIELD ENCRYPTION MIXIN
# ============================================================================

class EncryptedFieldMixin:
    """
    Mixin for SQLAlchemy models to handle encrypted fields
    
    Usage:
        class MyModel(db.Model, EncryptedFieldMixin):
            encrypted_field = db.Column(db.Text)
            
            ENCRYPTED_FIELDS = ['encrypted_field']
    """
    
    ENCRYPTED_FIELDS = []
    
    def set_encrypted_field(self, field_name, value):
        """Set an encrypted field value"""
        if value is None:
            setattr(self, field_name, None)
        else:
            encrypted = encrypt_value(str(value))
            setattr(self, field_name, encrypted)
    
    def get_encrypted_field(self, field_name):
        """Get a decrypted field value"""
        encrypted_value = getattr(self, field_name)
        if encrypted_value is None:
            return None
        
        # Try to decrypt
        decrypted = decrypt_value(encrypted_value)
        
        # If decryption fails, might be legacy unencrypted data
        if decrypted is None:
            logger.warning(f"Failed to decrypt {field_name}, returning raw value")
            return encrypted_value
        
        return decrypted
    
    def encrypt_all_fields(self):
        """Encrypt all fields marked as encrypted"""
        for field_name in self.ENCRYPTED_FIELDS:
            value = getattr(self, field_name)
            if value and not encryption_manager.is_encrypted(value):
                self.set_encrypted_field(field_name, value)


# ============================================================================
# MIGRATION HELPER
# ============================================================================

def migrate_to_encrypted_storage():
    """
    Migrate existing unencrypted sensitive data to encrypted storage
    Run this once after implementing encryption
    """
    from app import app, db
    from models import SystemSettings
    
    with app.app_context():
        try:
            # Get all system settings with sensitive values
            sensitive_keys = [
                'razorpay_key_id',
                'razorpay_key_secret',
                'gemini_api_key',
                'weather_api_key',
                'smtp_password',
                'database_password'
            ]
            
            settings = SystemSettings.query.filter(
                SystemSettings.setting_key.in_(sensitive_keys)
            ).all()
            
            encrypted_count = 0
            for setting in settings:
                value = setting.get_value()
                if value and not encryption_manager.is_encrypted(value):
                    # Encrypt the value
                    encrypted = encrypt_value(value)
                    setting.setting_value = encrypted
                    encrypted_count += 1
                    logger.info(f"Encrypted setting: {setting.setting_key}")
            
            db.session.commit()
            logger.info(f"Migration complete: {encrypted_count} settings encrypted")
            return encrypted_count
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Migration failed: {str(e)}")
            raise


# ============================================================================
# ENVIRONMENT VARIABLE HELPERS
# ============================================================================

def get_secure_config(key, default=None, use_env_first=True):
    """
    Get configuration value with preference for environment variables
    
    Args:
        key (str): Configuration key
        default: Default value if not found
        use_env_first (bool): Check environment variables first
    
    Returns:
        Configuration value
    """
    if use_env_first:
        # Check environment variable first
        env_value = os.environ.get(key)
        if env_value:
            return env_value
    
    # Fall back to database
    from models import SystemSettings
    try:
        setting = SystemSettings.query.filter_by(setting_key=key).first()
        if setting:
            value = setting.get_value()
            # Decrypt if encrypted
            if value and encryption_manager.is_encrypted(value):
                return decrypt_value(value)
            return value
    except:
        pass
    
    return default


def set_secure_config(key, value, encrypt=True):
    """
    Set configuration value with optional encryption
    
    Args:
        key (str): Configuration key
        value: Configuration value
        encrypt (bool): Whether to encrypt the value
    """
    from app import db
    from models import SystemSettings
    
    try:
        setting = SystemSettings.query.filter_by(setting_key=key).first()
        
        # Encrypt if requested
        if encrypt and value:
            value = encrypt_value(str(value))
        
        if setting:
            setting.setting_value = value
        else:
            setting = SystemSettings(
                setting_key=key,
                setting_value=value,
                value_type='encrypted' if encrypt else 'text'
            )
            db.session.add(setting)
        
        db.session.commit()
        logger.info(f"Secure config set: {key}")
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to set secure config: {str(e)}")
        raise


# ============================================================================
# SETTINGS ROLLBACK SYSTEM
# ============================================================================

class SettingsBackup:
    """Backup and rollback system for settings changes"""
    
    @staticmethod
    def create_backup(admin_id, description="Manual backup"):
        """
        Create a backup of all current settings
        
        Args:
            admin_id (int): ID of admin creating backup
            description (str): Backup description
        
        Returns:
            int: Backup ID
        """
        from app import db
        from models import SystemSettings, SettingsBackup as BackupModel
        import json
        from datetime import datetime
        
        try:
            # Get all current settings
            settings = SystemSettings.query.all()
            
            # Create backup data
            backup_data = {}
            for setting in settings:
                backup_data[setting.setting_key] = {
                    'value': setting.setting_value,
                    'type': setting.value_type,
                    'description': setting.description
                }
            
            # Create backup record
            backup = BackupModel(
                admin_id=admin_id,
                description=description,
                backup_data=json.dumps(backup_data),
                created_at=datetime.utcnow()
            )
            
            db.session.add(backup)
            db.session.commit()
            
            logger.info(f"Settings backup created: {backup.id}")
            return backup.id
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Failed to create backup: {str(e)}")
            raise
    
    @staticmethod
    def restore_backup(backup_id, admin_id):
        """
        Restore settings from a backup
        
        Args:
            backup_id (int): Backup ID to restore
            admin_id (int): ID of admin performing restore
        
        Returns:
            bool: Success status
        """
        from app import db
        from models import SystemSettings, SettingsBackup as BackupModel, AdminActionLog
        import json
        from datetime import datetime
        
        try:
            # Get backup
            backup = BackupModel.query.get(backup_id)
            if not backup:
                raise ValueError(f"Backup {backup_id} not found")
            
            # Parse backup data
            backup_data = json.loads(backup.backup_data)
            
            # Restore each setting
            restored_count = 0
            for key, data in backup_data.items():
                setting = SystemSettings.query.filter_by(setting_key=key).first()
                
                if setting:
                    setting.setting_value = data['value']
                    setting.value_type = data['type']
                    setting.description = data.get('description')
                else:
                    setting = SystemSettings(
                        setting_key=key,
                        setting_value=data['value'],
                        value_type=data['type'],
                        description=data.get('description')
                    )
                    db.session.add(setting)
                
                restored_count += 1
            
            # Log the restore action
            log = AdminActionLog(
                admin_id=admin_id,
                action_type='restore_settings_backup',
                target_type='system_settings',
                target_id=backup_id,
                description=f"Restored settings from backup: {backup.description}",
                ip_address=None,
                user_agent=None
            )
            db.session.add(log)
            
            db.session.commit()
            
            logger.info(f"Settings restored from backup {backup_id}: {restored_count} settings")
            return True
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Failed to restore backup: {str(e)}")
            raise
    
    @staticmethod
    def list_backups(limit=10):
        """
        List available backups
        
        Args:
            limit (int): Maximum number of backups to return
        
        Returns:
            list: List of backup records
        """
        from models import SettingsBackup as BackupModel
        
        try:
            backups = BackupModel.query.order_by(
                BackupModel.created_at.desc()
            ).limit(limit).all()
            
            return backups
            
        except Exception as e:
            logger.error(f"Failed to list backups: {str(e)}")
            return []
