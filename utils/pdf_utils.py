# utils/pdf_utils.py
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
from reportlab.lib.units import inch
from datetime import datetime

def generate_last7_pdf(name, email, results, buffer):
    """Generate a PDF report of the last 7 days' results"""
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    elements = []
    
    styles = getSampleStyleSheet()
    
    # Title
    title = Paragraph("Sudoku Game Results - Last 7 Days", styles['Title'])
    elements.append(title)
    elements.append(Spacer(1, 0.2 * inch))
    
    # User info
    user_info = Paragraph(f"<b>Name:</b> {name}<br/><b>Email:</b> {email}", styles['Normal'])
    elements.append(user_info)
    elements.append(Spacer(1, 0.2 * inch))
    
    # Results table
    if results:
        data = [['Date', 'Time (seconds)', 'Formatted Time']]
        
        for result in results:
            seconds = result[0]
            played_at = result[1]
            
            # Format date
            if isinstance(played_at, str):
                date_obj = datetime.fromisoformat(played_at.replace('Z', '+00:00'))
            else:
                date_obj = played_at
                
            date_str = date_obj.strftime('%Y-%m-%d %H:%M')
            
            # Format time
            minutes = seconds // 60
            remaining_seconds = seconds % 60
            time_str = f"{minutes}:{remaining_seconds:02d}"
            
            data.append([date_str, str(seconds), time_str])
        
        table = Table(data)
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 14),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 12),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        
        elements.append(table)
    else:
        no_data = Paragraph("No games played in the last 7 days.", styles['Normal'])
        elements.append(no_data)
    
    # Generate PDF
    doc.build(elements)
