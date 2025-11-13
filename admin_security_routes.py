"""
Admin Security Routes
Handles security-related admin operations including:
- Audit log viewing
- 2FA management
- Security settings
- IP whitelist management
"""

from flask import render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from app import app, db
from models import AdminActionLog, User, LoginAttempt
from role_hierarchy import admin_required
from security_enhancements import get_admin_action_logs, TwoFactorAuth
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


@app.route('/admin/security/audit-log')
@login_required
@admin_required
def admin_audit_log():
    """View comprehensive audit log of all admin actions"""
    page = request.args.get('page', 1, type=int)
    per_page = 50
    
    # Get filter parameters
    admin_id = request.args.get('admin_id', type=int)
    action_type = request.args.get('action_type', '')
    target_type = request.args.get('target_type', '')
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    
    # Build filters
    filters = {}
    if admin_id:
        filters['admin_id'] = admin_id
    if action_type:
        filters['action_type'] = action_type
    if target_type:
        filters['target_type'] = target_type
    if date_from:
        try:
            filters['date_from'] = datetime.strptime(date_from, '%Y-%m-%d')
        except ValueError:
            pass
    if date_to:
        try:
            filters['date_to'] = datetime.strptime(date_to, '%Y-%m-%d')
        except ValueError:
            pass
    
    # Get logs
    logs = get_admin_action_logs(page=page, per_page=per_page, filters=filters)
    
    # Get all admins for filter dropdown
    admins = User.query.filter_by(role='admin').all()
    
    # Get unique action types and target types for filters
    action_types = db.session.query(AdminActionLog.action_type).distinct().all()
    action_types = [at[0] for at in action_types if at[0]]
    
    target_types = db.session.query(AdminActionLog.target_type).distinct().all()
    target_types = [tt[0] for tt in target_types if tt[0]]
    
    # Get statistics
    total_actions = AdminActionLog.query.count()
    actions_today = AdminActionLog.query.filter(
        AdminActionLog.created_at >= datetime.utcnow().replace(hour=0, minute=0, second=0)
    ).count()
    actions_this_week = AdminActionLog.query.filter(
        AdminActionLog.created_at >= datetime.utcnow() - timedelta(days=7)
    ).count()
    
    return render_template('admin/security/audit_log.html',
                         logs=logs,
                         admins=admins,
                         action_types=action_types,
                         target_types=target_types,
                         total_actions=total_actions,
                         actions_today=actions_today,
                         actions_this_week=actions_this_week,
                         filters=filters)


@app.route('/admin/security/login-attempts')
@login_required
@admin_required
def admin_login_attempts():
    """View login attempts for security monitoring"""
    page = request.args.get('page', 1, type=int)
    per_page = 50
    
    # Get filter parameters
    success_filter = request.args.get('success', 'all')
    user_id = request.args.get('user_id', type=int)
    ip_address = request.args.get('ip', '')
    date_from = request.args.get('date_from', '')
    
    # Build query
    query = LoginAttempt.query
    
    if success_filter == 'success':
        query = query.filter_by(success=True)
    elif success_filter == 'failed':
        query = query.filter_by(success=False)
    
    if user_id:
        query = query.filter_by(user_id=user_id)
    
    if ip_address:
        query = query.filter(LoginAttempt.ip_address.like(f'%{ip_address}%'))
    
    if date_from:
        try:
            date_from_dt = datetime.strptime(date_from, '%Y-%m-%d')
            query = query.filter(LoginAttempt.timestamp >= date_from_dt)
        except ValueError:
            pass
    
    # Order by most recent first
    attempts = query.order_by(LoginAttempt.timestamp.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    # Get statistics
    total_attempts = LoginAttempt.query.count()
    failed_attempts = LoginAttempt.query.filter_by(success=False).count()
    failed_today = LoginAttempt.query.filter(
        LoginAttempt.success == False,
        LoginAttempt.timestamp >= datetime.utcnow().replace(hour=0, minute=0, second=0)
    ).count()
    
    # Get suspicious IPs (more than 5 failed attempts in last hour)
    one_hour_ago = datetime.utcnow() - timedelta(hours=1)
    suspicious_ips = db.session.query(
        LoginAttempt.ip_address,
        db.func.count(LoginAttempt.id).label('count')
    ).filter(
        LoginAttempt.success == False,
        LoginAttempt.timestamp >= one_hour_ago
    ).group_by(LoginAttempt.ip_address).having(
        db.func.count(LoginAttempt.id) > 5
    ).all()
    
    return render_template('admin/security/login_attempts.html',
                         attempts=attempts,
                         total_attempts=total_attempts,
                         failed_attempts=failed_attempts,
                         failed_today=failed_today,
                         suspicious_ips=suspicious_ips,
                         success_filter=success_filter)


@app.route('/admin/security/2fa-settings')
@login_required
@admin_required
def admin_2fa_settings():
    """Manage 2FA settings for admin accounts"""
    # Get all admin users
    admins = User.query.filter_by(role='admin').all()
    
    # Count 2FA enabled admins
    enabled_count = sum(1 for admin in admins if admin.two_factor_enabled)
    
    return render_template('admin/security/2fa_settings.html',
                         admins=admins,
                         enabled_count=enabled_count)


@app.route('/admin/security/enable-2fa', methods=['POST'])
@login_required
@admin_required
def admin_enable_2fa():
    """Enable 2FA for current admin user"""
    if current_user.two_factor_enabled:
        flash('2FA is already enabled for your account.', 'info')
        return redirect(url_for('admin_2fa_settings'))
    
    try:
        # Generate TOTP secret
        secret = TwoFactorAuth.generate_totp_secret()
        current_user.two_factor_secret = secret
        
        # Generate backup codes
        backup_codes = TwoFactorAuth.generate_backup_codes()
        import json
        current_user.backup_codes = json.dumps(backup_codes)
        
        db.session.commit()
        
        # Get QR code URI
        qr_uri = TwoFactorAuth.get_totp_uri(secret, current_user.username)
        
        flash('2FA setup initiated. Please scan the QR code with your authenticator app.', 'success')
        return render_template('admin/security/2fa_setup.html',
                             qr_uri=qr_uri,
                             secret=secret,
                             backup_codes=backup_codes)
    
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error enabling 2FA: {str(e)}")
        flash('Failed to enable 2FA. Please try again.', 'danger')
        return redirect(url_for('admin_2fa_settings'))


@app.route('/admin/security/verify-2fa', methods=['POST'])
@login_required
@admin_required
def admin_verify_2fa():
    """Verify 2FA token to complete setup"""
    token = request.form.get('token', '').strip()
    
    if not token:
        flash('Please enter the verification code.', 'warning')
        return redirect(url_for('admin_2fa_settings'))
    
    if not current_user.two_factor_secret:
        flash('2FA is not set up. Please start the setup process first.', 'warning')
        return redirect(url_for('admin_2fa_settings'))
    
    try:
        # Verify token
        if TwoFactorAuth.verify_totp(current_user.two_factor_secret, token):
            current_user.two_factor_enabled = True
            current_user.two_factor_verified_at = datetime.utcnow()
            db.session.commit()
            
            flash('2FA has been successfully enabled for your account!', 'success')
            logger.info(f"2FA enabled for admin user {current_user.id}")
        else:
            flash('Invalid verification code. Please try again.', 'danger')
    
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error verifying 2FA: {str(e)}")
        flash('Failed to verify 2FA. Please try again.', 'danger')
    
    return redirect(url_for('admin_2fa_settings'))


@app.route('/admin/security/disable-2fa', methods=['POST'])
@login_required
@admin_required
def admin_disable_2fa():
    """Disable 2FA for current admin user"""
    if not current_user.two_factor_enabled:
        flash('2FA is not enabled for your account.', 'info')
        return redirect(url_for('admin_2fa_settings'))
    
    try:
        current_user.two_factor_enabled = False
        current_user.two_factor_secret = None
        current_user.backup_codes = None
        db.session.commit()
        
        flash('2FA has been disabled for your account.', 'info')
        logger.warning(f"2FA disabled for admin user {current_user.id}")
    
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error disabling 2FA: {str(e)}")
        flash('Failed to disable 2FA. Please try again.', 'danger')
    
    return redirect(url_for('admin_2fa_settings'))


@app.route('/admin/security/settings', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_security_settings():
    """Manage general security settings"""
    from models import SystemSettings
    
    if request.method == 'POST':
        try:
            # Update IP whitelist
            ip_whitelist = request.form.get('ip_whitelist', '').strip()
            setting = SystemSettings.query.filter_by(setting_key='admin_ip_whitelist').first()
            if not setting:
                setting = SystemSettings(
                    setting_key='admin_ip_whitelist',
                    setting_value=ip_whitelist,
                    value_type='text',
                    description='Comma-separated list of IPs allowed for admin access'
                )
                db.session.add(setting)
            else:
                setting.set_value(ip_whitelist)
            
            # Update session timeout
            session_timeout = request.form.get('session_timeout', type=int)
            if session_timeout:
                setting = SystemSettings.query.filter_by(setting_key='session_timeout').first()
                if not setting:
                    setting = SystemSettings(
                        setting_key='session_timeout',
                        setting_value=str(session_timeout),
                        value_type='integer',
                        description='Session timeout in seconds'
                    )
                    db.session.add(setting)
                else:
                    setting.set_value(session_timeout)
            
            # Update max login attempts
            max_attempts = request.form.get('max_login_attempts', type=int)
            if max_attempts:
                setting = SystemSettings.query.filter_by(setting_key='max_login_attempts').first()
                if not setting:
                    setting = SystemSettings(
                        setting_key='max_login_attempts',
                        setting_value=str(max_attempts),
                        value_type='integer',
                        description='Maximum login attempts before lockout'
                    )
                    db.session.add(setting)
                else:
                    setting.set_value(max_attempts)
            
            db.session.commit()
            flash('Security settings updated successfully!', 'success')
            logger.info(f"Security settings updated by admin {current_user.id}")
        
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error updating security settings: {str(e)}")
            flash('Failed to update security settings.', 'danger')
    
    # Get current settings
    ip_whitelist_setting = SystemSettings.query.filter_by(setting_key='admin_ip_whitelist').first()
    session_timeout_setting = SystemSettings.query.filter_by(setting_key='session_timeout').first()
    max_attempts_setting = SystemSettings.query.filter_by(setting_key='max_login_attempts').first()
    
    return render_template('admin/security/settings.html',
                         ip_whitelist=ip_whitelist_setting.get_value() if ip_whitelist_setting else '',
                         session_timeout=session_timeout_setting.get_value() if session_timeout_setting else 3600,
                         max_attempts=max_attempts_setting.get_value() if max_attempts_setting else 5)


@app.route('/admin/security/export-audit-log')
@login_required
@admin_required
def admin_export_audit_log():
    """Export audit log to CSV"""
    import csv
    from io import StringIO
    from flask import make_response
    
    # Get all logs (or filtered logs)
    logs = AdminActionLog.query.order_by(AdminActionLog.created_at.desc()).all()
    
    # Create CSV
    si = StringIO()
    writer = csv.writer(si)
    
    # Write header
    writer.writerow([
        'ID', 'Admin ID', 'Admin Username', 'Action Type', 'Target Type',
        'Target ID', 'Description', 'IP Address', 'User Agent', 'Timestamp'
    ])
    
    # Write data
    for log in logs:
        writer.writerow([
            log.id,
            log.admin_id,
            log.admin.username if log.admin else 'Unknown',
            log.action_type,
            log.target_type,
            log.target_id,
            log.description,
            log.ip_address,
            log.user_agent,
            log.created_at.strftime('%Y-%m-%d %H:%M:%S')
        ])
    
    # Create response
    output = make_response(si.getvalue())
    output.headers["Content-Disposition"] = f"attachment; filename=audit_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    output.headers["Content-type"] = "text/csv"
    
    logger.info(f"Audit log exported by admin {current_user.id}")
    return output
