import secrets
import smtplib
from email.mime.text import MIMEText
from datetime import datetime, timedelta
from flask import flash
from bcrypt import hashpw, gensalt, checkpw
import json
import os

def hash_password(password):
    """Hash a password using bcrypt."""
    try:
        return hashpw(password.encode('utf-8'), gensalt())
    except Exception as e:
        flash(f'Password hashing failed: {str(e)}')
        return None

def verify_password(password, hashed):
    """Verify a password against its hash."""
    try:
        return checkpw(password.encode('utf-8'), hashed)
    except Exception as e:
        flash(f'Password verification failed: {str(e)}')
        return False

def generate_otp():
    """Generate a 6-character OTP."""
    return secrets.token_hex(3)

def send_email(to_email, content, subject='Sudoku App'):
    """Send an email using SMTP."""
    msg = MIMEText(content)
    msg['Subject'] = subject
    msg['From'] = os.getenv('EMAIL_FROM')
    msg['To'] = to_email
    try:
        with smtplib.SMTP('smtp.gmail.com', 587) as server:
            server.starttls()
            server.login(os.getenv('EMAIL_FROM'), os.getenv('EMAIL_PASSWORD'))
            server.send_message(msg)
        return True
    except Exception as e:
        flash(f'Email sending failed: {str(e)}')
        return False

def generate_captcha():
    """Generate a simple math CAPTCHA (question, answer)."""
    num1 = secrets.randbelow(20)
    num2 = secrets.randbelow(20)
    operator = secrets.choice(['+', '-', '*'])
    question = f"What is {num1} {operator} {num2}?"
    answer = str(eval(f"{num1}{operator}{num2}"))
    return question, answer

def validate_board(board):
    """Validate a 9x9 Sudoku board for correctness."""
    if not board or len(board) != 9 or any(len(row) != 9 for row in board):
        return False
    for i in range(9):
        for j in range(9):
            if board[i][j] != 0:
                num = board[i][j]
                board[i][j] = 0
                if not is_valid_move(board, num, i, j):
                    board[i][j] = num
                    return False
                board[i][j] = num
    return True

def is_valid_move(board, num, row, col):
    """Check if a number can be placed at the given position."""
    for i in range(9):
        if board[row][i] == num or board[i][col] == num:
            return False
    start_row, start_col = 3 * (row // 3), 3 * (col // 3)
    for i in range(start_row, start_row + 3):
        for j in range(start_col, start_col + 3):
            if board[i][j] == num:
                return False
    return True

def format_leaderboard_for_pdf(scores):
    """Format leaderboard data for PDF generation."""
    formatted = []
    for score in scores:
        formatted.append(f"{score.user.username}: {score.time:.1f}s")
    return formatted

def sanitize_input(data):
    """Sanitize input to prevent injection attacks."""
    if isinstance(data, str):
        return data.strip().replace('<', '&lt;').replace('>', '&gt;')
    return data
