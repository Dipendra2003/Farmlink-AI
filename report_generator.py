"""
FarmLink AI - PDF Report Generator for Pest Detection
Generates comprehensive PDF reports with analysis results and recommendations
"""

import os
from datetime import datetime
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.colors import HexColor, black, white
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as RLImage
from reportlab.platypus import PageBreak, KeepTogether
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT, TA_JUSTIFY
from reportlab.graphics.shapes import Drawing, Rect
from reportlab.graphics.charts.piecharts import Pie
from reportlab.graphics import renderPDF
from reportlab.lib import colors
from PIL import Image as PILImage
import json
import logging
import io
import qrcode
from flask import url_for

logger = logging.getLogger(__name__)

class PestDetectionPDFGenerator:
    """Generate comprehensive PDF reports for pest detection analysis"""
    
    def __init__(self):
        self.styles = getSampleStyleSheet()
        self._style_cache = {}  # Cache for common report elements
        self._image_cache = {}  # Cache for resized images
        self.setup_custom_styles()
    
    def setup_custom_styles(self):
        """Setup custom styles for the PDF"""
        # Modern Title style with larger font
        self.styles.add(ParagraphStyle(
            name='CustomTitle',
            parent=self.styles['Heading1'],
            fontSize=28,
            textColor=colors.white,
            spaceAfter=0,
            spaceBefore=0,
            alignment=TA_CENTER,
            fontName='Helvetica-Bold',
            leading=32
        ))
        
        # Subtitle style for report type
        self.styles.add(ParagraphStyle(
            name='SubTitle',
            parent=self.styles['Heading2'],
            fontSize=18,
            textColor=HexColor('#2E7D32'),
            spaceAfter=15,
            spaceBefore=15,
            fontName='Helvetica-Bold',
            alignment=TA_LEFT
        ))
        
        # Section header style with modern look
        self.styles.add(ParagraphStyle(
            name='SectionHeader',
            parent=self.styles['Heading3'],
            fontSize=13,
            textColor=HexColor('#2E7D32'),
            spaceAfter=10,
            spaceBefore=15,
            fontName='Helvetica-Bold'
        ))
        
        # Alert style for urgent issues
        self.styles.add(ParagraphStyle(
            name='AlertText',
            parent=self.styles['Normal'],
            fontSize=14,
            textColor=HexColor('#D32F2F'),
            fontName='Helvetica-Bold',
            spaceAfter=10,
            leading=18
        ))
        
        # Success style for healthy plants
        self.styles.add(ParagraphStyle(
            name='SuccessText',
            parent=self.styles['Normal'],
            fontSize=14,
            textColor=HexColor('#2E7D32'),
            fontName='Helvetica-Bold',
            spaceAfter=10,
            leading=18
        ))
        
        # Warning style for medium issues
        self.styles.add(ParagraphStyle(
            name='WarningText',
            parent=self.styles['Normal'],
            fontSize=14,
            textColor=HexColor('#F57C00'),
            fontName='Helvetica-Bold',
            spaceAfter=10,
            leading=18
        ))
        
        # Info text style
        self.styles.add(ParagraphStyle(
            name='InfoText',
            parent=self.styles['Normal'],
            fontSize=10,
            textColor=HexColor('#424242'),
            spaceAfter=8,
            leading=14
        ))
        
        # Cache common table styles for reuse
        self._cache_table_styles()
    
    def _cache_table_styles(self):
        """Cache common table styles for performance"""
        # Info table style
        self._style_cache['info_table'] = TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('TEXTCOLOR', (0, 0), (0, -1), HexColor('#2E7D32')),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ])
        
        # Results table style
        self._style_cache['results_table'] = TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), HexColor('#E8F5E8')),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('TEXTCOLOR', (0, 0), (0, -1), HexColor('#2E7D32')),
            ('GRID', (0, 0), (-1, -1), 1, colors.grey),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ])
        
        # Treatment table style (organic)
        self._style_cache['organic_table'] = TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), HexColor('#4CAF50')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 1, colors.grey),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 4),
            ('RIGHTPADDING', (0, 0), (-1, -1), 4),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ])
        
        # Treatment table style (chemical)
        self._style_cache['chemical_table'] = TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), HexColor('#FF9800')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 1, colors.grey),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 4),
            ('RIGHTPADDING', (0, 0), (-1, -1), 4),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ])
    
    def generate_report(self, analysis_data, user_data, output_path, timeout=5):
        """
        Generate complete PDF report for pest disease analysis
        
        Args:
            analysis_data: PestDiseaseAnalysis model instance or dict with analysis results
            user_data: User information dict with name, location, contact
            output_path: Path to save the PDF
            timeout: Maximum time in seconds for PDF generation (default: 5)
        """
        import signal
        
        def timeout_handler(signum, frame):
            raise TimeoutError("PDF generation exceeded timeout limit")
        
        try:
            # Set timeout alarm (only on Unix-like systems)
            if hasattr(signal, 'SIGALRM'):
                signal.signal(signal.SIGALRM, timeout_handler)
                signal.alarm(timeout)
            
            start_time = datetime.now()
            
            # Create PDF document
            doc = SimpleDocTemplate(
                output_path,
                pagesize=A4,
                rightMargin=72,
                leftMargin=72,
                topMargin=72,
                bottomMargin=18
            )
            
            # Build story (content)
            story = []
            
            # Add header with farmer details
            self._add_header(story, analysis_data, user_data)
            
            # Add crop information section
            self._add_crop_information(story, analysis_data)
            
            # Add analysis input section
            self._add_analysis_input(story, analysis_data)
            
            # Add uploaded image if available
            self._add_image_section(story, analysis_data)
            
            # Add identification results section
            self._add_identification_results(story, analysis_data)
            
            # Add treatment recommendations section
            self._add_treatment_recommendations(story, analysis_data)
            
            # Add preventive measures section
            self._add_preventive_measures(story, analysis_data)
            
            # Add alternative diagnoses section
            self._add_alternative_diagnoses(story, analysis_data)
            
            # Add regional context and government schemes
            self._add_regional_context(story, analysis_data)
            
            # Add footer with disclaimer
            self._add_footer(story)
            
            # Build PDF
            doc.build(story)
            
            # Cancel alarm
            if hasattr(signal, 'SIGALRM'):
                signal.alarm(0)
            
            elapsed_time = (datetime.now() - start_time).total_seconds()
            logger.info(f"PDF report generated successfully in {elapsed_time:.2f}s: {output_path}")
            return True
            
        except TimeoutError as e:
            logger.error(f"PDF generation timeout: {str(e)}")
            if hasattr(signal, 'SIGALRM'):
                signal.alarm(0)
            return False
        except Exception as e:
            logger.error(f"Error generating PDF report: {str(e)}")
            if hasattr(signal, 'SIGALRM'):
                signal.alarm(0)
            return False
    
    def _add_header(self, story, analysis_data, user_data):
        """Add modern header section with title and farmer details"""
        # Modern header with gradient-like background
        header_data = [[
            Paragraph("FarmLink AI", self.styles['CustomTitle']),
            Paragraph("<font color='white' size=12>Pest & Disease Analysis Report</font>", self.styles['Normal'])
        ]]
        
        header_table = Table(header_data, colWidths=[4*inch, 3*inch], rowHeights=[70])
        header_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), HexColor('#2E7D32')),
            ('ALIGN', (0, 0), (0, 0), 'LEFT'),
            ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 25),
            ('RIGHTPADDING', (0, 0), (-1, -1), 25),
            ('TOPPADDING', (0, 0), (-1, -1), 20),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 20),
        ]))
        
        story.append(header_table)
        story.append(Spacer(1, 25))
        
        # Extract analysis ID and generate report number
        analysis_id = None
        if hasattr(analysis_data, 'id'):
            analysis_id = analysis_data.id
        elif isinstance(analysis_data, dict):
            analysis_id = analysis_data.get('id')
        
        # Generate professional report number
        if analysis_id and analysis_id != 'N/A':
            report_number = f"PDA-{datetime.now().strftime('%Y%m%d')}-{analysis_id:05d}"
        else:
            # Fallback to timestamp-based ID if no analysis ID available
            report_number = f"PDA-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        
        # Report info banner
        report_info_data = [[
            Paragraph(f"<font size=13 color='#2E7D32'><b>Report ID: {report_number}</b></font>", self.styles['Normal']),
            Paragraph(f"<font size=10><b>Generated:</b> {datetime.now().strftime('%B %d, %Y at %I:%M %p')}</font>", self.styles['Normal'])
        ]]
        
        report_info_table = Table(report_info_data, colWidths=[4*inch, 3*inch])
        report_info_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), HexColor('#E8F5E9')),
            ('ALIGN', (0, 0), (0, 0), 'LEFT'),
            ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 15),
            ('RIGHTPADDING', (0, 0), (-1, -1), 15),
            ('TOPPADDING', (0, 0), (-1, -1), 12),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
            ('BOX', (0, 0), (-1, -1), 2, HexColor('#4CAF50')),
        ]))
        
        story.append(report_info_table)
        story.append(Spacer(1, 25))
        
        # Farmer details section with icon
        story.append(Paragraph("👨‍🌾 Farmer Details", self.styles['SubTitle']))
        story.append(Spacer(1, 10))
        
        farmer_info = [
            [
                Paragraph("<font color='white' size=10><b>Farmer Name</b></font>", self.styles['Normal']),
                Paragraph("<font color='white' size=10><b>Location</b></font>", self.styles['Normal']),
                Paragraph("<font color='white' size=10><b>Contact</b></font>", self.styles['Normal'])
            ],
            [
                Paragraph(f"<font size=10>{user_data.get('full_name', user_data.get('name', 'N/A'))}</font>", self.styles['Normal']),
                Paragraph(f"<font size=10>{user_data.get('location', 'Not specified')}</font>", self.styles['Normal']),
                Paragraph(f"<font size=10>{user_data.get('contact', user_data.get('phone', 'Not provided'))}</font>", self.styles['Normal'])
            ]
        ]
        
        farmer_table = Table(farmer_info, colWidths=[2.3*inch, 2.3*inch, 2.4*inch])
        farmer_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), HexColor('#4CAF50')),
            ('BACKGROUND', (0, 1), (-1, 1), HexColor('#F1F8E9')),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 10),
            ('RIGHTPADDING', (0, 0), (-1, -1), 10),
            ('TOPPADDING', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
            ('BOX', (0, 0), (-1, -1), 2, HexColor('#4CAF50')),
            ('LINEBELOW', (0, 0), (-1, 0), 2, HexColor('#2E7D32')),
            ('LINEBETWEEN', (0, 0), (-1, -1), 1, HexColor('#C8E6C9')),
        ]))
        
        story.append(farmer_table)
        story.append(Spacer(1, 25))
    
    def _add_crop_information(self, story, analysis_data):
        """Add modern crop information section"""
        story.append(Paragraph("🌾 Crop Information", self.styles['SubTitle']))
        story.append(Spacer(1, 10))
        
        # Extract crop data
        crop_type = analysis_data.crop_type if hasattr(analysis_data, 'crop_type') else analysis_data.get('crop_type', 'N/A')
        plant_stage = analysis_data.plant_stage if hasattr(analysis_data, 'plant_stage') else analysis_data.get('plant_stage', 'Not specified')
        location = analysis_data.location if hasattr(analysis_data, 'location') else analysis_data.get('location', 'Not specified')
        
        # Get crop name from relationship if available
        crop_name = 'N/A'
        if hasattr(analysis_data, 'crop') and analysis_data.crop:
            crop_name = analysis_data.crop.crop_name if hasattr(analysis_data.crop, 'crop_name') else 'N/A'
        
        crop_info = [
            [
                Paragraph("<font color='white' size=10><b>Crop Type</b></font>", self.styles['Normal']),
                Paragraph("<font color='white' size=10><b>Crop Name</b></font>", self.styles['Normal']),
                Paragraph("<font color='white' size=10><b>Plant Stage</b></font>", self.styles['Normal']),
                Paragraph("<font color='white' size=10><b>Location</b></font>", self.styles['Normal'])
            ],
            [
                Paragraph(f"<font size=10>{crop_type.title() if crop_type else 'N/A'}</font>", self.styles['Normal']),
                Paragraph(f"<font size=10>{crop_name}</font>", self.styles['Normal']),
                Paragraph(f"<font size=10>{plant_stage.title() if plant_stage else 'Not specified'}</font>", self.styles['Normal']),
                Paragraph(f"<font size=10>{location if location else 'Not specified'}</font>", self.styles['Normal'])
            ]
        ]
        
        crop_table = Table(crop_info, colWidths=[1.75*inch, 1.75*inch, 1.75*inch, 1.75*inch])
        crop_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), HexColor('#4CAF50')),
            ('BACKGROUND', (0, 1), (-1, 1), HexColor('#F1F8E9')),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
            ('RIGHTPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
            ('BOX', (0, 0), (-1, -1), 2, HexColor('#4CAF50')),
            ('LINEBELOW', (0, 0), (-1, 0), 2, HexColor('#2E7D32')),
            ('LINEBETWEEN', (0, 0), (-1, -1), 1, HexColor('#C8E6C9')),
        ]))
        
        story.append(crop_table)
        story.append(Spacer(1, 25))
    
    def _add_analysis_input(self, story, analysis_data):
        """Add modern analysis input section"""
        story.append(Paragraph("📊 Analysis Details", self.styles['SubTitle']))
        story.append(Spacer(1, 10))
        
        # Extract input data
        symptoms = analysis_data.symptoms_description if hasattr(analysis_data, 'symptoms_description') else analysis_data.get('symptoms_description', 'Not provided')
        urgency = analysis_data.urgency_level if hasattr(analysis_data, 'urgency_level') else analysis_data.get('urgency_level', 'Not specified')
        analysis_date = analysis_data.created_at if hasattr(analysis_data, 'created_at') else analysis_data.get('created_at', datetime.now())
        analysis_mode = analysis_data.analysis_mode if hasattr(analysis_data, 'analysis_mode') else analysis_data.get('analysis_mode', 'N/A')
        
        # Determine urgency color
        urgency_color = '#4CAF50'  # Low - Green
        if urgency and urgency.lower() in ['high', 'critical']:
            urgency_color = '#D32F2F'  # Red
        elif urgency and urgency.lower() == 'medium':
            urgency_color = '#F57C00'  # Orange
        
        input_info = [
            [
                Paragraph("<font color='white' size=10><b>Analysis Date</b></font>", self.styles['Normal']),
                Paragraph("<font color='white' size=10><b>Analysis Mode</b></font>", self.styles['Normal']),
                Paragraph("<font color='white' size=10><b>Urgency Level</b></font>", self.styles['Normal'])
            ],
            [
                Paragraph(f"<font size=9>{analysis_date.strftime('%B %d, %Y at %I:%M %p') if isinstance(analysis_date, datetime) else str(analysis_date)}</font>", self.styles['Normal']),
                Paragraph(f"<font size=9>{analysis_mode.title() if analysis_mode else 'N/A'}</font>", self.styles['Normal']),
                Paragraph(f"<font size=9 color='{urgency_color}'><b>{urgency.upper() if urgency else 'NOT SPECIFIED'}</b></font>", self.styles['Normal'])
            ]
        ]
        
        input_table = Table(input_info, colWidths=[2.3*inch, 2.3*inch, 2.4*inch])
        input_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), HexColor('#4CAF50')),
            ('BACKGROUND', (0, 1), (-1, 1), HexColor('#F1F8E9')),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
            ('RIGHTPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
            ('BOX', (0, 0), (-1, -1), 2, HexColor('#4CAF50')),
            ('LINEBELOW', (0, 0), (-1, 0), 2, HexColor('#2E7D32')),
            ('LINEBETWEEN', (0, 0), (-1, -1), 1, HexColor('#C8E6C9')),
        ]))
        
        story.append(input_table)
        
        # Add symptoms description if provided
        if symptoms and symptoms != 'Not provided':
            story.append(Spacer(1, 15))
            story.append(Paragraph("📝 Symptoms Description", self.styles['SectionHeader']))
            story.append(Spacer(1, 8))
            
            symptoms_data = [[Paragraph(f"<font size=10>{symptoms}</font>", self.styles['Normal'])]]
            symptoms_table = Table(symptoms_data, colWidths=[7*inch])
            symptoms_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, -1), HexColor('#FFFDE7')),
                ('BOX', (0, 0), (-1, -1), 1, HexColor('#FBC02D')),
                ('LEFTPADDING', (0, 0), (-1, -1), 15),
                ('RIGHTPADDING', (0, 0), (-1, -1), 15),
                ('TOPPADDING', (0, 0), (-1, -1), 12),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
            ]))
            story.append(symptoms_table)
        
        story.append(Spacer(1, 25))
    
    def _add_image_section(self, story, analysis_data):
        """Add uploaded image with modern styling"""
        # Handle both dict and object
        if isinstance(analysis_data, dict):
            image_path = analysis_data.get('image_path')
        else:
            image_path = getattr(analysis_data, 'image_path', None)
        
        if image_path and os.path.exists(image_path):
            try:
                story.append(Paragraph("📷 Uploaded Plant Image", self.styles['SubTitle']))
                story.append(Spacer(1, 10))
                
                # Resize image for PDF (max width 5 inches for better visibility)
                img = self._resize_image_for_pdf(image_path, max_width=5*inch, max_height=4*inch)
                if img:
                    # Create a bordered container for the image
                    image_data = [[img]]
                    image_table = Table(image_data, colWidths=[5.5*inch])
                    image_table.setStyle(TableStyle([
                        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                        ('BOX', (0, 0), (-1, -1), 3, HexColor('#4CAF50')),
                        ('BACKGROUND', (0, 0), (-1, -1), colors.white),
                        ('LEFTPADDING', (0, 0), (-1, -1), 15),
                        ('RIGHTPADDING', (0, 0), (-1, -1), 15),
                        ('TOPPADDING', (0, 0), (-1, -1), 15),
                        ('BOTTOMPADDING', (0, 0), (-1, -1), 15),
                    ]))
                    story.append(image_table)
                    story.append(Spacer(1, 25))
                    logger.info(f"Image added to PDF: {image_path}")
                else:
                    logger.warning(f"Could not resize image: {image_path}")
            except Exception as e:
                logger.warning(f"Could not embed image in PDF: {str(e)}")
        else:
            if image_path:
                logger.warning(f"Image path provided but file not found: {image_path}")
            else:
                logger.info("No image path provided for PDF")
    
    def _resize_image_for_pdf(self, image_path, max_width=4*inch, max_height=3*inch):
        """
        Resize image to fit in PDF while maintaining aspect ratio
        Optimizes image size to reduce PDF file size
        """
        try:
            # Check cache first
            cache_key = f"{image_path}_{max_width}_{max_height}"
            if cache_key in self._image_cache:
                return self._image_cache[cache_key]
            
            # Open image with PIL
            pil_img = PILImage.open(image_path)
            
            # Convert to RGB if necessary (for PNG with transparency)
            if pil_img.mode in ('RGBA', 'LA', 'P'):
                background = PILImage.new('RGB', pil_img.size, (255, 255, 255))
                if pil_img.mode == 'P':
                    pil_img = pil_img.convert('RGBA')
                background.paste(pil_img, mask=pil_img.split()[-1] if pil_img.mode == 'RGBA' else None)
                pil_img = background
            
            # Get original dimensions
            orig_width, orig_height = pil_img.size
            
            # Calculate aspect ratio
            aspect = orig_height / float(orig_width)
            
            # Determine new dimensions (in pixels for resizing)
            max_width_px = int(max_width / 72 * 150)  # 150 DPI for good quality
            max_height_px = int(max_height / 72 * 150)
            
            if orig_width > max_width_px or orig_height > max_height_px:
                if aspect > 1:
                    # Portrait
                    new_height_px = max_height_px
                    new_width_px = int(new_height_px / aspect)
                else:
                    # Landscape
                    new_width_px = max_width_px
                    new_height_px = int(new_width_px * aspect)
                
                # Resize image to reduce file size
                pil_img = pil_img.resize((new_width_px, new_height_px), PILImage.Resampling.LANCZOS)
            
            # Save optimized image to temporary buffer
            img_buffer = io.BytesIO()
            pil_img.save(img_buffer, format='JPEG', quality=85, optimize=True)
            img_buffer.seek(0)
            
            # Calculate display dimensions in points
            display_width = min(max_width, orig_width * 72 / 150)
            display_height = display_width * aspect
            
            if display_height > max_height:
                display_height = max_height
                display_width = display_height / aspect
            
            # Create ReportLab image from buffer
            img = RLImage(img_buffer, width=display_width, height=display_height)
            
            # Cache the result
            self._image_cache[cache_key] = img
            
            return img
            
        except Exception as e:
            logger.error(f"Error resizing image for PDF: {str(e)}")
            return None
    
    def _add_identification_results(self, story, analysis_data):
        """Add modern identification results section"""
        story.append(Paragraph("🔍 Identification Results", self.styles['SubTitle']))
        story.append(Spacer(1, 10))
        
        # Extract identification data
        identified_issue = analysis_data.identified_issue if hasattr(analysis_data, 'identified_issue') else analysis_data.get('identified_issue', 'Unknown')
        issue_type = analysis_data.issue_type if hasattr(analysis_data, 'issue_type') else analysis_data.get('issue_type', 'Unknown')
        confidence_score = analysis_data.confidence_score if hasattr(analysis_data, 'confidence_score') else analysis_data.get('confidence_score', 0)
        severity_level = analysis_data.severity_level if hasattr(analysis_data, 'severity_level') else analysis_data.get('severity_level', 'Unknown')
        description = analysis_data.description if hasattr(analysis_data, 'description') else analysis_data.get('description', '')
        
        # Determine status style and color based on severity
        if severity_level and severity_level.lower() in ['critical', 'high']:
            status_style = 'AlertText'
            status_icon = '⚠️ URGENT ACTION REQUIRED'
            severity_color = '#D32F2F'
            bg_color = '#FFEBEE'
        elif severity_level and severity_level.lower() == 'medium':
            status_style = 'WarningText'
            status_icon = '⚠️ ATTENTION NEEDED'
            severity_color = '#F57C00'
            bg_color = '#FFF3E0'
        else:
            status_style = 'SuccessText'
            status_icon = '✓ LOW RISK'
            severity_color = '#2E7D32'
            bg_color = '#E8F5E9'
        
        # Status banner
        status_data = [[Paragraph(f"<font size=14 color='{severity_color}'><b>{status_icon}</b></font>", self.styles['Normal'])]]
        status_table = Table(status_data, colWidths=[7*inch])
        status_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), HexColor(bg_color)),
            ('BOX', (0, 0), (-1, -1), 3, HexColor(severity_color)),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 15),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 15),
        ]))
        story.append(status_table)
        story.append(Spacer(1, 15))
        
        # Main issue display
        issue_data = [[Paragraph(f"<font size=16 color='#2E7D32'><b>{identified_issue if identified_issue else 'No specific issue identified'}</b></font>", self.styles['Normal'])]]
        issue_table = Table(issue_data, colWidths=[7*inch])
        issue_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), HexColor('#F1F8E9')),
            ('BOX', (0, 0), (-1, -1), 2, HexColor('#4CAF50')),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 20),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 20),
        ]))
        story.append(issue_table)
        story.append(Spacer(1, 15))
        
        # Results details table with modern styling
        results_data = [
            [
                Paragraph("<font color='white' size=10><b>Issue Type</b></font>", self.styles['Normal']),
                Paragraph("<font color='white' size=10><b>Confidence Score</b></font>", self.styles['Normal']),
                Paragraph("<font color='white' size=10><b>Severity Level</b></font>", self.styles['Normal'])
            ],
            [
                Paragraph(f"<font size=10>{issue_type.title() if issue_type else 'Unknown'}</font>", self.styles['Normal']),
                Paragraph(f"<font size=11><b>{confidence_score:.1f}%</b></font>" if confidence_score else "<font size=10>N/A</font>", self.styles['Normal']),
                Paragraph(f"<font size=10 color='{severity_color}'><b>{severity_level.upper() if severity_level else 'UNKNOWN'}</b></font>", self.styles['Normal'])
            ]
        ]
        
        results_table = Table(results_data, colWidths=[2.3*inch, 2.3*inch, 2.4*inch])
        results_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), HexColor('#4CAF50')),
            ('BACKGROUND', (0, 1), (-1, 1), HexColor('#F1F8E9')),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 10),
            ('RIGHTPADDING', (0, 0), (-1, -1), 10),
            ('TOPPADDING', (0, 0), (-1, -1), 12),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
            ('BOX', (0, 0), (-1, -1), 2, HexColor('#4CAF50')),
            ('LINEBELOW', (0, 0), (-1, 0), 2, HexColor('#2E7D32')),
            ('LINEBETWEEN', (0, 0), (-1, -1), 1, HexColor('#C8E6C9')),
        ]))
        
        story.append(results_table)
        
        # Add description if available
        if description and description.strip():
            story.append(Spacer(1, 15))
            story.append(Paragraph("📋 Detailed Description", self.styles['SectionHeader']))
            story.append(Spacer(1, 8))
            
            desc_data = [[Paragraph(f"<font size=10>{description}</font>", self.styles['Normal'])]]
            desc_table = Table(desc_data, colWidths=[7*inch])
            desc_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, -1), HexColor('#FFFDE7')),
                ('BOX', (0, 0), (-1, -1), 1, HexColor('#FBC02D')),
                ('LEFTPADDING', (0, 0), (-1, -1), 15),
                ('RIGHTPADDING', (0, 0), (-1, -1), 15),
                ('TOPPADDING', (0, 0), (-1, -1), 12),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
            ]))
            story.append(desc_table)
        
        story.append(Spacer(1, 25))
    
    def _add_treatment_recommendations(self, story, analysis_data):
        """Add modern treatment recommendations section with enhanced tables"""
        story.append(Paragraph("💊 Treatment Recommendations", self.styles['SubTitle']))
        story.append(Spacer(1, 10))
        
        # Get treatment recommendations - handle both model objects and dictionaries
        treatment_recs = None
        
        # Try model object methods first
        if hasattr(analysis_data, 'get_treatment_recommendations'):
            treatment_recs = analysis_data.get_treatment_recommendations()
        elif hasattr(analysis_data, 'treatment_recommendations'):
            try:
                treatment_recs = json.loads(analysis_data.treatment_recommendations) if isinstance(analysis_data.treatment_recommendations, str) else analysis_data.treatment_recommendations
            except:
                treatment_recs = analysis_data.treatment_recommendations
        # Try dictionary access
        elif isinstance(analysis_data, dict):
            # Check for recommendations in dict structure
            if 'treatment_recommendations' in analysis_data:
                treatment_recs = analysis_data.get('treatment_recommendations', {})
            elif 'recommendations' in analysis_data:
                # Handle the structure from advanced_routes.py
                recs = analysis_data.get('recommendations', {})
                if isinstance(recs, dict):
                    treatment_recs = {
                        'immediate_actions': recs.get('immediate_actions', []),
                        'organic_treatments': [],
                        'chemical_treatments': [],
                        'monitoring_advice': recs.get('monitoring_advice', [])
                    }
        
        # Fallback
        if not treatment_recs:
            treatment_recs = {}
        
        if not treatment_recs or not isinstance(treatment_recs, dict):
            # Show a helpful message when no recommendations are available
            no_data_text = """
            <font size=10>
            Treatment recommendations are being generated. This may happen when:<br/>
            <b>•</b> The analysis is still processing<br/>
            <b>•</b> The AI service is temporarily unavailable<br/>
            <b>•</b> The issue identified requires expert consultation<br/><br/>
            <b>Recommended Actions:</b><br/>
            1. Refresh the report after a few minutes<br/>
            2. Consult with local agricultural experts<br/>
            3. Visit your nearest Krishi Vigyan Kendra (KVK)
            </font>
            """
            
            no_data_box = [[Paragraph(no_data_text, self.styles['Normal'])]]
            no_data_table = Table(no_data_box, colWidths=[7*inch])
            no_data_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, -1), HexColor('#FFF3E0')),
                ('BOX', (0, 0), (-1, -1), 2, HexColor('#FF9800')),
                ('LEFTPADDING', (0, 0), (-1, -1), 15),
                ('RIGHTPADDING', (0, 0), (-1, -1), 15),
                ('TOPPADDING', (0, 0), (-1, -1), 15),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 15),
            ]))
            story.append(no_data_box)
            story.append(Spacer(1, 25))
            return
        
        # Immediate actions with modern styling
        immediate_actions = treatment_recs.get('immediate_actions', [])
        if immediate_actions:
            story.append(Paragraph("⚡ Immediate Actions Required", self.styles['SectionHeader']))
            story.append(Spacer(1, 8))
            
            for i, action in enumerate(immediate_actions, 1):
                action_data = [[Paragraph(f"<font size=10><b>{i}.</b> {action}</font>", self.styles['Normal'])]]
                action_table = Table(action_data, colWidths=[7*inch])
                action_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, -1), HexColor('#FFEBEE')),
                    ('BOX', (0, 0), (-1, -1), 1, HexColor('#EF5350')),
                    ('LEFTPADDING', (0, 0), (-1, -1), 12),
                    ('RIGHTPADDING', (0, 0), (-1, -1), 12),
                    ('TOPPADDING', (0, 0), (-1, -1), 10),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
                ]))
                story.append(action_table)
                story.append(Spacer(1, 6))
            story.append(Spacer(1, 15))
        
        # Organic treatments table with modern design
        organic_treatments = treatment_recs.get('organic_treatments', [])
        
        # Always show organic treatment section
        story.append(Paragraph("• Organic Treatment Options", self.styles['SectionHeader']))
        story.append(Spacer(1, 8))
        
        if organic_treatments and len(organic_treatments) > 0:
            story.append(Paragraph("🌿 Organic Treatment Options", self.styles['SectionHeader']))
            story.append(Spacer(1, 8))
            
            organic_data = [[
                Paragraph("<font color='white' size=9><b>Treatment</b></font>", self.styles['Normal']),
                Paragraph("<font color='white' size=9><b>Application</b></font>", self.styles['Normal']),
                Paragraph("<font color='white' size=9><b>Dosage</b></font>", self.styles['Normal']),
                Paragraph("<font color='white' size=9><b>Timing</b></font>", self.styles['Normal']),
                Paragraph("<font color='white' size=9><b>Cost</b></font>", self.styles['Normal'])
            ]]
            
            for treatment in organic_treatments:
                if isinstance(treatment, dict):
                    organic_data.append([
                        Paragraph(f"<font size=9>{treatment.get('name', 'N/A')}</font>", self.styles['Normal']),
                        Paragraph(f"<font size=8>{treatment.get('application', 'N/A')}</font>", self.styles['Normal']),
                        Paragraph(f"<font size=8>{treatment.get('dosage', 'N/A')}</font>", self.styles['Normal']),
                        Paragraph(f"<font size=8>{treatment.get('timing', 'N/A')}</font>", self.styles['Normal']),
                        Paragraph(f"<font size=8>{treatment.get('cost_estimate', 'N/A')}</font>", self.styles['Normal'])
                    ])
            
            if len(organic_data) > 1:
                organic_table = Table(organic_data, colWidths=[1.5*inch, 1.4*inch, 1.3*inch, 1.4*inch, 1.4*inch])
                organic_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), HexColor('#4CAF50')),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                    ('BOX', (0, 0), (-1, -1), 2, HexColor('#4CAF50')),
                    ('LINEBELOW', (0, 0), (-1, 0), 2, HexColor('#2E7D32')),
                    ('INNERGRID', (0, 1), (-1, -1), 0.5, HexColor('#C8E6C9')),
                    ('LEFTPADDING', (0, 0), (-1, -1), 6),
                    ('RIGHTPADDING', (0, 0), (-1, -1), 6),
                    ('TOPPADDING', (0, 0), (-1, -1), 8),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
                    ('ROWBACKGROUNDS', (0, 1), (-1, -1), [HexColor('#F1F8E9'), colors.white]),
                ]))
                story.append(organic_table)
                story.append(Spacer(1, 20))
        else:
            # Show generic organic treatment recommendations
            generic_organic = """
            <font size=9>
            <b>General Organic Treatment Recommendations:</b><br/><br/>
            While specific treatments are being generated, consider these organic options:<br/><br/>
            <b>1. Neem Oil Solution</b><br/>
            • Application: Spray on affected areas<br/>
            • Dosage: 5ml per liter of water<br/>
            • Timing: Early morning or evening<br/>
            • Cost: Rs. 50-100 per treatment<br/><br/>
            
            <b>2. Garlic-Chili Extract</b><br/>
            • Application: Foliar spray<br/>
            • Dosage: 50g garlic + 50g chili per liter<br/>
            • Timing: Weekly application<br/>
            • Cost: Rs. 20-40 per treatment<br/><br/>
            
            <b>3. Cow Urine Solution</b><br/>
            • Application: Diluted spray (1:10 ratio)<br/>
            • Dosage: 100ml per liter of water<br/>
            • Timing: Twice weekly<br/>
            • Cost: Rs. 10-20 per treatment<br/><br/>
            
            <i>Note: Consult local agricultural experts for specific recommendations based on your crop and issue.</i>
            </font>
            """
            
            generic_box = [[Paragraph(generic_organic, self.styles['Normal'])]]
            generic_table = Table(generic_box, colWidths=[7*inch])
            generic_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, -1), HexColor('#F1F8E9')),
                ('BOX', (0, 0), (-1, -1), 2, HexColor('#4CAF50')),
                ('LEFTPADDING', (0, 0), (-1, -1), 15),
                ('RIGHTPADDING', (0, 0), (-1, -1), 15),
                ('TOPPADDING', (0, 0), (-1, -1), 15),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 15),
            ]))
            story.append(generic_table)
            story.append(Spacer(1, 20))
        
        # Chemical treatments table with modern design
        chemical_treatments = treatment_recs.get('chemical_treatments', [])
        
        # Always show chemical treatment section
        story.append(Paragraph("• Chemical Treatment Options", self.styles['SectionHeader']))
        story.append(Spacer(1, 8))
        
        if chemical_treatments and len(chemical_treatments) > 0:
            story.append(Paragraph("⚗️ Chemical Treatment Options", self.styles['SectionHeader']))
            story.append(Spacer(1, 8))
            
            chemical_data = [[
                Paragraph("<font color='white' size=9><b>Treatment</b></font>", self.styles['Normal']),
                Paragraph("<font color='white' size=9><b>Application</b></font>", self.styles['Normal']),
                Paragraph("<font color='white' size=9><b>Dosage</b></font>", self.styles['Normal']),
                Paragraph("<font color='white' size=9><b>Timing</b></font>", self.styles['Normal']),
                Paragraph("<font color='white' size=9><b>Cost</b></font>", self.styles['Normal'])
            ]]
            
            for treatment in chemical_treatments:
                if isinstance(treatment, dict):
                    chemical_data.append([
                        Paragraph(f"<font size=9>{treatment.get('name', 'N/A')}</font>", self.styles['Normal']),
                        Paragraph(f"<font size=8>{treatment.get('application', 'N/A')}</font>", self.styles['Normal']),
                        Paragraph(f"<font size=8>{treatment.get('dosage', 'N/A')}</font>", self.styles['Normal']),
                        Paragraph(f"<font size=8>{treatment.get('timing', 'N/A')}</font>", self.styles['Normal']),
                        Paragraph(f"<font size=8>{treatment.get('cost_estimate', 'N/A')}</font>", self.styles['Normal'])
                    ])
            
            if len(chemical_data) > 1:
                chemical_table = Table(chemical_data, colWidths=[1.5*inch, 1.4*inch, 1.3*inch, 1.4*inch, 1.4*inch])
                chemical_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), HexColor('#FF9800')),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                    ('BOX', (0, 0), (-1, -1), 2, HexColor('#FF9800')),
                    ('LINEBELOW', (0, 0), (-1, 0), 2, HexColor('#F57C00')),
                    ('INNERGRID', (0, 1), (-1, -1), 0.5, HexColor('#FFE0B2')),
                    ('LEFTPADDING', (0, 0), (-1, -1), 6),
                    ('RIGHTPADDING', (0, 0), (-1, -1), 6),
                    ('TOPPADDING', (0, 0), (-1, -1), 8),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
                    ('ROWBACKGROUNDS', (0, 1), (-1, -1), [HexColor('#FFF3E0'), colors.white]),
                ]))
                story.append(chemical_table)
                
                # Add precautions note with modern styling
                precautions_list = []
                for treatment in chemical_treatments:
                    if isinstance(treatment, dict) and treatment.get('precautions'):
                        precautions_list.append(treatment.get('precautions'))
                
                if precautions_list:
                    story.append(Spacer(1, 12))
                    story.append(Paragraph("⚠️ Safety Precautions", self.styles['SectionHeader']))
                    story.append(Spacer(1, 6))
                    
                    for precaution in precautions_list:
                        prec_data = [[Paragraph(f"<font size=9>• {precaution}</font>", self.styles['Normal'])]]
                        prec_table = Table(prec_data, colWidths=[7*inch])
                        prec_table.setStyle(TableStyle([
                            ('BACKGROUND', (0, 0), (-1, -1), HexColor('#FFF3E0')),
                            ('BOX', (0, 0), (-1, -1), 1, HexColor('#FF9800')),
                            ('LEFTPADDING', (0, 0), (-1, -1), 12),
                            ('RIGHTPADDING', (0, 0), (-1, -1), 12),
                            ('TOPPADDING', (0, 0), (-1, -1), 8),
                            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
                        ]))
                        story.append(prec_table)
                        story.append(Spacer(1, 4))
        else:
            # Show generic chemical treatment recommendations
            generic_chemical = """
            <font size=9>
            <b>General Chemical Treatment Recommendations:</b><br/><br/>
            While specific treatments are being generated, consider these chemical options:<br/><br/>
            <b>1. Broad Spectrum Insecticide</b><br/>
            • Application: Foliar spray<br/>
            • Dosage: As per manufacturer's instructions<br/>
            • Timing: Early morning application<br/>
            • Cost: Rs. 200-500 per treatment<br/><br/>
            
            <b>2. Systemic Fungicide</b><br/>
            • Application: Soil drench or foliar spray<br/>
            • Dosage: Follow label recommendations<br/>
            • Timing: At first sign of disease<br/>
            • Cost: Rs. 300-600 per treatment<br/><br/>
            
            <b>3. Contact Pesticide</b><br/>
            • Application: Direct spray on pests<br/>
            • Dosage: As recommended by manufacturer<br/>
            • Timing: When pest population is high<br/>
            • Cost: Rs. 150-400 per treatment<br/><br/>
            
            <b>⚠ IMPORTANT SAFETY PRECAUTIONS:</b><br/>
            • Always wear protective equipment (gloves, mask, goggles)<br/>
            • Follow manufacturer's dosage instructions strictly<br/>
            • Maintain recommended pre-harvest intervals<br/>
            • Store chemicals safely away from food and children<br/>
            • Dispose of empty containers properly<br/>
            • Avoid spraying during windy conditions<br/><br/>
            
            <i>Note: Consult certified agricultural experts or visit your nearest Krishi Vigyan Kendra for specific chemical recommendations.</i>
            </font>
            """
            
            generic_chem_box = [[Paragraph(generic_chemical, self.styles['Normal'])]]
            generic_chem_table = Table(generic_chem_box, colWidths=[7*inch])
            generic_chem_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, -1), HexColor('#FFF3E0')),
                ('BOX', (0, 0), (-1, -1), 2, HexColor('#FF9800')),
                ('LEFTPADDING', (0, 0), (-1, -1), 15),
                ('RIGHTPADDING', (0, 0), (-1, -1), 15),
                ('TOPPADDING', (0, 0), (-1, -1), 15),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 15),
            ]))
            story.append(generic_chem_table)
        
        story.append(Spacer(1, 25))
    
    def _add_preventive_measures(self, story, analysis_data):
        """Add modern preventive measures section"""
        story.append(Paragraph("🛡️ Preventive Measures", self.styles['SubTitle']))
        story.append(Spacer(1, 10))
        
        # Get preventive measures - handle both model objects and dictionaries
        preventive_measures = None
        
        # Try model object methods first
        if hasattr(analysis_data, 'get_preventive_measures'):
            preventive_measures = analysis_data.get_preventive_measures()
        elif hasattr(analysis_data, 'preventive_measures'):
            try:
                preventive_measures = json.loads(analysis_data.preventive_measures) if isinstance(analysis_data.preventive_measures, str) else analysis_data.preventive_measures
            except:
                preventive_measures = analysis_data.preventive_measures
        # Try dictionary access
        elif isinstance(analysis_data, dict):
            # Check for preventive_measures in dict structure
            if 'preventive_measures' in analysis_data:
                preventive_measures = analysis_data.get('preventive_measures', [])
            elif 'recommendations' in analysis_data:
                # Handle the structure from advanced_routes.py
                recs = analysis_data.get('recommendations', {})
                if isinstance(recs, dict):
                    preventive_measures = recs.get('long_term_care', [])
        
        # Fallback
        if not preventive_measures:
            preventive_measures = []
        
        if preventive_measures and isinstance(preventive_measures, list) and len(preventive_measures) > 0:
            for i, measure in enumerate(preventive_measures, 1):
                measure_data = [[Paragraph(f"<font size=10><b>{i}.</b> {measure}</font>", self.styles['Normal'])]]
                measure_table = Table(measure_data, colWidths=[7*inch])
                measure_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, -1), HexColor('#E3F2FD')),
                    ('BOX', (0, 0), (-1, -1), 1, HexColor('#2196F3')),
                    ('LEFTPADDING', (0, 0), (-1, -1), 12),
                    ('RIGHTPADDING', (0, 0), (-1, -1), 12),
                    ('TOPPADDING', (0, 0), (-1, -1), 10),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
                ]))
                story.append(measure_table)
                story.append(Spacer(1, 6))
        else:
            # Show helpful message when no preventive measures are available
            no_data_text = """
            <font size=10>
            Preventive measures are being generated. General recommendations:<br/><br/>
            <b>•</b> Maintain proper field hygiene and sanitation<br/>
            <b>•</b> Use disease-free seeds and planting materials<br/>
            <b>•</b> Follow crop rotation practices<br/>
            <b>•</b> Ensure proper drainage and irrigation<br/>
            <b>•</b> Monitor crops regularly for early detection<br/>
            <b>•</b> Remove and destroy infected plant parts<br/>
            <b>•</b> Maintain optimal plant spacing for air circulation<br/><br/>
            <i>For specific preventive measures, please refresh the report or consult agricultural experts.</i>
            </font>
            """
            
            no_data = [[Paragraph(no_data_text, self.styles['Normal'])]]
            no_table = Table(no_data, colWidths=[7*inch])
            no_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, -1), HexColor('#E3F2FD')),
                ('BOX', (0, 0), (-1, -1), 2, HexColor('#2196F3')),
                ('LEFTPADDING', (0, 0), (-1, -1), 15),
                ('RIGHTPADDING', (0, 0), (-1, -1), 15),
                ('TOPPADDING', (0, 0), (-1, -1), 15),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 15),
            ]))
            story.append(no_table)
        
        story.append(Spacer(1, 25))
    
    def _add_alternative_diagnoses(self, story, analysis_data):
        """Add modern alternative diagnoses section if available"""
        # Get additional diagnoses - handle both model objects and dictionaries
        additional_diagnoses = None
        
        # Try model object methods first
        if hasattr(analysis_data, 'get_additional_diagnoses'):
            additional_diagnoses = analysis_data.get_additional_diagnoses()
        elif hasattr(analysis_data, 'additional_diagnoses'):
            try:
                additional_diagnoses = json.loads(analysis_data.additional_diagnoses) if isinstance(analysis_data.additional_diagnoses, str) else analysis_data.additional_diagnoses
            except:
                additional_diagnoses = analysis_data.additional_diagnoses
        # Try dictionary access
        elif isinstance(analysis_data, dict):
            # Check for additional_diagnoses in dict structure
            if 'additional_diagnoses' in analysis_data:
                additional_diagnoses = analysis_data.get('additional_diagnoses', [])
            elif 'predictions' in analysis_data:
                # Handle the structure from advanced_routes.py - extract alternative predictions
                predictions = analysis_data.get('predictions', [])
                if isinstance(predictions, list) and len(predictions) > 1:
                    additional_diagnoses = []
                    for pred in predictions[1:]:  # Skip first prediction (main diagnosis)
                        if isinstance(pred, dict):
                            additional_diagnoses.append({
                                'issue': pred.get('class', 'Unknown'),
                                'confidence': pred.get('confidence_percentage', 0),
                                'key_difference': pred.get('details', {}).get('symptoms', 'N/A') if isinstance(pred.get('details'), dict) else 'N/A'
                            })
        
        # Fallback
        if not additional_diagnoses:
            additional_diagnoses = []
        
        if additional_diagnoses and isinstance(additional_diagnoses, list) and len(additional_diagnoses) > 0:
            story.append(Paragraph("🔄 Alternative Diagnoses", self.styles['SubTitle']))
            story.append(Spacer(1, 8))
            
            intro_data = [[Paragraph("<font size=10><i>Other possible issues to consider based on the analysis:</i></font>", self.styles['Normal'])]]
            intro_table = Table(intro_data, colWidths=[7*inch])
            intro_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, -1), HexColor('#FFF3E0')),
                ('LEFTPADDING', (0, 0), (-1, -1), 12),
                ('RIGHTPADDING', (0, 0), (-1, -1), 12),
                ('TOPPADDING', (0, 0), (-1, -1), 8),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ]))
            story.append(intro_table)
            story.append(Spacer(1, 10))
            
            # Create modern table for alternative diagnoses
            alt_data = [[
                Paragraph("<font color='white' size=10><b>Issue</b></font>", self.styles['Normal']),
                Paragraph("<font color='white' size=10><b>Confidence</b></font>", self.styles['Normal']),
                Paragraph("<font color='white' size=10><b>Key Difference</b></font>", self.styles['Normal'])
            ]]
            
            for alt in additional_diagnoses:
                if isinstance(alt, dict):
                    alt_data.append([
                        Paragraph(f"<font size=9>{alt.get('issue', 'Unknown')}</font>", self.styles['Normal']),
                        Paragraph(f"<font size=9><b>{alt.get('confidence', 0):.1f}%</b></font>" if isinstance(alt.get('confidence'), (int, float)) else f"<font size=9>{str(alt.get('confidence', 'N/A'))}</font>", self.styles['Normal']),
                        Paragraph(f"<font size=9>{alt.get('key_difference', 'N/A')}</font>", self.styles['Normal'])
                    ])
            
            if len(alt_data) > 1:
                alt_table = Table(alt_data, colWidths=[2.2*inch, 1.3*inch, 3.5*inch])
                alt_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), HexColor('#FFC107')),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('ALIGN', (0, 0), (1, -1), 'CENTER'),
                    ('ALIGN', (2, 0), (2, -1), 'LEFT'),
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                    ('BOX', (0, 0), (-1, -1), 2, HexColor('#FFC107')),
                    ('LINEBELOW', (0, 0), (-1, 0), 2, HexColor('#FF8F00')),
                    ('INNERGRID', (0, 1), (-1, -1), 0.5, HexColor('#FFE082')),
                    ('LEFTPADDING', (0, 0), (-1, -1), 8),
                    ('RIGHTPADDING', (0, 0), (-1, -1), 8),
                    ('TOPPADDING', (0, 0), (-1, -1), 10),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
                    ('ROWBACKGROUNDS', (0, 1), (-1, -1), [HexColor('#FFF8E1'), colors.white]),
                ]))
                story.append(alt_table)
                story.append(Spacer(1, 25))
    
    def _add_regional_context(self, story, analysis_data):
        """Add regional context and government schemes sections"""
        # Get treatment recommendations for regional context
        treatment_recs = None
        if hasattr(analysis_data, 'get_treatment_recommendations'):
            treatment_recs = analysis_data.get_treatment_recommendations()
        elif hasattr(analysis_data, 'treatment_recommendations'):
            try:
                treatment_recs = json.loads(analysis_data.treatment_recommendations) if isinstance(analysis_data.treatment_recommendations, str) else analysis_data.treatment_recommendations
            except:
                treatment_recs = analysis_data.treatment_recommendations
        else:
            treatment_recs = analysis_data.get('treatment_recommendations', {})
        
        if treatment_recs and isinstance(treatment_recs, dict):
            # Regional context
            regional_context = treatment_recs.get('regional_context', {})
            if regional_context and isinstance(regional_context, dict):
                story.append(Paragraph("Regional Context", self.styles['SubTitle']))
                
                if regional_context.get('common_in_region'):
                    story.append(Paragraph(f"• This issue is common in your region", self.styles['Normal']))
                
                if regional_context.get('seasonal_prevalence'):
                    story.append(Paragraph(f"• Seasonal Pattern: {regional_context.get('seasonal_prevalence')}", self.styles['Normal']))
                
                if regional_context.get('local_treatment_availability'):
                    story.append(Paragraph(f"• Treatment Availability: {regional_context.get('local_treatment_availability')}", self.styles['Normal']))
                
                story.append(Spacer(1, 15))
            
            # Government schemes
            govt_schemes = treatment_recs.get('government_schemes', [])
            if govt_schemes and isinstance(govt_schemes, list) and len(govt_schemes) > 0:
                story.append(Paragraph("Applicable Government Schemes", self.styles['SectionHeader']))
                for scheme in govt_schemes:
                    story.append(Paragraph(f"• {scheme}", self.styles['Normal']))
                story.append(Spacer(1, 20))
    
    def _add_footer(self, story):
        """Add modern footer with disclaimer and expert consultation recommendation"""
        story.append(Spacer(1, 30))
        
        # Disclaimer box with modern styling
        disclaimer = """
        <font size=10><b>⚠️ IMPORTANT DISCLAIMER</b></font><br/><br/>
        <font size=9>
        This analysis is generated by AI technology and should be used as a <b>guidance tool only</b>. 
        The recommendations provided are based on image analysis and symptom descriptions, which may not capture 
        all aspects of your crop's condition. For critical plant health issues, high-severity problems, or 
        when in doubt, please consult with a local agricultural expert, extension officer, or visit your 
        nearest Krishi Vigyan Kendra (KVK).<br/><br/>
        <b>FarmLink AI is not responsible for any crop losses or decisions made based solely on this report.</b>
        </font>
        """
        
        disclaimer_data = [[Paragraph(disclaimer, self.styles['Normal'])]]
        disclaimer_table = Table(disclaimer_data, colWidths=[7*inch])
        disclaimer_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), HexColor('#FFEBEE')),
            ('BOX', (0, 0), (-1, -1), 2, HexColor('#D32F2F')),
            ('LEFTPADDING', (0, 0), (-1, -1), 20),
            ('RIGHTPADDING', (0, 0), (-1, -1), 20),
            ('TOPPADDING', (0, 0), (-1, -1), 15),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 15),
        ]))
        
        story.append(disclaimer_table)
        story.append(Spacer(1, 20))
        
        # Expert consultation recommendation with modern design
        expert_consult = """
        <font size=10 color='#2E7D32'><b>👨‍🔬 Expert Consultation Recommended</b></font><br/><br/>
        <font size=9>
        For personalized advice and verification of this analysis, we strongly recommend consulting with:<br/><br/>
        <b>•</b> Local Agricultural Extension Officers<br/>
        <b>•</b> Krishi Vigyan Kendra (KVK) experts<br/>
        <b>•</b> FarmLink AI Expert Forum (available on our platform)<br/>
        <b>•</b> State Agricultural Universities<br/>
        <b>•</b> Certified Plant Pathologists
        </font>
        """
        
        expert_data = [[Paragraph(expert_consult, self.styles['Normal'])]]
        expert_table = Table(expert_data, colWidths=[7*inch])
        expert_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), HexColor('#E8F5E9')),
            ('BOX', (0, 0), (-1, -1), 2, HexColor('#4CAF50')),
            ('LEFTPADDING', (0, 0), (-1, -1), 20),
            ('RIGHTPADDING', (0, 0), (-1, -1), 20),
            ('TOPPADDING', (0, 0), (-1, -1), 15),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 15),
        ]))
        
        story.append(expert_table)
        story.append(Spacer(1, 25))
        
        # Modern footer with branding
        footer_text = """
        <font size=9 color='#757575'>
        <b>Need Help?</b> Visit our Expert Forum or contact FarmLink AI support team<br/>
        📧 farmlink76@gmail.com | 📞 +91 7644868038 | 🌐 www.farmlinkai.com
        </font>
        """
        
        footer_data = [[Paragraph(footer_text, self.styles['Normal'])]]
        footer_table = Table(footer_data, colWidths=[7*inch])
        footer_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ]))
        
        story.append(footer_table)
        story.append(Spacer(1, 10))
        
        # Branding footer
        branding = """
        <font size=11 color='#2E7D32'><b>FarmLink AI</b></font><br/>
        <font size=8 color='#757575'>Empowering Farmers with Technology | Powered by Advanced AI</font>
        """
        
        branding_data = [[Paragraph(branding, self.styles['Normal'])]]
        branding_table = Table(branding_data, colWidths=[7*inch])
        branding_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), HexColor('#F1F8E9')),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 12),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
        ]))
        
        story.append(branding_table)

# Global instance
pdf_generator = PestDetectionPDFGenerator()

def generate_pest_detection_report(analysis_data, user_data, output_path):
    """
    Generate PDF report for pest disease analysis
    
    Args:
        analysis_data: PestDiseaseAnalysis model instance or dict with analysis results
        user_data: User information dict with name, location, contact
        output_path: Path to save the PDF
    
    Returns:
        bool: True if successful, False otherwise
    """
    return pdf_generator.generate_report(analysis_data, user_data, output_path)


class OrderInvoicePDFGenerator:
    """Generate professional PDF invoices for orders"""
    
    def __init__(self):
        self.styles = getSampleStyleSheet()
        self.setup_custom_styles()
    
    def setup_custom_styles(self):
        """Setup custom styles for invoice PDF"""
        # Title style
        self.styles.add(ParagraphStyle(
            name='InvoiceTitle',
            parent=self.styles['Heading1'],
            fontSize=28,
            textColor=HexColor('#2E7D32'),
            spaceAfter=10,
            alignment=TA_CENTER,
            fontName='Helvetica-Bold'
        ))
        
        # Invoice number style
        self.styles.add(ParagraphStyle(
            name='InvoiceNumber',
            parent=self.styles['Normal'],
            fontSize=14,
            textColor=HexColor('#388E3C'),
            spaceAfter=20,
            alignment=TA_CENTER,
            fontName='Helvetica-Bold'
        ))
        
        # Section header
        self.styles.add(ParagraphStyle(
            name='InvoiceSectionHeader',
            parent=self.styles['Heading3'],
            fontSize=12,
            textColor=HexColor('#2E7D32'),
            spaceAfter=10,
            spaceBefore=15,
            fontName='Helvetica-Bold'
        ))
    
    def _generate_tracking_qr_code(self, order_id, tracking_number):
        """
        Generate QR code for tracking page
        
        Args:
            order_id: Order ID
            tracking_number: Tracking number
            
        Returns:
            ReportLab Image object or None if generation fails
        """
        try:
            # Generate tracking URL (using relative path since we don't have request context)
            # In production, this should be the full URL with domain
            tracking_url = f"https://farmlinkai.com/orders/{order_id}/track"
            
            # Create QR code
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=10,
                border=4,
            )
            qr.add_data(tracking_url)
            qr.make(fit=True)
            
            # Create QR code image
            qr_img = qr.make_image(fill_color="black", back_color="white")
            
            # Save to buffer
            img_buffer = io.BytesIO()
            qr_img.save(img_buffer, format='PNG')
            img_buffer.seek(0)
            
            # Create ReportLab image
            qr_image = RLImage(img_buffer, width=1.5*inch, height=1.5*inch)
            
            return qr_image
            
        except Exception as e:
            logger.error(f"Error generating QR code for tracking: {str(e)}")
            return None
    
    def _add_tracking_qr_section(self, story, order):
        """
        Add tracking information section with QR code
        
        Args:
            story: PDF story list
            order: Order model instance
        """
        try:
            # Generate QR code
            qr_image = self._generate_tracking_qr_code(order.id, order.tracking_number)
            
            if qr_image:
                # Create tracking info box with QR code
                tracking_header = Paragraph(
                    "<font color='#2E7D32' size=11><b>📦 TRACK YOUR SHIPMENT</b></font>", 
                    self.styles['Normal']
                )
                story.append(tracking_header)
                story.append(Spacer(1, 8))
                
                # Create table with QR code and tracking info side by side
                tracking_info_text = f"""
                <font size=9>
                <b>Scan QR code to track your order</b><br/>
                <br/>
                Tracking Number: <b>{order.tracking_number}</b><br/>
                Courier: <b>{order.courier_name.title() if order.courier_name else 'N/A'}</b><br/>
                Status: <b>{order.shipment_status.replace('_', ' ').title() if order.shipment_status else 'N/A'}</b><br/>
                """
                
                if order.estimated_delivery_date:
                    tracking_info_text += f"Est. Delivery: <b>{order.estimated_delivery_date.strftime('%B %d, %Y')}</b><br/>"
                
                tracking_info_text += """
                <br/>
                <i>Or visit: farmlinkai.com/orders/{}/track</i>
                </font>
                """.format(order.id)
                
                tracking_data = [
                    [qr_image, Paragraph(tracking_info_text, self.styles['Normal'])]
                ]
                
                tracking_table = Table(tracking_data, colWidths=[2*inch, 5*inch])
                tracking_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, -1), HexColor('#E8F5E9')),
                    ('BOX', (0, 0), (-1, -1), 2, HexColor('#4CAF50')),
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                    ('ALIGN', (0, 0), (0, 0), 'CENTER'),
                    ('LEFTPADDING', (0, 0), (-1, -1), 12),
                    ('RIGHTPADDING', (0, 0), (-1, -1), 12),
                    ('TOPPADDING', (0, 0), (-1, -1), 12),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
                ]))
                
                story.append(tracking_table)
                story.append(Spacer(1, 20))
                
        except Exception as e:
            logger.error(f"Error adding tracking QR section: {str(e)}")
            # Continue without QR code if there's an error
    
    def generate_invoice(self, order, output_path):
        """
        Generate invoice PDF for an order
        
        Args:
            order: Order model instance
            output_path: Path to save the PDF
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Create PDF document
            doc = SimpleDocTemplate(
                output_path,
                pagesize=A4,
                rightMargin=50,
                leftMargin=50,
                topMargin=50,
                bottomMargin=30
            )
            
            # Build story (content)
            story = []
            
            # Add header
            self._add_invoice_header(story, order)
            
            # Add buyer and seller information
            self._add_party_information(story, order)
            
            # Add order details table
            self._add_order_details(story, order)
            
            # Add payment information
            self._add_payment_information(story, order)
            
            # Add footer
            self._add_invoice_footer(story, order)
            
            # Build PDF
            doc.build(story)
            
            logger.info(f"Invoice generated successfully for order {order.id}: {output_path}")
            return True
            
        except Exception as e:
            logger.error(f"Error generating invoice for order {order.id}: {str(e)}")
            logger.exception("Detailed traceback:")
            return False
    
    def _add_invoice_header(self, story, order):
        """Add invoice header with logo and title"""
        # Create custom style for header text to prevent cutting
        header_style = ParagraphStyle(
            name='HeaderStyle',
            parent=self.styles['Normal'],
            fontSize=22,
            textColor=colors.white,
            fontName='Helvetica-Bold',
            leading=26,  # Line height - prevents cutting
            spaceBefore=0,
            spaceAfter=0
        )
        
        subtitle_style = ParagraphStyle(
            name='SubtitleStyle',
            parent=self.styles['Normal'],
            fontSize=10,
            textColor=colors.white,
            fontName='Helvetica',
            leading=12,
            spaceBefore=0,
            spaceAfter=0
        )
        
        # Create header with colored background - Fixed text cutting issue
        header_data = [[
            Paragraph("FarmLink AI", header_style),
            Paragraph("Tax Invoice / Bill of Supply", subtitle_style)
        ]]
        
        # Increased row height to prevent text cutting
        header_table = Table(header_data, colWidths=[4*inch, 3*inch], rowHeights=[60])
        header_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), HexColor('#2E7D32')),
            ('ALIGN', (0, 0), (0, 0), 'LEFT'),
            ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 20),
            ('RIGHTPADDING', (0, 0), (-1, -1), 20),
            ('TOPPADDING', (0, 0), (-1, -1), 15),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 15),
        ]))
        
        story.append(header_table)
        story.append(Spacer(1, 20))
        
        # Invoice number and date in colored box
        # Generate invoice number inline to avoid circular import
        date_str = datetime.utcnow().strftime('%Y%m%d')
        invoice_number = f"INV-{date_str}-{order.id:05d}"
        
        invoice_info_data = [[
            Paragraph(f"<font size=14 color='#2E7D32'><b>Invoice Number: {invoice_number}</b></font>", self.styles['Normal']),
            Paragraph(f"<font size=10><b>Invoice Date:</b> {order.created_at.strftime('%B %d, %Y')}</font>", self.styles['Normal'])
        ]]
        
        invoice_info_table = Table(invoice_info_data, colWidths=[4*inch, 3*inch])
        invoice_info_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), HexColor('#E8F5E9')),
            ('ALIGN', (0, 0), (0, 0), 'LEFT'),
            ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 10),
            ('RIGHTPADDING', (0, 0), (-1, -1), 10),
            ('TOPPADDING', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
            ('BOX', (0, 0), (-1, -1), 1, HexColor('#4CAF50')),
        ]))
        
        story.append(invoice_info_table)
        story.append(Spacer(1, 25))
    
    def _add_party_information(self, story, order):
        """Add buyer and seller information with enhanced styling"""
        # Create two-column layout for buyer and seller with colored headers
        party_data = [
            [
                Paragraph("<font color='white' size=11><b>📦 BILL TO (Buyer)</b></font>", self.styles['Normal']),
                Paragraph("<font color='white' size=11><b>🚜 SHIP FROM (Seller)</b></font>", self.styles['Normal'])
            ],
            [
                Paragraph(f"<font size=10>"
                         f"<b>Name:</b> {order.buyer.full_name}<br/>"
                         f"<b>ID:</b> #{order.buyer.id}<br/>"
                         f"<b>Email:</b> {order.buyer.email}<br/>"
                         f"<b>Phone:</b> {order.buyer.phone or 'N/A'}<br/>"
                         f"<b>Location:</b> {order.buyer.location or 'N/A'}"
                         f"</font>", 
                         self.styles['Normal']),
                Paragraph(f"<font size=10>"
                         f"<b>Name:</b> {order.farmer_user.full_name}<br/>"
                         f"<b>ID:</b> #{order.farmer_user.id}<br/>"
                         f"<b>Email:</b> {order.farmer_user.email}<br/>"
                         f"<b>Phone:</b> {order.farmer_user.phone or 'N/A'}<br/>"
                         f"<b>Location:</b> {order.farmer_user.location or 'N/A'}"
                         f"</font>", 
                         self.styles['Normal'])
            ]
        ]
        
        party_table = Table(party_data, colWidths=[3.5*inch, 3.5*inch])
        party_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), HexColor('#4CAF50')),
            ('BACKGROUND', (0, 1), (-1, 1), HexColor('#F1F8E9')),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 12),
            ('RIGHTPADDING', (0, 0), (-1, -1), 12),
            ('TOPPADDING', (0, 0), (-1, 0), 8),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
            ('TOPPADDING', (0, 1), (-1, 1), 12),
            ('BOTTOMPADDING', (0, 1), (-1, 1), 12),
            ('BOX', (0, 0), (-1, -1), 2, HexColor('#4CAF50')),
            ('LINEBELOW', (0, 0), (-1, 0), 2, HexColor('#2E7D32')),
            ('LINEBEFORE', (1, 0), (1, -1), 1, HexColor('#C8E6C9')),
        ]))
        
        story.append(party_table)
        story.append(Spacer(1, 20))
        
        # Delivery address with icon and colored background
        if order.delivery_address:
            delivery_header = Paragraph("<font color='#2E7D32' size=11><b>📍 DELIVERY ADDRESS</b></font>", self.styles['Normal'])
            story.append(delivery_header)
            story.append(Spacer(1, 5))
            
            delivery_data = [[Paragraph(f"<font size=10>{order.delivery_address}</font>", self.styles['Normal'])]]
            delivery_table = Table(delivery_data, colWidths=[7*inch])
            delivery_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, -1), HexColor('#E8F5E9')),
                ('BOX', (0, 0), (-1, -1), 1, HexColor('#4CAF50')),
                ('LEFTPADDING', (0, 0), (-1, -1), 12),
                ('RIGHTPADDING', (0, 0), (-1, -1), 12),
                ('TOPPADDING', (0, 0), (-1, -1), 10),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
            ]))
            story.append(delivery_table)
            story.append(Spacer(1, 20))
    
    def _add_order_details(self, story, order):
        """Add order details table with enhanced styling"""
        # Section header with icon
        header = Paragraph("<font color='#2E7D32' size=12><b>📋 ORDER DETAILS</b></font>", self.styles['Normal'])
        story.append(header)
        story.append(Spacer(1, 10))
        
        # Order information with alternating row colors
        order_info_data = [
            ['Order ID:', f"#{order.id}"],
            ['Order Date:', order.created_at.strftime('%B %d, %Y at %I:%M %p')],
            ['Order Status:', order.status.upper()],
            ['Delivery Method:', order.delivery_method.title() if order.delivery_method else 'Standard']
        ]
        
        # Add tracking information if shipment is created (status is "shipped" or later)
        if order.tracking_number and order.shipment_status in ['shipped', 'in_transit', 'out_for_delivery', 'delivered']:
            order_info_data.append(['Tracking Number:', order.tracking_number])
            
            if order.courier_name:
                order_info_data.append(['Courier Service:', order.courier_name.title()])
            
            if order.shipped_at:
                order_info_data.append(['Shipped Date:', order.shipped_at.strftime('%B %d, %Y at %I:%M %p')])
            
            if order.estimated_delivery_date:
                order_info_data.append(['Estimated Delivery:', order.estimated_delivery_date.strftime('%B %d, %Y')])
        
        order_info_table = Table(order_info_data, colWidths=[2*inch, 5*inch])
        
        # Create alternating row colors
        table_style = [
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('LEFTPADDING', (0, 0), (-1, -1), 10),
            ('RIGHTPADDING', (0, 0), (-1, -1), 10),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('TEXTCOLOR', (0, 0), (0, -1), HexColor('#2E7D32')),
        ]
        
        # Add alternating backgrounds
        for i in range(len(order_info_data)):
            if i % 2 == 0:
                table_style.append(('BACKGROUND', (0, i), (-1, i), HexColor('#F1F8E9')))
            else:
                table_style.append(('BACKGROUND', (0, i), (-1, i), colors.white))
        
        order_info_table.setStyle(TableStyle(table_style))
        
        story.append(order_info_table)
        story.append(Spacer(1, 15))
        
        # Add tracking QR code if shipment is created
        if order.tracking_number and order.shipment_status in ['shipped', 'in_transit', 'out_for_delivery', 'delivered']:
            self._add_tracking_qr_section(story, order)
        
        # Product details table with gradient-like header
        product_data = [
            [
                Paragraph("<font color='white' size=10><b>Product/Crop</b></font>", self.styles['Normal']),
                Paragraph("<font color='white' size=10><b>Category</b></font>", self.styles['Normal']),
                Paragraph("<font color='white' size=10><b>Quantity</b></font>", self.styles['Normal']),
                Paragraph("<font color='white' size=10><b>Rate/Unit</b></font>", self.styles['Normal']),
                Paragraph("<font color='white' size=10><b>Amount</b></font>", self.styles['Normal'])
            ]
        ]
        
        product_data.append([
            Paragraph(f"<font size=10><b>{order.crop.name}</b></font>", self.styles['Normal']),
            Paragraph(f"<font size=9>{order.crop.category.title()}</font>", self.styles['Normal']),
            Paragraph(f"<font size=9>{order.quantity_requested} {order.crop.unit}</font>", self.styles['Normal']),
            Paragraph(f"<font size=9>Rs. {order.price_per_unit:.2f}</font>", self.styles['Normal']),
            Paragraph(f"<font size=10><b>Rs. {order.total_amount:.2f}</b></font>", self.styles['Normal'])
        ])
        
        product_table = Table(product_data, colWidths=[2*inch, 1.5*inch, 1.2*inch, 1.2*inch, 1.1*inch])
        product_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), HexColor('#4CAF50')),
            ('BACKGROUND', (0, 1), (-1, 1), HexColor('#F1F8E9')),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
            ('BOX', (0, 0), (-1, -1), 2, HexColor('#4CAF50')),
            ('LINEBELOW', (0, 0), (-1, 0), 2, HexColor('#2E7D32')),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('ALIGN', (2, 0), (-1, -1), 'RIGHT'),
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
            ('RIGHTPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ]))
        
        story.append(product_table)
        story.append(Spacer(1, 15))
        
        # Enhanced total amount section with visual appeal
        story.append(Spacer(1, 10))
        
        # Create a visually striking total section
        total_data = [
            # Subtotal row with light background
            [
                Paragraph("<font size=11 color='#424242'>Subtotal</font>", self.styles['Normal']),
                Paragraph(f"<font size=11 color='#424242'>Rs. {order.total_amount:,.2f}</font>", self.styles['Normal'])
            ],
            # Tax row with light background
            [
                Paragraph("<font size=11 color='#424242'>Tax (Included)</font>", self.styles['Normal']),
                Paragraph("<font size=11 color='#424242'>Rs. 0.00</font>", self.styles['Normal'])
            ],
            # Discount row (if applicable) - can be added later
            [
                Paragraph("<font size=11 color='#757575'>Discount</font>", self.styles['Normal']),
                Paragraph("<font size=11 color='#757575'>Rs. 0.00</font>", self.styles['Normal'])
            ],
            # Grand total with prominent styling
            [
                Paragraph("<font size=16 color='white'><b>GRAND TOTAL</b></font>", self.styles['Normal']),
                Paragraph(f"<font size=18 color='white'><b>Rs. {order.total_amount:,.2f}</b></font>", self.styles['Normal'])
            ]
        ]
        
        total_table = Table(total_data, colWidths=[4.5*inch, 2.5*inch])
        total_table.setStyle(TableStyle([
            # Alignment
            ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            
            # Subtotal and Tax rows - light gray background
            ('BACKGROUND', (0, 0), (-1, 0), HexColor('#F5F5F5')),
            ('BACKGROUND', (0, 1), (-1, 1), HexColor('#FAFAFA')),
            ('BACKGROUND', (0, 2), (-1, 2), HexColor('#F5F5F5')),
            
            # Grand Total row - vibrant green gradient effect
            ('BACKGROUND', (0, 3), (-1, 3), HexColor('#2E7D32')),
            
            # Borders
            ('BOX', (0, 0), (-1, -1), 2, HexColor('#4CAF50')),
            ('LINEBELOW', (0, 0), (-1, 0), 1, HexColor('#E0E0E0')),
            ('LINEBELOW', (0, 1), (-1, 1), 1, HexColor('#E0E0E0')),
            ('LINEBELOW', (0, 2), (-1, 2), 2, HexColor('#4CAF50')),
            
            # Padding for better spacing
            ('TOPPADDING', (0, 0), (-1, 2), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 2), 10),
            ('TOPPADDING', (0, 3), (-1, 3), 15),
            ('BOTTOMPADDING', (0, 3), (-1, 3), 15),
            ('LEFTPADDING', (0, 0), (-1, -1), 15),
            ('RIGHTPADDING', (0, 0), (-1, -1), 15),
        ]))
        
        story.append(total_table)
        
        # Add a decorative note below total
        story.append(Spacer(1, 10))
        note_data = [[
            Paragraph(
                "<font size=9 color='#757575'><i>✓ Amount in Indian Rupees (INR) | All prices are inclusive of applicable taxes</i></font>",
                self.styles['Normal']
            )
        ]]
        note_table = Table(note_data, colWidths=[7*inch])
        note_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ]))
        story.append(note_table)
        story.append(Spacer(1, 20))
    
    def _add_payment_information(self, story, order):
        """Add payment information with enhanced styling - starts on new page"""
        # Add page break before payment information to ensure it's on a new page
        story.append(PageBreak())
        
        # Create payment section elements
        payment_elements = []
        
        # Section header with icon
        header = Paragraph("<font color='#2E7D32' size=12><b>💳 PAYMENT INFORMATION</b></font>", self.styles['Normal'])
        payment_elements.append(header)
        payment_elements.append(Spacer(1, 10))
        
        payment_data = [
            ['Payment Status:', order.payment_status.upper()],
            ['Payment Method:', 'Online Payment (Razorpay)']
        ]
        
        if order.razorpay_payment_id:
            payment_data.append(['Payment ID:', order.razorpay_payment_id])
        
        if order.razorpay_order_id:
            payment_data.append(['Transaction ID:', order.razorpay_order_id])
        
        payment_table = Table(payment_data, colWidths=[2*inch, 5*inch])
        
        # Create alternating row colors
        table_style = [
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('LEFTPADDING', (0, 0), (-1, -1), 10),
            ('RIGHTPADDING', (0, 0), (-1, -1), 10),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('TEXTCOLOR', (0, 0), (0, -1), HexColor('#2E7D32')),
        ]
        
        # Add alternating backgrounds
        for i in range(len(payment_data)):
            if i % 2 == 0:
                table_style.append(('BACKGROUND', (0, i), (-1, i), HexColor('#E3F2FD')))
            else:
                table_style.append(('BACKGROUND', (0, i), (-1, i), colors.white))
        
        payment_table.setStyle(TableStyle(table_style))
        
        payment_elements.append(payment_table)
        payment_elements.append(Spacer(1, 20))
        
        # Use KeepTogether to prevent payment section from splitting across pages
        story.append(KeepTogether(payment_elements))
    
    def _add_invoice_footer(self, story, order):
        """Add invoice footer with terms and signature"""
        # Terms and conditions with colored box
        terms_header = Paragraph("<font color='#2E7D32' size=11><b>📜 TERMS & CONDITIONS</b></font>", self.styles['Normal'])
        story.append(terms_header)
        story.append(Spacer(1, 8))
        
        terms = """
        <font size=9>
        1. This is a computer-generated invoice and does not require a physical signature.<br/>
        2. All disputes are subject to jurisdiction of courts in the seller's location.<br/>
        3. Goods once sold will not be taken back or exchanged.<br/>
        4. Please inspect the goods at the time of delivery.<br/>
        5. For any queries, please contact FarmLink AI support.
        </font>
        """
        
        terms_data = [[Paragraph(terms, self.styles['Normal'])]]
        terms_table = Table(terms_data, colWidths=[7*inch])
        terms_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), HexColor('#FFFDE7')),
            ('BOX', (0, 0), (-1, -1), 1, HexColor('#FBC02D')),
            ('LEFTPADDING', (0, 0), (-1, -1), 12),
            ('RIGHTPADDING', (0, 0), (-1, -1), 12),
            ('TOPPADDING', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ]))
        
        story.append(terms_table)
        story.append(Spacer(1, 20))
        
        # Signature section with enhanced styling
        signature_data = [
            [
                Paragraph("<font size=9 color='grey'>Buyer Signature</font>", self.styles['Normal']),
                Paragraph("<font size=9 color='grey'>For FarmLink AI</font>", self.styles['Normal'])
            ],
            ['', ''],
            ['', ''],
            [
                Paragraph("<font size=10><b>_____________________</b></font>", self.styles['Normal']),
                Paragraph("<font size=10><b>_____________________</b></font>", self.styles['Normal'])
            ],
            [
                Paragraph("<font size=9 color='#2E7D32'><b>Buyer</b></font>", self.styles['Normal']),
                Paragraph("<font size=9 color='#2E7D32'><b>Authorized Signatory</b></font>", self.styles['Normal'])
            ]
        ]
        
        signature_table = Table(signature_data, colWidths=[3.5*inch, 3.5*inch])
        signature_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ]))
        
        story.append(signature_table)
        story.append(Spacer(1, 25))
        
        # Footer with colored background
        footer_data = [[
            Paragraph(
                "<font color='white' size=10><b>🌾 Thank you for choosing FarmLink AI!</b></font><br/>"
                "<font color='white' size=8>This is a digitally generated invoice. No signature required.</font><br/>"
                "<font color='white' size=8>📧 farmlink76@gmail.com | 🌐 www.farmlinkai.com | 📞 +91 7644868038</font>",
                self.styles['Normal']
            )
        ]]
        
        footer_table = Table(footer_data, colWidths=[7*inch])
        footer_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), HexColor('#2E7D32')),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 15),
            ('RIGHTPADDING', (0, 0), (-1, -1), 15),
            ('TOPPADDING', (0, 0), (-1, -1), 12),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
        ]))
        
        story.append(footer_table)


# Global invoice generator instance
invoice_generator = OrderInvoicePDFGenerator()


def generate_order_invoice(order, output_path):
    """
    Generate PDF invoice for an order
    
    Args:
        order: Order model instance
        output_path: Path to save the PDF
        
    Returns:
        bool: True if successful, False otherwise
    """
    return invoice_generator.generate_invoice(order, output_path)
