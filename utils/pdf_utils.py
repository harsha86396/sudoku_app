from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from datetime import datetime

def generate_last7_pdf(username, email, rows, out_stream):
    width, height = letter
    pdf = canvas.Canvas(out_stream, pagesize=letter)
    pdf.setTitle("Sudoku – Last 7 Days")

    # Cover
    pdf.setFont("Helvetica-Bold", 24)
    pdf.drawCentredString(width/2, height-150, "Sudoku AI")
    pdf.setFont("Helvetica", 18)
    pdf.drawCentredString(width/2, height-190, "Activity Report (Last 7 Days)")
    pdf.setFont("Helvetica", 12)
    pdf.drawCentredString(width/2, height-230, f"User: {username} ({email})")
    pdf.drawCentredString(width/2, height-250, f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    pdf.showPage()

    y = height - 60
    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawString(50, y, "Recent Games")
    y -= 20
    pdf.setFont("Helvetica", 11)
    if not rows:
        pdf.drawString(50, y, "No games recorded in the last 7 days.")
        y -= 14
    else:
        for seconds, played_at in rows:
            pdf.drawString(50, y, f"- {played_at} — {seconds}s")
            y -= 14
            if y < 60:
                pdf.showPage(); y = height - 60
    pdf.showPage()
    pdf.save()
