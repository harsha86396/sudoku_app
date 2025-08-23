
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from datetime import datetime

def generate_last7_pdf(path: str, stats: dict):
    """
    stats: {"new_users": int, "games_played": int, "top_player": str, "top_time": int}
    """
    c = canvas.Canvas(path, pagesize=letter)
    w, h = letter
    c.setFont("Helvetica-Bold", 20)
    c.drawString(72, h - 72, "Weekly Sudoku Digest")
    c.setFont("Helvetica", 12)
    c.drawString(72, h - 110, f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    c.drawString(72, h - 150, f"New users: {stats.get('new_users',0)}")
    c.drawString(72, h - 170, f"Games played: {stats.get('games_played',0)}")
    top_player = stats.get('top_player') or 'N/A'
    top_time = stats.get('top_time')
    c.drawString(72, h - 190, f"Top player: {top_player}")
    if isinstance(top_time, int):
        c.drawString(72, h - 210, f"Best time: {top_time} seconds")
    c.showPage()
    c.save()
