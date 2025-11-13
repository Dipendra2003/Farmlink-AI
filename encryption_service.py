"""
Encryption service for handling sensitive KYC data
Uses Fernet (AES-256) encryption for secure data storage
"""
import os
from cryptography.fernet import Fernet
from typing import Optional


class EncryptionService:
    """Service for encrypting and decrypting sensitive KYC data"""
    
    def __init__(self, encryption_key: Optional[str] = None):
        """
        Initialize encryption service with encryption key
        
        Args:
            encryption_key: Base64-encoded Fernet key. If None, reads from environment.
        """
        if encryption_key is None:
            encryption_key = os.environ.get('KYC_ENCRYPTION_KEY')
        
        if not encryption_key:
            raise ValueError(
                "KYC_ENCRYPTION_KEY not found in environment variables. "
                "Generate one using: python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'"
            )
        
        # Convert string key to bytes if needed
        if isinstance(encryption_key, str):
            encryption_key = encryption_key.encode()
        
        self.cipher = Fernet(encryption_key)
    
    def encrypt(self, plaintext: str) -> bytes:
        """
        Encrypt plaintext data using AES-256 (via Fernet)
        
        Args:
            plaintext: The data to encrypt (e.g., Aadhaar number, PAN, bank account)
        
        Returns:
            Encrypted data as bytes
        
        Raises:
            ValueError: If plaintext is empty or None
        """
        if not plaintext:
            raise ValueError("Cannot encrypt empty or None value")
        
        # Convert to bytes if string
        if isinstance(plaintext, str):
            plaintext = plaintext.encode('utf-8')
        
        # Encrypt and return
        return self.cipher.encrypt(plaintext)
    
    def decrypt(self, ciphertext: bytes) -> str:
        """
        Decrypt encrypted data
        
        Args:
            ciphertext: The encrypted data as bytes
        
        Returns:
            Decrypted plaintext as string
        
        Raises:
            ValueError: If ciphertext is empty or None
            cryptography.fernet.InvalidToken: If decryption fails (wrong key or corrupted data)
        """
        if not ciphertext:
            raise ValueError("Cannot decrypt empty or None value")
        
        # Decrypt and return as string
        decrypted_bytes = self.cipher.decrypt(ciphertext)
        return decrypted_bytes.decode('utf-8')
    
    @staticmethod
    def mask_aadhaar(aadhaar: str) -> str:
        """
        Mask Aadhaar number to show only last 4 digits
        Format: XXXX-XXXX-1234
        
        Args:
            aadhaar: 12-digit Aadhaar number (with or without hyphens)
        
        Returns:
            Masked Aadhaar string
        
        Example:
            >>> mask_aadhaar("123456789012")
            "XXXX-XXXX-9012"
            >>> mask_aadhaar("1234-5678-9012")
            "XXXX-XXXX-9012"
        """
        if not aadhaar:
            return ""
        
        # Remove any existing hyphens or spaces
        clean_aadhaar = aadhaar.replace('-', '').replace(' ', '')
        
        # Validate length
        if len(clean_aadhaar) != 12:
            return "XXXX-XXXX-XXXX"  # Return fully masked if invalid
        
        # Get last 4 digits
        last_four = clean_aadhaar[-4:]
        
        # Return masked format
        return f"XXXX-XXXX-{last_four}"
    
    @staticmethod
    def mask_bank_account(account_number: str) -> str:
        """
        Mask bank account number to show only last 4 digits
        Format: XXXXXXXXXX1234
        
        Args:
            account_number: Bank account number (9-18 digits)
        
        Returns:
            Masked account number string
        
        Example:
            >>> mask_bank_account("1234567890123456")
            "XXXXXXXXXXXX3456"
            >>> mask_bank_account("123456789")
            "XXXXX6789"
        """
        if not account_number:
            return ""
        
        # Remove any spaces or hyphens
        clean_account = account_number.replace(' ', '').replace('-', '')
        
        # Validate it's numeric and reasonable length
        if not clean_account.isdigit() or len(clean_account) < 4:
            return "XXXX"  # Return minimal mask if invalid
        
        # Get last 4 digits
        last_four = clean_account[-4:]
        
        # Calculate number of X's needed
        num_x = len(clean_account) - 4
        
        # Return masked format
        return f"{'X' * num_x}{last_four}"
    
    @staticmethod
    def generate_key() -> str:
        """
        Generate a new Fernet encryption key
        
        Returns:
            Base64-encoded encryption key as string
        
        Note:
            This should only be used once during initial setup.
            Store the generated key securely in environment variables.
        """
        return Fernet.generate_key().decode()


# Singleton instance for application-wide use
_encryption_service_instance: Optional[EncryptionService] = None


def get_encryption_service() -> EncryptionService:
    """
    Get or create singleton EncryptionService instance
    
    Returns:
        EncryptionService instance
    """
    global _encryption_service_instance
    
    if _encryption_service_instance is None:
        _encryption_service_instance = EncryptionService()
    
    return _encryption_service_instance
