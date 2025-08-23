
import os

class Config:
    # Base directory
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))
    DB_PATH = os.environ.get("DB_PATH") or os.path.join(BASE_DIR, "sudoku.db")

    SECRET_KEY = os.environ.get("SECRET_KEY", "change-me-please")
    SESSION_COOKIE_NAME = "sudoku_session"

    # Admin
    ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@harsha.local")
    ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")

    # Email (optional; login will never depend on email send success)
    SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
    SMTP_USER = os.environ.get("SMTP_USER", "")
    SMTP_PASS = os.environ.get("SMTP_PASS", "")
    SMTP_USE_TLS = os.environ.get("SMTP_USE_TLS", "1") == "1"
    FROM_EMAIL = os.environ.get("FROM_EMAIL", "no-reply@harsha.local")

    # OTP
    OTP_EXPIRE_MINUTES = int(os.environ.get("OTP_EXPIRE_MINUTES", "10"))
    OTP_RATE_LIMIT_SECONDS = int(os.environ.get("OTP_RATE_LIMIT_SECONDS", "60"))

    # Branding
    BRAND = os.environ.get("BRAND", "Sudoku • Harsha Enterprises")
