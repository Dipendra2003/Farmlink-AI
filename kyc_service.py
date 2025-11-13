"""
KYC Business Logic Service
Handles KYC submission, verification, and status management
"""

import logging
from datetime import datetime
from typing import Optional, Dict, List, Tuple
from sqlalchemy import func
from flask import current_app

from extensions import db
from models import SellerKYC, KYCAuditLog, User
from encryption_service import get_encryption_service
from kyc_file_service import KYCFileService
from email_service import EmailService

logger = logging.getLogger(__name__)
email_service = EmailService()


class KYCService:
    """Service for KYC business logic"""
    
    @staticmethod
    def submit_kyc(user_id: int, form_data: Dict, files: Dict) -> Tuple[bool, str, Optional[SellerKYC]]:
        """
        Submit KYC application
        
        Args:
            user_id: User ID submitting KYC
            form_data: Dictionary containing form fields (aadhaar_no, pan_no, bank_account, ifsc)
            files: Dictionary containing uploaded files (aadhaar_front, aadhaar_back, pan_card, land_proof)
        
        Returns:
            Tuple of (success: bool, message: str, kyc_record: SellerKYC or None)
        """
        try:
            # Check if user exists and is a seller
            user = User.query.get(user_id)
            if not user:
                return False, "User not found", None
            
            if user.role not in ['farmer', 'manager_farmer']:
                return False, "Only sellers can submit KYC", None
            
            # Check if user already has pending or verified KYC (non-archived)
            existing_kyc = SellerKYC.query.filter_by(
                user_id=user_id, 
                is_archived=False
            ).order_by(SellerKYC.created_at.desc()).first()
            
            is_resubmission = False
            old_status = None
            
            if existing_kyc:
                if existing_kyc.status == 'verified':
                    return False, "You already have a verified KYC application", None
                elif existing_kyc.status == 'pending':
                    return False, "You already have a pending KYC application. Please wait for review.", None
                elif existing_kyc.status == 'rejected':
                    # Archive the rejected KYC record
                    is_resubmission = True
                    old_status = existing_kyc.status
                    existing_kyc.is_archived = True
                    logger.info(f"Archiving rejected KYC record {existing_kyc.id} for user {user_id}")
            
            # Get encryption service
            encryption_service = get_encryption_service()
            
            # Encrypt sensitive data
            try:
                aadhaar_encrypted = encryption_service.encrypt(form_data['aadhaar_no'])
                pan_encrypted = encryption_service.encrypt(form_data['pan_no'])
                bank_account_encrypted = encryption_service.encrypt(form_data['bank_account'])
            except Exception as e:
                logger.error(f"Encryption error for user {user_id}: {str(e)}")
                return False, "Failed to encrypt sensitive data. Please try again.", None
            
            # Save uploaded files
            document_paths = {}
            file_service = KYCFileService()
            
            # Required files
            required_files = {
                'aadhaar_front': files.get('aadhaar_front'),
                'aadhaar_back': files.get('aadhaar_back'),
                'pan_card': files.get('pan_card')
            }
            
            for doc_type, file in required_files.items():
                if not file:
                    return False, f"Missing required document: {doc_type}", None
                
                file_path = file_service.save_kyc_document(file, user_id, doc_type)
                if not file_path:
                    return False, f"Failed to save {doc_type}. Please check file format and size.", None
                
                document_paths[doc_type] = file_path
            
            # Optional land proof
            if files.get('land_proof'):
                land_proof_path = file_service.save_kyc_document(files['land_proof'], user_id, 'land_proof')
                if land_proof_path:
                    document_paths['land_proof'] = land_proof_path
            
            # Create new KYC record
            kyc_record = SellerKYC(
                user_id=user_id,
                aadhaar_no_encrypted=aadhaar_encrypted,
                pan_no_encrypted=pan_encrypted,
                bank_account_encrypted=bank_account_encrypted,
                ifsc=form_data['ifsc'],
                document_paths=document_paths,
                status='pending',
                is_archived=False
            )
            
            db.session.add(kyc_record)
            db.session.flush()  # Get the ID
            
            # Create audit log entry
            audit_log = KYCAuditLog(
                kyc_id=kyc_record.id,
                action='resubmitted' if is_resubmission else 'submitted',
                performed_by=user_id,
                old_status=old_status,
                new_status='pending',
                notes='KYC application resubmitted after rejection' if is_resubmission else 'KYC application submitted'
            )
            db.session.add(audit_log)
            
            # Commit transaction
            db.session.commit()
            
            logger.info(f"KYC {'resubmitted' if is_resubmission else 'submitted'} successfully for user {user_id}, KYC ID: {kyc_record.id}")
            
            # Send confirmation email
            try:
                email_service.send_kyc_submission_confirmation(user)
            except Exception as e:
                logger.error(f"Failed to send KYC submission confirmation email: {str(e)}")
                # Don't fail the submission if email fails
            
            return True, "KYC application submitted successfully. You will be notified once reviewed.", kyc_record
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error submitting KYC for user {user_id}: {str(e)}", exc_info=True)
            return False, "An error occurred while submitting KYC. Please try again.", None
    
    @staticmethod
    def get_kyc_status(user_id: int) -> Optional[SellerKYC]:
        """
        Get KYC status for a user (most recent non-archived record)
        
        Args:
            user_id: User ID to check
        
        Returns:
            SellerKYC record or None if not found
        """
        try:
            kyc_record = SellerKYC.query.filter_by(
                user_id=user_id,
                is_archived=False
            ).order_by(SellerKYC.created_at.desc()).first()
            return kyc_record
        except Exception as e:
            logger.error(f"Error getting KYC status for user {user_id}: {str(e)}")
            return None
    
    @staticmethod
    def approve_kyc(kyc_id: int, admin_id: int) -> Tuple[bool, str]:
        """
        Approve KYC application
        
        Args:
            kyc_id: KYC record ID to approve
            admin_id: Admin user ID performing the action
        
        Returns:
            Tuple of (success: bool, message: str)
        """
        try:
            # Get KYC record
            kyc_record = SellerKYC.query.get(kyc_id)
            if not kyc_record:
                return False, "KYC record not found"
            
            # Check if already verified
            if kyc_record.status == 'verified':
                return False, "KYC is already verified"
            
            # Update status
            old_status = kyc_record.status
            kyc_record.status = 'verified'
            kyc_record.verified_by = admin_id
            kyc_record.verified_at = datetime.utcnow()
            kyc_record.rejection_reason = None  # Clear any previous rejection reason
            
            # Create audit log entry
            audit_log = KYCAuditLog(
                kyc_id=kyc_id,
                action='approved',
                performed_by=admin_id,
                old_status=old_status,
                new_status='verified',
                notes='KYC application approved by admin'
            )
            db.session.add(audit_log)
            
            # Commit transaction
            db.session.commit()
            
            logger.info(f"KYC {kyc_id} approved by admin {admin_id}")
            
            # Send approval email
            try:
                email_service.send_kyc_approval_notification(kyc_record.user)
            except Exception as e:
                logger.error(f"Failed to send KYC approval email: {str(e)}")
                # Don't fail the approval if email fails
            
            return True, "KYC approved successfully"
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error approving KYC {kyc_id}: {str(e)}", exc_info=True)
            return False, "An error occurred while approving KYC. Please try again."
    
    @staticmethod
    def reject_kyc(kyc_id: int, admin_id: int, reason: str) -> Tuple[bool, str]:
        """
        Reject KYC application
        
        Args:
            kyc_id: KYC record ID to reject
            admin_id: Admin user ID performing the action
            reason: Rejection reason (minimum 10 characters)
        
        Returns:
            Tuple of (success: bool, message: str)
        """
        try:
            # Validate rejection reason
            if not reason or len(reason.strip()) < 10:
                return False, "Rejection reason must be at least 10 characters"
            
            # Get KYC record
            kyc_record = SellerKYC.query.get(kyc_id)
            if not kyc_record:
                return False, "KYC record not found"
            
            # Check if already rejected
            if kyc_record.status == 'rejected':
                return False, "KYC is already rejected"
            
            # Update status
            old_status = kyc_record.status
            kyc_record.status = 'rejected'
            kyc_record.rejection_reason = reason.strip()
            kyc_record.verified_by = admin_id
            kyc_record.verified_at = datetime.utcnow()
            
            # Create audit log entry
            audit_log = KYCAuditLog(
                kyc_id=kyc_id,
                action='rejected',
                performed_by=admin_id,
                old_status=old_status,
                new_status='rejected',
                notes=f'KYC application rejected: {reason.strip()}'
            )
            db.session.add(audit_log)
            
            # Commit transaction
            db.session.commit()
            
            logger.info(f"KYC {kyc_id} rejected by admin {admin_id}")
            
            # Send rejection email
            try:
                email_service.send_kyc_rejection_notification(kyc_record.user, reason.strip())
            except Exception as e:
                logger.error(f"Failed to send KYC rejection email: {str(e)}")
                # Don't fail the rejection if email fails
            
            return True, "KYC rejected successfully"
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error rejecting KYC {kyc_id}: {str(e)}", exc_info=True)
            return False, "An error occurred while rejecting KYC. Please try again."
    
    @staticmethod
    def get_pending_kyc_list(limit: Optional[int] = None, offset: int = 0) -> List[SellerKYC]:
        """
        Get all pending KYC applications for admin dashboard (non-archived only)
        
        Args:
            limit: Maximum number of records to return (None for all)
            offset: Number of records to skip
        
        Returns:
            List of SellerKYC records with status 'pending'
        """
        try:
            query = SellerKYC.query.filter_by(
                status='pending',
                is_archived=False
            ).order_by(SellerKYC.created_at.asc())
            
            if limit:
                query = query.limit(limit).offset(offset)
            
            return query.all()
        except Exception as e:
            logger.error(f"Error getting pending KYC list: {str(e)}")
            return []
    
    @staticmethod
    def get_kyc_statistics() -> Dict:
        """
        Get KYC statistics for admin analytics (non-archived records only)
        
        Returns:
            Dictionary containing KYC statistics:
            - total_submissions: Total KYC submissions (including archived)
            - pending_count: Number of pending applications
            - verified_count: Number of verified applications
            - rejected_count: Number of rejected applications
            - avg_verification_time_hours: Average time to verify (in hours)
            - oldest_pending_days: Age of oldest pending application (in days)
            - submissions_last_30_days: List of daily submission counts for last 30 days
            - oldest_pending_applications: List of 10 oldest pending applications
        """
        try:
            # Get counts by status (non-archived only for active counts)
            total_submissions = SellerKYC.query.count()  # Include archived for total
            pending_count = SellerKYC.query.filter_by(status='pending', is_archived=False).count()
            verified_count = SellerKYC.query.filter_by(status='verified', is_archived=False).count()
            rejected_count = SellerKYC.query.filter_by(status='rejected', is_archived=False).count()
            
            # Calculate average verification time (for verified and rejected applications, non-archived)
            verified_records = SellerKYC.query.filter(
                SellerKYC.status.in_(['verified', 'rejected']),
                SellerKYC.verified_at.isnot(None),
                SellerKYC.is_archived == False
            ).all()
            
            avg_verification_time_hours = 0
            if verified_records:
                total_hours = 0
                for record in verified_records:
                    time_diff = record.verified_at - record.created_at
                    total_hours += time_diff.total_seconds() / 3600
                avg_verification_time_hours = round(total_hours / len(verified_records), 2)
            
            # Get oldest pending application age (non-archived)
            oldest_pending = SellerKYC.query.filter_by(
                status='pending',
                is_archived=False
            ).order_by(
                SellerKYC.created_at.asc()
            ).first()
            
            oldest_pending_days = 0
            if oldest_pending:
                time_diff = datetime.utcnow() - oldest_pending.created_at
                oldest_pending_days = time_diff.days
            
            # Get submissions for last 30 days (grouped by date, all submissions including archived)
            from datetime import timedelta
            thirty_days_ago = datetime.utcnow() - timedelta(days=30)
            
            submissions_by_date = db.session.query(
                func.date(SellerKYC.created_at).label('date'),
                func.count(SellerKYC.id).label('count')
            ).filter(
                SellerKYC.created_at >= thirty_days_ago
            ).group_by(
                func.date(SellerKYC.created_at)
            ).order_by('date').all()
            
            # Format submissions data
            submissions_last_30_days = [
                {'date': str(row.date), 'count': row.count}
                for row in submissions_by_date
            ]
            
            # Get 10 oldest pending applications (non-archived)
            oldest_pending_applications = SellerKYC.query.filter_by(
                status='pending',
                is_archived=False
            ).order_by(
                SellerKYC.created_at.asc()
            ).limit(10).all()
            
            return {
                'total_submissions': total_submissions,
                'pending_count': pending_count,
                'verified_count': verified_count,
                'rejected_count': rejected_count,
                'avg_verification_time_hours': avg_verification_time_hours,
                'oldest_pending_days': oldest_pending_days,
                'submissions_last_30_days': submissions_last_30_days,
                'oldest_pending_applications': oldest_pending_applications
            }
            
        except Exception as e:
            logger.error(f"Error getting KYC statistics: {str(e)}", exc_info=True)
            return {
                'total_submissions': 0,
                'pending_count': 0,
                'verified_count': 0,
                'rejected_count': 0,
                'avg_verification_time_hours': 0,
                'oldest_pending_days': 0,
                'submissions_last_30_days': [],
                'oldest_pending_applications': []
            }
    
    @staticmethod
    def is_seller_verified(user_id: int) -> bool:
        """
        Check if seller has verified KYC (most recent non-archived record)
        
        Args:
            user_id: User ID to check
        
        Returns:
            True if seller has verified KYC, False otherwise
        """
        try:
            # Check if user is a seller
            user = User.query.get(user_id)
            if not user or user.role not in ['farmer', 'manager_farmer']:
                return True  # Non-sellers don't need KYC
            
            # Check KYC status (most recent non-archived)
            kyc_record = SellerKYC.query.filter_by(
                user_id=user_id, 
                status='verified',
                is_archived=False
            ).order_by(SellerKYC.created_at.desc()).first()
            return kyc_record is not None
            
        except Exception as e:
            logger.error(f"Error checking seller verification for user {user_id}: {str(e)}")
            return False
    
    @staticmethod
    def get_kyc_by_id(kyc_id: int) -> Optional[SellerKYC]:
        """
        Get KYC record by ID
        
        Args:
            kyc_id: KYC record ID
        
        Returns:
            SellerKYC record or None if not found
        """
        try:
            return SellerKYC.query.get(kyc_id)
        except Exception as e:
            logger.error(f"Error getting KYC record {kyc_id}: {str(e)}")
            return None
    
    @staticmethod
    def get_decrypted_kyc_data(kyc_record: SellerKYC) -> Dict:
        """
        Get decrypted KYC data for admin view
        
        Args:
            kyc_record: SellerKYC record
        
        Returns:
            Dictionary with decrypted data and masked versions
        """
        try:
            encryption_service = get_encryption_service()
            
            # Decrypt sensitive data
            aadhaar = encryption_service.decrypt(kyc_record.aadhaar_no_encrypted)
            pan = encryption_service.decrypt(kyc_record.pan_no_encrypted)
            bank_account = encryption_service.decrypt(kyc_record.bank_account_encrypted)
            
            # Create masked versions
            aadhaar_masked = encryption_service.mask_aadhaar(aadhaar)
            bank_account_masked = encryption_service.mask_bank_account(bank_account)
            
            return {
                'aadhaar': aadhaar,
                'aadhaar_masked': aadhaar_masked,
                'pan': pan,
                'bank_account': bank_account,
                'bank_account_masked': bank_account_masked,
                'ifsc': kyc_record.ifsc
            }
            
        except Exception as e:
            logger.error(f"Error decrypting KYC data for record {kyc_record.id}: {str(e)}")
            return {
                'aadhaar': 'Error',
                'aadhaar_masked': 'XXXX-XXXX-XXXX',
                'pan': 'Error',
                'bank_account': 'Error',
                'bank_account_masked': 'XXXX',
                'ifsc': kyc_record.ifsc
            }
    
    @staticmethod
    def get_all_kyc_list(status: Optional[str] = None, limit: Optional[int] = None, offset: int = 0, include_archived: bool = False) -> List[SellerKYC]:
        """
        Get all KYC applications with optional filtering
        
        Args:
            status: Filter by status ('pending', 'verified', 'rejected', or None for all)
            limit: Maximum number of records to return (None for all)
            offset: Number of records to skip
            include_archived: Whether to include archived records (default False)
        
        Returns:
            List of SellerKYC records
        """
        try:
            query = SellerKYC.query
            
            if not include_archived:
                query = query.filter_by(is_archived=False)
            
            if status:
                query = query.filter_by(status=status)
            
            query = query.order_by(SellerKYC.created_at.desc())
            
            if limit:
                query = query.limit(limit).offset(offset)
            
            return query.all()
        except Exception as e:
            logger.error(f"Error getting KYC list: {str(e)}")
            return []
    
    @staticmethod
    def get_user_kyc_history(user_id: int) -> List[SellerKYC]:
        """
        Get all KYC submissions for a user (including archived) for admin audit access
        
        Args:
            user_id: User ID to get history for
        
        Returns:
            List of all SellerKYC records for the user, ordered by created_at descending
        """
        try:
            return SellerKYC.query.filter_by(
                user_id=user_id
            ).order_by(SellerKYC.created_at.desc()).all()
        except Exception as e:
            logger.error(f"Error getting KYC history for user {user_id}: {str(e)}")
            return []
