# ===== App Config =====
import os

# Email
EMAIL_ENABLED = True
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_USER = os.environ.get("SMTP_USER", "harsha86396@gmail.com")
SMTP_PASS = os.environ.get("SMTP_PASS", "mstxbkcvhtstpncp")  # set via env var in production

# Flask secret key (used for sessions & CSRF)
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-change-this")

# App branding
APP_NAME = "Sudoku powered by Harsha Enterprises"

# Admin panel credentials
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@sudoku.local")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")  # set via env var in production

# OTP settings
OTP_EXP_MINUTES = int(os.environ.get("OTP_EXP_MINUTES", 10))
OTP_RATE_LIMIT_SECONDS = int(os.environ.get("OTP_RATE_LIMIT_SECONDS", 60))  # per email

# Weekly digest
DIGEST_ENABLED = os.environ.get("DIGEST_ENABLED", "true").lower() == "true"
DIGEST_IST_TIME = os.environ.get("DIGEST_IST_TIME", "18:00")

# Stable absolute database path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.environ.get("DATABASE_PATH") or os.path.join(BASE_DIR, "sudoku.db")
