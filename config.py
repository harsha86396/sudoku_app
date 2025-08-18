import os
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.environ.get('DATABASE_PATH') or os.path.join('/mnt/disk', 'sudoku.db')

# App Config
EMAIL_ENABLED = os.environ.get('EMAIL_ENABLED', 'True') == 'True'
SMTP_SERVER = os.environ.get('SMTP_SERVER', 'smtp.gmail.com')
SMTP_PORT = int(os.environ.get('SMTP_PORT', 587))
SMTP_USER = os.environ.get('SMTP_USER', 'harsha86396@gmail.com')
SMTP_PASS = os.environ.get('SMTP_PASS', 'mstxbkcvhtstpncp')

SECRET_KEY = os.environ.get('SECRET_KEY', 'your-very-secret-key-123456')
APP_NAME = "Sudoku powered by Harsha Enterprises"

# Admin panel credentials
ADMIN_EMAIL = os.environ.get('ADMIN_EMAIL', 'admin@sudoku.local')
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'admin123')

# OTP settings
OTP_EXP_MINUTES = int(os.environ.get('OTP_EXP_MINUTES', 10))
OTP_RATE_LIMIT_SECONDS = int(os.environ.get('OTP_RATE_LIMIT_SECONDS', 60))

# Weekly digest
DIGEST_ENABLED = os.environ.get('DIGEST_ENABLED', 'True') == 'True'
DIGEST_IST_TIME = os.environ.get('DIGEST_IST_TIME', '18:00')
