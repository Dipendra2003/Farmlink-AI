"""
FarmLink AI - Admin Analytics Routes
Comprehensive analytics and reporting for administrators
"""

from flask import render_template, redirect, url_for, flash, request, jsonify, send_file
from flask_login import login_required, current_user
from app import app, db
from models import User, Crop, Order, Payment
from role_hierarchy import admin_required
from analytics_service import AnalyticsService
from datetime import datetime, timedelta
import io
import csv
import json
import logging

logger = logging.getLogger(__name__)


@app.route('/admin/analytics')
@login_required
@admin_required
def admin_analytics_dashboard():
    """Main analytics dashboard for administrators"""
    # Get date range from query params or default to last 30 days
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=30)
    
    date_range = request.args.get('range', '30')
    if date_range == '7':
        start_date = end_date - timedelta(days=7)
    elif date_range == '90':
        start_date = end_date - timedelta(days=90)
    elif date_range == '365':
        start_date = end_date - timedelta(days=365)
    
    # Get analytics data
    overview = AnalyticsService.get_platform_overview(start_date, end_date)
    monthly_comparison = AnalyticsService.get_monthly_comparison(6)
    
    return render_template(
        'admin/analytics_dashboard.html',
        overview=overview,
        monthly_comparison=monthly_comparison,
        date_range=date_range,
        start_date=start_date,
        end_date=end_date
    )


@app.route('/admin/analytics/sales')
@login_required
@admin_required
def admin_sales_report():
    """Detailed sales analytics and reports"""
    # Get date range
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=30)
    
    date_range = request.args.get('range', '30')
    if date_range == '7':
        start_date = end_date - timedelta(days=7)
    elif date_range == '90':
        start_date = end_date - timedelta(days=90)
    elif date_range == '365':
        start_date = end_date - timedelta(days=365)
    
    # Get sales report
    sales_report = AnalyticsService.get_sales_report(start_date, end_date)
    
    return render_template(
        'admin/sales_report.html',
        report=sales_report,
        date_range=date_range
    )


@app.route('/admin/analytics/crops')
@login_required
@admin_required
def admin_crop_analytics():
    """Crop statistics and analytics"""
    crop_analytics = AnalyticsService.get_crop_analytics()
    
    return render_template(
        'admin/crop_analytics.html',
        analytics=crop_analytics
    )


@app.route('/admin/analytics/users')
@login_required
@admin_required
def admin_user_analytics_report():
    """User analytics and statistics"""
    user_analytics = AnalyticsService.get_user_analytics_report()
    
    return render_template(
        'admin/user_analytics_report.html',
        analytics=user_analytics
    )


@app.route('/admin/analytics/engagement')
@login_required
@admin_required
def admin_engagement_metrics():
    """Platform engagement metrics"""
    engagement = AnalyticsService.get_engagement_metrics()
    
    return render_template(
        'admin/engagement_metrics.html',
        metrics=engagement
    )


# =============================================================================
# EXPORT ROUTES
# =============================================================================

@app.route('/admin/analytics/export/sales/<format>')
@login_required
@admin_required
def export_sales_report(format):
    """Export sales report in various formats"""
    try:
        # Get date range
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=30)
        
        date_range = request.args.get('range', '30')
        if date_range == '7':
            start_date = end_date - timedelta(days=7)
        elif date_range == '90':
            start_date = end_date - timedelta(days=90)
        elif date_range == '365':
            start_date = end_date - timedelta(days=365)
        
        # Get sales report
        report = AnalyticsService.get_sales_report(start_date, end_date)
        
        if format == 'csv':
            return _export_sales_csv(report)
        elif format == 'json':
            return _export_sales_json(report)
        elif format == 'pdf':
            return _export_sales_pdf(report)
        else:
            flash('Invalid export format', 'danger')
            return redirect(url_for('admin_sales_report'))
            
    except Exception as e:
        logger.error(f"Error exporting sales report: {str(e)}")
        flash('Error exporting report', 'danger')
        return redirect(url_for('admin_sales_report'))


@app.route('/admin/analytics/export/crops/<format>')
@login_required
@admin_required
def export_crop_analytics(format):
    """Export crop analytics in various formats"""
    try:
        analytics = AnalyticsService.get_crop_analytics()
        
        if format == 'csv':
            return _export_crop_csv(analytics)
        elif format == 'json':
            return _export_crop_json(analytics)
        else:
            flash('Invalid export format', 'danger')
            return redirect(url_for('admin_crop_analytics'))
            
    except Exception as e:
        logger.error(f"Error exporting crop analytics: {str(e)}")
        flash('Error exporting analytics', 'danger')
        return redirect(url_for('admin_crop_analytics'))


@app.route('/admin/analytics/export/users/<format>')
@login_required
@admin_required
def export_user_analytics(format):
    """Export user analytics in various formats"""
    try:
        analytics = AnalyticsService.get_user_analytics_report()
        
        if format == 'csv':
            return _export_user_csv(analytics)
        elif format == 'json':
            return _export_user_json(analytics)
        else:
            flash('Invalid export format', 'danger')
            return redirect(url_for('admin_user_analytics_report'))
            
    except Exception as e:
        logger.error(f"Error exporting user analytics: {str(e)}")
        flash('Error exporting analytics', 'danger')
        return redirect(url_for('admin_user_analytics_report'))


# =============================================================================
# HELPER FUNCTIONS FOR EXPORTS
# =============================================================================

def _export_sales_csv(report):
    """Export sales report as CSV"""
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Write summary
    writer.writerow(['Sales Report Summary'])
    writer.writerow(['Period', f"{report['period']['start']} to {report['period']['end']}"])
    writer.writerow(['Total Orders', report['summary']['total_orders']])
    writer.writerow(['Completed Orders', report['summary']['completed_orders']])
    writer.writerow(['Total Revenue', f"₹{report['summary']['total_revenue']:.2f}"])
    writer.writerow(['Average Order Value', f"₹{report['summary']['average_order_value']:.2f}"])
    writer.writerow([])
    
    # Write daily sales
    writer.writerow(['Daily Sales'])
    writer.writerow(['Date', 'Orders', 'Revenue'])
    for day in report['daily_sales']:
        writer.writerow([day['date'], day['orders'], f"₹{day['revenue']:.2f}"])
    writer.writerow([])
    
    # Write top crops
    writer.writerow(['Top Selling Crops'])
    writer.writerow(['Crop Name', 'Category', 'Orders', 'Revenue'])
    for crop in report['top_crops']:
        writer.writerow([crop['name'], crop['category'], crop['orders'], f"₹{crop['revenue']:.2f}"])
    
    output.seek(0)
    return send_file(
        io.BytesIO(output.getvalue().encode('utf-8')),
        mimetype='text/csv',
        as_attachment=True,
        download_name=f'sales_report_{datetime.now().strftime("%Y%m%d")}.csv'
    )


def _export_sales_json(report):
    """Export sales report as JSON"""
    output = json.dumps(report, indent=2)
    return send_file(
        io.BytesIO(output.encode('utf-8')),
        mimetype='application/json',
        as_attachment=True,
        download_name=f'sales_report_{datetime.now().strftime("%Y%m%d")}.json'
    )


def _export_sales_pdf(report):
    """Export sales report as PDF"""
    try:
        from reportlab.lib.pagesizes import A4, letter
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import inch
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER
        
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4)
        story = []
        styles = getSampleStyleSheet()
        
        # Title
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=24,
            textColor=colors.HexColor('#2E7D32'),
            spaceAfter=30,
            alignment=TA_CENTER
        )
        story.append(Paragraph("Sales Report", title_style))
        story.append(Spacer(1, 20))
        
        # Period
        story.append(Paragraph(f"Period: {report['period']['start']} to {report['period']['end']}", styles['Normal']))
        story.append(Spacer(1, 20))
        
        # Summary table
        summary_data = [
            ['Metric', 'Value'],
            ['Total Orders', str(report['summary']['total_orders'])],
            ['Completed Orders', str(report['summary']['completed_orders'])],
            ['Total Revenue', f"₹{report['summary']['total_revenue']:.2f}"],
            ['Average Order Value', f"₹{report['summary']['average_order_value']:.2f}"]
        ]
        
        summary_table = Table(summary_data, colWidths=[3*inch, 2*inch])
        summary_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 12),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        
        story.append(summary_table)
        story.append(Spacer(1, 30))
        
        # Top crops
        story.append(Paragraph("Top Selling Crops", styles['Heading2']))
        story.append(Spacer(1, 10))
        
        crop_data = [['Crop Name', 'Category', 'Orders', 'Revenue']]
        for crop in report['top_crops'][:10]:
            crop_data.append([
                crop['name'],
                crop['category'],
                str(crop['orders']),
                f"₹{crop['revenue']:.2f}"
            ])
        
        crop_table = Table(crop_data, colWidths=[2*inch, 1.5*inch, 1*inch, 1.5*inch])
        crop_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        
        story.append(crop_table)
        
        # Build PDF
        doc.build(story)
        buffer.seek(0)
        
        return send_file(
            buffer,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=f'sales_report_{datetime.now().strftime("%Y%m%d")}.pdf'
        )
        
    except ImportError:
        flash('PDF export requires reportlab library', 'warning')
        return redirect(url_for('admin_sales_report'))


def _export_crop_csv(analytics):
    """Export crop analytics as CSV"""
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Category statistics
    writer.writerow(['Crop Analytics by Category'])
    writer.writerow(['Category', 'Count', 'Total Quantity', 'Avg Price'])
    for cat in analytics['categories']:
        writer.writerow([cat['category'], cat['count'], cat['total_quantity'], f"₹{cat['avg_price']:.2f}"])
    writer.writerow([])
    
    # Top farmers
    writer.writerow(['Top Farmers'])
    writer.writerow(['Farmer Name', 'Crop Count', 'Total Value'])
    for farmer in analytics['top_farmers']:
        writer.writerow([farmer['name'], farmer['crop_count'], f"₹{farmer['total_value']:.2f}"])
    
    output.seek(0)
    return send_file(
        io.BytesIO(output.getvalue().encode('utf-8')),
        mimetype='text/csv',
        as_attachment=True,
        download_name=f'crop_analytics_{datetime.now().strftime("%Y%m%d")}.csv'
    )


def _export_crop_json(analytics):
    """Export crop analytics as JSON"""
    output = json.dumps(analytics, indent=2)
    return send_file(
        io.BytesIO(output.encode('utf-8')),
        mimetype='application/json',
        as_attachment=True,
        download_name=f'crop_analytics_{datetime.now().strftime("%Y%m%d")}.json'
    )


def _export_user_csv(analytics):
    """Export user analytics as CSV"""
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Top buyers
    writer.writerow(['Top Buyers'])
    writer.writerow(['Name', 'Orders', 'Total Spent'])
    for buyer in analytics['top_buyers']:
        writer.writerow([buyer['name'], buyer['orders'], f"₹{buyer['total_spent']:.2f}"])
    writer.writerow([])
    
    # Top farmers
    writer.writerow(['Top Farmers'])
    writer.writerow(['Name', 'Orders', 'Total Revenue'])
    for farmer in analytics['top_farmers']:
        writer.writerow([farmer['name'], farmer['orders'], f"₹{farmer['total_revenue']:.2f}"])
    writer.writerow([])
    
    # Top rated users
    writer.writerow(['Top Rated Users'])
    writer.writerow(['Name', 'Average Rating', 'Rating Count'])
    for user in analytics['top_rated_users']:
        writer.writerow([user['name'], f"{user['avg_rating']:.2f}", user['rating_count']])
    
    output.seek(0)
    return send_file(
        io.BytesIO(output.getvalue().encode('utf-8')),
        mimetype='text/csv',
        as_attachment=True,
        download_name=f'user_analytics_{datetime.now().strftime("%Y%m%d")}.csv'
    )


def _export_user_json(analytics):
    """Export user analytics as JSON"""
    output = json.dumps(analytics, indent=2)
    return send_file(
        io.BytesIO(output.encode('utf-8')),
        mimetype='application/json',
        as_attachment=True,
        download_name=f'user_analytics_{datetime.now().strftime("%Y%m%d")}.json'
    )
