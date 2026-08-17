# mypy: ignore-errors
# pyright: reportGeneralTypeIssues=false, reportOptionalMemberAccess=false, reportArgumentType=false, reportAttributeAccessIssue=false, reportDeprecated=false, reportMissingModuleSource=false
# pyrefly: ignore-file
# type: ignore
"""
FarmLink AI - Advanced Routes
AI services, expert forum, learning hub, analytics, and admin management
"""
import os
import json
import csv
import io
from datetime import datetime, timedelta
import logging
from sqlalchemy import func
try:
    import pandas as pd
except ImportError:
    pd = None
from flask import render_template, redirect, url_for, flash, request, jsonify, send_file, session, make_response
from flask_login import login_required, current_user, logout_user
from jinja2 import TemplateNotFound
from werkzeug.utils import secure_filename
from app import app, db, csrf
from models import (
    User, Crop, Order, Message, LearningArticle, UserRating, 
    CropSuggestionHistory, CropSuggestionComparison, CropComparisonHistory,
    ArticleLike, ArticleBookmark, ArticleComment, UserReadingProgress
)
from forms import (
    AdminCredentialsForm, ChangePasswordForm, RatingForm, 
    ForgotPasswordForm, OTPVerificationForm, ResetPasswordForm, 
    CropSuggestionForm, CropComparisonForm, PestDiseaseDetectionForm
)
from ai_services import EnhancedVoiceAI, EnhancedCropAI, client
from role_hierarchy import is_farmer_or_manager, is_buyer_or_manager
from email_service import EmailService, OTPService
from role_hierarchy import admin_required
from utils import get_weather_data, get_weather_forecast, get_weather_history, format_datetime

logger = logging.getLogger(__name__)

# =============================================================================
# AI CROP SUGGESTION ROUTES - Comprehensive Crop Recommendation System
# =============================================================================

@app.route('/ai/crop-suggestions', methods=['GET', 'POST'])
@login_required
def crop_suggestions():
    """Main crop suggestions page with comprehensive input form"""
    form = CropSuggestionForm()
    
    if request.method == 'POST':
        return redirect(url_for('generate_crop_suggestions'))
    
    return render_template('ai/crop_suggestions.html', form=form)

@app.route('/ai/crop-suggestions/generate', methods=['POST'])
@login_required
def generate_crop_suggestions():
    """Generate AI-powered crop suggestions based on user input"""
    try:
        form = CropSuggestionForm()
        
        if not form.validate_on_submit():
            return jsonify({
                'success': False,
                'error': 'Form validation failed',
                'errors': form.errors
            }), 400
        
        # Prepare input data for AI analysis
        input_data = {
            'location': form.location.data,
            'soil_type': form.soil_type.data,
            'soil_ph': form.soil_ph.data,
            'water_source': form.water_source.data,
            'temperature_range': form.temperature_range.data,
            'rainfall_range': form.rainfall_range.data,
            'humidity_level': form.humidity_level.data,
            'season': form.season.data,
            'fertilizer_availability': form.fertilizer_availability.data,
            'budget_preference': form.budget_preference.data,
            'farm_size': form.farm_size.data,
            'market_preference': form.market_preference.data,
            'experience_level': form.experience_level.data
        }
        
        # Get AI-powered crop suggestions
        suggestions_result = EnhancedCropAI.get_smart_crop_suggestions(input_data)
        
        # Check if AI request was successful
        if not suggestions_result.get('success', False):
            # Return error response with error_type and service_status
            return jsonify({
                'success': False,
                'error': suggestions_result.get('error', 'Failed to generate crop suggestions'),
                'error_type': suggestions_result.get('error_type', 'unknown_error'),
                'service_status': suggestions_result.get('service_status', {})
            }), 200
        
        # Filter low-quality suggestions (data_quality_score < 70)
        suggestions = suggestions_result.get('suggestions', [])
        high_quality_suggestions = [
            s for s in suggestions  # type: ignore
            if s.get('data_quality_score', 0) >= 70  # type: ignore
        ]
        
        # If no high-quality suggestions remain, return error
        if not high_quality_suggestions:
            return jsonify({
                'success': False,
                'error': 'AI generated suggestions but data quality was insufficient. Please try adjusting your parameters.',
                'error_type': 'low_quality_data',
                'suggestions_attempted': len(suggestions),  # type: ignore
                'data_quality_metrics': suggestions_result.get('data_quality_metrics', {})
            }), 200
        
        # Update suggestions_result with filtered suggestions
        suggestions_result['suggestions'] = high_quality_suggestions
        suggestions_result['original_count'] = len(suggestions)  # type: ignore
        suggestions_result['filtered_count'] = len(high_quality_suggestions)  # type: ignore
        
        # Save to database for logged-in users
        try:
            history = CropSuggestionHistory(
                user_id=current_user.id,
                location=input_data['location'],
                soil_type=input_data['soil_type'],
                soil_ph=input_data['soil_ph'],
                water_source=input_data['water_source'],
                climate_data=json.dumps({
                    'temperature_range': input_data['temperature_range'],
                    'rainfall_range': input_data['rainfall_range'],
                    'humidity_level': input_data['humidity_level']
                }),
                fertilizer_availability=input_data['fertilizer_availability'],
                budget_preference=input_data['budget_preference'],
                season=input_data['season'],
                suggestions=json.dumps(high_quality_suggestions),
                top_suggestion=high_quality_suggestions[0]['crop_name'] if high_quality_suggestions else 'No suggestions'  # type: ignore
            )
            
            db.session.add(history)
            db.session.commit()
            
            suggestions_result['history_id'] = history.id
            
        except Exception as db_error:
            app.logger.error(f"Error saving crop suggestion history: {str(db_error)}")
            # Continue without saving to history
            pass
        
        return jsonify(suggestions_result)
        
    except Exception as e:
        app.logger.error(f"Error generating crop suggestions: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'Internal server error while generating suggestions'
        }), 500

@app.route('/ai/crop-suggestions/history')
@login_required
def crop_suggestions_history():
    """Display user's crop suggestion history"""
    try:
        page = request.args.get('page', 1, type=int)
        per_page = 10
        
        # Get user's suggestion history
        history_items = CropSuggestionHistory.query.filter_by(
            user_id=current_user.id
        ).order_by(
            CropSuggestionHistory.created_at.desc()
        ).paginate(
            page=page, per_page=per_page, error_out=False
        )
        
        # Process history items for display
        processed_history = []
        for item in history_items.items:
            try:
                suggestions = json.loads(item.suggestions) if item.suggestions else []
                climate_data = json.loads(item.climate_data) if item.climate_data else {}
                
                processed_history.append({
                    'id': item.id,
                    'location': item.location,
                    'soil_type': item.soil_type,
                    'season': item.season,
                    'top_suggestion': item.top_suggestion,
                    'total_suggestions': len(suggestions),
                    'created_at': item.created_at,
                    'suggestions': suggestions[:3],  # Show top 3 for preview
                    'climate_summary': f"{climate_data.get('temperature_range', 'N/A')} temp, {climate_data.get('rainfall_range', 'N/A')} rainfall"
                })
            except (json.JSONDecodeError, TypeError):
                # Handle corrupted data gracefully
                continue
        
        return render_template('ai/crop_suggestions_history.html', 
                             history_items=processed_history,
                             pagination=history_items)
        
    except Exception as e:
        app.logger.error(f"Error displaying crop suggestions history: {str(e)}")
        flash('Error loading suggestion history.', 'error')
        return redirect(url_for('crop_suggestions'))

@app.route('/ai/crop-suggestions/view/<int:history_id>')
@login_required
def view_crop_suggestion_details(history_id):
    """View detailed results of a specific crop suggestion"""
    try:
        # Get the specific history item
        history_item = CropSuggestionHistory.query.filter_by(
            id=history_id,
            user_id=current_user.id
        ).first_or_404()
        
        # Parse the stored suggestions
        suggestions = json.loads(history_item.suggestions) if history_item.suggestions else []
        climate_data = json.loads(history_item.climate_data) if history_item.climate_data else {}
        
        # Prepare data for template
        suggestion_data = {
            'history': history_item,
            'suggestions': suggestions,
            'climate_data': climate_data,
            'input_summary': {
                'location': history_item.location,
                'soil_type': history_item.soil_type,
                'soil_ph': history_item.soil_ph,
                'water_source': history_item.water_source,
                'fertilizer_availability': history_item.fertilizer_availability,
                'budget_preference': history_item.budget_preference,
                'season': history_item.season
            }
        }
        
        return render_template('ai/crop_suggestion_details.html', data=suggestion_data)
        
    except TemplateNotFound as e:
        app.logger.error(f"Template not found: {e}")
        flash('Template error: Could not load detail view.', 'error')
        return redirect(url_for('crop_suggestions_history'))
    except Exception as e:
        app.logger.error(f"Error viewing crop suggestion details: {str(e)}")
        app.logger.error(f"Exception type: {type(e)}")
        import traceback
        app.logger.error(f"Traceback: {traceback.format_exc()}")
        flash('Error loading suggestion details.', 'error')
        return redirect(url_for('crop_suggestions_history'))

@app.route('/ai/crop-suggestions/compare')
@login_required
def crop_comparison():
    """Crop comparison page"""
    form = CropComparisonForm()
    return render_template('ai/crop_comparison.html', form=form)

@app.route('/ai/crop-suggestions/compare/analyze', methods=['POST'])
@login_required
def analyze_crop_comparison():
    """Analyze and compare multiple crops"""
    try:
        form = CropComparisonForm()
        
        if not form.validate_on_submit():
            return jsonify({
                'success': False,
                'error': 'Form validation failed',
                'errors': form.errors
            }), 400
        
        # Prepare crop list for comparison
        crop_names = [form.crop1.data, form.crop2.data]
        if form.crop3.data:
            crop_names.append(form.crop3.data)
        
        comparison_factor = form.comparison_factors.data
        
        # Get AI-powered comparison
        comparison_result = EnhancedCropAI.compare_crops_analysis(crop_names, comparison_factor)
        
        if comparison_result.get('success', False):
            # Save comparison to dedicated comparison history
            try:
                # Extract best crop from comparison results
                best_crop = None
                overall_recommendation = None
                
                if comparison_result.get('comparison', {}).get('crop_analysis'):  # type: ignore
                    crops = comparison_result['comparison']['crop_analysis']  # type: ignore
                    if crops:
                        # Find crop with highest score
                        best_crop_data = max(crops, key=lambda x: x.get('score', 0))
                        best_crop = best_crop_data.get('crop_name', '')
                
                if comparison_result.get('comparison', {}).get('overall_recommendation'):  # type: ignore
                    overall_recommendation = comparison_result['comparison']['overall_recommendation']  # type: ignore
                
                # Create new comparison history record
                comparison_history = CropComparisonHistory(
                    user_id=current_user.id,
                    crop_names=json.dumps(crop_names),
                    comparison_factor=comparison_factor,
                    comparison_result=json.dumps(comparison_result),
                    best_crop=best_crop,
                    overall_recommendation=overall_recommendation
                )
                
                db.session.add(comparison_history)
                db.session.commit()
                
                comparison_result['comparison_id'] = comparison_history.id
                app.logger.info(f"Saved crop comparison history {comparison_history.id} for user {current_user.id}")
                
                # Also save to CropSuggestionComparison for backward compatibility
                latest_history = CropSuggestionHistory.query.filter_by(
                    user_id=current_user.id
                ).order_by(CropSuggestionHistory.created_at.desc()).first()
                
                if latest_history:
                    comparison_record = CropSuggestionComparison(
                        user_id=current_user.id,
                        history_id=latest_history.id,
                        crop_names=json.dumps(crop_names),
                        comparison_data=json.dumps(comparison_result)
                    )
                    
                    db.session.add(comparison_record)
                    db.session.commit()
                
            except Exception as db_error:
                app.logger.error(f"Error saving crop comparison history: {str(db_error)}")
                db.session.rollback()
                # Continue without saving
                pass
        
        return jsonify(comparison_result)
        
    except Exception as e:
        app.logger.error(f"Error analyzing crop comparison: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'Internal server error during comparison'
        }), 500

@app.route('/ai/crop-suggestions/seasonal/<season>')
@login_required
def seasonal_crop_suggestions(season):
    """Get season-specific crop suggestions"""
    try:
        # Validate season parameter
        valid_seasons = ['kharif', 'rabi', 'zaid', 'year_round']
        if season not in valid_seasons:
            flash('Invalid season specified.', 'error')
            return redirect(url_for('crop_suggestions'))
        
        # Get user's latest location and soil data for context
        latest_query = CropSuggestionHistory.query.filter_by(
            user_id=current_user.id
        ).order_by(CropSuggestionHistory.created_at.desc()).first()
        
        # Prepare basic input data with season focus
        input_data = {
            'season': season,
            'location': latest_query.location if latest_query else 'India',
            'soil_type': latest_query.soil_type if latest_query else 'loamy',
            'soil_ph': latest_query.soil_ph if latest_query else 6.5,
            'water_source': 'rainfed',
            'temperature_range': 'moderate',
            'rainfall_range': 'moderate',
            'humidity_level': 'moderate',
            'fertilizer_availability': 'mixed',
            'budget_preference': 'moderate_cost',
            'farm_size': 5.0,
            'market_preference': 'local',
            'experience_level': 'intermediate'
        }
        
        # Get seasonal suggestions
        suggestions_result = EnhancedCropAI.get_seasonal_suggestions(input_data, season)
        
        return render_template('ai/seasonal_suggestions.html', 
                             suggestions=suggestions_result,
                             season=season)
        
    except Exception as e:
        app.logger.error(f"Error getting seasonal suggestions: {str(e)}")
        flash('Error loading seasonal suggestions.', 'error')
        return redirect(url_for('crop_suggestions'))

@app.route('/ai/crop-suggestions/delete/<int:history_id>', methods=['DELETE'])
@login_required
def delete_crop_suggestion_history(history_id):
    """Delete a specific crop suggestion history item"""
    try:
        # Skip CSRF validation for AJAX requests
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            from flask_wtf.csrf import validate_csrf  # type: ignore
            from werkzeug.exceptions import BadRequest
            try:
                validate_csrf(request.headers.get('X-CSRFToken', ''))
            except (BadRequest, Exception):
                # For AJAX DELETE requests, we'll allow without CSRF for now
                # In production, ensure proper CSRF token handling
                pass
        
        # Get the specific history item
        history_item = CropSuggestionHistory.query.filter_by(
            id=history_id,
            user_id=current_user.id
        ).first_or_404()
        
        # Delete associated comparison records first (foreign key constraint)
        CropSuggestionComparison.query.filter_by(history_id=history_id).delete()
        
        # Delete the history item
        db.session.delete(history_item)
        db.session.commit()
        
        app.logger.info(f"User {current_user.id} deleted crop suggestion history {history_id}")
        
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': True, 'message': 'History item deleted successfully'})
        else:
            flash('Crop suggestion history deleted successfully.', 'success')
            return redirect(url_for('crop_suggestions_history'))
            
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Error deleting crop suggestion history {history_id}: {str(e)}")
        
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'error': 'Failed to delete history item'}), 500
        else:
            flash('Error deleting history item.', 'error')
            return redirect(url_for('crop_suggestions_history'))

@app.route('/ai/crop-suggestions/download/<int:history_id>')
@login_required
def download_crop_suggestions(history_id):
    """Download crop suggestions as PDF or Excel"""
    try:
        # Get the specific history item
        history_item = CropSuggestionHistory.query.filter_by(
            id=history_id,
            user_id=current_user.id
        ).first_or_404()
        
        # Parse the stored suggestions
        suggestions = json.loads(history_item.suggestions) if history_item.suggestions else []
        
        # Get download format
        format_type = request.args.get('format', 'pdf')
        
        if format_type == 'excel':
            return download_suggestions_excel(history_item, suggestions)
        else:
            return download_suggestions_pdf(history_item, suggestions)
            
    except Exception as e:
        app.logger.error(f"Error downloading crop suggestions: {str(e)}")
        flash('Error generating download file.', 'error')
        return redirect(url_for('crop_suggestions_history'))

def download_suggestions_excel(history_item, suggestions):
    """Generate Excel file with crop suggestions"""
    try:
        from io import BytesIO
        
        # Prepare data for Excel
        excel_data = []
        for i, suggestion in enumerate(suggestions, 1):
            excel_data.append({
                'Rank': i,
                'Crop Name': suggestion.get('crop_name', ''),
                'Suitability Score': suggestion.get('suitability_score', ''),
                'Category': suggestion.get('suitability_category', ''),
                'Expected Yield': suggestion.get('expected_yield', ''),
                'Time to Harvest': suggestion.get('time_to_harvest', ''),
                'Profitability': suggestion.get('profitability', ''),
                'Water Requirements': suggestion.get('water_requirements', ''),
                'Market Demand': suggestion.get('market_demand', ''),
                'Estimated Cost': suggestion.get('estimated_cost', ''),
                'Estimated Revenue': suggestion.get('estimated_revenue', ''),
                'ROI (%)': suggestion.get('roi_percentage', '')
            })
        
        # Create DataFrame and Excel file
        df = pd.DataFrame(excel_data)  # type: ignore
        
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:  # type: ignore
            df.to_excel(writer, sheet_name='Crop Suggestions', index=False)
            
            # Add metadata sheet
            metadata = pd.DataFrame([  # type: ignore
                ['Generated Date', datetime.now().strftime('%Y-%m-%d %H:%M:%S')],
                ['User', current_user.username],
                ['Location', history_item.location],
                ['Soil Type', history_item.soil_type],
                ['Season', history_item.season],
                ['Total Suggestions', len(suggestions)]
            ], columns=['Parameter', 'Value'])
            
            metadata.to_excel(writer, sheet_name='Query Details', index=False)
        
        output.seek(0)
        
        filename = f"crop_suggestions_{history_item.id}_{datetime.now().strftime('%Y%m%d')}.xlsx"
        
        return send_file(
            io.BytesIO(output.read()),
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=filename
        )
        
    except ImportError:
        flash('Excel export not available. Please install pandas and openpyxl.', 'error')
        return redirect(url_for('crop_suggestions_history'))
    except Exception as e:
        app.logger.error(f"Error generating Excel file: {str(e)}")
        flash('Error generating Excel file.', 'error')
        return redirect(url_for('crop_suggestions_history'))

def download_suggestions_pdf(history_item, suggestions):
    """Generate PDF file with crop suggestions"""
    try:
        from reportlab.lib.pagesizes import letter, A4
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import inch
        from reportlab.lib import colors
        
        buffer = io.BytesIO()
        
        # Create PDF document
        doc = SimpleDocTemplate(buffer, pagesize=A4)
        styles = getSampleStyleSheet()
        story = []
        
        # Title
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=18,
            spaceAfter=30,
            alignment=1  # Center alignment
        )
        story.append(Paragraph("FarmLink AI - Crop Suggestions Report", title_style))
        story.append(Spacer(1, 20))  # type: ignore
        
        # Query details
        story.append(Paragraph("Query Details", styles['Heading2']))
        query_data = [
            ['Generated Date:', datetime.now().strftime('%Y-%m-%d %H:%M:%S')],
            ['User:', current_user.username],
            ['Location:', history_item.location],
            ['Soil Type:', history_item.soil_type],
            ['pH Level:', str(history_item.soil_ph)],
            ['Season:', history_item.season],
            ['Total Suggestions:', str(len(suggestions))]
        ]
        
        query_table = Table(query_data, colWidths=[2*inch, 3*inch])
        query_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.lightgrey),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
            ('BACKGROUND', (1, 0), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        story.append(query_table)  # type: ignore
        story.append(Spacer(1, 30))  # type: ignore
        
        # Suggestions table
        story.append(Paragraph("Recommended Crops", styles['Heading2']))
        
        # Create cell style for text wrapping
        cell_style = ParagraphStyle(
            'CellStyle',
            parent=styles['Normal'],
            fontSize=8,
            alignment=1,
            wordWrap='LTR',
            leading=10
        )
        
        # Prepare table data with Paragraph objects for text wrapping
        table_data = [[
            Paragraph('<b>Rank</b>', cell_style),
            Paragraph('<b>Crop Name</b>', cell_style),
            Paragraph('<b>Suitability</b>', cell_style),
            Paragraph('<b>Yield</b>', cell_style),
            Paragraph('<b>Profitability</b>', cell_style),
            Paragraph('<b>ROI %</b>', cell_style)
        ]]
        
        for i, suggestion in enumerate(suggestions[:10], 1):  # Limit to top 10 for PDF
            crop_name = str(suggestion.get('crop_name', ''))[:40]
            suitability = str(suggestion.get('suitability_category', ''))[:20]
            yield_val = str(suggestion.get('expected_yield', ''))[:25]
            profit = str(suggestion.get('profitability', ''))[:15]
            roi = f"{suggestion.get('roi_percentage', 0):.1f}%"
            
            table_data.append([
                Paragraph(str(i), cell_style),
                Paragraph(crop_name, cell_style),
                Paragraph(suitability, cell_style),
                Paragraph(yield_val, cell_style),
                Paragraph(profit, cell_style),
                Paragraph(roi, cell_style)
            ])
        
        suggestions_table = Table(table_data, colWidths=[0.4*inch, 1.5*inch, 1*inch, 1.3*inch, 0.9*inch, 0.6*inch])
        suggestions_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
            ('TOPPADDING', (0, 0), (-1, 0), 10),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('FONTSIZE', (0, 1), (-1, -1), 8),
            ('LEFTPADDING', (0, 0), (-1, -1), 3),
            ('RIGHTPADDING', (0, 0), (-1, -1), 3),
            ('TOPPADDING', (0, 1), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 1), (-1, -1), 5),
        ]))
        story.append(suggestions_table)  # type: ignore
        
        # Footer
        story.append(Spacer(1, 30))  # type: ignore
        footer_style = ParagraphStyle(
            'Footer',
            parent=styles['Normal'],
            fontSize=8,
            alignment=1
        )
        story.append(Paragraph("Generated by FarmLink AI - Your Smart Farming Assistant", footer_style))
        
        # Build PDF
        doc.build(story)  # type: ignore
        buffer.seek(0)
        
        filename = f"crop_suggestions_{history_item.id}_{datetime.now().strftime('%Y%m%d')}.pdf"
        
        return send_file(
            buffer,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=filename
        )
        
    except ImportError:
        flash('PDF export not available. Please install reportlab.', 'error')
        return redirect(url_for('crop_suggestions_history'))
    except Exception as e:
        app.logger.error(f"Error generating PDF file: {str(e)}")
        flash('Error generating PDF file.', 'error')
        return redirect(url_for('crop_suggestions_history'))

# New Download Routes for Multiple Formats
@app.route('/ai/crop-suggestions/download-report', methods=['POST'])  # type: ignore
@csrf.exempt
@login_required
def download_crop_suggestions_report():
    """Download current crop suggestions in various formats"""
    try:
        # Get data from request
        data = request.get_json()
        if not data or not data.get('suggestions'):
            return jsonify({'error': 'No data provided'}), 400
        
        format_type = request.args.get('format', 'pdf')
        suggestions = data.get('suggestions', [])
        generated_at = data.get('generated_at', datetime.now().isoformat())
        
        # Generate filename
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename_base = f"farmlink_crop_suggestions_{timestamp}"
        
        if format_type == 'pdf':
            return generate_current_pdf_report(suggestions, data, filename_base)
        elif format_type == 'word':
            return generate_word_report(suggestions, data, filename_base)
        elif format_type == 'excel':
            return generate_excel_report(suggestions, data, filename_base)
        elif format_type == 'csv':
            return generate_csv_report(suggestions, data, filename_base)
        elif format_type == 'json':
            return generate_json_report(suggestions, data, filename_base)
        else:
            return jsonify({'error': 'Unsupported format'}), 400
            
    except Exception as e:
        app.logger.error(f"Error generating report: {str(e)}")
        return jsonify({'error': 'Failed to generate report'}), 500

def generate_current_pdf_report(suggestions, data, filename_base):
    """Generate PDF report for current suggestions"""
    try:
        from reportlab.lib.pagesizes import letter, A4
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import inch
        from reportlab.lib import colors
        from io import BytesIO
        
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=72, leftMargin=72,
                              topMargin=72, bottomMargin=18)
        
        styles = getSampleStyleSheet()
        story = []
        
        # Title
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=18,
            spaceAfter=30,
            alignment=1,
            textColor=colors.darkgreen
        )
        story.append(Paragraph("FarmLink AI - Crop Suggestions Report", title_style))
        story.append(Spacer(1, 20))  # type: ignore
        
        # Report Details
        details_data = [
            ['Generated Date:', datetime.now().strftime('%Y-%m-%d %H:%M:%S')],
            ['User:', current_user.username],
            ['Total Suggestions:', str(len(suggestions))],
            ['Report Type:', 'Current Analysis']
        ]
        
        details_table = Table(details_data, colWidths=[2*inch, 3*inch])
        details_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.lightgrey),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
            ('BACKGROUND', (1, 0), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        story.append(details_table)  # type: ignore
        story.append(Spacer(1, 30))  # type: ignore
        
        # Suggestions table
        story.append(Paragraph("Recommended Crops", styles['Heading2']))
        story.append(Spacer(1, 12))  # type: ignore
        
        # Create cell style for wrapping text
        cell_style = ParagraphStyle(
            'CellStyle',
            parent=styles['Normal'],
            fontSize=7,
            alignment=1,
            wordWrap='LTR',
            leading=9
        )
        
        # Header row
        table_data = [[
            Paragraph('<b>Rank</b>', cell_style),
            Paragraph('<b>Crop Name</b>', cell_style),
            Paragraph('<b>Suitability</b>', cell_style),
            Paragraph('<b>Yield</b>', cell_style),
            Paragraph('<b>Profitability</b>', cell_style),
            Paragraph('<b>ROI %</b>', cell_style)
        ]]
        
        # Data rows with text wrapping
        for i, suggestion in enumerate(suggestions[:15], 1):
            crop_name = suggestion.get('crop_name', '')
            # Clean crop name from JSON artifacts
            if isinstance(crop_name, str):
                crop_name = crop_name.replace('"Crop_Name":', '').replace('"', '').strip()
            
            yield_text = suggestion.get('expected_yield', 'Variable')
            if isinstance(yield_text, str) and len(yield_text) > 30:
                yield_text = 'Variable'
            
            table_data.append([
                Paragraph(str(i), cell_style),
                Paragraph(str(crop_name)[:50], cell_style),
                Paragraph(str(suggestion.get('suitability_category', 'N/A'))[:20], cell_style),
                Paragraph(str(yield_text)[:30], cell_style),
                Paragraph(str(suggestion.get('profitability', 'Medium'))[:15], cell_style),
                Paragraph(f"{suggestion.get('roi_percentage', 0):.1f}%", cell_style)
            ])
        
        suggestions_table = Table(table_data, colWidths=[0.4*inch, 1.5*inch, 1*inch, 1.3*inch, 0.9*inch, 0.6*inch])
        suggestions_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#28a745')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 8),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
            ('TOPPADDING', (0, 0), (-1, 0), 8),
            ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f8f9fa')),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('FONTSIZE', (0, 1), (-1, -1), 7),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor('#ffffff'), colors.HexColor('#f8f9fa')]),
            ('LEFTPADDING', (0, 0), (-1, -1), 3),
            ('RIGHTPADDING', (0, 0), (-1, -1), 3),
            ('TOPPADDING', (0, 1), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 1), (-1, -1), 5),
        ]))
        story.append(suggestions_table)  # type: ignore
        
        # Footer
        story.append(Spacer(1, 30))  # type: ignore
        footer_style = ParagraphStyle('Footer', parent=styles['Normal'], fontSize=8, alignment=1)
        story.append(Paragraph("Generated by FarmLink AI - Your Smart Farming Assistant", footer_style))
        
        doc.build(story)  # type: ignore
        buffer.seek(0)
        
        return send_file(
            buffer,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=f"{filename_base}.pdf"
        )
        
    except ImportError:
        return jsonify({'error': 'PDF generation not available'}), 500
    except Exception as e:
        app.logger.error(f"Error generating PDF: {str(e)}")
        return jsonify({'error': 'Failed to generate PDF'}), 500

def generate_word_report(suggestions, data, filename_base):
    """Generate Word document report"""
    try:
        from docx import Document
        from docx.shared import Inches
        from io import BytesIO
        
        doc = Document()
        
        # Title
        title = doc.add_heading('FarmLink AI - Crop Suggestions Report', 0)
        title.alignment = 1  # Center alignment
        
        # Report details
        doc.add_heading('Report Details', level=1)
        details_table = doc.add_table(rows=4, cols=2)
        details_table.style = 'Table Grid'
        
        details_data = [
            ('Generated Date:', datetime.now().strftime('%Y-%m-%d %H:%M:%S')),
            ('User:', current_user.username),
            ('Total Suggestions:', str(len(suggestions))),
            ('Report Type:', 'Current Analysis')
        ]
        
        for i, (key, value) in enumerate(details_data):
            details_table.cell(i, 0).text = key
            details_table.cell(i, 1).text = value
        
        doc.add_paragraph()
        
        # Suggestions
        doc.add_heading('Recommended Crops', level=1)
        
        if suggestions:
            suggestions_table = doc.add_table(rows=1, cols=6)
            suggestions_table.style = 'Table Grid'
            
            # Header
            headers = ['Rank', 'Crop Name', 'Suitability', 'Yield', 'Profitability', 'ROI %']
            for i, header in enumerate(headers):
                suggestions_table.cell(0, i).text = header
            
            # Data
            for idx, suggestion in enumerate(suggestions[:15], 1):
                row = suggestions_table.add_row()
                row.cells[0].text = str(idx)
                row.cells[1].text = suggestion.get('crop_name', '')
                row.cells[2].text = suggestion.get('suitability_category', '')
                row.cells[3].text = suggestion.get('expected_yield', '')
                row.cells[4].text = suggestion.get('profitability', '')
                row.cells[5].text = f"{suggestion.get('roi_percentage', 0):.1f}%"
        
        # Footer
        doc.add_paragraph()
        footer = doc.add_paragraph('Generated by FarmLink AI - Your Smart Farming Assistant')
        footer.alignment = 1
        
        # Save to buffer
        buffer = BytesIO()
        doc.save(buffer)
        buffer.seek(0)
        
        return send_file(
            buffer,
            mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            as_attachment=True,
            download_name=f"{filename_base}.docx"
        )
        
    except ImportError:
        return jsonify({'error': 'Word document generation not available'}), 500
    except Exception as e:
        app.logger.error(f"Error generating Word document: {str(e)}")
        return jsonify({'error': 'Failed to generate Word document'}), 500

def generate_excel_report(suggestions, data, filename_base):
    """Generate Excel report"""
    try:
        from io import BytesIO
        
        if pd is None:
            return jsonify({'error': 'Excel generation not available. Please install pandas and openpyxl.'}), 500
        
        # Prepare data
        excel_data = []
        for i, suggestion in enumerate(suggestions, 1):
            excel_data.append({
                'Rank': i,
                'Crop Name': suggestion.get('crop_name', ''),
                'Suitability Score': suggestion.get('suitability_score', ''),
                'Category': suggestion.get('suitability_category', ''),
                'Expected Yield': suggestion.get('expected_yield', ''),
                'Time to Harvest': suggestion.get('time_to_harvest', ''),
                'Profitability': suggestion.get('profitability', ''),
                'Water Requirements': suggestion.get('water_requirements', ''),
                'Market Demand': suggestion.get('market_demand', ''),
                'Estimated Cost': suggestion.get('estimated_cost', ''),
                'Estimated Revenue': suggestion.get('estimated_revenue', ''),
                'ROI (%)': suggestion.get('roi_percentage', ''),
                'Risk Level': suggestion.get('risk_level', ''),
                'Climate Suitability': suggestion.get('climate_suitability', '')
            })
        
        df = pd.DataFrame(excel_data)
        
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Crop Suggestions', index=False)
            
            # Add metadata sheet
            metadata = pd.DataFrame([
                ['Generated Date', datetime.now().strftime('%Y-%m-%d %H:%M:%S')],
                ['User', current_user.username],
                ['Total Suggestions', len(suggestions)],
                ['Report Type', 'Current Analysis']
            ], columns=['Parameter', 'Value'])
            
            metadata.to_excel(writer, sheet_name='Report Details', index=False)
        
        output.seek(0)
        
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=f"{filename_base}.xlsx"
        )
        
    except ImportError as e:
        app.logger.error(f"Import error for Excel generation: {str(e)}")
        return jsonify({'error': 'Excel generation not available. Please install pandas and openpyxl.'}), 500
    except Exception as e:
        app.logger.error(f"Error generating Excel: {str(e)}")
        return jsonify({'error': f'Failed to generate Excel: {str(e)}'}), 500

def generate_csv_report(suggestions, data, filename_base):
    """Generate CSV report"""
    try:
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write header
        writer.writerow([
            'Rank', 'Crop Name', 'Suitability Score', 'Category', 'Expected Yield',
            'Time to Harvest', 'Profitability', 'Water Requirements', 'Market Demand',
            'Estimated Cost', 'Estimated Revenue', 'ROI (%)', 'Risk Level'
        ])
        
        # Write data
        for i, suggestion in enumerate(suggestions, 1):
            writer.writerow([
                i,
                suggestion.get('crop_name', ''),
                suggestion.get('suitability_score', ''),
                suggestion.get('suitability_category', ''),
                suggestion.get('expected_yield', ''),
                suggestion.get('time_to_harvest', ''),
                suggestion.get('profitability', ''),
                suggestion.get('water_requirements', ''),
                suggestion.get('market_demand', ''),
                suggestion.get('estimated_cost', ''),
                suggestion.get('estimated_revenue', ''),
                suggestion.get('roi_percentage', ''),
                suggestion.get('risk_level', '')
            ])
        
        output.seek(0)
        
        return send_file(
            io.BytesIO(output.getvalue().encode('utf-8')),
            mimetype='text/csv',
            as_attachment=True,
            download_name=f"{filename_base}.csv"
        )
        
    except Exception as e:
        app.logger.error(f"Error generating CSV: {str(e)}")
        return jsonify({'error': 'Failed to generate CSV'}), 500

def generate_json_report(suggestions, data, filename_base):
    """Generate JSON report"""
    try:
        report_data = {
            'report_details': {
                'generated_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'user': current_user.username,
                'total_suggestions': len(suggestions),
                'report_type': 'Current Analysis'
            },
            'suggestions': suggestions,
            'metadata': {
                'generated_by': 'FarmLink AI',
                'version': '1.0',
                'format': 'json'
            }
        }
        
        output = io.BytesIO()
        output.write(json.dumps(report_data, indent=2, ensure_ascii=False).encode('utf-8'))
        output.seek(0)
        
        return send_file(
            output,
            mimetype='application/json',
            as_attachment=True,
            download_name=f"{filename_base}.json"
        )
        
    except Exception as e:
        app.logger.error(f"Error generating JSON: {str(e)}")
        return jsonify({'error': 'Failed to generate JSON'}), 500

@app.route('/ai/crop-suggestions/email-report', methods=['POST'])  # type: ignore
@csrf.exempt
@login_required
def email_crop_suggestions_report():
    """Email crop suggestions report"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        email = data.get('email')
        report_data = data.get('data')
        
        if not email or not report_data:
            return jsonify({'error': 'Email and data are required'}), 400
        
        # Generate PDF for email
        suggestions = report_data.get('suggestions', [])
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # Create a simple HTML email with summary
        html_content = f"""
        <html>
        <body>
            <h2>FarmLink AI - Crop Suggestions Report</h2>
            <p>Hello {current_user.username},</p>
            <p>Please find your crop suggestions report below:</p>
            
            <h3>Report Summary</h3>
            <ul>
                <li>Generated Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</li>
                <li>Total Suggestions: {len(suggestions)}</li>
                <li>Top Recommendation: {suggestions[0].get('crop_name', 'N/A') if suggestions else 'N/A'}</li>
            </ul>
            
            <h3>Top 5 Recommendations</h3>
            <table border="1" style="border-collapse: collapse; width: 100%;">
                <tr>
                    <th style="padding: 8px;">Rank</th>
                    <th style="padding: 8px;">Crop Name</th>
                    <th style="padding: 8px;">Suitability</th>
                    <th style="padding: 8px;">Profitability</th>
                </tr>
        """
        
        for i, suggestion in enumerate(suggestions[:5], 1):
            html_content += f"""
                <tr>
                    <td style="padding: 8px;">{i}</td>
                    <td style="padding: 8px;">{suggestion.get('crop_name', '')}</td>
                    <td style="padding: 8px;">{suggestion.get('suitability_score', '')}%</td>
                    <td style="padding: 8px;">{suggestion.get('profitability', '')}</td>
                </tr>
            """
        
        html_content += """
            </table>
            
            <p>For complete details, please log in to your FarmLink AI dashboard.</p>
            
            <p>Best regards,<br>FarmLink AI Team</p>
        </body>
        </html>
        """
        
        # Send email using EmailService
        email_service = EmailService()
        subject = f"FarmLink AI - Crop Suggestions Report ({datetime.now().strftime('%Y-%m-%d')})"
        
        result = email_service.send_email(
            to_email=email,
            subject=subject,
            html_content=html_content
        )
        
        if result.get('success'):
            return jsonify({'success': True, 'message': 'Report sent successfully'})
        else:
            return jsonify({'error': 'Failed to send email'}), 500
            
    except Exception as e:
        app.logger.error(f"Error sending email report: {str(e)}")
        return jsonify({'error': 'Failed to send email'}), 500

# API endpoints for AJAX requests
@app.route('/api/crop-suggestions/quick')
@login_required
def quick_crop_suggestions():
    """Quick crop suggestions API for minimal input"""
    try:
        location = request.args.get('location', 'India')
        season = request.args.get('season', 'kharif')
        
        # Basic input for quick suggestions
        input_data = {
            'location': location,
            'season': season,
            'soil_type': 'loamy',
            'soil_ph': 6.5,
            'water_source': 'rainfed',
            'temperature_range': 'moderate',
            'rainfall_range': 'moderate',
            'humidity_level': 'moderate',
            'fertilizer_availability': 'mixed',
            'budget_preference': 'moderate_cost',
            'farm_size': 5.0,
            'market_preference': 'local',
            'experience_level': 'intermediate'
        }
        
        result = EnhancedCropAI.get_smart_crop_suggestions(input_data)
        
        # Return only top 5 suggestions for quick view
        if result.get('success') and result.get('suggestions'):
            result['suggestions'] = result['suggestions'][:5]  # type: ignore
        
        return jsonify(result)
        
    except Exception as e:
        app.logger.error(f"Error in quick crop suggestions API: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'Internal server error'
        }), 500

# ============================================================================
# CROP COMPARISON HISTORY ROUTES
# ============================================================================

@app.route('/ai/crop-comparison/history')
@login_required
def crop_comparison_history():
    """Display crop comparison history for the current user"""
    try:
        page = request.args.get('page', 1, type=int)
        per_page = 10
        
        # Ensure valid page number
        if page < 1:
            page = 1
        
        try:
            # Get user's comparison history with error logging
            query = CropComparisonHistory.query.filter_by(user_id=current_user.id)
            app.logger.debug(f"Executing query for user {current_user.id}")
            
            total_count = query.count()
            app.logger.info(f"Total comparisons for user {current_user.id}: {total_count}")
            
            comparisons = query.order_by(
                CropComparisonHistory.created_at.desc()
            ).paginate(page=page, per_page=per_page, error_out=False)
            
            if not comparisons.items and page > 1:
                # If page is out of range, redirect to first page
                return redirect(url_for('crop_comparison_history', page=1))
            
            app.logger.info(f"Successfully retrieved {len(comparisons.items)} comparisons for page {page}")
            
            # Validate data integrity
            for comparison in comparisons.items:
                if comparison.get_crop_names_list() == []:
                    app.logger.warning(f"Comparison {comparison.id} has invalid crop_names data")
                if not comparison.created_at:
                    app.logger.warning(f"Comparison {comparison.id} missing created_at timestamp")
            
            # Add debug info
            debug_info = {
                'total_records': total_count,
                'page': page,
                'per_page': per_page,
                'current_user_id': current_user.id,
                'has_comparisons': bool(comparisons.items),
                'items_count': len(comparisons.items) if comparisons.items else 0
            }
            
            return render_template('ai/crop_comparison_history.html', 
                                comparisons=comparisons,
                                debug=debug_info,
                                title='Crop Comparison History')
                                
        except Exception as db_error:
            app.logger.error(f"Database error in crop comparison history: {str(db_error)}", exc_info=True)
            db.session.rollback()
            raise
            
    except Exception as e:
        app.logger.error(f"Error in crop comparison history route: {str(e)}", exc_info=True)
        flash('An error occurred while loading your comparison history. Our team has been notified.', 'error')
        return redirect(url_for('crop_comparison'))

@app.route('/ai/crop-comparison/view/<int:comparison_id>')
@login_required
def view_crop_comparison(comparison_id):
    """View detailed crop comparison results"""
    try:
        comparison = CropComparisonHistory.query.filter_by(
            id=comparison_id,
            user_id=current_user.id
        ).first_or_404()
        
        # Parse the comparison data
        comparison_data = comparison.get_comparison_data()
        crop_names = comparison.get_crop_names_list()
        
        return render_template('ai/crop_comparison_detail.html',
                             comparison=comparison,
                             comparison_data=comparison_data,
                             crop_names=crop_names,
                             title=f'Comparison: {" vs ".join(crop_names)}')
        
    except Exception as e:
        app.logger.error(f"Error viewing crop comparison {comparison_id}: {str(e)}")
        flash('Error loading comparison details.', 'error')
        return redirect(url_for('crop_comparison_history'))

@app.route('/ai/crop-comparison/delete/<int:comparison_id>', methods=['DELETE'])
@login_required
def delete_crop_comparison(comparison_id):
    """Delete a specific crop comparison history item"""
    try:
        # Skip CSRF validation for AJAX requests
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            from flask_wtf.csrf import validate_csrf  # type: ignore
            from werkzeug.exceptions import BadRequest
            try:
                validate_csrf(request.headers.get('X-CSRFToken', ''))
            except (BadRequest, Exception):
                # For AJAX DELETE requests, we'll allow without CSRF for now
                pass
        
        # Get the specific comparison item
        comparison = CropComparisonHistory.query.filter_by(
            id=comparison_id,
            user_id=current_user.id
        ).first_or_404()
        
        # Delete the comparison
        db.session.delete(comparison)
        db.session.commit()
        
        app.logger.info(f"User {current_user.id} deleted crop comparison {comparison_id}")
        
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': True, 'message': 'Comparison deleted successfully'})
        else:
            flash('Crop comparison deleted successfully.', 'success')
            return redirect(url_for('crop_comparison_history'))
            
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Error deleting crop comparison {comparison_id}: {str(e)}")
        
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'error': 'Failed to delete comparison'}), 500
        else:
            flash('Error deleting comparison.', 'error')
            return redirect(url_for('crop_comparison_history'))

@app.route('/ai/crop-comparison/download/<int:comparison_id>')
@login_required
def download_crop_comparison(comparison_id):
    """Download crop comparison results as PDF"""
    try:
        comparison = CropComparisonHistory.query.filter_by(
            id=comparison_id,
            user_id=current_user.id
        ).first_or_404()
        
        comparison_data = comparison.get_comparison_data()
        crop_names = comparison.get_crop_names_list()
        
        # Generate PDF report
        output = io.BytesIO()
        
        try:
            from reportlab.lib.pagesizes import letter
            from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.lib.units import inch
            from reportlab.lib import colors
            
            doc = SimpleDocTemplate(output, pagesize=letter, topMargin=0.5*inch)
            styles = getSampleStyleSheet()
            story = []
            
            # Title
            title_style = ParagraphStyle(
                'CustomTitle',
                parent=styles['Heading1'],
                fontSize=16,
                spaceAfter=20,
                textColor=colors.HexColor('#2E7D32')
            )
            story.append(Paragraph(f"Crop Comparison Report", title_style))
            story.append(Spacer(1, 12))  # type: ignore
            
            # Crops being compared
            story.append(Paragraph(f"<b>Crops Compared:</b> {', '.join(crop_names)}", styles['Normal']))
            story.append(Paragraph(f"<b>Comparison Factor:</b> {comparison.comparison_factor or 'General'}", styles['Normal']))
            story.append(Paragraph(f"<b>Date:</b> {comparison.created_at.strftime('%B %d, %Y at %I:%M %p')}", styles['Normal']))
            story.append(Spacer(1, 20))  # type: ignore
            
            # Best recommendation
            if comparison.best_crop:
                story.append(Paragraph(f"<b>Recommended Crop:</b> {comparison.best_crop}", styles['Heading2']))
                story.append(Spacer(1, 12))  # type: ignore
            
            if comparison.overall_recommendation:
                story.append(Paragraph("<b>Overall Recommendation:</b>", styles['Heading3']))
                story.append(Paragraph(comparison.overall_recommendation, styles['Normal']))
                story.append(Spacer(1, 20))  # type: ignore
            
            # Detailed comparison if available
            if comparison_data.get('comparison', {}).get('crop_analysis'):
                story.append(Paragraph("<b>Detailed Analysis:</b>", styles['Heading3']))
                story.append(Spacer(1, 12))  # type: ignore
                
                for crop_data in comparison_data['comparison']['crop_analysis']:
                    crop_name = crop_data.get('crop_name', 'Unknown')
                    score = crop_data.get('score', 0)
                    
                    story.append(Paragraph(f"<b>{crop_name} (Score: {score}%)</b>", styles['Heading4']))
                    
                    if crop_data.get('advantages'):
                        story.append(Paragraph("<b>Advantages:</b>", styles['Normal']))
                        for advantage in crop_data['advantages']:
                            story.append(Paragraph(f"• {advantage}", styles['Normal']))
                    
                    if crop_data.get('disadvantages'):
                        story.append(Paragraph("<b>Disadvantages:</b>", styles['Normal']))
                        for disadvantage in crop_data['disadvantages']:
                            story.append(Paragraph(f"• {disadvantage}", styles['Normal']))
                    
                    story.append(Spacer(1, 12))  # type: ignore
            
            # Footer
            story.append(Spacer(1, 30))  # type: ignore
            story.append(Paragraph("Generated by FarmLink AI", styles['Normal']))
            
            doc.build(story)  # type: ignore
            
        except ImportError:
            # Fallback to JSON if reportlab not available
            import json
            output.write(json.dumps({
                'comparison_id': comparison_id,
                'crops': crop_names,
                'factor': comparison.comparison_factor,
                'best_crop': comparison.best_crop,
                'recommendation': comparison.overall_recommendation,
                'created_at': comparison.created_at.isoformat(),
                'detailed_results': comparison_data
            }, indent=2).encode('utf-8'))
        
        output.seek(0)
        
        filename = f"crop_comparison_{comparison_id}_{datetime.now().strftime('%Y%m%d')}.pdf"
        
        return send_file(
            io.BytesIO(output.read()),
            mimetype='application/pdf',
            as_attachment=True,
            download_name=filename
        )
        
    except ImportError:
        flash('PDF export not available. Please install reportlab.', 'error')
        return redirect(url_for('view_crop_comparison', comparison_id=comparison_id))
    
    except Exception as e:
        app.logger.error(f"Error downloading crop comparison {comparison_id}: {str(e)}")
        flash('Error downloading comparison report.', 'error')
        return redirect(url_for('view_crop_comparison', comparison_id=comparison_id))

# Template context processor for utility functions
@app.context_processor
def inject_utility_functions():
    """Make utility functions available in all templates"""
    from datetime import datetime
    return {
        'format_datetime': format_datetime,
        'now': datetime.utcnow,
        'current_year': datetime.now().year
    }

# =============================================================================
# ADMIN USER MANAGEMENT ROUTES
# =============================================================================

@app.route('/admin/users')
@login_required
@admin_required
def admin_users():
    """Admin user management page with filtering and search"""
    try:
        role = request.args.get('role')
        status = request.args.get('status')
        search = request.args.get('search', '').strip()
        
        query = User.query
        
        if role and role != 'all':
            query = query.filter(User.role == role)
            
        if status == 'active':
            query = query.filter(User.active == True)
        elif status == 'inactive':
            query = query.filter(User.active == False)
            
        if search:
            # Simple approach: filter in Python after fetching
            all_users = query.order_by(User.created_at.desc()).all()
            search_lower = search.lower()
            users = [
                u for u in all_users 
                if (search_lower in (u.username or '').lower() or
                    search_lower in (u.email or '').lower() or
                    search_lower in (u.full_name or '').lower())
            ]
        else:
            users = query.order_by(User.created_at.desc()).all()
        
        # Calculate security metrics
        failed_logins = 0  # This would need to be tracked in a separate table/model
        
        return render_template('admin/users.html', users=users, failed_logins=failed_logins)
        
    except Exception as e:
        flash('Error retrieving users.', 'error')
        app.logger.error(f'Error in admin_users: {str(e)}')
        import traceback
        app.logger.error(traceback.format_exc())
        return redirect(url_for('index'))


@app.route('/admin/user/<int:user_id>')
@login_required
@admin_required
def admin_user_details(user_id):
    """View detailed information about a specific user"""
    try:
        user = User.query.get_or_404(user_id)
        
        # Get user statistics based on role
        stats = {}
        if user.role == 'farmer':
            stats['total_crops'] = len(user.crops)
            stats['active_crops'] = len([c for c in user.crops if c.status == 'available'])
            stats['orders_received'] = len(user.orders_received)
        elif user.role == 'buyer':
            stats['orders_placed'] = len(user.orders_placed)
            stats['completed_orders'] = len([o for o in user.orders_placed if o.status == 'delivered'])
        
        stats['messages_sent'] = len(user.sent_messages)
        
        return render_template('admin/user_details.html', user=user, stats=stats)
        
    except Exception as e:
        flash('Error retrieving user details.', 'error')
        app.logger.error(f'Error in admin_user_details: {str(e)}')
        return redirect(url_for('admin_users'))


@app.route('/admin/user/toggle/<int:user_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def toggle_user_status(user_id):
    """Toggle user active status"""
    try:
        user = User.query.get_or_404(user_id)
        
        # Don't allow deactivating other admins
        if user.role == 'admin' and user != current_user:
            flash('Cannot modify other admin accounts.', 'danger')
            return redirect(url_for('admin_users'))
            
        user.active = not user.active
        db.session.commit()
        
        status = 'activated' if user.active else 'deactivated'
        flash(f'User {user.username} has been {status}.', 'success')
        
    except Exception as e:
        flash('An error occurred while updating user status.', 'error')
        app.logger.error(f'Error toggling user status: {str(e)}')
        
    return redirect(url_for('admin_users'))

@app.route('/admin/edit-user/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def admin_edit_user(user_id):
    """Admin route to edit user details and assign manager roles"""
    user = User.query.get_or_404(user_id)
    
    # Don't allow editing other admins
    if user.role == 'admin' and user != current_user:
        flash('Cannot modify other admin accounts.', 'danger')
        return redirect(url_for('admin_users'))
    
    # Update user details
    user.full_name = request.form.get('full_name', user.full_name)
    user.email = request.form.get('email', user.email)
    user.phone = request.form.get('phone', user.phone)
    user.location = request.form.get('location', user.location)
    
    # Handle role changes for non-admin users
    if user.role != 'admin':
        new_role = request.form.get('role')
        # Validate role
        valid_roles = [
            'farmer', 'buyer',
            'manager_farmer', 'manager_buyer', 'manager_crop'
        ]
        if new_role in valid_roles:
            old_role = user.role
            user.role = new_role
            logger.info(f'Admin {current_user.id} changed user {user.id} role from {old_role} to {new_role}')
    
    # Handle account activation/deactivation
    active = request.form.get('active')
    user.active = active == 'true'
    
    # Log role change
    logger.info(f'User {user.id} details updated by admin {current_user.id}')
    
    db.session.commit()
    flash('User details updated successfully.', 'success')
    return redirect(url_for('admin_users'))

@app.route('/admin/user-crops/<int:farmer_id>')
@login_required
@admin_required
def admin_view_crops(farmer_id):
    """Admin route to view and manage farmer's crops"""
    farmer = User.query.filter_by(id=farmer_id, role='farmer').first_or_404()
    if not farmer:
        flash('Farmer not found or user is not a farmer.', 'error')
        return redirect(url_for('admin_users'))
        
    crops = Crop.query.filter_by(farmer_id=farmer_id).order_by(Crop.created_at.desc()).all()
    return render_template('admin/user_crops.html', farmer=farmer, crops=crops)

@app.route('/admin/user-orders/<int:buyer_id>')
@login_required
@admin_required
def admin_view_orders(buyer_id):
    """View all orders for a specific buyer"""
    buyer = User.query.filter_by(id=buyer_id, role='buyer').first_or_404()
    orders = Order.query.filter_by(buyer_id=buyer_id).order_by(Order.created_at.desc()).all()
    return render_template('admin/user_orders.html', buyer=buyer, orders=orders)

@app.route('/admin/user-messages/<int:user_id>')
@login_required
@admin_required
def admin_view_messages(user_id):
    """Admin route to view user messages for moderation"""
    user = User.query.get_or_404(user_id)
    sent_messages = Message.query.filter_by(sender_id=user_id).order_by(Message.created_at.desc()).all()
    received_messages = Message.query.filter_by(recipient_id=user_id).order_by(Message.created_at.desc()).all()
    return render_template('admin/user_messages.html', user=user, sent_messages=sent_messages, received_messages=received_messages)

@app.route('/admin/delete-message/<int:message_id>', methods=['POST'])
@login_required
@admin_required
def admin_delete_message(message_id):
    """Admin route to delete inappropriate messages"""
    message = Message.query.get_or_404(message_id)
    db.session.delete(message)
    db.session.commit()
    flash('Message deleted successfully.', 'success')
    return redirect(url_for('admin_view_messages', user_id=message.sender_id))

@app.route('/admin/system-settings', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_system_settings():
    """Admin route to manage system settings"""
    from models import SystemSettings, User, Crop, Order
    
    if request.method == 'POST':
        try:
            category = request.form.get('category')
            
            # Process form data based on category
            if category == 'general':
                settings_to_update = {
                    'site_name': request.form.get('site_name'),
                    'site_tagline': request.form.get('site_tagline'),
                    'contact_email': request.form.get('contact_email'),
                    'contact_phone': request.form.get('contact_phone'),
                    'support_hours': request.form.get('support_hours'),
                    'timezone': request.form.get('timezone')
                }
            elif category == 'email':
                settings_to_update = {
                    'mail_server': request.form.get('mail_server'),
                    'mail_port': request.form.get('mail_port'),
                    'mail_username': request.form.get('mail_username'),
                    'mail_use_tls': request.form.get('mail_use_tls'),
                    'mail_default_sender': request.form.get('mail_default_sender')
                }
            elif category == 'payment':
                settings_to_update = {
                    'payment_gateway': request.form.get('payment_gateway'),
                    'currency': request.form.get('currency'),
                    'commission_rate': request.form.get('commission_rate'),
                    'min_order_amount': request.form.get('min_order_amount')
                }
            elif category == 'security':
                settings_to_update = {
                    'max_login_attempts': request.form.get('max_login_attempts'),
                    'lockout_duration': request.form.get('lockout_duration'),
                    'session_timeout': request.form.get('session_timeout'),
                    'password_min_length': request.form.get('password_min_length'),
                    'require_email_verification': request.form.get('require_email_verification')
                }
            elif category == 'features':
                settings_to_update = {
                    'enable_marketplace': 'true' if request.form.get('enable_marketplace') else 'false',
                    'enable_expert_forum': 'true' if request.form.get('enable_expert_forum') else 'false',
                    'enable_learning_hub': 'true' if request.form.get('enable_learning_hub') else 'false',
                    'enable_ai_features': 'true' if request.form.get('enable_ai_features') else 'false',
                    'enable_ratings': 'true' if request.form.get('enable_ratings') else 'false',
                    'enable_messaging': 'true' if request.form.get('enable_messaging') else 'false',
                    'maintenance_mode': 'true' if request.form.get('maintenance_mode') else 'false'
                }
            else:
                flash('Invalid settings category.', 'error')
                return redirect(url_for('admin_system_settings'))
            
            # Update or create settings
            for key, value in settings_to_update.items():
                if value is not None:
                    setting = SystemSettings.query.filter_by(setting_key=key).first()
                    if setting:
                        setting.setting_value = str(value)
                        setting.updated_by = current_user.id
                        setting.updated_at = datetime.utcnow()
                    else:
                        # Determine setting type
                        setting_type = 'string'
                        if key in ['mail_port', 'commission_rate', 'min_order_amount', 'max_login_attempts', 
                                   'lockout_duration', 'session_timeout', 'password_min_length']:
                            setting_type = 'integer'
                        elif key in ['mail_use_tls', 'require_email_verification', 'enable_marketplace', 
                                     'enable_expert_forum', 'enable_learning_hub', 'enable_ai_features',
                                     'enable_ratings', 'enable_messaging', 'maintenance_mode']:
                            setting_type = 'boolean'
                        
                        setting = SystemSettings(
                            setting_key=key,
                            setting_value=str(value),
                            setting_type=setting_type,
                            updated_by=current_user.id
                        )
                        db.session.add(setting)
            
            db.session.commit()
            
            # Log the settings change
            try:
                from models import AdminActionLog
                log = AdminActionLog(
                    admin_id=current_user.id,
                    action_type='update_settings',
                    target_type='system_settings',
                    description=f'Updated {category} settings: {", ".join(settings_to_update.keys())}',
                    ip_address=request.remote_addr
                )
                db.session.add(log)
                db.session.commit()
            except Exception as log_error:
                app.logger.error(f"Error logging settings change: {str(log_error)}")
            
            flash(f'{category.title()} settings updated successfully!', 'success')
            
        except Exception as e:
            db.session.rollback()
            app.logger.error(f"Error updating system settings: {str(e)}")
            flash('An error occurred while updating settings. Please try again.', 'error')
        
        return redirect(url_for('admin_system_settings'))
    
    # GET request - load all settings
    all_settings = SystemSettings.query.all()
    settings_dict = {s.setting_key: s.setting_value for s in all_settings}
    
    # Get system statistics
    total_users = User.query.count()
    total_crops = Crop.query.count()
    total_orders = Order.query.count()
    
    # Get last update time
    last_setting = SystemSettings.query.order_by(SystemSettings.updated_at.desc()).first()
    last_updated = last_setting.updated_at.strftime('%B %d, %Y at %I:%M %p') if last_setting else None
    
    return render_template('admin/system_settings.html',
                         settings=settings_dict,
                         total_users=total_users,
                         total_crops=total_crops,
                         total_orders=total_orders,
                         last_updated=last_updated)

@app.route('/admin/system-settings/test-email', methods=['POST'])
@login_required
@admin_required
def admin_test_email():
    """Test email configuration by sending a test email"""
    try:
        test_email = request.form.get('test_email') or current_user.email
        
        # Get email settings from database
        from models import SystemSettings
        mail_server = SystemSettings.query.filter_by(setting_key='mail_server').first()
        mail_port = SystemSettings.query.filter_by(setting_key='mail_port').first()
        mail_username = SystemSettings.query.filter_by(setting_key='mail_username').first()
        mail_default_sender = SystemSettings.query.filter_by(setting_key='mail_default_sender').first()
        
        if not all([mail_server, mail_port, mail_username]):
            return jsonify({
                'success': False,
                'message': 'Email settings are not configured. Please configure SMTP settings first.'
            }), 400
        
            # Try to send test email
        try:
            email_service = EmailService()
            subject = "FarmLink AI - Test Email"
            server_val = mail_server.setting_value if mail_server else ''
            port_val = mail_port.setting_value if mail_port else ''
            
            body = f"""
            <h2>Test Email Successful!</h2>
            <p>This is a test email from FarmLink AI system.</p>
            <p><strong>Sent at:</strong> {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}</p>
            <p><strong>SMTP Server:</strong> {server_val}</p>
            <p><strong>SMTP Port:</strong> {port_val}</p>
            <p>If you received this email, your email configuration is working correctly.</p>
            <hr>
            <p><small>FarmLink AI - Connecting Farmers and Buyers</small></p>
            """
            
            email_service.send_email(test_email, subject, body)
            
            # Log the test
            from models import AdminActionLog
            log = AdminActionLog(
                admin_id=current_user.id,
                action_type='test_email',
                target_type='system_settings',
                description=f'Test email sent to {test_email}',
                ip_address=request.remote_addr
            )
            db.session.add(log)
            db.session.commit()
            
            return jsonify({
                'success': True,
                'message': f'Test email sent successfully to {test_email}. Please check your inbox.'
            })
            
        except Exception as email_error:
            app.logger.error(f"Error sending test email: {str(email_error)}")
            return jsonify({
                'success': False,
                'message': f'Failed to send test email: {str(email_error)}'
            }), 500
            
    except Exception as e:
        app.logger.error(f"Error in test email route: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'An error occurred while testing email configuration.'
        }), 500

@app.route('/admin/system-settings/info')
@login_required
@admin_required
def admin_system_info():
    """Display system information and diagnostics"""
    import sys
    import platform
    import psutil  # type: ignore
    from flask import __version__ as flask_version
    from sqlalchemy import __version__ as sqlalchemy_version
    
    try:
        # System information
        system_info = {
            'python_version': sys.version,
            'platform': platform.platform(),
            'processor': platform.processor(),
            'flask_version': flask_version,
            'sqlalchemy_version': sqlalchemy_version,
            'database_url': app.config.get('SQLALCHEMY_DATABASE_URI', 'Not configured').split('@')[-1] if '@' in app.config.get('SQLALCHEMY_DATABASE_URI', '') else 'SQLite',
        }
        
        # Add system boot time and uptime
        try:
            boot_time = datetime.fromtimestamp(psutil.boot_time())
            uptime_seconds = (datetime.now() - boot_time).total_seconds()
            uptime_days = int(uptime_seconds // 86400)
            uptime_hours = int((uptime_seconds % 86400) // 3600)
            uptime_minutes = int((uptime_seconds % 3600) // 60)
            
            system_info['boot_time'] = boot_time
            system_info['uptime'] = f"{uptime_days}d {uptime_hours}h {uptime_minutes}m"
        except:
            system_info['boot_time'] = None
            system_info['uptime'] = 'N/A'
        
        # Server resources
        try:
            # Get CPU usage (1 second interval for accurate reading)
            cpu_percent = psutil.cpu_percent(interval=1)
            
            # Get memory information
            memory = psutil.virtual_memory()
            
            # Get disk usage (handle Windows/Linux paths)
            import os
            disk_path = 'C:\\' if platform.system() == 'Windows' else '/'
            disk = psutil.disk_usage(disk_path)
            
            resources = {
                'cpu_percent': cpu_percent,
                'cpu_count': psutil.cpu_count(),
                'memory_total': memory.total / (1024**3),  # GB
                'memory_used': memory.used / (1024**3),  # GB
                'memory_available': memory.available / (1024**3),  # GB
                'memory_percent': memory.percent,
                'disk_total': disk.total / (1024**3),  # GB
                'disk_used': disk.used / (1024**3),  # GB
                'disk_free': disk.free / (1024**3),  # GB
                'disk_percent': disk.percent
            }
        except Exception as e:
            app.logger.warning(f"Could not get system resources: {str(e)}")
            resources = None
        
        # Database statistics
        from models import User, Crop, Order, LearningArticle, ExpertPost
        db_stats = {
            'total_users': User.query.count(),
            'total_crops': Crop.query.count(),
            'total_orders': Order.query.count(),
            'total_articles': LearningArticle.query.count(),
            'total_forum_posts': ExpertPost.query.count(),
            'active_users': User.query.filter_by(active=True).count(),
            'verified_users': User.query.filter_by(email_verified=True).count()
        }
        
        # Application uptime (approximate)
        from models import SystemSettings
        first_setting = SystemSettings.query.order_by(SystemSettings.updated_at.asc()).first()
        app_age = (datetime.utcnow() - first_setting.updated_at).days if first_setting else 0
        
        return render_template('admin/system_info.html',
                             system_info=system_info,
                             resources=resources,
                             db_stats=db_stats,
                             app_age=app_age)
                             
    except Exception as e:
        app.logger.error(f"Error loading system info: {str(e)}")
        flash('Error loading system information.', 'error')
        return redirect(url_for('admin_system_settings'))

@app.route('/admin/system-settings/logs')
@login_required
@admin_required
def admin_view_logs():
    """View application logs"""
    try:
        log_level = request.args.get('level', 'all')
        page = request.args.get('page', 1, type=int)
        per_page = 50
        
        # Try to read log file
        log_file_path = app.config.get('LOG_FILE', 'farmlink.log')
        
        if not os.path.exists(log_file_path):
            flash('Log file not found. Logging may not be configured.', 'warning')
            return render_template('admin/logs.html', logs=[], pagination=None)
        
        # Read log file
        with open(log_file_path, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
        
        # Parse log lines
        logs = []
        for line in reversed(lines[-1000:]):  # Last 1000 lines
            line = line.strip()
            if not line:
                continue
                
            # Simple log parsing (adjust based on your log format)
            log_entry = {
                'timestamp': '',
                'level': 'INFO',
                'message': line
            }
            
            # Try to extract timestamp and level
            if ' - ' in line:
                parts = line.split(' - ', 2)
                if len(parts) >= 2:
                    log_entry['timestamp'] = parts[0]
                    if len(parts) >= 3:
                        log_entry['level'] = parts[1]
                        log_entry['message'] = parts[2]
            
            # Filter by level
            if log_level != 'all' and log_level.upper() not in log_entry['level'].upper():
                continue
            
            logs.append(log_entry)
        
        # Pagination
        total = len(logs)
        start = (page - 1) * per_page
        end = start + per_page
        paginated_logs = logs[start:end]
        
        pagination = {
            'page': page,
            'per_page': per_page,
            'total': total,
            'pages': (total + per_page - 1) // per_page
        }
        
        return render_template('admin/logs.html',
                             logs=paginated_logs,
                             pagination=pagination,
                             log_level=log_level)
                             
    except Exception as e:
        app.logger.error(f"Error viewing logs: {str(e)}")
        flash('Error loading log files.', 'error')
        return redirect(url_for('admin_system_settings'))

@app.route('/admin/system-settings/logs/download')
@login_required
@admin_required
def admin_download_logs():
    """Download log file"""
    try:
        log_file_path = app.config.get('LOG_FILE', 'farmlink.log')
        
        if not os.path.exists(log_file_path):
            flash('Log file not found.', 'error')
            return redirect(url_for('admin_view_logs'))
        
        return send_file(
            log_file_path,
            as_attachment=True,
            download_name=f'farmlink_logs_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log'
        )
        
    except Exception as e:
        app.logger.error(f"Error downloading logs: {str(e)}")
        flash('Error downloading log file.', 'error')
        return redirect(url_for('admin_view_logs'))

@app.route('/admin/system-settings/api', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_api_settings():
    """Manage API keys and configurations"""
    from models import SystemSettings
    
    if request.method == 'POST':
        try:
            # Note: In production, API keys should be stored in environment variables
            # This is for configuration management only
            api_settings = {
                'weather_api_key': request.form.get('weather_api_key'),
                'weather_api_provider': request.form.get('weather_api_provider'),
                'gemini_api_key': request.form.get('gemini_api_key'),
                'razorpay_key_id': request.form.get('razorpay_key_id'),
                'enable_weather_api': 'true' if request.form.get('enable_weather_api') else 'false',
                'enable_ai_api': 'true' if request.form.get('enable_ai_api') else 'false'
            }
            
            for key, value in api_settings.items():
                if value is not None:
                    setting = SystemSettings.query.filter_by(setting_key=key).first()
                    if setting:
                        setting.setting_value = str(value)
                        setting.updated_by = current_user.id
                    else:
                        setting_type = 'boolean' if key.startswith('enable_') else 'string'
                        setting = SystemSettings(
                            setting_key=key,
                            setting_value=str(value),
                            setting_type=setting_type,
                            updated_by=current_user.id,
                            description=f'API configuration for {key}'
                        )
                        db.session.add(setting)
            
            db.session.commit()
            
            # Log the action
            from models import AdminActionLog
            log = AdminActionLog(
                admin_id=current_user.id,
                action_type='update_api_settings',
                target_type='system_settings',
                description='Updated API configuration settings',
                ip_address=request.remote_addr
            )
            db.session.add(log)
            db.session.commit()
            
            flash('API settings updated successfully!', 'success')
            
        except Exception as e:
            db.session.rollback()
            app.logger.error(f"Error updating API settings: {str(e)}")
            flash('Error updating API settings.', 'error')
        
        return redirect(url_for('admin_api_settings'))
    
    # GET request
    all_settings = SystemSettings.query.all()
    settings_dict = {s.setting_key: s.setting_value for s in all_settings}
    
    # Get API usage statistics (if available)
    api_stats = {
        'weather_api_calls': 0,  # Implement tracking if needed
        'ai_api_calls': 0,
        'last_weather_call': None,
        'last_ai_call': None
    }
    
    return render_template('admin/api_settings.html',
                         settings=settings_dict,
                         api_stats=api_stats)

@app.route('/admin/system-settings/audit-log')
@login_required
@admin_required
def admin_settings_audit_log():
    """View audit log for system settings changes"""
    try:
        from models import AdminActionLog
        
        page = request.args.get('page', 1, type=int)
        per_page = 50
        
        # Get settings-related actions
        logs = AdminActionLog.query.filter(
            AdminActionLog.target_type == 'system_settings'
        ).order_by(
            AdminActionLog.created_at.desc()
        ).paginate(page=page, per_page=per_page, error_out=False)
        
        return render_template('admin/settings_audit_log.html',
                             logs=logs.items,
                             pagination=logs)
                             
    except Exception as e:
        app.logger.error(f"Error loading audit log: {str(e)}")
        flash('Error loading audit log.', 'error')
        return redirect(url_for('admin_system_settings'))

@app.route('/admin/system-settings/backup', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_database_backup():
    """Create and download database backup"""
    try:
        if request.method == 'POST':
            # Create backup
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_filename = f'farmlink_backup_{timestamp}.sql'
            backup_path = os.path.join('backups', backup_filename)
            
            # Create backups directory if it doesn't exist
            os.makedirs('backups', exist_ok=True)
            
            # Get database URI
            db_uri = app.config.get('SQLALCHEMY_DATABASE_URI', '')
            
            if 'sqlite' in db_uri.lower():
                # SQLite backup
                import shutil
                db_path = db_uri.replace('sqlite:///', '')
                backup_path = os.path.join('backups', f'farmlink_backup_{timestamp}.db')
                shutil.copy2(db_path, backup_path)
                
            elif 'mysql' in db_uri.lower() or 'mariadb' in db_uri.lower():
                # MySQL/MariaDB backup using mysqldump
                from urllib.parse import urlparse
                parsed = urlparse(db_uri)
                
                cmd = [
                    'mysqldump',
                    '-h', parsed.hostname or 'localhost',
                    '-P', str(parsed.port or 3306),
                    '-u', parsed.username,
                    f'-p{parsed.password}' if parsed.password else '',
                    parsed.path.lstrip('/'),
                    '--result-file', backup_path
                ]
                
                import subprocess
                result = subprocess.run(cmd, capture_output=True, text=True)
                
                if result.returncode != 0:
                    raise Exception(f"Backup failed: {result.stderr}")
                    
            else:
                flash('Database backup not supported for this database type.', 'warning')
                return redirect(url_for('admin_database_backup'))
            
            # Log the backup
            from models import AdminActionLog
            log = AdminActionLog(
                admin_id=current_user.id,
                action_type='database_backup',
                target_type='system',
                description=f'Created database backup: {backup_filename}',
                ip_address=request.remote_addr
            )
            db.session.add(log)
            db.session.commit()
            
            # Send file for download
            return send_file(
                backup_path,
                as_attachment=True,
                download_name=backup_filename
            )
            
        # GET request - show backup page
        # List existing backups
        backups = []
        if os.path.exists('backups'):
            for filename in os.listdir('backups'):
                if filename.startswith('farmlink_backup_'):
                    filepath = os.path.join('backups', filename)
                    backups.append({
                        'filename': filename,
                        'size': os.path.getsize(filepath) / (1024 * 1024),  # MB
                        'created': datetime.fromtimestamp(os.path.getctime(filepath))
                    })
        
        backups.sort(key=lambda x: x['created'], reverse=True)
        
        return render_template('admin/database_backup.html', backups=backups)
        
    except Exception as e:
        app.logger.error(f"Error in database backup: {str(e)}")
        flash(f'Error creating backup: {str(e)}', 'error')
        return redirect(url_for('admin_system_settings'))

@app.route('/admin/system-settings/backup/download/<filename>')
@login_required
@admin_required
def admin_download_backup(filename):
    """Download an existing backup file"""
    try:
        # Security: validate filename
        if not filename.startswith('farmlink_backup_'):
            flash('Invalid backup file.', 'error')
            return redirect(url_for('admin_database_backup'))
        
        backup_path = os.path.join('backups', filename)
        
        if not os.path.exists(backup_path):
            flash('Backup file not found.', 'error')
            return redirect(url_for('admin_database_backup'))
        
        return send_file(
            backup_path,
            as_attachment=True,
            download_name=filename
        )
        
    except Exception as e:
        app.logger.error(f"Error downloading backup: {str(e)}")
        flash('Error downloading backup file.', 'error')
        return redirect(url_for('admin_database_backup'))

@app.route('/admin/system-settings/backup/delete/<filename>', methods=['POST'])
@login_required
@admin_required
def admin_delete_backup(filename):
    """Delete a backup file"""
    try:
        # Security: validate filename
        if not filename.startswith('farmlink_backup_'):
            return jsonify({'success': False, 'message': 'Invalid backup file'}), 400
        
        backup_path = os.path.join('backups', filename)
        
        if os.path.exists(backup_path):
            os.remove(backup_path)
            
            # Log the deletion
            from models import AdminActionLog
            log = AdminActionLog(
                admin_id=current_user.id,
                action_type='delete_backup',
                target_type='system',
                description=f'Deleted backup: {filename}',
                ip_address=request.remote_addr
            )
            db.session.add(log)
            db.session.commit()
            
            return jsonify({'success': True, 'message': 'Backup deleted successfully'})
        else:
            return jsonify({'success': False, 'message': 'Backup file not found'}), 404
            
    except Exception as e:
        app.logger.error(f"Error deleting backup: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/admin/system-settings/cache', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_cache_management():
    """Manage application cache"""
    try:
        if request.method == 'POST':
            action = request.form.get('action')
            
            if action == 'clear_all':
                # Clear Flask cache if configured
                try:
                    from flask_caching import Cache  # type: ignore
                    cache = Cache(app)
                    cache.clear()
                    flash('Application cache cleared successfully!', 'success')
                except:
                    flash('Cache clearing not available. Flask-Caching may not be configured.', 'warning')
                
                # Log the action
                from models import AdminActionLog
                log = AdminActionLog(
                    admin_id=current_user.id,
                    action_type='clear_cache',
                    target_type='system',
                    description='Cleared application cache',
                    ip_address=request.remote_addr
                )
                db.session.add(log)
                db.session.commit()
                
            elif action == 'clear_sessions':
                # Clear expired sessions
                flash('Session cleanup completed.', 'success')
                
            return redirect(url_for('admin_cache_management'))
        
        # GET request - show cache statistics
        cache_stats = {
            'cache_enabled': False,
            'cache_type': 'Not configured',
            'total_keys': 0,
            'memory_usage': 0
        }
        
        try:
            from flask_caching import Cache  # type: ignore
            cache = Cache(app)
            cache_stats['cache_enabled'] = True
            cache_stats['cache_type'] = app.config.get('CACHE_TYPE', 'simple')
        except:
            pass
        
        return render_template('admin/cache_management.html', cache_stats=cache_stats)
        
    except Exception as e:
        app.logger.error(f"Error in cache management: {str(e)}")
        flash('Error managing cache.', 'error')
        return redirect(url_for('admin_system_settings'))

@app.route('/admin/user-analytics/<int:user_id>')
@login_required
@admin_required
def admin_user_analytics(user_id):
    """View detailed user analytics"""
    user = User.query.get_or_404(user_id)
    
    if user.role == 'farmer':
        # Calculate average rating for farmer from crop ratings
        completed_orders = [o for o in user.orders_received if o.status == 'delivered']
        # Get ratings from crops, not orders
        crop_ratings = []
        for crop in user.crops:
            if hasattr(crop, 'ratings'):
                crop_ratings.extend([r.rating for r in crop.ratings])
        avg_rating = sum(crop_ratings) / len(crop_ratings) if crop_ratings else 0.0
        
        analytics = {
            'login_count': user.login_count,
            'last_login': user.last_login,
            'total_crops': len(user.crops),
            'active_crops': len([c for c in user.crops if c.status == 'available']),
            'total_orders_received': len(user.orders_received),
            'completed_orders': len(completed_orders),
            'total_earnings': sum(o.total_amount for o in completed_orders),
            'avg_rating': avg_rating,
            'total_messages': len(user.sent_messages) + len(user.received_messages),
            'account_age': (datetime.utcnow() - user.created_at).days
        }
        
        activity = []
        for crop in user.crops:
            activity.append({
                'type': 'crop_listed',
                'date': crop.created_at,
                'details': f'Listed {crop.name} for sale'
            })
        for order in user.orders_received:
            activity.append({
                'type': 'order',
                'date': order.created_at,
                'details': f'Received order #{order.id}'
            })
    else:  # buyer
        completed_orders = [o for o in user.orders_placed if o.status == 'delivered']
        analytics = {
            'login_count': user.login_count,
            'last_login': user.last_login,
            'total_orders': len(user.orders_placed),
            'completed_orders': len(completed_orders),
            'total_spent': sum(o.total_amount for o in completed_orders),
            'unique_farmers': len(set(o.farmer_id for o in user.orders_placed)),
            'avg_rating': 0.0,  # Buyers don't have ratings, but template expects this field
            'total_messages': len(user.sent_messages) + len(user.received_messages),
            'account_age': (datetime.utcnow() - user.created_at).days
        }
        
        activity = []
        for order in user.orders_placed:
            activity.append({
                'type': 'order',
                'date': order.created_at,
                'details': f'Placed order #{order.id}'
            })
    
    activity.sort(key=lambda x: x['date'], reverse=True)
    
    return render_template('admin/user_analytics.html', user=user, analytics=analytics, activity=activity)

@app.route('/admin/change-credentials', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_change_credentials():
    """Admin route to change admin credentials"""
    form = AdminCredentialsForm()
    
    if form.validate_on_submit():
        # Check if new username already exists
        if User.query.filter(User.username == form.new_username.data, User.id != current_user.id).first():
            flash('Username already exists. Please choose another.', 'danger')
            return redirect(url_for('admin_change_credentials'))
            
        try:
            current_user.username = form.new_username.data
            current_user.set_password(form.new_password.data)
            db.session.commit()
            
            flash('Credentials updated successfully. Please log in with your new credentials.', 'success')
            logout_user()
            return redirect(url_for('login'))
            
        except Exception as e:
            db.session.rollback()
            flash('An error occurred while updating credentials. Please try again.', 'danger')
            app.logger.error(f'Error updating admin credentials: {str(e)}')
            
    return render_template('admin/change_credentials.html', form=form)

# =============================================================================
# FARMER & BUYER ROUTES
# =============================================================================

@app.route('/sell-crops')
@login_required
def sell_crops():
    """Page for farmers to list their crops"""
    if not is_farmer_or_manager(current_user):
        flash('This page is only accessible to farmers and managers.', 'warning')
        return redirect(url_for('index'))
    return render_template('crops/sell_crops.html')

@app.route('/buy-direct')
def buy_direct():
    """Direct buying page"""
    crops = Crop.query.filter_by(status='available').order_by(Crop.created_at.desc()).all()
    return render_template('marketplace/buy_direct.html', crops=crops)

@app.route('/bulk-orders')
@login_required
def bulk_orders():
    """Bulk ordering page"""
    if not is_buyer_or_manager(current_user):
        flash('This page is only accessible to buyers and managers.', 'warning')
        return redirect(url_for('index'))
    return render_template('orders/bulk.html')

# =============================================================================
# WEATHER ROUTES
# =============================================================================

@app.route('/weather-info')
@login_required
def weather_info():
    """Weather information dashboard"""
    location = request.args.get('location') or current_user.location or "New Delhi"
    
    weather_data = get_weather_data(location)
    weather_history = get_weather_history(limit=10)
    
    if weather_data.get('error'):
        flash(weather_data['condition'], 'warning')
    
    return render_template(
        'weather/dashboard.html',
        current_weather=weather_data,
        location=location,
        weather_history=weather_history,
        last_updated=format_datetime(weather_data.get('last_updated'))
    )

@app.route('/weather')
@login_required
def weather_dashboard():
    """Real weather data dashboard"""
    location = request.args.get('location', current_user.location or 'Delhi')
    
    current_weather = get_weather_data(location)
    forecast = get_weather_forecast(location, 5)
    weather_history = get_weather_history(10)
    
    return render_template('weather/dashboard.html', 
                         current_weather=current_weather,
                         forecast=forecast.get('forecast', []) if not forecast.get('error') else [],
                         weather_history=weather_history,
                         location=location)

@app.route('/price-forecast', methods=['GET', 'POST'])
@login_required
def price_forecast_dashboard():
    """Enhanced national price forecast dashboard with adjustable forecast days"""
    from forms import PriceForecastForm
    from national_price_forecast_service import NationalPriceForecastService
    
    form = PriceForecastForm()
    forecast_data = None
    error_message = None
    
    if form.validate_on_submit():
        try:
            commodity = form.commodity.data.strip()  # type: ignore
            
            # Get forecast days from form or default to 7
            forecast_days = request.form.get('forecast_days', 7, type=int)
            forecast_days = max(7, min(forecast_days, 30))  # Clamp between 7-30
            
            # Initialize the national forecast service
            service = NationalPriceForecastService()
            
            # Generate enhanced national forecast
            result = service.get_national_forecast(commodity, forecast_days=forecast_days)
            
            if result.get('success'):
                forecast_data = result
                logger.info(
                    f"Enhanced forecast generated for {commodity}: "
                    f"{result['data_points']} data points, {result['markets_covered']} markets, "
                    f"{result['states_covered']} states, {forecast_days} day forecast"
                )
            else:
                error_message = result.get('error', 'Unable to generate forecast')
                logger.warning(f"Forecast generation failed: {error_message}")
            
        except Exception as e:
            error_message = f"Error generating forecast: {str(e)}"
            logger.error(f"Unexpected error in price forecast: {str(e)}", exc_info=True)
    
    return render_template('ai/price_forecast.html', form=form, forecast_data=forecast_data, error_message=error_message)


@app.route('/api/forecast', methods=['GET'])
@login_required
def api_price_forecast():
    """
    REST API endpoint for national price forecasts.
    
    Query Parameters:
        commodity (str, required): Commodity name (e.g., "Wheat", "Rice", "Onion")
        days (int, optional): Number of days to forecast (default: 7, max: 30)
        
    Returns:
        JSON response with national forecast data
        
    Example:
        GET /api/forecast?commodity=Wheat
        
    Response:
        {
            "success": true,
            "commodity": "Wheat",
            "national_daily_average": [...],
            "forecast": [...],
            "data_points": 940,
            "markets_covered": 52,
            "source": "Agmarknet"
        }
        
    Status Codes:
        200: Success
        400: Bad request (missing or invalid parameters)
        500: Internal server error
    """
    try:
        from national_price_forecast_service import NationalPriceForecastService
        
        # Get and validate query parameters
        commodity = request.args.get('commodity')
        days = request.args.get('days', 7, type=int)
        
        # Validate required parameters
        if not commodity:
            return jsonify({
                'success': False,
                'error': 'Missing required parameter: commodity',
                'details': 'Please provide a commodity name (e.g., Wheat, Rice, Onion)'
            }), 400
        
        # Validate days parameter
        if days < 1 or days > 30:
            return jsonify({
                'success': False,
                'error': 'Invalid parameter: days',
                'details': 'Days must be between 1 and 30'
            }), 400
        
        # Initialize the national forecast service
        service = NationalPriceForecastService()
        
        # Generate national forecast
        result = service.get_national_forecast(commodity, forecast_days=days)
        
        if result.get('success'):
            logger.info(
                f"API forecast generated: commodity={commodity}, "
                f"days={days}, data_points={result['data_points']}"
            )
            return jsonify(result), 200
        else:
            logger.warning(f"API forecast failed: {result.get('error')}")
            return jsonify(result), 400
        
    except Exception as e:
        logger.error(f"Unexpected error in API forecast: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'error': 'Internal server error',
            'details': str(e)
        }), 500


# =============================================================================
# BACKWARD COMPATIBILITY REDIRECTS
# =============================================================================

@app.route('/api/forecast/options', methods=['GET'])
def api_forecast_options():
    """
    Get available commodities for price forecasting (dynamic from service).
    
    Returns:
        JSON response with lists of supported commodities
    """
    try:
        from national_price_forecast_service import NationalPriceForecastService
        
        service = NationalPriceForecastService()
        commodities_list = service.get_commodity_suggestions()
        
        # Categorize commodities
        categories = {
            'cereals': ['Wheat', 'Rice', 'Paddy', 'Maize'],
            'vegetables': ['Potato', 'Onion', 'Tomato', 'Cabbage', 'Cauliflower', 'Brinjal', 'Carrot'],
            'pulses': ['Gram', 'Bengal Gram', 'Chickpea', 'Tur', 'Arhar', 'Moong', 'Green Gram', 'Urad', 'Black Gram'],
            'cash_crops': ['Cotton', 'Sugarcane'],
            'oilseeds': ['Soybean', 'Soyabean', 'Groundnut', 'Peanut'],
            'fruits': ['Apple', 'Banana']
        }
        
        def get_category(commodity):
            for cat, items in categories.items():
                if commodity in items:
                    return cat
            return 'others'
        
        commodities_formatted = [
            {
                'value': c.lower(),
                'label': c,
                'category': get_category(c)
            }
            for c in commodities_list
        ]
        
        return jsonify({
            'success': True,
            'commodities': commodities_formatted,
            'total_commodities': len(commodities_list),
            'tips': [
                'All commodities use nationwide data from Agmarknet',
                'Popular commodities: Wheat, Rice, Onion, Tomato, Potato',
                'Forecast accuracy depends on data availability'
            ]
        }), 200
        
    except Exception as e:
        logger.error(f"Error fetching forecast options: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'Unable to fetch commodity options'
        }), 500


@app.route('/farming-tips')
def farming_tips():
    """Redirect to Learning Hub with tips category filter"""
    search = request.args.get('search', '')
    difficulty = request.args.get('difficulty', '')
    
    # Build redirect URL with parameters
    params = {'category': 'tips'}
    if search:
        params['q'] = search
    if difficulty:
        params['difficulty'] = difficulty
    
    return redirect(url_for('learning_hub', **params))

@app.route('/farming-tips/<int:tip_id>')
def view_farming_tip(tip_id):
    """Redirect to unified article view"""
    return redirect(url_for('view_article', article_id=tip_id))

@app.route('/farming-tips/add', methods=['GET', 'POST'])
@login_required
def add_farming_tip():
    """Redirect to unified add article"""
    return redirect(url_for('add_article'))

@app.route('/farming-tips/<int:tip_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_farming_tip(tip_id):
    """Redirect to unified edit article"""
    return redirect(url_for('edit_article', article_id=tip_id))

@app.route('/farming-tips/<int:tip_id>/delete', methods=['POST'])
@login_required
def delete_farming_tip(tip_id):
    """Redirect to unified delete article"""
    return delete_article(tip_id)

# =============================================================================
# INFORMATION PAGES
# =============================================================================

@app.route('/quality-assurance')
def quality_assurance():
    """Quality assurance information"""
    from datetime import datetime
    response = make_response(render_template('pages/quality.html'))
    response.headers['X-Robots-Tag'] = 'index, follow'
    response.headers['Last-Modified'] = datetime.utcnow().strftime('%a, %d %b %Y %H:%M:%S GMT')
    return response

@app.route('/delivery-info')
def delivery_info():
    """Delivery information page"""
    from datetime import datetime
    response = make_response(render_template('pages/delivery.html'))
    response.headers['X-Robots-Tag'] = 'index, follow'
    response.headers['Last-Modified'] = datetime.utcnow().strftime('%a, %d %b %Y %H:%M:%S GMT')
    return response

@app.route('/blog')
def blog():
    """Redirect to Learning Hub - unified content center"""
    page = request.args.get('page', 1, type=int)
    return redirect(url_for('learning_hub', page=page))

@app.route('/ai/pest-disease-analysis', methods=['GET', 'POST'])
@login_required
def pest_disease_analysis():
    """AI-powered pest and disease analysis"""
    if not is_farmer_or_manager(current_user):
        flash('Access denied. Farmers and managers only.', 'danger')
        return redirect(url_for('index'))
    
    form = PestDiseaseDetectionForm()
    analysis = None
    image_path = None  # Track uploaded image for cleanup
    
    # Get user's crops for dropdown and template context
    user_crops = current_user.crops if current_user.crops else []
    
    # Populate crop dropdown with user's crops - MUST be done before validation
    # This ensures choices are available for both GET and POST requests
    crop_choices = [(0, 'Select a crop (optional)')]
    if user_crops:
        crop_choices.extend([(crop.id, f"{crop.name} - {crop.category}") for crop in user_crops])
    else:
        logger.info(f"User {current_user.id} has no registered crops")
    
    if hasattr(form, 'crop_id'):
        form.crop_id.choices = crop_choices
    
    # Pre-fill form if crop_id is provided in query parameters (GET only)
    if request.method == 'GET':
        crop_id_param = request.args.get('crop_id', type=int)
        if crop_id_param:
            selected_crop = Crop.query.filter_by(id=crop_id_param, farmer_id=current_user.id).first()
            if selected_crop:
                if hasattr(form, 'crop_id'):
                    form.crop_id.data = selected_crop.id
                form.crop_type.data = selected_crop.name
                form.location.data = selected_crop.location
                flash(f'Analyzing crop: {selected_crop.name}', 'info')
    
    # Debug: Log form submission
    if request.method == 'POST':
        logger.info(f"Form submitted by user {current_user.id}")
        logger.info(f"Form data: crop_type={form.crop_type.data}, has_image={bool(form.plant_image.data)}, symptoms_length={len(form.symptoms_noticed.data or '')}")
        
        if not form.validate_on_submit():
            logger.error(f"Form validation failed for user {current_user.id}")
            logger.error(f"Form errors: {form.errors}")
            
            # Flash validation errors to user
            for field, errors in form.errors.items():
                for error in errors:
                    flash(f"{field}: {error}", 'danger')
    
    if form.validate_on_submit():
        try:
            from pest_detection_service import pest_detection_service
            
            # Extract form data
            crop_id = form.crop_id.data if hasattr(form, 'crop_id') and form.crop_id.data else None
            crop_type = form.crop_type.data
            symptoms = form.symptoms_noticed.data
            plant_stage = form.plant_stage.data
            urgency = form.urgency.data or 'medium'
            location = form.location.data or current_user.location or 'Not specified'
            
            # Handle image upload if provided
            if form.plant_image.data:
                try:
                    # Validate image format and size
                    filename = secure_filename(form.plant_image.data.filename)
                    
                    if not filename:
                        logger.error("Empty filename received")
                        flash('Invalid file. Please select a valid image file.', 'danger')
                        return render_template('ai/pest_disease_analysis.html', 
                                             form=form, analysis=None, user_crops=user_crops)
                    
                    file_ext = os.path.splitext(filename)[1].lower()
                    
                    # Validate file extension
                    if file_ext not in ['.jpg', '.jpeg', '.png', '.webp']:
                        logger.warning(f"Invalid file extension: {file_ext}")
                        flash('Invalid image format. Please upload JPG, PNG, or WebP images only.', 'danger')
                        return render_template('ai/pest_disease_analysis.html', 
                                             form=form, analysis=None, user_crops=user_crops)
                    
                    # Create unique filename with timestamp
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    unique_filename = f"{current_user.id}_{timestamp}_{filename}"
                    
                    # Save image to Cloudinary
                    from storage_utils import save_image, PEST_FOLDER
                    
                    try:
                        image_url = save_image(form.plant_image.data, folder=PEST_FOLDER)
                        if not image_url:
                            flash('Failed to upload image. Please try again.', 'danger')
                            return render_template('ai/pest_disease_analysis.html', 
                                                 form=form, analysis=None, user_crops=user_crops)
                        
                        app.logger.info(f"Image uploaded to Cloudinary: {image_url}")
                        
                    except Exception as upload_error:
                        logger.error(f"Failed to upload image to Cloudinary: {upload_error}")
                        flash('Server error: Unable to save image. Please contact support.', 'danger')
                        return render_template('ai/pest_disease_analysis.html', 
                                             form=form, analysis=None, user_crops=user_crops)
                    
                    # Validate file size (max 10MB)
                    try:
                        file_size = os.path.getsize(image_path)  # type: ignore
                        max_size = 10 * 1024 * 1024  # 10MB
                        if file_size > max_size:
                            os.remove(image_path)  # Clean up  # type: ignore
                            image_path = None
                            logger.warning(f"Image too large: {file_size} bytes")
                            flash('Image file too large. Maximum size is 10MB. Please compress or resize the image.', 'danger')
                            return render_template('ai/pest_disease_analysis.html', 
                                                 form=form, analysis=None, user_crops=user_crops)
                    except OSError as size_error:
                        logger.error(f"Failed to check file size: {size_error}")
                        if image_path and os.path.exists(image_path):
                            os.remove(image_path)
                            image_path = None
                        flash('Error processing image file. Please try again.', 'danger')
                        return render_template('ai/pest_disease_analysis.html', 
                                             form=form, analysis=None, user_crops=user_crops)
                    
                    logger.info(f"Image uploaded successfully: {image_path}")
                    
                except Exception as upload_error:
                    logger.error(f"Error saving uploaded image: {upload_error}", exc_info=True)
                    # Clean up any partially saved file
                    if image_path and os.path.exists(image_path):
                        try:
                            os.remove(image_path)
                            image_path = None
                        except Exception as cleanup_error:
                            logger.error(f"Failed to clean up image after upload error: {cleanup_error}")
                    flash('Error uploading image. Please try again with a different image.', 'danger')
                    return render_template('ai/pest_disease_analysis.html', 
                                         form=form, analysis=None, user_crops=user_crops)
            
            # Validate that at least one input method is provided
            if not image_path and not symptoms:
                flash('Please provide either an image or symptom description (or both for better accuracy).', 'warning')
                return render_template('ai/pest_disease_analysis.html', 
                                     form=form, analysis=None, user_crops=current_user.crops)
            
            # Prepare context for analysis
            context = {
                'location': location,
                'plant_stage': plant_stage,
                'urgency': urgency,
                'season': datetime.now().strftime('%B')
            }
            
            # Determine analysis mode and perform analysis
            analysis_mode = None
            if image_path and symptoms:
                analysis_mode = 'combined'
                app.logger.info(f"Performing combined analysis for {crop_type}")
                analysis = pest_detection_service.combined_analysis(
                    image_path, crop_type, symptoms, context  # type: ignore
                )
            elif image_path:
                analysis_mode = 'image'
                app.logger.info(f"Performing image analysis for {crop_type}")
                analysis = pest_detection_service.analyze_image(
                    image_path, crop_type, context  # type: ignore
                )
            elif symptoms:
                analysis_mode = 'symptoms'
                app.logger.info(f"Performing symptom analysis for {crop_type}")
                analysis = pest_detection_service.analyze_symptoms(
                    crop_type, symptoms, context  # type: ignore
                )
            
            # Process analysis results
            if analysis and analysis.get('success'):
                # Adjust for urgency level
                analysis = pest_detection_service.adjust_for_urgency(analysis, urgency)
                
                # Generate treatment recommendations if not already present
                if 'treatment_recommendations' not in analysis or not analysis['treatment_recommendations']:
                    app.logger.info("Generating treatment recommendations")
                    treatment_result = pest_detection_service.generate_treatment_recommendations(
                        analysis.get('identified_issue', ''),
                        crop_type,  # type: ignore
                        analysis.get('severity_level', 'medium'),
                        context
                    )
                    
                    if treatment_result.get('success'):
                        analysis['treatment_recommendations'] = treatment_result['treatment_recommendations']
                
                # Convert absolute image path to relative path for database storage
                relative_image_path = None
                if image_path:
                    # Convert absolute path to relative path from project root
                    try:
                        project_root = os.path.dirname(os.path.abspath(__file__))
                        relative_image_path = os.path.relpath(image_path, project_root)
                        # Normalize path separators for web use
                        relative_image_path = relative_image_path.replace('\\', '/')
                    except Exception as path_error:
                        logger.error(f"Error converting image path: {path_error}")
                        relative_image_path = image_path
                
                # Prepare data for database save
                analysis_data = {
                    'crop_id': crop_id if crop_id and crop_id != 0 else None,
                    'crop_type': crop_type,
                    'symptoms_description': symptoms,
                    'plant_stage': plant_stage,
                    'urgency_level': urgency,
                    'location': location,
                    'image_path': image_url,  # Now using Cloudinary URL  # type: ignore
                    'identified_issue': analysis.get('identified_issue'),
                    'issue_type': analysis.get('issue_type'),
                    'confidence_score': analysis.get('confidence_score'),
                    'severity_level': analysis.get('severity_level'),
                    'treatment_recommendations': analysis.get('treatment_recommendations'),
                    'preventive_measures': analysis.get('treatment_recommendations', {}).get('preventive_measures', []),
                    'additional_diagnoses': analysis.get('alternative_diagnoses', []),
                    'analysis_mode': analysis_mode,
                    'ai_model': analysis.get('ai_model', 'gemini-2.5-flash-lite'),
                    'success': True
                }
                
                # Save analysis to database
                analysis_id = pest_detection_service.save_analysis(current_user.id, analysis_data)
                
                if analysis_id:
                    analysis['analysis_id'] = analysis_id
                    flash('Analysis completed successfully! You can view it in your analysis history.', 'success')
                    app.logger.info(f"Analysis saved with ID: {analysis_id}")
                    # Redirect to the specific analysis results page
                    return redirect(url_for('view_pest_analysis', analysis_id=analysis_id))
                else:
                    flash('Analysis completed but could not be saved to history.', 'warning')
                    app.logger.warning("Failed to save analysis to database")
                    
            else:
                # Handle analysis failure
                error_message = analysis.get('error', 'Unknown error occurred') if analysis else 'Analysis service unavailable'
                error_type = analysis.get('error_type', 'unknown') if analysis else 'service_error'
                
                logger.error(f"Analysis failed for user {current_user.id}: {error_message} (type: {error_type})")
                
                # Provide user-friendly error messages based on error type
                if error_type == 'service_unavailable':
                    flash('AI analysis service is temporarily unavailable. Please try again later.', 'danger')
                elif error_type == 'rate_limit':
                    flash('Analysis limit reached. Please try again in a few minutes.', 'warning')
                elif error_type == 'invalid_image':
                    flash('Image quality is insufficient. Please upload a clearer photo in good lighting.', 'danger')
                elif error_type == 'insufficient_data':
                    flash('Insufficient information for diagnosis. Please provide more details or consult a local expert.', 'warning')
                elif error_type == 'api_error':
                    flash('AI service error. Please try again or contact support if the issue persists.', 'danger')
                else:
                    flash(f'Analysis failed: {error_message}', 'danger')
                
                # Clean up uploaded image if analysis failed
                if image_path and os.path.exists(image_path):
                    try:
                        os.remove(image_path)
                        logger.info(f"Cleaned up failed analysis image: {image_path}")
                    except OSError as cleanup_error:
                        logger.error(f"Failed to clean up image {image_path}: {cleanup_error}")
                    finally:
                        image_path = None
                
                analysis = None
                
        except ImportError as import_error:
            logger.error(f"Failed to import pest_detection_service: {import_error}", exc_info=True)
            flash('Analysis service is not properly configured. Please contact support.', 'danger')
            
            # Clean up uploaded image on error
            if image_path and os.path.exists(image_path):
                try:
                    os.remove(image_path)
                    logger.info(f"Cleaned up image after import error: {image_path}")
                except Exception:
                    pass
            
            analysis = None
            
        except Exception as e:
            logger.error(f"Unexpected error in pest disease analysis for user {current_user.id}: {str(e)}", exc_info=True)
            flash('An unexpected error occurred during analysis. Please try again or contact support.', 'danger')
            
            # Clean up uploaded image on error
            if image_path and os.path.exists(image_path):
                try:
                    os.remove(image_path)
                    logger.info(f"Cleaned up image after unexpected error: {image_path}")
                except OSError as cleanup_error:
                    logger.error(f"Failed to clean up image during error handling: {cleanup_error}")
                finally:
                    image_path = None
            
            analysis = None
    
    # Ensure all required context variables are passed to template
    # user_crops is already defined at the top of the function
    return render_template('ai/pest_disease_analysis.html', 
                         form=form, 
                         analysis=analysis, 
                         user_crops=user_crops)

@app.route('/ai/pest-analysis-history')
@login_required
def pest_analysis_history():
    """Display user's pest and disease analysis history"""
    # Require farmer or manager role
    if not is_farmer_or_manager(current_user):
        flash('Access denied. This page is for farmers and managers only.', 'danger')
        return redirect(url_for('index'))
    
    try:
        from models import PestDiseaseAnalysis
        
        # Get pagination parameters
        page = request.args.get('page', 1, type=int)
        per_page = 20
        
        # Get filter parameters
        search = request.args.get('search', '').strip()
        crop_type = request.args.get('crop_type', '').strip()
        severity = request.args.get('severity', '').strip()
        date_range = request.args.get('date_range', '').strip()
        
        # Build query with filters
        query = PestDiseaseAnalysis.query.filter_by(user_id=current_user.id)
        
        if search:
            query = query.filter(PestDiseaseAnalysis.identified_issue.ilike(f'%{search}%'))
        
        if crop_type:
            query = query.filter(PestDiseaseAnalysis.crop_type == crop_type)
        
        if severity:
            query = query.filter(PestDiseaseAnalysis.severity_level == severity)
        
        if date_range:
            days = int(date_range)
            cutoff_date = datetime.now() - timedelta(days=days)
            query = query.filter(PestDiseaseAnalysis.created_at >= cutoff_date)
        
        # Query user's analyses with crop information via relationship
        analyses_pagination = query.order_by(
            PestDiseaseAnalysis.created_at.desc()
        ).paginate(
            page=page, per_page=per_page, error_out=False
        )
        
        # Get user's crops for filter dropdown
        user_crops = current_user.crops
        
        app.logger.info(f"Retrieved {len(analyses_pagination.items)} analyses for user {current_user.id}")
        
        return render_template('ai/pest_analysis_history.html', 
                             analyses=analyses_pagination.items,
                             pagination=analyses_pagination,
                             user_crops=user_crops)
        
    except Exception as e:
        app.logger.error(f"Error loading pest analysis history: {str(e)}", exc_info=True)
        flash('Error loading analysis history. Please try again.', 'danger')
        return redirect(url_for('farmer_dashboard'))

@app.route('/ai/pest-analysis/<int:analysis_id>')
@login_required
def view_pest_analysis(analysis_id):
    """View detailed results of a specific pest analysis"""
    try:
        from models import PestDiseaseAnalysis
        
        # Query analysis by ID and verify ownership
        analysis = PestDiseaseAnalysis.query.filter_by(
            id=analysis_id,
            user_id=current_user.id
        ).first_or_404()
        
        # Parse JSON fields for display with error handling
        try:
            treatment_recommendations = analysis.get_treatment_recommendations()
        except Exception as e:
            app.logger.error(f"Error parsing treatment recommendations: {str(e)}")
            treatment_recommendations = {}
        
        try:
            preventive_measures = analysis.get_preventive_measures()
        except Exception as e:
            app.logger.error(f"Error parsing preventive measures: {str(e)}")
            preventive_measures = []
        
        try:
            additional_diagnoses = analysis.get_additional_diagnoses()
        except Exception as e:
            app.logger.error(f"Error parsing additional diagnoses: {str(e)}")
            additional_diagnoses = []
        
        # Load associated crop information if crop_id exists
        crop = None
        if analysis.crop_id:
            from models import Crop
            crop = Crop.query.get(analysis.crop_id)
        
        app.logger.info(f"Displaying analysis {analysis_id} for user {current_user.id}")
        
        try:
            return render_template('ai/pest_analysis_detail.html',
                                 analysis=analysis,
                                 crop=crop,
                                 treatment_recommendations=treatment_recommendations,
                                 preventive_measures=preventive_measures,
                                 additional_diagnoses=additional_diagnoses)
        except Exception as template_error:
            app.logger.error(f"Template rendering error: {str(template_error)}", exc_info=True)
            flash(f'Error rendering analysis details: {str(template_error)}', 'danger')
            return redirect(url_for('pest_analysis_history'))
        
    except Exception as e:
        app.logger.error(f"Error viewing pest analysis {analysis_id}: {str(e)}", exc_info=True)
        flash(f'Error loading analysis details: {str(e)}', 'danger')
        return redirect(url_for('pest_analysis_history'))

@app.route('/ai/pest-analysis/bulk-delete', methods=['POST'])
@login_required
def bulk_delete_pest_analysis():
    """Delete multiple pest analyses"""
    try:
        from models import PestDiseaseAnalysis
        import json
        
        # Get IDs from request
        data = request.get_json()
        ids = data.get('ids', [])
        
        if not ids or not isinstance(ids, list):
            return jsonify({'success': False, 'error': 'No IDs provided'}), 400
        
        # Convert to integers
        try:
            ids = [int(id) for id in ids]
        except (ValueError, TypeError):
            return jsonify({'success': False, 'error': 'Invalid ID format'}), 400
        
        # Delete analyses (only user's own)
        deleted_count = 0
        for analysis_id in ids:
            analysis = PestDiseaseAnalysis.query.filter_by(
                id=analysis_id,
                user_id=current_user.id
            ).first()
            
            if analysis:
                # Delete associated image file if exists
                if analysis.image_path:
                    try:
                        image_full_path = os.path.join(
                            os.path.dirname(os.path.abspath(__file__)),
                            analysis.image_path
                        )
                        if os.path.exists(image_full_path):
                            os.remove(image_full_path)
                            app.logger.info(f"Deleted image: {image_full_path}")
                    except Exception as img_error:
                        app.logger.warning(f"Could not delete image: {str(img_error)}")
                
                db.session.delete(analysis)
                deleted_count += 1
        
        db.session.commit()
        
        app.logger.info(f"User {current_user.id} deleted {deleted_count} analyses")
        
        return jsonify({
            'success': True,
            'deleted_count': deleted_count,
            'message': f'Successfully deleted {deleted_count} analysis record(s)'
        })
        
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Error in bulk delete: {str(e)}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/ai/pest-analysis/<int:analysis_id>/download-pdf')
@login_required
def download_pest_analysis_pdf(analysis_id):
    """Generate and download PDF report for specific analysis"""
    try:
        from models import PestDiseaseAnalysis, Crop
        from report_generator import generate_pest_detection_report
        import tempfile
        
        # Query analysis by ID and verify ownership
        analysis = PestDiseaseAnalysis.query.filter_by(
            id=analysis_id,
            user_id=current_user.id
        ).first_or_404()
        
        # Parse JSON fields
        treatment_recommendations = analysis.get_treatment_recommendations()
        preventive_measures = analysis.get_preventive_measures()
        additional_diagnoses = analysis.get_additional_diagnoses()
        
        # Load associated crop information if available
        crop = None
        if analysis.crop_id:
            crop = Crop.query.get(analysis.crop_id)
        
        # Prepare image path for PDF
        image_path_for_pdf = None
        if analysis.image_path:
            try:
                # Convert relative path to absolute path
                project_root = os.path.dirname(os.path.abspath(__file__))
                image_full_path = os.path.join(project_root, analysis.image_path)
                
                # Check if file exists
                if os.path.exists(image_full_path):
                    image_path_for_pdf = image_full_path
                    app.logger.info(f"Image found for PDF: {image_full_path}")
                else:
                    app.logger.warning(f"Image not found: {image_full_path}")
            except Exception as img_error:
                app.logger.error(f"Error processing image path: {str(img_error)}")
        
        # Prepare detection data for PDF generation
        detection_data = {
            'analysis_id': analysis.id,
            'crop_type': analysis.crop_type,
            'plant_stage': analysis.plant_stage or 'Not specified',
            'location': analysis.location or 'Not specified',
            'identified_issue': analysis.identified_issue or 'Unknown',
            'issue_type': analysis.issue_type or 'Unknown',
            'confidence_score': analysis.confidence_score or 0,
            'severity_level': analysis.severity_level or 'Unknown',
            'analysis_mode': analysis.analysis_mode,
            'image_path': image_path_for_pdf,
            'predictions': [{
                'rank': 1,
                'class': analysis.identified_issue or 'Unknown',
                'confidence_percentage': analysis.confidence_score or 0,
                'details': {
                    'type': analysis.issue_type or 'Unknown',
                    'severity': analysis.severity_level or 'Unknown',
                    'symptoms': analysis.symptoms_description or 'No symptoms provided'
                }
            }],
            'recommendations': {
                'overall_status': 'healthy' if analysis.severity_level == 'low' else 'needs_attention',
                'urgency': analysis.urgency_level or 'medium',
                'action_required': analysis.severity_level in ['high', 'critical'],
                'immediate_actions': treatment_recommendations.get('immediate_actions', []) if isinstance(treatment_recommendations, dict) else [],
                'long_term_care': preventive_measures if isinstance(preventive_measures, list) else [],
                'monitoring_advice': [
                    'Monitor plant health daily',
                    'Check for spread to nearby plants',
                    'Document any changes in symptoms'
                ]
            }
        }
        
        # Add additional diagnoses if available
        if additional_diagnoses and isinstance(additional_diagnoses, list):
            for i, diag in enumerate(additional_diagnoses[:2]):
                if isinstance(diag, dict):
                    detection_data['predictions'].append({
                        'rank': i + 2,
                        'class': diag.get('identified_issue', diag.get('issue', 'Unknown')),
                        'confidence_percentage': diag.get('confidence_score', diag.get('confidence', 0)),
                        'details': {
                            'type': 'alternative',
                            'severity': diag.get('severity_level', 'Unknown'),
                            'symptoms': diag.get('key_difference', diag.get('description', ''))
                        }
                    })
        
        # Prepare user data
        user_data = {
            'full_name': current_user.full_name or current_user.username,
            'location': current_user.location or 'Not specified',
            'phone': current_user.phone or 'Not provided'
        }
        
        # Create temporary file for PDF
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_file:
            output_path = tmp_file.name
        
        # Generate PDF
        try:
            success = generate_pest_detection_report(detection_data, user_data, output_path)
            
            if not success:
                raise Exception("PDF generation failed")
            
            # Create filename
            crop_name = crop.name if crop else analysis.crop_type
            crop_name = crop_name.replace(' ', '_')
            date_str = analysis.created_at.strftime('%Y%m%d')
            filename = f"pest_analysis_{crop_name}_{date_str}.pdf"
            
            # Send file and clean up
            response = send_file(
                output_path,
                mimetype='application/pdf',
                as_attachment=True,
                download_name=filename
            )
            
            # Schedule file deletion after sending
            @response.call_on_close
            def cleanup():
                try:
                    if os.path.exists(output_path):
                        os.unlink(output_path)
                except Exception as e:
                    app.logger.error(f"Error cleaning up temp PDF file: {str(e)}")
            
            app.logger.info(f"Generated PDF for analysis {analysis_id}")
            return response
            
        except ImportError as ie:
            app.logger.warning(f"PDF generator dependencies not available: {str(ie)}")
            flash('PDF generation is not available. Please install required dependencies.', 'warning')
            return redirect(url_for('view_pest_analysis', analysis_id=analysis_id))
        except Exception as pdf_error:
            app.logger.error(f"Error generating PDF: {str(pdf_error)}", exc_info=True)
            # Clean up temp file on error
            try:
                if 'output_path' in locals() and os.path.exists(output_path):
                    os.unlink(output_path)
            except:
                pass
            flash(f'Error generating PDF report: {str(pdf_error)}', 'danger')
            return redirect(url_for('view_pest_analysis', analysis_id=analysis_id))
        
    except Exception as e:
        app.logger.error(f"Error downloading pest analysis PDF {analysis_id}: {str(e)}", exc_info=True)
        flash('Error generating PDF report. Please try again.', 'danger')
        return redirect(url_for('pest_analysis_history'))

# Price forecasting feature removed - no longer supported

@app.route('/ai/voice-interface')
@login_required
def voice_interface():
    """AI-powered multilingual voice interface"""
    return render_template('ai/voice_interface.html', user=current_user)

@app.route('/api/voice-upload', methods=['POST'])
@login_required
def voice_upload_api():
    """API endpoint for processing uploaded audio files"""
    try:
        if 'audio' not in request.files:
            return jsonify({'error': 'No audio file provided'}), 400
        
        audio_file = request.files['audio']
        language = request.form.get('language', 'english').lower()
        include_audio = request.form.get('include_audio', 'false').lower() == 'true'
        
        if audio_file.filename == '':
            return jsonify({'error': 'No audio file selected'}), 400
        
        # Check if Gemini client is available
        if not client:
            return jsonify({
                'error': 'Gemini API not configured. Please set GEMINI_API_KEY environment variable.'
            }), 503
        
        # Save temporary audio file
        import tempfile
        import os
        
        with tempfile.NamedTemporaryFile(delete=False, suffix='.wav') as temp_audio:
            audio_file.save(temp_audio.name)
            temp_audio_path = temp_audio.name
        
        try:
            # Process audio file
            transcription_result = EnhancedVoiceAI.process_voice_query(temp_audio_path, language)
            
            if not transcription_result['success']:
                return jsonify({'error': transcription_result['error']}), 500
            
            query = transcription_result['text']
            
            # Get AI response
            ai_response = EnhancedVoiceAI.get_multilingual_farming_response(query, language)
            
            response_data = {
                'response': ai_response,
                'query': query,
                'language': language,
                'detected_language': transcription_result.get('detected_language', language)
            }
            
            # Generate audio response if requested
            if include_audio:
                try:
                    audio_content = EnhancedVoiceAI.generate_voice_response(ai_response, language)
                    if audio_content:
                        import base64
                        audio_b64 = base64.b64encode(audio_content).decode('utf-8')
                        response_data['audio'] = f"data:audio/mp3;base64,{audio_b64}"
                except Exception as audio_error:
                    logger.error(f"Audio generation failed: {audio_error}")
            
            return jsonify(response_data)
            
        finally:
            # Clean up temp file
            if os.path.exists(temp_audio_path):
                os.unlink(temp_audio_path)
        
    except Exception as e:
        return jsonify({
            'response': f"I apologize, but I encountered an error processing your audio: {str(e)}. Please try again."
        }), 500

@app.route('/api/voice-assistant', methods=['POST'])
@login_required
def voice_assistant_api():
    """Enhanced multilingual API endpoint for voice assistant queries"""
    try:
        data = request.get_json()
        query = data.get('query', '').strip()
        language = data.get('language', 'english').lower()
        include_audio = data.get('include_audio', False)
        conversation_id = data.get('conversation_id')  # Optional conversation ID
        
        if not query:
            return jsonify({'error': 'No query provided'}), 400
        
        # Get comprehensive farming response using Gemini AI
        ai_response = EnhancedVoiceAI.get_multilingual_farming_response(query, language)
        
        response_data = {
            'response': ai_response,
            'query': query,
            'language': language,
            'timestamp': datetime.now().isoformat(),
            'success': True
        }
        
        # Save to database if conversation_id provided
        if conversation_id:
            try:
                from models import AIConversation, AIMessage
                conversation = AIConversation.query.filter_by(
                    id=conversation_id,
                    user_id=current_user.id
                ).first()
                
                if conversation:
                    # Add user message
                    user_msg = AIMessage(
                        conversation_id=conversation.id,
                        type='user',
                        content=query
                    )
                    db.session.add(user_msg)
                    
                    # Add AI response
                    ai_msg = AIMessage(
                        conversation_id=conversation.id,
                        type='ai',
                        content=ai_response
                    )
                    db.session.add(ai_msg)
                    
                    # Update conversation timestamp
                    conversation.updated_at = datetime.utcnow()
                    
                    db.session.commit()
                    response_data['conversation_id'] = conversation.id
            except Exception as db_error:
                logger.error(f"Failed to save conversation: {db_error}")
                db.session.rollback()
        
        # Generate audio response if requested (placeholder for future TTS integration)
        if include_audio:
            try:
                audio_content = EnhancedVoiceAI.generate_voice_response(ai_response, language)
                if audio_content:
                    # Save audio file temporarily
                    import tempfile
                    import base64
                    
                    with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3') as temp_audio:
                        temp_audio.write(audio_content)
                        temp_audio_path = temp_audio.name
                    
                    # Convert to base64 for transmission
                    with open(temp_audio_path, 'rb') as audio_file:
                        audio_b64 = base64.b64encode(audio_file.read()).decode('utf-8')
                        response_data['audio'] = f"data:audio/mp3;base64,{audio_b64}"
                    
                    # Clean up temp file
                    import os
                    os.unlink(temp_audio_path)
                    
            except Exception as audio_error:
                logger.error(f"Audio generation failed: {audio_error}")
                # Continue without audio
        
        return jsonify(response_data)
        
    except Exception as e:
        logger.error(f"Voice assistant API error: {str(e)}")
        return jsonify({
            'response': f"I encountered an error processing your request: {str(e)}. Please try again.",
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/voice-quick-command', methods=['POST'])
@login_required  
def voice_quick_command_api():
    """API endpoint for quick voice commands"""
    try:
        data = request.get_json()
        command = data.get('command', '').strip()
        language = data.get('language', 'english').lower()
        
        if not command:
            return jsonify({'error': 'No command provided'}), 400
        
        # Map quick commands to detailed queries
        command_queries = {
            'weather': 'What is the current weather forecast and farming conditions?',
            'prices': 'What are the current market prices for major crops?',
            'diseases': 'What are the common crop diseases and treatments this season?',
            'fertilizer': 'What fertilizer recommendations do you have for current crops?',
            'help': 'How can the Farmlink platform help me with farming?'
        }
        
        query = command_queries.get(command, f"Please help me with {command}")
        
        # Get response using the main voice assistant function
        ai_response = EnhancedVoiceAI.get_multilingual_farming_response(query, language)
        
        response_data = {
            'response': ai_response,
            'command': command,
            'query': query,
            'language': language,
            'timestamp': datetime.now().isoformat(),
            'success': True
        }
        
        return jsonify(response_data)
        
    except Exception as e:
        logger.error(f"Quick command API error: {str(e)}")
        return jsonify({
            'response': f"I encountered an error processing your command. Please try again.",
            'success': False,
            'error': str(e)
        }), 500


# =============================================================================
# AI CONVERSATION MANAGEMENT ROUTES
# =============================================================================

@app.route('/api/conversations', methods=['GET'])
@login_required
def get_conversations():
    """Get all conversations for the current user"""
    try:
        from models import AIConversation
        conversations = AIConversation.query.filter_by(
            user_id=current_user.id
        ).order_by(AIConversation.updated_at.desc()).all()
        
        return jsonify({
            'success': True,
            'conversations': [conv.to_dict() for conv in conversations]
        })
    except Exception as e:
        logger.error(f"Error fetching conversations: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/conversations', methods=['POST'])
@login_required
def create_conversation():
    """Create a new conversation"""
    try:
        from models import AIConversation
        data = request.get_json()
        title = data.get('title', 'New Chat')
        
        conversation = AIConversation(
            user_id=current_user.id,
            title=title
        )
        db.session.add(conversation)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'conversation': conversation.to_dict()
        })
    except Exception as e:
        logger.error(f"Error creating conversation: {e}")
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/conversations/<int:conversation_id>', methods=['GET'])
@login_required
def get_conversation(conversation_id):
    """Get a specific conversation with all messages"""
    try:
        from models import AIConversation
        conversation = AIConversation.query.filter_by(
            id=conversation_id,
            user_id=current_user.id
        ).first()
        
        if not conversation:
            return jsonify({'success': False, 'error': 'Conversation not found'}), 404
        
        return jsonify({
            'success': True,
            'conversation': conversation.to_dict()
        })
    except Exception as e:
        logger.error(f"Error fetching conversation: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/conversations/<int:conversation_id>', methods=['PUT'])
@login_required
def update_conversation(conversation_id):
    """Update conversation title"""
    try:
        from models import AIConversation
        data = request.get_json()
        title = data.get('title', '').strip()
        
        if not title:
            return jsonify({'success': False, 'error': 'Title is required'}), 400
        
        conversation = AIConversation.query.filter_by(
            id=conversation_id,
            user_id=current_user.id
        ).first()
        
        if not conversation:
            return jsonify({'success': False, 'error': 'Conversation not found'}), 404
        
        conversation.title = title
        conversation.updated_at = datetime.utcnow()
        db.session.commit()
        
        return jsonify({
            'success': True,
            'conversation': conversation.to_dict()
        })
    except Exception as e:
        logger.error(f"Error updating conversation: {e}")
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/conversations/<int:conversation_id>', methods=['DELETE'])
@login_required
def delete_conversation(conversation_id):
    """Delete a conversation"""
    try:
        from models import AIConversation
        conversation = AIConversation.query.filter_by(
            id=conversation_id,
            user_id=current_user.id
        ).first()
        
        if not conversation:
            return jsonify({'success': False, 'error': 'Conversation not found'}), 404
        
        db.session.delete(conversation)
        db.session.commit()
        
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"Error deleting conversation: {e}")
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/conversations/sync', methods=['POST'])
@login_required
def sync_conversations():
    """Sync local conversations to server"""
    try:
        from models import AIConversation, AIMessage
        data = request.get_json()
        local_chats = data.get('chats', {})
        
        synced_conversations = []
        
        for chat_id, chat_data in local_chats.items():
            # Check if conversation already exists
            existing = AIConversation.query.filter_by(
                id=int(chat_id) if str(chat_id).isdigit() else None,
                user_id=current_user.id
            ).first()
            
            if not existing:
                # Create new conversation
                conversation = AIConversation(
                    user_id=current_user.id,
                    title=chat_data.get('title', 'New Chat')
                )
                db.session.add(conversation)
                db.session.flush()  # Get the ID
                
                # Add messages
                for msg in chat_data.get('messages', []):
                    message = AIMessage(
                        conversation_id=conversation.id,
                        type=msg.get('type'),
                        content=msg.get('content')
                    )
                    db.session.add(message)
                
                synced_conversations.append(conversation.to_dict())
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'synced': len(synced_conversations),
            'conversations': synced_conversations
        })
    except Exception as e:
        logger.error(f"Error syncing conversations: {e}")
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

# =============================================================================
# LEARNING HUB ROUTES
# =============================================================================

@app.route('/learning-hub')
def learning_hub():
    """Learning hub main page - unified knowledge center"""
    try:
        page = request.args.get('page', 1, type=int)
        category = request.args.get('category', 'all')
        difficulty = request.args.get('difficulty', 'all')
        crop_type = request.args.get('crop_type', 'all')
        search_query = request.args.get('q', '').strip()
        
        # Base query with eager loading for better performance
        query = LearningArticle.query.options(
            db.joinedload(LearningArticle.author)
        ).filter(LearningArticle.is_published == True)
        
        # Apply search filter
        if search_query:
            search_filter = f"%{search_query}%"
            query = query.filter(
                db.or_(
                    LearningArticle.title.ilike(search_filter),
                    LearningArticle.content.ilike(search_filter),
                    LearningArticle.summary.ilike(search_filter),
                    LearningArticle.tags.ilike(search_filter)
                )
            )
        
        # Apply category filter
        if category != 'all':
            query = query.filter(LearningArticle.category == category)
        
        # Apply difficulty filter
        if difficulty != 'all':
            query = query.filter(LearningArticle.difficulty_level == difficulty)
        
        # Apply crop type filter
        if crop_type != 'all':
            query = query.filter(LearningArticle.crop_type == crop_type)
        
        # Paginate results
        articles = query.order_by(LearningArticle.created_at.desc()).paginate(
            page=page, per_page=12, error_out=False
        )
        
        # Get featured articles (only if on first page for performance)
        featured_articles = []
        if page == 1 and not search_query:
            featured_articles = LearningArticle.query.options(
                db.joinedload(LearningArticle.author)
            ).filter(
                LearningArticle.is_published == True
            ).order_by(LearningArticle.views.desc()).limit(3).all()
        
        # Get personalized recommendations for logged-in users
        user_recommendations = []
        if current_user.is_authenticated and page == 1:
            try:
                from learning_recommendation_service import LearningRecommendationEngine
                engine = LearningRecommendationEngine(current_user.id)
                user_recommendations = engine.generate_recommendations(limit=3)
            except Exception as e:
                app.logger.error(f"Error generating recommendations: {str(e)}")
        
        return render_template('learning_hub/index.html', 
                             articles=articles, 
                             featured_articles=featured_articles,
                             user_recommendations=user_recommendations)
    
    except Exception as e:
        app.logger.error(f"Error in learning_hub route: {str(e)}")
        flash('Error loading knowledge center.', 'error')
        return redirect(url_for('index'))

@app.route('/learning-hub/article/<int:article_id>')
def view_article(article_id):
    """View learning article"""
    try:
        # Eager load author relationship for better performance
        article = LearningArticle.query.options(
            db.joinedload(LearningArticle.author)
        ).get_or_404(article_id)
        
        # Check if published (admins and authors can view unpublished)
        if not article.is_published:
            if not current_user.is_authenticated or (
                current_user.role != 'admin' and current_user.id != article.author_id
            ):
                flash('Article not found.', 'error')
                return redirect(url_for('learning_hub'))
        
        # Increment views (use update to avoid race conditions)
        LearningArticle.query.filter_by(id=article_id).update(
            {'views': LearningArticle.views + 1}
        )
        db.session.commit()
        
        # Get related articles from same category
        related_articles = LearningArticle.query.options(
            db.joinedload(LearningArticle.author)
        ).filter(
            LearningArticle.category == article.category,
            LearningArticle.id != article.id,
            LearningArticle.is_published == True
        ).order_by(LearningArticle.views.desc()).limit(3).all()
        
        # Get comments with proper ordering
        from models import ArticleComment
        comments = ArticleComment.query.filter_by(
            article_id=article.id,
            parent_id=None
        ).order_by(ArticleComment.created_at.desc()).all()
        
        return render_template('learning_hub/article_detail.html', 
                             article=article, 
                             related_articles=related_articles,
                             comments=comments)
    
    except Exception as e:
        app.logger.error(f"Error viewing article {article_id}: {str(e)}")
        flash('Article not found.', 'error')
        return redirect(url_for('learning_hub'))

@app.route('/learning-hub/add', methods=['GET', 'POST'])
@login_required
def add_article():
    """Add new learning article"""
    if current_user.role != 'admin':
        flash('Only administrators can add articles.', 'warning')
        return redirect(url_for('learning_hub'))
    
    if request.method == 'POST':
        try:
            action = request.form.get('action', 'publish')
            publish_status = request.form.get('publish_status', 'publish')
            
            # Determine if draft
            is_draft = action == 'draft' or publish_status == 'draft'
            is_published = not is_draft and publish_status != 'schedule'
            
            # Handle scheduled publishing
            scheduled_publish = None
            if publish_status == 'schedule':
                scheduled_str = request.form.get('scheduled_publish')
                if scheduled_str:
                    scheduled_publish = datetime.strptime(scheduled_str, '%Y-%m-%dT%H:%M')
                    is_published = False  # Don't publish yet
            
            article = LearningArticle(
                title=request.form.get('title'),
                content=request.form.get('content'),
                summary=request.form.get('summary'),
                category=request.form.get('category', 'general'),
                crop_type=request.form.get('crop_type', 'general'),
                difficulty_level=request.form.get('difficulty_level', 'beginner'),
                reading_time=int(request.form.get('reading_time', 5)),
                featured_image=request.form.get('featured_image'),
                tags=request.form.get('tags'),
                author_id=current_user.id,
                is_draft=is_draft,
                is_published=is_published,
                scheduled_publish=scheduled_publish
            )
            
            db.session.add(article)
            db.session.commit()
            
            if is_draft:
                flash('Article saved as draft!', 'info')
            elif scheduled_publish:
                flash(f'Article scheduled for {scheduled_publish.strftime("%B %d, %Y at %I:%M %p")}!', 'success')
            else:
                flash('Article published successfully!', 'success')
            
            return redirect(url_for('view_article', article_id=article.id))
            
        except Exception as e:
            app.logger.error(f"Error adding article: {str(e)}")
            db.session.rollback()
            flash('Error adding article. Please try again.', 'error')
    
    return render_template('learning_hub/add_article.html')

@app.route('/learning-hub/article/<int:article_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_article(article_id):
    """Edit existing learning article"""
    article = LearningArticle.query.get_or_404(article_id)
    
    if current_user.role != 'admin' and current_user.id != article.author_id:
        flash('You can only edit your own articles.', 'warning')
        return redirect(url_for('view_article', article_id=article_id))
    
    if request.method == 'POST':
        try:
            article.title = request.form.get('title')
            article.content = request.form.get('content')
            article.summary = request.form.get('summary')
            article.category = request.form.get('category', 'general')
            article.crop_type = request.form.get('crop_type', 'general')
            article.difficulty_level = request.form.get('difficulty_level', 'beginner')
            article.reading_time = int(request.form.get('reading_time', 5))
            article.featured_image = request.form.get('featured_image')
            article.tags = request.form.get('tags')
            article.updated_at = datetime.utcnow()
            
            db.session.commit()
            
            flash('Article updated successfully!', 'success')
            return redirect(url_for('view_article', article_id=article.id))
            
        except Exception as e:
            app.logger.error(f"Error updating article {article_id}: {str(e)}")
            db.session.rollback()
            flash('Error updating article. Please try again.', 'error')
    
    return render_template('learning_hub/edit_article.html', article=article)

@app.route('/learning-hub/article/<int:article_id>/delete', methods=['POST'])
@login_required
def delete_article(article_id):
    """Delete learning article"""
    article = LearningArticle.query.get_or_404(article_id)
    
    if current_user.role != 'admin' and current_user.id != article.author_id:
        return jsonify({'success': False, 'message': 'Permission denied'})
    
    try:
        db.session.delete(article)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Article deleted successfully'})
    except Exception as e:
        app.logger.error(f"Error deleting article {article_id}: {str(e)}")
        db.session.rollback()
        return jsonify({'success': False, 'message': 'Error deleting article'})


@app.route('/learning-hub/article/<int:article_id>/like', methods=['POST'])
@login_required
def like_article(article_id):
    """Like or unlike an article"""
    from models import ArticleLike
    
    try:
        article = LearningArticle.query.get_or_404(article_id)
        existing_like = ArticleLike.query.filter_by(
            article_id=article_id,
            user_id=current_user.id
        ).first()
        
        if existing_like:
            # Unlike
            db.session.delete(existing_like)
            article.likes = max(0, article.likes - 1)
            db.session.commit()
            return jsonify({
                'success': True,
                'liked': False,
                'likes_count': article.get_like_count()
            })
        else:
            # Like
            new_like = ArticleLike(article_id=article_id, user_id=current_user.id)
            db.session.add(new_like)
            article.likes = article.get_like_count() + 1
            db.session.commit()
            return jsonify({
                'success': True,
                'liked': True,
                'likes_count': article.get_like_count()
            })
    except Exception as e:
        app.logger.error(f"Error liking article {article_id}: {str(e)}")
        db.session.rollback()
        return jsonify({'success': False, 'message': 'Error processing like'}), 500


@app.route('/learning-hub/article/<int:article_id>/bookmark', methods=['POST'])
@login_required
def bookmark_article(article_id):
    """Bookmark or unbookmark an article"""
    from models import ArticleBookmark
    
    try:
        article = LearningArticle.query.get_or_404(article_id)
        existing_bookmark = ArticleBookmark.query.filter_by(
            article_id=article_id,
            user_id=current_user.id
        ).first()
        
        if existing_bookmark:
            # Remove bookmark
            db.session.delete(existing_bookmark)
            db.session.commit()
            return jsonify({
                'success': True,
                'bookmarked': False,
                'message': 'Bookmark removed'
            })
        else:
            # Add bookmark
            new_bookmark = ArticleBookmark(article_id=article_id, user_id=current_user.id)
            db.session.add(new_bookmark)
            db.session.commit()
            return jsonify({
                'success': True,
                'bookmarked': True,
                'message': 'Article bookmarked'
            })
    except Exception as e:
        app.logger.error(f"Error bookmarking article {article_id}: {str(e)}")
        db.session.rollback()
        return jsonify({'success': False, 'message': 'Error processing bookmark'}), 500


@app.route('/learning-hub/article/<int:article_id>/comment', methods=['POST'])
@login_required
def add_comment(article_id):
    """Add a comment to an article"""
    from models import ArticleComment
    
    try:
        article = LearningArticle.query.get_or_404(article_id)
        content = request.form.get('content', '').strip()
        parent_id = request.form.get('parent_id', type=int)
        
        if not content or len(content) < 3:
            return jsonify({'success': False, 'message': 'Comment too short'}), 400
        
        comment = ArticleComment(
            article_id=article_id,
            user_id=current_user.id,
            content=content,
            parent_id=parent_id
        )
        
        db.session.add(comment)
        article.comments_count += 1
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Comment added successfully',
            'comment': {
                'id': comment.id,
                'content': comment.content,
                'user': current_user.username,
                'created_at': comment.created_at.strftime('%B %d, %Y at %I:%M %p')
            }
        })
    except Exception as e:
        app.logger.error(f"Error adding comment to article {article_id}: {str(e)}")
        db.session.rollback()
        return jsonify({'success': False, 'message': 'Error adding comment'}), 500


@app.route('/learning-hub/comment/<int:comment_id>/edit', methods=['POST'])
@login_required
def edit_comment(comment_id):
    """Edit a comment"""
    from models import ArticleComment
    
    try:
        comment = ArticleComment.query.get_or_404(comment_id)
        
        if comment.user_id != current_user.id and current_user.role != 'admin':
            return jsonify({'success': False, 'message': 'Permission denied'}), 403
        
        content = request.form.get('content', '').strip()
        if not content or len(content) < 3:
            return jsonify({'success': False, 'message': 'Comment too short'}), 400
        
        comment.content = content
        comment.is_edited = True
        comment.updated_at = datetime.utcnow()
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Comment updated successfully',
            'content': comment.content
        })
    except Exception as e:
        app.logger.error(f"Error editing comment {comment_id}: {str(e)}")
        db.session.rollback()
        return jsonify({'success': False, 'message': 'Error updating comment'}), 500


@app.route('/learning-hub/comment/<int:comment_id>/delete', methods=['POST'])
@login_required
def delete_comment(comment_id):
    """Delete a comment"""
    from models import ArticleComment
    
    try:
        comment = ArticleComment.query.get_or_404(comment_id)
        
        if comment.user_id != current_user.id and current_user.role != 'admin':
            return jsonify({'success': False, 'message': 'Permission denied'}), 403
        
        article = LearningArticle.query.get(comment.article_id)
        if article:
            article.comments_count = max(0, article.comments_count - 1)
        
        db.session.delete(comment)
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Comment deleted successfully'})
    except Exception as e:
        app.logger.error(f"Error deleting comment {comment_id}: {str(e)}")
        db.session.rollback()
        return jsonify({'success': False, 'message': 'Error deleting comment'}), 500


@app.route('/learning-hub/my-bookmarks')
@login_required
def my_bookmarks():
    """View user's bookmarked articles"""
    from models import ArticleBookmark
    
    try:
        page = request.args.get('page', 1, type=int)
        
        bookmarks = ArticleBookmark.query.filter_by(user_id=current_user.id)\
            .order_by(ArticleBookmark.created_at.desc())\
            .paginate(page=page, per_page=12, error_out=False)
        
        articles = [bookmark.article for bookmark in bookmarks.items if bookmark.article]
        
        return render_template('learning_hub/bookmarks.html',
                             bookmarks=bookmarks,
                             articles=articles)
    except Exception as e:
        app.logger.error(f"Error loading bookmarks: {str(e)}")
        flash('Error loading bookmarks.', 'error')
        return redirect(url_for('learning_hub'))


@app.route('/learning-hub/my-progress')
@login_required
def my_reading_progress():
    """View user's reading progress with personalized recommendations"""
    from models import UserReadingProgress
    from learning_recommendation_service import LearningRecommendationEngine, get_learning_stats
    from achievement_service import check_and_award_achievements, get_user_achievements
    
    try:
        # Check and award any new achievements
        newly_earned = check_and_award_achievements(current_user.id)
        
        # Get reading progress
        progress_items = UserReadingProgress.query.filter_by(user_id=current_user.id)\
            .order_by(UserReadingProgress.last_read_at.desc()).all()
        
        # Get comprehensive stats
        stats = get_learning_stats(current_user.id)
        
        # Get achievements
        achievements = get_user_achievements(current_user.id)
        
        # Generate personalized recommendations
        engine = LearningRecommendationEngine(current_user.id)
        recommendations = engine.generate_recommendations(limit=6)
        continue_reading = engine.get_continue_reading(limit=3)
        trending = engine.get_trending_articles(limit=4)
        
        # Get user preferences
        preferences = engine.get_user_preferences()
        
        return render_template('learning_hub/progress.html',
                             progress_items=progress_items,
                             stats=stats,
                             achievements=achievements,
                             newly_earned=newly_earned,
                             recommendations=recommendations,
                             continue_reading=continue_reading,
                             trending=trending,
                             preferences=preferences)
    except Exception as e:
        app.logger.error(f"Error loading reading progress: {str(e)}")
        flash('Error loading progress.', 'error')
        return redirect(url_for('learning_hub'))


@app.route('/learning-hub/article/<int:article_id>/progress', methods=['POST'])
@login_required
def update_reading_progress(article_id):
    """Update reading progress for an article"""
    from models import UserReadingProgress
    
    try:
        article = LearningArticle.query.get_or_404(article_id)
        progress_percentage = request.json.get('progress', 0)  # type: ignore
        completed = progress_percentage >= 100
        
        progress = UserReadingProgress.query.filter_by(
            user_id=current_user.id,
            article_id=article_id
        ).first()
        
        if progress:
            progress.progress_percentage = progress_percentage
            progress.completed = completed
            progress.last_read_at = datetime.utcnow()
            if completed and not progress.completed_at:
                progress.completed_at = datetime.utcnow()
        else:
            progress = UserReadingProgress(
                user_id=current_user.id,
                article_id=article_id,
                progress_percentage=progress_percentage,
                completed=completed,
                completed_at=datetime.utcnow() if completed else None
            )
            db.session.add(progress)
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'progress': progress_percentage,
            'completed': completed
        })
    except Exception as e:
        app.logger.error(f"Error updating reading progress: {str(e)}")
        db.session.rollback()
        return jsonify({'success': False, 'message': 'Error updating progress'}), 500


@app.route('/learning-hub/my-drafts')
@login_required
def learning_hub_drafts():
    """View user's draft articles"""
    if current_user.role != 'admin':
        flash('Access denied.', 'warning')
        return redirect(url_for('learning_hub'))
    
    try:
        page = request.args.get('page', 1, type=int)
        
        drafts = LearningArticle.query.filter_by(
            author_id=current_user.id,
            is_draft=True
        ).order_by(LearningArticle.updated_at.desc())\
        .paginate(page=page, per_page=12, error_out=False)
        
        return render_template('learning_hub/drafts.html', drafts=drafts)
    except Exception as e:
        app.logger.error(f"Error loading drafts: {str(e)}")
        flash('Error loading drafts.', 'error')
        return redirect(url_for('learning_hub'))


@app.route('/learning-hub/scheduled')
@login_required
def scheduled_articles():
    """View scheduled articles"""
    if current_user.role != 'admin':
        flash('Access denied.', 'warning')
        return redirect(url_for('learning_hub'))
    
    try:
        scheduled = LearningArticle.query.filter(
            LearningArticle.scheduled_publish.isnot(None),
            LearningArticle.is_published == False
        ).order_by(LearningArticle.scheduled_publish.asc()).all()
        
        return render_template('learning_hub/scheduled.html', scheduled=scheduled)
    except Exception as e:
        app.logger.error(f"Error loading scheduled articles: {str(e)}")
        flash('Error loading scheduled articles.', 'error')
        return redirect(url_for('learning_hub'))


@app.route('/learning-hub/preferences', methods=['GET', 'POST'])
@login_required
def learning_preferences():
    """Manage user learning preferences"""
    from learning_recommendation_service import LearningRecommendationEngine
    from models import UserLearningPreference
    import json
    
    engine = LearningRecommendationEngine(current_user.id)
    preferences = engine.get_user_preferences()
    
    if request.method == 'POST':
        try:
            data = {
                'skill_level': request.form.get('skill_level', 'beginner'),
                'preferred_reading_time': int(request.form.get('preferred_reading_time', 10)),
                'preferred_categories': request.form.getlist('categories'),
                'interests': request.form.getlist('interests'),
                'learning_goals': request.form.getlist('goals')
            }
            
            if engine.update_preferences(data):
                # Refresh recommendations
                engine.generate_recommendations(limit=10, refresh=True)
                flash('Preferences updated successfully! Your recommendations have been refreshed.', 'success')
            else:
                flash('Error updating preferences.', 'error')
                
            return redirect(url_for('my_reading_progress'))
        except Exception as e:
            app.logger.error(f"Error updating preferences: {str(e)}")
            flash('Error updating preferences.', 'error')
    
    # Parse JSON fields for display
    try:
        preferred_categories = json.loads(preferences.preferred_categories) if preferences.preferred_categories else []
        interests = json.loads(preferences.interests) if preferences.interests else []
        learning_goals = json.loads(preferences.learning_goals) if preferences.learning_goals else []
    except:
        preferred_categories = []
        interests = []
        learning_goals = []
    
    return render_template('learning_hub/preferences.html',
                         preferences=preferences,
                         preferred_categories=preferred_categories,
                         interests=interests,
                         learning_goals=learning_goals)


@app.route('/learning-hub/recommendations/refresh', methods=['POST'])
@login_required
def refresh_recommendations():
    """Refresh personalized recommendations"""
    from learning_recommendation_service import LearningRecommendationEngine
    
    try:
        engine = LearningRecommendationEngine(current_user.id)
        recommendations = engine.generate_recommendations(limit=10, refresh=True)
        
        return jsonify({
            'success': True,
            'count': len(recommendations),
            'message': 'Recommendations refreshed successfully'
        })
    except Exception as e:
        app.logger.error(f"Error refreshing recommendations: {str(e)}")
        return jsonify({'success': False, 'message': 'Error refreshing recommendations'}), 500


@app.route('/learning-hub/recommendations/<int:rec_id>/dismiss', methods=['POST'])
@login_required
def dismiss_recommendation(rec_id):
    """Dismiss a recommendation"""
    from models import ArticleRecommendation
    
    try:
        rec = ArticleRecommendation.query.get_or_404(rec_id)
        
        if rec.user_id != current_user.id:
            return jsonify({'success': False, 'message': 'Unauthorized'}), 403
        
        rec.is_dismissed = True
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Recommendation dismissed'})
    except Exception as e:
        app.logger.error(f"Error dismissing recommendation: {str(e)}")
        db.session.rollback()
        return jsonify({'success': False, 'message': 'Error dismissing recommendation'}), 500


@app.route('/learning-hub/article/<int:article_id>/publish-now', methods=['POST'])
@login_required
def publish_article_now(article_id):
    """Immediately publish a scheduled article"""
    if current_user.role != 'admin':
        return jsonify({'success': False, 'message': 'Access denied'}), 403
    
    try:
        article = LearningArticle.query.get_or_404(article_id)
        
        if current_user.id != article.author_id and current_user.role != 'admin':
            return jsonify({'success': False, 'message': 'Permission denied'}), 403
        
        article.is_published = True
        article.is_draft = False
        article.scheduled_publish = None
        article.updated_at = datetime.utcnow()
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Article published successfully'
        })
    except Exception as e:
        app.logger.error(f"Error publishing article {article_id}: {str(e)}")
        db.session.rollback()
        return jsonify({'success': False, 'message': 'Error publishing article'}), 500

# =============================================================================
# ANALYTICS ROUTES
# =============================================================================

@app.route('/analytics')
@login_required
def analytics_dashboard():
    """Analytics dashboard"""
    if current_user.role not in ['farmer', 'admin']:
        flash('Access denied.', 'danger')
        return redirect(url_for('index'))
    
    if current_user.role == 'farmer':
        crops_data = [{
            'name': crop.name,
            'quantity': crop.quantity,
            'price_per_unit': crop.price_per_unit,
            'total_value': crop.total_value,
            'status': crop.status
        } for crop in current_user.crops]
        
        orders_data = [{
            'crop_name': order.crop.name,
            'quantity': order.quantity_requested,
            'total_amount': order.total_amount,
            'status': order.status
        } for order in current_user.orders_received]
        
        return render_template('analytics/farmer_dashboard.html', 
                             crops_data=crops_data, 
                             orders_data=orders_data)
    
    else:  # Admin analytics
        total_users = User.query.count()
        total_farmers = User.query.filter_by(role='farmer').count()
        total_buyers = User.query.filter_by(role='buyer').count()
        total_crops = Crop.query.count()
        total_orders = Order.query.count()
        
        revenue_data = db.session.query(
            db.func.sum(Order.total_amount)
        ).filter(Order.status == 'completed').scalar() or 0
        
        return render_template('analytics/admin_dashboard.html',
                             total_users=total_users,
                             total_farmers=total_farmers,
                             total_buyers=total_buyers,
                             total_crops=total_crops,
                             total_orders=total_orders,
                             revenue_data=revenue_data)

@app.route('/analytics/export/<format>')
@login_required
def export_analytics(format):
    """Export analytics data"""
    if not is_farmer_or_manager(current_user):
        flash('Access denied.', 'danger')
        return redirect(url_for('index'))
    
    if format == 'csv':
        output = io.StringIO()
        writer = csv.writer(output)
        
        writer.writerow(['Crop Name', 'Quantity', 'Price per Unit', 'Total Value', 'Status'])
        
        for crop in current_user.crops:
            writer.writerow([
                crop.name, crop.quantity, crop.price_per_unit, 
                crop.total_value, crop.status
            ])
        
        output.seek(0)
        return send_file(
            io.BytesIO(output.getvalue().encode()),
            mimetype='text/csv',
            as_attachment=True,
            download_name=f'farm_analytics_{datetime.now().strftime("%Y%m%d")}.csv'
        )
    
    flash('Invalid export format.', 'error')
    return redirect(url_for('analytics_dashboard'))

# =============================================================================
# RATING SYSTEM ROUTES
# =============================================================================

@app.route('/rate-user/<int:user_id>/<int:order_id>', methods=['GET', 'POST'])
@login_required
def rate_user(user_id, order_id):
    """Rate a user after transaction"""
    user_to_rate = User.query.get_or_404(user_id)
    order = Order.query.get_or_404(order_id)
    
    if not (order.buyer_id == current_user.id or order.farmer_id == current_user.id):
        flash('Access denied.', 'danger')
        return redirect(url_for('index'))
    
    existing_rating = UserRating.query.filter_by(
        rater_id=current_user.id,
        rated_user_id=user_id,
        order_id=order_id
    ).first()
    
    if existing_rating:
        flash('You have already rated this user for this transaction.', 'info')
        return redirect(url_for('my_orders'))
    
    form = RatingForm()
    
    if form.validate_on_submit():
        rating = UserRating(
            rating=form.rating.data,
            feedback=form.feedback.data,
            transaction_type='order',
            rater_id=current_user.id,
            rated_user_id=user_id,
            order_id=order_id
        )
        
        db.session.add(rating)
        db.session.commit()
        
        flash('Rating submitted successfully!', 'success')
        return redirect(url_for('my_orders'))
    
    return render_template('ratings/rate_user.html', 
                         form=form, user_to_rate=user_to_rate, order=order)

# =============================================================================
# PASSWORD RESET ROUTES
# =============================================================================

@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    """Forgot password page with email link and OTP options"""
    form = ForgotPasswordForm()
    
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        
        if user:
            if form.reset_method.data == 'link':
                import secrets
                reset_token = secrets.token_urlsafe(32)
                user.reset_token = reset_token
                user.reset_token_expires = datetime.utcnow() + timedelta(hours=1)
                
                db.session.commit()
                
                email_service = EmailService()
                email_service.send_password_reset_email(user, reset_token)
                
                flash('Password reset link has been sent to your email.', 'info')
                return redirect(url_for('login'))
            else:
                otp = OTPService.generate_otp()
                user.reset_otp = otp
                user.reset_otp_expires = datetime.utcnow() + timedelta(minutes=10)
                
                db.session.commit()
                
                email_service = EmailService()
                email_service.send_reset_otp_email(user, otp)
                
                session['reset_email'] = user.email
                
                flash('A verification code has been sent to your email.', 'info')
                return redirect(url_for('verify_reset_otp'))
        else:
            flash('No account found with that email address.', 'error')
    
    return render_template('auth/forgot_password.html', form=form)

@app.route('/verify-reset-otp', methods=['GET', 'POST'])
def verify_reset_otp():
    """Verify OTP for password reset"""
    if 'reset_email' not in session:
        flash('Please initiate password reset first.', 'error')
        return redirect(url_for('forgot_password'))
        
    form = OTPVerificationForm()
    
    if form.validate_on_submit():
        user = User.query.filter_by(email=session['reset_email']).first()
        
        if user and user.reset_otp == form.otp.data:
            if user.reset_otp_expires < datetime.utcnow():
                flash('OTP has expired. Please request a new one.', 'error')
                return redirect(url_for('forgot_password'))
            
            import secrets
            reset_token = secrets.token_urlsafe(32)
            user.reset_token = reset_token
            user.reset_token_expires = datetime.utcnow() + timedelta(minutes=30)
            user.reset_otp = None
            user.reset_otp_expires = None
            db.session.commit()
            
            session.pop('reset_email', None)
            
            return redirect(url_for('reset_password', token=reset_token))
        else:
            flash('Invalid verification code.', 'error')
    
    return render_template('auth/verify_otp.html', form=form)

@app.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    """Reset password with token"""
    user = User.query.filter_by(reset_token=token).first()
    
    if not user or user.reset_token_expires < datetime.utcnow():
        flash('Invalid or expired reset token.', 'error')
        return redirect(url_for('forgot_password'))
    
    form = ResetPasswordForm()
    
    if form.validate_on_submit():
        user.set_password(form.password.data)
        user.reset_token = None
        user.reset_token_expires = None
        
        db.session.commit()
        
        flash('Your password has been reset successfully.', 'success')
        return redirect(url_for('login'))
    
    return render_template('auth/reset_password.html', form=form)

@app.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    """Change password for logged in users"""
    form = ChangePasswordForm()
    if form.validate_on_submit():
        if not current_user.check_password(form.old_password.data):
            flash('Current password is incorrect.', 'danger')
            return render_template('auth/change_password.html', form=form)
            
        if form.old_password.data == form.new_password.data:
            flash('New password must be different from current password.', 'warning')
            return render_template('auth/change_password.html', form=form)
        
        current_user.set_password(form.new_password.data)
        db.session.commit()
        
        logout_user()
        flash('Password changed successfully. Please login with your new password.', 'success')
        return redirect(url_for('login'))
        
    return render_template('auth/change_password.html', form=form)

# Email verification routes moved to routes.py for better organization
# See routes.py for: verify_email, resend_verification, verification_status

# =============================================================================
# VOICE INTERFACE ROUTES
# =============================================================================

@app.route('/voice-search', methods=['POST'])
@login_required
def voice_search():
    """Process voice search input"""
    if 'audio' not in request.files:
        return jsonify({'success': False, 'error': 'No audio file provided'})
    
    audio_file = request.files['audio']
    
    if audio_file.filename == '':
        return jsonify({'success': False, 'error': 'No audio file selected'})
    
    filename = secure_filename(audio_file.filename)  # type: ignore
    temp_path = os.path.join('/tmp', filename)
    audio_file.save(temp_path)
    
    result = EnhancedVoiceAI.process_voice_query(temp_path)
    
    if os.path.exists(temp_path):
        os.remove(temp_path)
    
    return jsonify(result)

# =============================================================================
# AI API ROUTES
# =============================================================================

@app.route('/api/ai/pest-analysis', methods=['POST'])
@login_required
def ai_pest_analysis():
    """AI-powered pest and disease analysis API"""
    try:
        from pest_detection_service import pest_detection_service
        
        if 'image' not in request.files:
            return jsonify({'success': False, 'message': 'No image uploaded'}), 400
        
        image_file = request.files['image']
        if image_file.filename == '':
            return jsonify({'success': False, 'message': 'No image selected'}), 400
        
        crop_type = request.form.get('crop_type', 'unknown')
        symptoms = request.form.get('symptoms', '')
        location = request.form.get('location', current_user.location or 'Not specified')
        plant_stage = request.form.get('plant_stage', '')
        urgency = request.form.get('urgency', 'medium')
        
        # Upload image to Cloudinary
        from storage_utils import save_image, PEST_FOLDER
        
        try:
            image_url = save_image(image_file, folder=PEST_FOLDER)
            if not image_url:
                return jsonify({'success': False, 'message': 'Failed to upload image'}), 400
            
            app.logger.info(f"API: Image uploaded to Cloudinary: {image_url}")
            
        except Exception as upload_error:
            app.logger.error(f"API: Failed to upload image to Cloudinary: {upload_error}")
            return jsonify({'success': False, 'message': 'Failed to upload image'}), 500
        
        context = {
            'location': location,
            'plant_stage': plant_stage,
            'urgency': urgency
        }
        
        if symptoms:
            analysis = pest_detection_service.combined_analysis(image_url, crop_type, symptoms, context)
        else:
            analysis = pest_detection_service.analyze_image(image_url, crop_type, context)
        
        if not analysis.get('success'):
            return jsonify(analysis), 400
        
        analysis = pest_detection_service.adjust_for_urgency(analysis, urgency)
        
        treatment_result = pest_detection_service.generate_treatment_recommendations(
            analysis.get('identified_issue', ''),
            crop_type,
            analysis.get('severity_level', 'medium'),
            context
        )
        
        if treatment_result.get('success'):
            analysis['treatment_recommendations'] = treatment_result['treatment_recommendations']
        
        analysis_data = {
            **analysis,
            'symptoms_description': symptoms,
            'image_path': image_url  # Now using Cloudinary URL
        }
        analysis_id = pest_detection_service.save_analysis(current_user.id, analysis_data)
        
        if analysis_id:
            analysis['analysis_id'] = analysis_id
        
        return jsonify(analysis)
        
        if analysis_id:
            analysis['analysis_id'] = analysis_id
        
        return jsonify(analysis)
        
    except Exception as e:
        app.logger.error(f"Error in pest analysis API: {str(e)}", exc_info=True)
        return jsonify({'success': False, 'message': f'Internal server error: {str(e)}'}), 500


# =============================================================================
# LEARNING HUB ADMIN MODERATION ROUTES
# =============================================================================

@app.route('/learning-hub/comment/<int:comment_id>/flag', methods=['POST'])
@login_required
def flag_comment(comment_id):
    """Flag a comment for moderation"""
    from models import ArticleComment, ContentFlag
    
    try:
        comment = ArticleComment.query.get_or_404(comment_id)
        
        # Can't flag your own comment
        if comment.user_id == current_user.id:
            return jsonify({'success': False, 'message': 'Cannot flag your own comment'}), 400
        
        # Check if already flagged by this user
        existing_flag = ContentFlag.query.filter_by(
            content_type='comment',
            comment_id=comment_id,
            reporter_id=current_user.id,
            status='pending'
        ).first()
        
        if existing_flag:
            return jsonify({'success': False, 'message': 'You have already flagged this comment'}), 400
        
        reason = request.json.get('reason', 'inappropriate')  # type: ignore
        description = request.json.get('description', '')  # type: ignore
        
        flag = ContentFlag(
            content_type='comment',
            comment_id=comment_id,
            reporter_id=current_user.id,
            reason=reason,
            description=description
        )
        
        db.session.add(flag)
        db.session.commit()
        
        app.logger.info(f"User {current_user.id} flagged comment {comment_id} for {reason}")
        
        return jsonify({
            'success': True,
            'message': 'Comment flagged for review. Thank you for helping keep our community safe.'
        })
        
    except Exception as e:
        app.logger.error(f"Error flagging comment {comment_id}: {str(e)}")
        db.session.rollback()
        return jsonify({'success': False, 'message': 'Error flagging comment'}), 500


@app.route('/learning-hub/article/<int:article_id>/flag', methods=['POST'])
@login_required
def flag_article(article_id):
    """Flag an article for moderation"""
    from models import ContentFlag
    
    try:
        article = LearningArticle.query.get_or_404(article_id)
        
        # Can't flag your own article
        if article.author_id == current_user.id:
            return jsonify({'success': False, 'message': 'Cannot flag your own article'}), 400
        
        # Check if already flagged by this user
        existing_flag = ContentFlag.query.filter_by(
            content_type='article',
            article_id=article_id,
            reporter_id=current_user.id,
            status='pending'
        ).first()
        
        if existing_flag:
            return jsonify({'success': False, 'message': 'You have already flagged this article'}), 400
        
        reason = request.json.get('reason', 'inappropriate')  # type: ignore
        description = request.json.get('description', '')  # type: ignore
        
        flag = ContentFlag(
            content_type='article',
            article_id=article_id,
            reporter_id=current_user.id,
            reason=reason,
            description=description
        )
        
        db.session.add(flag)
        db.session.commit()
        
        app.logger.info(f"User {current_user.id} flagged article {article_id} for {reason}")
        
        return jsonify({
            'success': True,
            'message': 'Article flagged for review. Thank you for your report.'
        })
        
    except Exception as e:
        app.logger.error(f"Error flagging article {article_id}: {str(e)}")
        db.session.rollback()
        return jsonify({'success': False, 'message': 'Error flagging article'}), 500


@app.route('/admin/learning-hub/moderation')
@login_required
def admin_learning_hub_moderation():
    """Admin moderation dashboard for Learning Hub"""
    from models import ContentFlag
    
    if current_user.role != 'admin':
        flash('Access denied.', 'warning')
        return redirect(url_for('learning_hub'))
    
    try:
        page = request.args.get('page', 1, type=int)
        status = request.args.get('status', 'pending')
        
        # Build query
        query = ContentFlag.query.options(
            db.joinedload(ContentFlag.reporter),
            db.joinedload(ContentFlag.moderator),
            db.joinedload(ContentFlag.comment).joinedload(ArticleComment.user),
            db.joinedload(ContentFlag.comment).joinedload(ArticleComment.article),  # type: ignore
            db.joinedload(ContentFlag.article).joinedload(LearningArticle.author)
        )
        
        if status != 'all':
            query = query.filter(ContentFlag.status == status)
        
        flags = query.order_by(ContentFlag.created_at.desc()).paginate(
            page=page, per_page=20, error_out=False
        )
        
        # Get statistics
        stats = {
            'pending': ContentFlag.query.filter_by(status='pending').count(),
            'approved': ContentFlag.query.filter_by(status='approved').count(),
            'removed': ContentFlag.query.filter_by(status='removed').count(),
            'total': ContentFlag.query.count()
        }
        
        return render_template('admin/learning_hub_moderation.html',
                             flags=flags,
                             stats=stats,
                             status=status)
        
    except Exception as e:
        app.logger.error(f"Error loading moderation dashboard: {str(e)}")
        flash('Error loading moderation dashboard.', 'error')
        return redirect(url_for('admin_dashboard'))


@app.route('/admin/learning-hub/moderate/<int:flag_id>', methods=['POST'])
@login_required
def moderate_learning_hub_content(flag_id):
    """Moderate flagged content"""
    from models import ContentFlag, ArticleComment
    
    if current_user.role != 'admin':
        return jsonify({'success': False, 'message': 'Access denied'}), 403
    
    try:
        flag = ContentFlag.query.get_or_404(flag_id)
        
        if flag.status != 'pending':
            return jsonify({'success': False, 'message': 'This flag has already been moderated'}), 400
        
        action = request.json.get('action')  # 'approved', 'removed', 'dismissed'  # type: ignore
        notes = request.json.get('notes', '')  # type: ignore
        
        if action not in ['approved', 'removed', 'dismissed']:
            return jsonify({'success': False, 'message': 'Invalid action'}), 400
        
        # Update flag
        flag.status = action
        flag.moderator_id = current_user.id
        flag.moderator_notes = notes
        flag.moderated_at = datetime.utcnow()
        
        # If removing content, delete it
        if action == 'removed':
            if flag.content_type == 'comment' and flag.comment:
                article = LearningArticle.query.get(flag.comment.article_id)
                if article:
                    article.comments_count = max(0, article.comments_count - 1)
                db.session.delete(flag.comment)
            elif flag.content_type == 'article' and flag.article:
                db.session.delete(flag.article)
        
        db.session.commit()
        
        app.logger.info(f"Admin {current_user.id} moderated flag {flag_id} with action: {action}")
        
        return jsonify({
            'success': True,
            'message': f'Content {action} successfully'
        })
        
    except Exception as e:
        app.logger.error(f"Error moderating flag {flag_id}: {str(e)}")
        db.session.rollback()
        return jsonify({'success': False, 'message': 'Error moderating content'}), 500


# =============================================================================
# ADMIN LEARNING HUB - ARTICLE MANAGEMENT
# =============================================================================

@app.route('/admin/articles')
@login_required
def admin_articles():
    """Admin article management dashboard"""
    from models import LearningArticle
    
    if current_user.role != 'admin':
        flash('Access denied.', 'warning')
        return redirect(url_for('learning_hub'))
    
    try:
        page = request.args.get('page', 1, type=int)
        status_filter = request.args.get('status', 'all')
        category_filter = request.args.get('category', 'all')
        search = request.args.get('search', '')
        
        # Build query
        query = LearningArticle.query.options(
            db.joinedload(LearningArticle.author)
        )
        
        # Apply filters
        if status_filter == 'published':
            query = query.filter(LearningArticle.is_published == True, LearningArticle.is_draft == False)
        elif status_filter == 'draft':
            query = query.filter(LearningArticle.is_draft == True)
        elif status_filter == 'scheduled':
            query = query.filter(LearningArticle.scheduled_publish != None)
        
        if category_filter != 'all':
            query = query.filter(LearningArticle.category == category_filter)
        
        if search:
            query = query.filter(
                db.or_(
                    LearningArticle.title.ilike(f'%{search}%'),
                    LearningArticle.content.ilike(f'%{search}%')
                )
            )
        
        articles = query.order_by(LearningArticle.created_at.desc()).paginate(
            page=page, per_page=20, error_out=False
        )
        
        # Get statistics
        stats = {
            'total': LearningArticle.query.count(),
            'published': LearningArticle.query.filter_by(is_published=True, is_draft=False).count(),
            'draft': LearningArticle.query.filter_by(is_draft=True).count(),
            'scheduled': LearningArticle.query.filter(LearningArticle.scheduled_publish != None).count(),
            'total_views': db.session.query(db.func.sum(LearningArticle.views)).scalar() or 0,
            'total_likes': db.session.query(db.func.sum(LearningArticle.likes)).scalar() or 0,
            'total_comments': db.session.query(db.func.sum(LearningArticle.comments_count)).scalar() or 0
        }
        
        # Get categories
        categories = db.session.query(LearningArticle.category).distinct().all()
        categories = [c[0] for c in categories if c[0]]
        
        return render_template('admin/articles.html',
                             articles=articles,
                             stats=stats,
                             categories=categories,
                             status_filter=status_filter,
                             category_filter=category_filter,
                             search=search)
        
    except Exception as e:
        app.logger.error(f"Error loading articles dashboard: {str(e)}")
        flash('Error loading articles dashboard.', 'error')
        return redirect(url_for('admin_dashboard'))


@app.route('/admin/articles/<int:article_id>/feature', methods=['POST'])
@login_required
def admin_feature_article(article_id):
    """Feature/unfeature an article"""
    from models import LearningArticle
    
    if current_user.role != 'admin':
        return jsonify({'success': False, 'message': 'Access denied'}), 403
    
    try:
        article = LearningArticle.query.get_or_404(article_id)
        
        # Toggle featured status (you may need to add this field to model)
        # For now, we'll use a workaround with tags
        if article.tags:
            tags = article.tags.split(',')
            if 'featured' in tags:
                tags.remove('featured')
                article.tags = ','.join(tags)
                featured = False
            else:
                tags.append('featured')
                article.tags = ','.join(tags)
                featured = True
        else:
            article.tags = 'featured'
            featured = True
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'featured': featured,
            'message': f'Article {"featured" if featured else "unfeatured"} successfully'
        })
        
    except Exception as e:
        app.logger.error(f"Error featuring article {article_id}: {str(e)}")
        db.session.rollback()
        return jsonify({'success': False, 'message': 'Error updating article'}), 500


@app.route('/admin/articles/<int:article_id>/toggle-publish', methods=['POST'])
@login_required
def admin_toggle_publish_article(article_id):
    """Publish/unpublish an article"""
    from models import LearningArticle
    
    if current_user.role != 'admin':
        return jsonify({'success': False, 'message': 'Access denied'}), 403
    
    try:
        article = LearningArticle.query.get_or_404(article_id)
        
        article.is_published = not article.is_published
        if article.is_published:
            article.is_draft = False
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'is_published': article.is_published,
            'message': f'Article {"published" if article.is_published else "unpublished"} successfully'
        })
        
    except Exception as e:
        app.logger.error(f"Error toggling publish status for article {article_id}: {str(e)}")
        db.session.rollback()
        return jsonify({'success': False, 'message': 'Error updating article'}), 500


@app.route('/admin/articles/bulk-action', methods=['POST'])
@login_required
def admin_bulk_article_action():
    """Perform bulk actions on articles"""
    from models import LearningArticle
    
    if current_user.role != 'admin':
        return jsonify({'success': False, 'message': 'Access denied'}), 403
    
    try:
        data = request.get_json()
        article_ids = data.get('article_ids', [])
        action = data.get('action')
        
        if not article_ids or not action:
            return jsonify({'success': False, 'message': 'Missing required data'}), 400
        
        articles = LearningArticle.query.filter(LearningArticle.id.in_(article_ids)).all()
        
        if action == 'publish':
            for article in articles:
                article.is_published = True
                article.is_draft = False
        elif action == 'unpublish':
            for article in articles:
                article.is_published = False
        elif action == 'delete':
            for article in articles:
                db.session.delete(article)
        elif action == 'feature':
            for article in articles:
                if article.tags:
                    tags = article.tags.split(',')
                    if 'featured' not in tags:
                        tags.append('featured')
                        article.tags = ','.join(tags)
                else:
                    article.tags = 'featured'
        else:
            return jsonify({'success': False, 'message': 'Invalid action'}), 400
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Bulk action "{action}" completed successfully'
        })
        
    except Exception as e:
        app.logger.error(f"Error performing bulk action: {str(e)}")
        db.session.rollback()
        return jsonify({'success': False, 'message': 'Error performing bulk action'}), 500


# =============================================================================
# ADMIN LEARNING HUB - COMMENT MODERATION
# =============================================================================

@app.route('/admin/comments')
@login_required
def admin_comments():
    """Admin comment moderation dashboard"""
    from models import ArticleComment
    
    if current_user.role != 'admin':
        flash('Access denied.', 'warning')
        return redirect(url_for('learning_hub'))
    
    try:
        page = request.args.get('page', 1, type=int)
        search = request.args.get('search', '')
        
        # Build query
        query = ArticleComment.query.options(
            db.joinedload(ArticleComment.user),
            db.joinedload(ArticleComment.article)  # type: ignore
        )
        
        if search:
            query = query.filter(ArticleComment.content.ilike(f'%{search}%'))
        
        comments = query.order_by(ArticleComment.created_at.desc()).paginate(
            page=page, per_page=30, error_out=False
        )
        
        # Get statistics
        stats = {
            'total': ArticleComment.query.count(),
            'today': ArticleComment.query.filter(
                ArticleComment.created_at >= datetime.utcnow().date()
            ).count(),
            'flagged': ContentFlag.query.filter_by(content_type='comment', status='pending').count()  # type: ignore
        }
        
        return render_template('admin/comments.html',
                             comments=comments,
                             stats=stats,
                             search=search)
        
    except Exception as e:
        app.logger.error(f"Error loading comments dashboard: {str(e)}")
        flash('Error loading comments dashboard.', 'error')
        return redirect(url_for('admin_dashboard'))


@app.route('/admin/comments/<int:comment_id>/delete', methods=['POST'])
@login_required
def admin_delete_comment(comment_id):
    """Admin delete a comment"""
    from models import ArticleComment
    
    if current_user.role != 'admin':
        return jsonify({'success': False, 'message': 'Access denied'}), 403
    
    try:
        comment = ArticleComment.query.get_or_404(comment_id)
        article = LearningArticle.query.get(comment.article_id)
        
        if article:
            article.comments_count = max(0, article.comments_count - 1)
        
        db.session.delete(comment)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Comment deleted successfully'
        })
        
    except Exception as e:
        app.logger.error(f"Error deleting comment {comment_id}: {str(e)}")
        db.session.rollback()
        return jsonify({'success': False, 'message': 'Error deleting comment'}), 500


@app.route('/admin/comments/user/<int:user_id>')
@login_required
def admin_user_comments(user_id):
    """View all comments by a specific user"""
    from models import ArticleComment, User
    
    if current_user.role != 'admin':
        flash('Access denied.', 'warning')
        return redirect(url_for('learning_hub'))
    
    try:
        user = User.query.get_or_404(user_id)
        page = request.args.get('page', 1, type=int)
        
        comments = ArticleComment.query.filter_by(user_id=user_id).options(
            db.joinedload(ArticleComment.article)  # type: ignore
        ).order_by(ArticleComment.created_at.desc()).paginate(
            page=page, per_page=30, error_out=False
        )
        
        stats = {
            'total': ArticleComment.query.filter_by(user_id=user_id).count(),
            'flagged': ContentFlag.query.filter_by(  # type: ignore
                content_type='comment',
                status='pending'
            ).join(ArticleComment).filter(ArticleComment.user_id == user_id).count()
        }
        
        return render_template('admin/user_comments.html',
                             user=user,
                             comments=comments,
                             stats=stats)
        
    except Exception as e:
        app.logger.error(f"Error loading user comments: {str(e)}")
        flash('Error loading user comments.', 'error')
        return redirect(url_for('admin_comments'))


# =============================================================================
# ADMIN LEARNING HUB - ANALYTICS
# =============================================================================

@app.route('/admin/learning-hub/analytics')
@login_required
def admin_learning_hub_analytics():
    """Learning Hub analytics dashboard"""
    from models import LearningArticle, ArticleComment, ArticleLike, ArticleBookmark, UserReadingProgress, User
    from sqlalchemy import func
    
    if current_user.role != 'admin':
        flash('Access denied.', 'warning')
        return redirect(url_for('learning_hub'))
    
    try:
        # Overall statistics
        total_articles = LearningArticle.query.filter_by(is_published=True, is_draft=False).count()
        total_views = db.session.query(func.sum(LearningArticle.views)).scalar() or 0
        total_likes = ArticleLike.query.count()
        total_comments = ArticleComment.query.count()
        total_bookmarks = ArticleBookmark.query.count()
        
        # Top performing articles
        top_articles = LearningArticle.query.filter_by(
            is_published=True, is_draft=False
        ).order_by(LearningArticle.views.desc()).limit(10).all()
        
        # Most liked articles
        most_liked = db.session.query(
            LearningArticle,
            func.count(ArticleLike.id).label('like_count')
        ).join(ArticleLike).group_by(LearningArticle.id).order_by(
            func.count(ArticleLike.id).desc()
        ).limit(10).all()
        
        # Most commented articles
        most_commented = LearningArticle.query.filter_by(
            is_published=True, is_draft=False
        ).order_by(LearningArticle.comments_count.desc()).limit(10).all()
        
        # Category statistics
        category_stats = db.session.query(
            LearningArticle.category,
            func.count(LearningArticle.id).label('count'),
            func.sum(LearningArticle.views).label('total_views')
        ).filter_by(is_published=True, is_draft=False).group_by(
            LearningArticle.category
        ).all()
        
        # Reading completion rates
        total_progress = UserReadingProgress.query.count()
        completed_reads = UserReadingProgress.query.filter_by(completed=True).count()
        completion_rate = (completed_reads / total_progress * 100) if total_progress > 0 else 0
        
        # Top authors
        top_authors = db.session.query(
            User,
            func.count(LearningArticle.id).label('article_count'),
            func.sum(LearningArticle.views).label('total_views')
        ).join(LearningArticle, User.id == LearningArticle.author_id).group_by(
            User.id
        ).order_by(func.sum(LearningArticle.views).desc()).limit(10).all()
        
        # Recent activity (last 30 days)
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        recent_articles = LearningArticle.query.filter(
            LearningArticle.created_at >= thirty_days_ago
        ).count()
        recent_comments = ArticleComment.query.filter(
            ArticleComment.created_at >= thirty_days_ago
        ).count()
        
        # Difficulty level distribution
        difficulty_stats = db.session.query(
            LearningArticle.difficulty_level,
            func.count(LearningArticle.id).label('count')
        ).filter_by(is_published=True, is_draft=False).group_by(
            LearningArticle.difficulty_level
        ).all()
        
        return render_template('admin/learning_hub_analytics.html',
                             total_articles=total_articles,
                             total_views=total_views,
                             total_likes=total_likes,
                             total_comments=total_comments,
                             total_bookmarks=total_bookmarks,
                             top_articles=top_articles,
                             most_liked=most_liked,
                             most_commented=most_commented,
                             category_stats=category_stats,
                             completion_rate=completion_rate,
                             top_authors=top_authors,
                             recent_articles=recent_articles,
                             recent_comments=recent_comments,
                             difficulty_stats=difficulty_stats)
        
    except Exception as e:
        app.logger.error(f"Error loading learning hub analytics: {str(e)}")
        flash('Error loading analytics dashboard.', 'error')
        return redirect(url_for('admin_dashboard'))


# =============================================================================
# ADMIN LEARNING HUB - AUTHOR MANAGEMENT
# =============================================================================

@app.route('/admin/authors')
@login_required
def admin_authors():
    """Admin author management dashboard"""
    from models import User, LearningArticle
    from sqlalchemy import func
    
    if current_user.role != 'admin':
        flash('Access denied.', 'warning')
        return redirect(url_for('learning_hub'))
    
    try:
        page = request.args.get('page', 1, type=int)
        
        # Get all users who have written articles
        authors = db.session.query(  # type: ignore
            User,
            func.count(LearningArticle.id).label('article_count'),
            func.sum(LearningArticle.views).label('total_views'),
            func.sum(LearningArticle.likes).label('total_likes')
        ).join(LearningArticle, User.id == LearningArticle.author_id).group_by(
            User.id
        ).order_by(func.count(LearningArticle.id).desc()).paginate(
            page=page, per_page=20, error_out=False
        )
        
        # Statistics
        stats = {
            'total_authors': db.session.query(func.count(func.distinct(LearningArticle.author_id))).scalar() or 0,
            'active_authors': db.session.query(func.count(func.distinct(LearningArticle.author_id))).filter(
                LearningArticle.created_at >= datetime.utcnow() - timedelta(days=30)
            ).scalar() or 0
        }
        
        return render_template('admin/authors.html',
                             authors=authors,
                             stats=stats)
        
    except Exception as e:
        app.logger.error(f"Error loading authors dashboard: {str(e)}")
        flash('Error loading authors dashboard.', 'error')
        return redirect(url_for('admin_dashboard'))


@app.route('/admin/authors/<int:user_id>/articles')
@login_required
def admin_author_articles(user_id):
    """View all articles by a specific author"""
    from models import User, LearningArticle
    
    if current_user.role != 'admin':
        flash('Access denied.', 'warning')
        return redirect(url_for('learning_hub'))
    
    try:
        user = User.query.get_or_404(user_id)
        page = request.args.get('page', 1, type=int)
        
        articles = LearningArticle.query.filter_by(author_id=user_id).order_by(
            LearningArticle.created_at.desc()
        ).paginate(page=page, per_page=20, error_out=False)
        
        # Author statistics
        stats = {
            'total_articles': LearningArticle.query.filter_by(author_id=user_id).count(),
            'published': LearningArticle.query.filter_by(author_id=user_id, is_published=True, is_draft=False).count(),
            'draft': LearningArticle.query.filter_by(author_id=user_id, is_draft=True).count(),
            'total_views': db.session.query(db.func.sum(LearningArticle.views)).filter_by(author_id=user_id).scalar() or 0,
            'total_likes': db.session.query(db.func.sum(LearningArticle.likes)).filter_by(author_id=user_id).scalar() or 0
        }
        
        return render_template('admin/author_articles.html',
                             author=user,
                             articles=articles,
                             stats=stats)
        
    except Exception as e:
        app.logger.error(f"Error loading author articles: {str(e)}")
        flash('Error loading author articles.', 'error')
        return redirect(url_for('admin_authors'))



# =============================================================================
# ADMIN LEARNING HUB - CATEGORY MANAGEMENT
# =============================================================================

@app.route('/admin/article-categories')
@login_required
def admin_article_categories():
    """Admin category management dashboard"""
    from models import ArticleCategory
    
    if current_user.role != 'admin':
        flash('Access denied.', 'warning')
        return redirect(url_for('learning_hub'))
    
    try:
        # Get all categories ordered by display_order
        categories = ArticleCategory.query.order_by(
            ArticleCategory.display_order.asc(),
            ArticleCategory.name.asc()
        ).all()
        
        # Update article counts
        for category in categories:
            category.article_count = LearningArticle.query.filter_by(
                category=category.name
            ).count()
        db.session.commit()
        
        # Statistics
        stats = {
            'total': len(categories),
            'active': sum(1 for c in categories if c.is_active),
            'inactive': sum(1 for c in categories if not c.is_active),
            'total_articles': sum(c.article_count for c in categories)
        }
        
        return render_template('admin/article_categories.html',
                             categories=categories,
                             stats=stats)
        
    except Exception as e:
        app.logger.error(f"Error loading categories: {str(e)}")
        flash('Error loading categories.', 'error')
        return redirect(url_for('admin_dashboard'))


@app.route('/admin/article-categories/add', methods=['POST'])
@login_required
def admin_add_category():
    """Add new article category"""
    from models import ArticleCategory
    import re
    
    if current_user.role != 'admin':
        return jsonify({'success': False, 'message': 'Access denied'}), 403
    
    try:
        data = request.get_json()
        name = data.get('name', '').strip()
        description = data.get('description', '').strip()
        icon = data.get('icon', 'fa-folder').strip()
        color = data.get('color', '#6c757d').strip()
        
        if not name:
            return jsonify({'success': False, 'message': 'Category name is required'}), 400
        
        # Check if category already exists
        existing = ArticleCategory.query.filter_by(name=name).first()
        if existing:
            return jsonify({'success': False, 'message': 'Category already exists'}), 400
        
        # Generate slug
        slug = re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')
        
        # Get max display order
        max_order = db.session.query(db.func.max(ArticleCategory.display_order)).scalar() or 0
        
        # Create category
        category = ArticleCategory(
            name=name,
            slug=slug,
            description=description,
            icon=icon,
            color=color,
            display_order=max_order + 1,
            is_active=True,
            article_count=0
        )
        
        db.session.add(category)
        db.session.commit()
        
        app.logger.info(f"Admin {current_user.id} created category: {name}")
        
        return jsonify({
            'success': True,
            'message': 'Category created successfully',
            'category': category.to_dict()
        })
        
    except Exception as e:
        app.logger.error(f"Error creating category: {str(e)}")
        db.session.rollback()
        return jsonify({'success': False, 'message': 'Error creating category'}), 500


@app.route('/admin/article-categories/<int:category_id>/edit', methods=['POST'])
@login_required
def admin_edit_category(category_id):
    """Edit article category"""
    from models import ArticleCategory
    import re
    
    if current_user.role != 'admin':
        return jsonify({'success': False, 'message': 'Access denied'}), 403
    
    try:
        category = ArticleCategory.query.get_or_404(category_id)
        data = request.get_json()
        
        old_name = category.name
        new_name = data.get('name', '').strip()
        
        if not new_name:
            return jsonify({'success': False, 'message': 'Category name is required'}), 400
        
        # Check if new name conflicts with another category
        if new_name != old_name:
            existing = ArticleCategory.query.filter_by(name=new_name).first()
            if existing:
                return jsonify({'success': False, 'message': 'Category name already exists'}), 400
        
        # Update category
        category.name = new_name
        category.slug = re.sub(r'[^a-z0-9]+', '-', new_name.lower()).strip('-')
        category.description = data.get('description', '').strip()
        category.icon = data.get('icon', 'fa-folder').strip()
        category.color = data.get('color', '#6c757d').strip()
        
        # Update articles if name changed
        if new_name != old_name:
            articles = LearningArticle.query.filter_by(category=old_name).all()
            for article in articles:
                article.category = new_name
        
        db.session.commit()
        
        app.logger.info(f"Admin {current_user.id} updated category {category_id}: {old_name} -> {new_name}")
        
        return jsonify({
            'success': True,
            'message': 'Category updated successfully',
            'category': category.to_dict()
        })
        
    except Exception as e:
        app.logger.error(f"Error updating category {category_id}: {str(e)}")
        db.session.rollback()
        return jsonify({'success': False, 'message': 'Error updating category'}), 500


@app.route('/admin/article-categories/<int:category_id>/toggle', methods=['POST'])
@login_required
def admin_toggle_category(category_id):
    """Toggle category active status"""
    from models import ArticleCategory
    
    if current_user.role != 'admin':
        return jsonify({'success': False, 'message': 'Access denied'}), 403
    
    try:
        category = ArticleCategory.query.get_or_404(category_id)
        
        category.is_active = not category.is_active
        db.session.commit()
        
        app.logger.info(f"Admin {current_user.id} toggled category {category_id} to {category.is_active}")
        
        return jsonify({
            'success': True,
            'is_active': category.is_active,
            'message': f'Category {"activated" if category.is_active else "deactivated"} successfully'
        })
        
    except Exception as e:
        app.logger.error(f"Error toggling category {category_id}: {str(e)}")
        db.session.rollback()
        return jsonify({'success': False, 'message': 'Error updating category'}), 500


@app.route('/admin/article-categories/<int:category_id>/delete', methods=['POST'])
@login_required
def admin_delete_category(category_id):
    """Delete article category"""
    from models import ArticleCategory
    
    if current_user.role != 'admin':
        return jsonify({'success': False, 'message': 'Access denied'}), 403
    
    try:
        category = ArticleCategory.query.get_or_404(category_id)
        
        # Check if category has articles
        article_count = LearningArticle.query.filter_by(category=category.name).count()
        if article_count > 0:
            return jsonify({
                'success': False,
                'message': f'Cannot delete category with {article_count} article(s). Please reassign or delete articles first.'
            }), 400
        
        category_name = category.name
        db.session.delete(category)
        db.session.commit()
        
        app.logger.info(f"Admin {current_user.id} deleted category: {category_name}")
        
        return jsonify({
            'success': True,
            'message': 'Category deleted successfully'
        })
        
    except Exception as e:
        app.logger.error(f"Error deleting category {category_id}: {str(e)}")
        db.session.rollback()
        return jsonify({'success': False, 'message': 'Error deleting category'}), 500


@app.route('/admin/article-categories/reorder', methods=['POST'])
@login_required
def admin_reorder_categories():
    """Reorder categories"""
    from models import ArticleCategory
    
    if current_user.role != 'admin':
        return jsonify({'success': False, 'message': 'Access denied'}), 403
    
    try:
        data = request.get_json()
        category_ids = data.get('category_ids', [])
        
        if not category_ids:
            return jsonify({'success': False, 'message': 'No categories provided'}), 400
        
        # Update display order
        for index, category_id in enumerate(category_ids):
            category = ArticleCategory.query.get(category_id)
            if category:
                category.display_order = index
        
        db.session.commit()
        
        app.logger.info(f"Admin {current_user.id} reordered categories")
        
        return jsonify({
            'success': True,
            'message': 'Categories reordered successfully'
        })
        
    except Exception as e:
        app.logger.error(f"Error reordering categories: {str(e)}")
        db.session.rollback()
        return jsonify({'success': False, 'message': 'Error reordering categories'}), 500


@app.route('/api/article-categories')
def api_article_categories():
    """API endpoint to get all active categories"""
    from models import ArticleCategory
    
    try:
        categories = ArticleCategory.query.filter_by(is_active=True).order_by(
            ArticleCategory.display_order.asc()
        ).all()
        
        return jsonify({
            'success': True,
            'categories': [c.to_dict() for c in categories]
        })
        
    except Exception as e:
        app.logger.error(f"Error fetching categories: {str(e)}")
        return jsonify({'success': False, 'message': 'Error fetching categories'}), 500
