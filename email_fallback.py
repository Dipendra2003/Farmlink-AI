"""
Email Fallback Service - Graceful degradation when SMTP fails
"""
import logging
from datetime import datetime
import json
import os

class EmailFallbackService:
    """Handles email failures gracefully"""
    
    def __init__(self):
        self.fallback_log = "email_fallback.log"
        self.failed_emails = []
    
    def log_failed_email(self, to_email, subject, html_content, error):
        """Log failed email for later retry"""
        failed_email = {
            "timestamp": datetime.utcnow().isoformat(),
            "to": to_email,
            "subject": subject,
            "error": str(error),
            "html_preview": html_content[:200] if html_content else None
        }
        
        self.failed_emails.append(failed_email)
        
        # Log to file
        try:
            with open(self.fallback_log, 'a') as f:
                f.write(json.dumps(failed_email) + '\n')
        except Exception as e:
            logging.error(f"Failed to log email failure: {e}")
        
        logging.warning(f"Email failed and logged for retry: {to_email} - {subject}")
    
    def get_failed_emails(self, limit=100):
        """Retrieve failed emails for retry"""
        return self.failed_emails[-limit:]
    
    def retry_failed_emails(self, email_service):
        """Retry sending failed emails"""
        if not self.failed_emails:
            return {"success": True, "message": "No failed emails to retry"}
        
        retry_results = {
            "total": len(self.failed_emails),
            "success": 0,
            "failed": 0,
            "errors": []
        }
        
        emails_to_retry = self.failed_emails.copy()
        self.failed_emails.clear()
        
        for email_data in emails_to_retry:
            try:
                # Attempt to resend
                result = email_service.send_email(
                    email_data['to'],
                    email_data['subject'],
                    email_data.get('html_preview', '')
                )
                
                if result.get('success'):
                    retry_results['success'] += 1
                else:
                    retry_results['failed'] += 1
                    self.failed_emails.append(email_data)
                    retry_results['errors'].append(result.get('error'))
            except Exception as e:
                retry_results['failed'] += 1
                self.failed_emails.append(email_data)
                retry_results['errors'].append(str(e))
        
        return retry_results
    
    def send_notification_to_admin(self, admin_email, failure_count):
        """Notify admin about email failures (via alternative method)"""
        logging.critical(f"EMAIL SYSTEM FAILURE: {failure_count} emails failed to send")
        # In production, you could use SMS, Slack webhook, or other notification method
        return {"success": True, "message": "Admin notified via logs"}

# Global instance
email_fallback = EmailFallbackService()
