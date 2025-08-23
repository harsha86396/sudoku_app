
from app import create_app
app = create_app()

# For Render/WSGI
if __name__ != "__main__":
    application = app
