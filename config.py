# ===== App Config =====
EMAIL_ENABLED = True
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_USER = "harsha86396@gmail.com"
SMTP_PASS = "mstxbkcvhtstpncp"  # Gmail App Password you provided

SECRET_KEY = "please-change-this-very-secret-key"
APP_NAME = "Sudoku powered by Harsha Enterprises"

# Admin panel credentials
ADMIN_EMAIL = "admin@sudoku.local"
ADMIN_PASSWORD = "admin123"  # change in production

# OTP settings
OTP_EXP_MINUTES = 10
OTP_RATE_LIMIT_SECONDS = 60  # per email

# Weekly digest
DIGEST_ENABLED = True
DIGEST_IST_TIME = "18:00"
