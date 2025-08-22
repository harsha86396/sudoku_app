Sudoku Secure Pro 🎮

Welcome to Sudoku Secure Pro, a modern web-based Sudoku game built with Flask, featuring easy, medium, and hard difficulty levels, secure authentication, and a sleek UI with Tailwind CSS. Whether you're a casual player or a developer, this project offers an engaging experience with robust features.

Features 🌟





Multiple Difficulty Levels: Choose from Easy (35 cells removed), Medium (45 cells removed), or Hard (55 cells removed) puzzles.



Secure Authentication: Register, login, and reset passwords with OTP (email-based) and CAPTCHA protection.



Guest Mode: Play without an account (scores not saved).



Leaderboard: View top scores and download a PDF of the last 7 days' rankings.



Weekly Email Digest: Opt-in for weekly score updates.



Admin Dashboard: Manage users (admin-only).



Dark/Light Theme: Toggle between themes for a personalized experience.



Responsive Design: Works on desktop and mobile with Tailwind CSS.

Getting Started 🚀

Prerequisites





Python 3.8+



Git



A Gmail account for SMTP (for OTP and digests)

Installation





Clone the repository:

git clone https://github.com/harsha86396/sudoku_app.git
cd sudoku_app



Install dependencies:

pip install -r 06_requirements.txt



Set up environment variables in .env:

FLASK_ENV=development
SECRET_KEY=your-secret-key
DATABASE_URL=sqlite:///sudoku.db
EMAIL_FROM=your-email@gmail.com
EMAIL_PASSWORD=your-email-password
ADMIN_USERNAME=admin
ADMIN_PASSWORD=securepassword



Initialize the database:

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



Run locally:

python 01_app.py

Visit http://127.0.0.1:5000.

Deployment

Deploy to Render:





Push to GitHub (ensure .env is in .gitignore).



Create a Web Service on Render, select the repository.



Set environment variables in Render’s dashboard.



Use PostgreSQL for production (update DATABASE_URL).



Build Command: pip install -r 06_requirements.txt



Start Command: gunicorn app:app

Usage 📖





Play: Choose a difficulty (Easy, Medium, Hard) from the homepage.



Guest Mode: Play without logging in; scores won’t save.



Leaderboard: View top scores or download a PDF.



Admin: Access /admin with admin credentials to manage users.



Reset Password: Use the forgot password flow with OTP.

See docs/01_installation.md for detailed instructions.

Contributing 🤝

We welcome contributions! Check docs/03_contributing.md for guidelines.

License 📜

MIT License. See LICENSE for details.



Built with 💻 by harsha86396. Enjoy the game! 🎉
