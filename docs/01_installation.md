Installation Guide





Clone the Repository:

git clone https://github.com/harsha86396/sudoku_app.git
cd sudoku_app



Install Dependencies:

pip install -r 06_requirements.txt



Set Up Environment Variables: Create a .env file:

FLASK_ENV=development
SECRET_KEY=your-secret-key
DATABASE_URL=sqlite:///sudoku.db
EMAIL_FROM=your-email@gmail.com
EMAIL_PASSWORD=your-email-password
ADMIN_USERNAME=admin
ADMIN_PASSWORD=securepassword



Initialize Database:

from app import app, db
with app.app_context():
    db.create_all()
    from models import User
    from utils import hash_password
    admin = User(
        username='admin',
        email='admin@example.com',
        password=hash_password('securepassword'),
        is_admin=True
    )
    db.session.add(admin)
    db.session.commit()



Run Locally:

python 01_app.py

Visit http://127.0.0.1:5000.

For production deployment, see the README.
