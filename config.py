import os

ADMIN_USERNAME = os.getenv('ADMIN_USERNAME', 'admin')
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', 'securepassword')
EMAIL_API_KEY = os.getenv('EMAIL_API_KEY', '')
