from flask import Flask, render_template, request, redirect, url_for, flash, session, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf import FlaskForm, CSRFProtect
from wtforms import StringField, PasswordField, SubmitField
from wtforms.validators import DataRequired, Email, EqualTo
from dotenv import load_dotenv
from datetime import datetime, timedelta
import os
import schedule
import time
import threading
import json
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from models import User, Score, OTP
from sudoku import generate_sudoku
from utils import hash_password, verify_password, generate_otp, send_email, generate_captcha, validate_board, format_leaderboard_for_pdf, sanitize_input

load_dotenv()
app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'fallback-secret-key')
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///sudoku.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SESSION_COOKIE_SECURE'] = True
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
csrf = CSRFProtect(app)
limiter = Limiter(app, key_func=get_remote_address)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Forms for CSRF protection
class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Login')

class RegisterForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired()])
    confirm_password = PasswordField('Confirm Password', validators=[DataRequired(), EqualTo('password')])
    captcha = StringField('CAPTCHA', validators=[DataRequired()])
    submit = SubmitField('Register')

class ForgotPasswordForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    captcha = StringField('CAPTCHA', validators=[DataRequired()])
    submit = SubmitField('Send OTP')

class ResetPasswordForm(FlaskForm):
    otp = StringField('OTP', validators=[DataRequired()])
    password = PasswordField('New Password', validators=[DataRequired()])
    confirm_password = PasswordField('Confirm Password', validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField('Reset Password')

# Weekly digest
def send_weekly_digest():
    users = User.query.filter_by(email_digest=True).all()
    for user in users:
        scores = Score.query.filter_by(user_id=user.id).order_by(Score.time.asc()).limit(5).all()
        content = f"Hello {sanitize_input(user.username)},\n\nYour top scores this week:\n"
        content += '\n'.join([f"- {score.time:.1f} seconds on {score.date.strftime('%Y-%m-%d')}" for score in scores])
        send_email(user.email, content, 'Weekly Sudoku Digest')

schedule.every().monday.at('09:00').do(send_weekly_digest)

def run_schedule():
    while True:
        schedule.run_pending()
        time.sleep(60)

threading.Thread(target=run_schedule, daemon=True).start()

# Routes
@app.route('/')
def index():
    return render_template('02_index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        username = sanitize_input(form.username.data)
        user = User.query.filter_by(username=username).first()
        if user and verify_password(form.password.data, user.password):
            login_user(user)
            session['theme'] = session.get('theme', 'light')
            flash('Logged in successfully.')
            return redirect(url_for('index'))
        flash('Invalid username or password.')
    return render_template('03_login.html', form=form)

@app.route('/register', methods=['GET', 'POST'])
@limiter.limit('5 per minute')
def register():
    form = RegisterForm()
    captcha_question, captcha_answer = generate_captcha()
    if form.validate_on_submit():
        if form.captcha.data != captcha_answer:
            flash('Invalid CAPTCHA.')
            return render_template('04_register.html', form=form, captcha_question=captcha_question)
        username = sanitize_input(form.username.data)
        email = sanitize_input(form.email.data)
        if User.query.filter_by(username=username).first() or User.query.filter_by(email=email).first():
            flash('Username or email already exists.')
            return render_template('04_register.html', form=form, captcha_question=captcha_question)
        hashed = hash_password(form.password.data)
        if not hashed:
            return render_template('04_register.html', form=form, captcha_question=captcha_question)
        user = User(username=username, email=email, password=hashed)
        db.session.add(user)
        db.session.commit()
        flash('Registered successfully. Please log in.')
        return redirect(url_for('login'))
    return render_template('04_register.html', form=form, captcha_question=captcha_question)

@app.route('/forgot_password', methods=['GET', 'POST'])
@limiter.limit('3 per minute')
def forgot_password():
    form = ForgotPasswordForm()
    captcha_question, captcha_answer = generate_captcha()
    if form.validate_on_submit():
        if form.captcha.data != captcha_answer:
            flash('Invalid CAPTCHA.')
            return render_template('05_forgot_password.html', form=form, captcha_question=captcha_question)
        email = sanitize_input(form.email.data)
        user = User.query.filter_by(email=email).first()
        if not user:
            flash('Email not found.')
            return render_template('05_forgot_password.html', form=form, captcha_question=captcha_question)
        otp = generate_otp()
        expires_at = datetime.utcnow() + timedelta(minutes=10)
        otp_entry = OTP.query.filter_by(email=email).first()
        if otp_entry:
            otp_entry.otp = otp
            otp_entry.expires_at = expires_at
        else:
            otp_entry = OTP(email=email, otp=otp, expires_at=expires_at)
            db.session.add(otp_entry)
        db.session.commit()
        if send_email(email, f'Your OTP is {otp}', 'Sudoku App - OTP'):
            flash('OTP sent to your email.')
            return redirect(url_for('reset_password', email=email))
        return render_template('05_forgot_password.html', form=form, captcha_question=captcha_question)
    return render_template('05_forgot_password.html', form=form, captcha_question=captcha_question)

@app.route('/reset_password', methods=['GET', 'POST'])
def reset_password():
    form = ResetPasswordForm()
    if form.validate_on_submit():
        otp_entry = OTP.query.filter_by(otp=sanitize_input(form.otp.data)).first()
        if not otp_entry or otp_entry.expires_at < datetime.utcnow():
            flash('Invalid or expired OTP.')
            return render_template('06_reset_password.html', form=form)
        user = User.query.filter_by(email=otp_entry.email).first()
        if user:
            hashed = hash_password(form.password.data)
            if not hashed:
                return render_template('06_reset_password.html', form=form)
            user.password = hashed
            db.session.delete(otp_entry)
            db.session.commit()
            flash('Password reset successfully.')
            return redirect(url_for('login'))
        flash('User not found.')
    return render_template('06_reset_password.html', form=form, email=request.args.get('email', ''))

@app.route('/resend_otp', methods=['POST'])
@limiter.limit('1 per minute', key_func=lambda: request.form['email'])
def resend_otp():
    email = sanitize_input(request.form['email'])
    user = User.query.filter_by(email=email).first()
    if not user:
        flash('Email not found.')
        return redirect(url_for('forgot_password'))
    otp = generate_otp()
    expires_at = datetime.utcnow() + timedelta(minutes=10)
    otp_entry = OTP.query.filter_by(email=email).first()
    if otp_entry:
        otp_entry.otp = otp
        otp_entry.expires_at = expires_at
    else:
        otp_entry = OTP(email=email, otp=otp, expires_at=expires_at)
        db.session.add(otp_entry)
    db.session.commit()
    if send_email(email, f'Your new OTP is {otp}', 'Sudoku App - OTP'):
        flash('OTP resent successfully.')
    return redirect(url_for('reset_password', email=email))

@app.route('/play/<difficulty>', methods=['GET', 'POST'])
def play(difficulty='medium'):
    if difficulty not in ['easy', 'medium', 'hard']:
        flash('Invalid difficulty level.')
        return redirect(url_for('index'))
    if request.method == 'POST':
        if not current_user.is_authenticated:
            flash('Guest scores are not saved.')
        try:
            user_board = json.loads(sanitize_input(request.form.get('board', '[]')))
        except json.JSONDecodeError:
            flash('Invalid board data.')
            return redirect(url_for('play', difficulty=difficulty))
        solution = session.get('solution')
        if not solution or not validate_board(user_board):
            flash('Invalid board data.')
            return redirect(url_for('play', difficulty=difficulty))
        if user_board == session['solution']:
            time_taken = float(request.form.get('time', 0))
            if current_user.is_authenticated:
                score = Score(user_id=current_user.id, time=time_taken)
                db.session.add(score)
                db.session.commit()
                flash('Puzzle solved! Score saved.')
            else:
                flash('Puzzle solved! Log in to save your score.')
            return redirect(url_for('leaderboard'))
        flash('Puzzle not solved yet.')
    puzzle, solution = generate_sudoku(difficulty)
    session['puzzle'] = puzzle
    session['solution'] = solution
    session['hints_used'] = 0
    return render_template('07_play.html', puzzle=puzzle, difficulty=difficulty)

@app.route('/hint', methods=['POST'])
def hint():
    if session.get('hints_used', 0) >= 3:
        flash('No more hints available.')
        return redirect(url_for('play', difficulty=request.form['difficulty']))
    puzzle = session.get('puzzle')
    solution = session.get('solution')
    if not puzzle or not solution:
        flash('Invalid session data.')
        return redirect(url_for('index'))
    for i in range(9):
        for j in range(9):
            if puzzle[i][j] == 0:
                puzzle[i][j] = solution[i][j]
                session['puzzle'] = puzzle
                session['hints_used'] = session.get('hints_used', 0) + 1
                return redirect(url_for('play', difficulty=request.form['difficulty']))
    return redirect(url_for('play', difficulty=request.form['difficulty']))

@app.route('/leaderboard')
def leaderboard():
    leaderboard_data = db.session.query(
        User.username,
        func.min(Score.time).label('best_time')
    ).join(Score, User.id == Score.user_id
    ).group_by(User.id
    ).order_by(func.min(Score.time).asc()
    ).all()
    return render_template('08_leaderboard.html', leaderboard=leaderboard_data)

@app.route('/download_leaderboard')
@login_required
def download_leaderboard():
    seven_days_ago = datetime.utcnow() - timedelta(days=7)
    scores = Score.query.filter(Score.date >= seven_days_ago).all()
    pdf = canvas.Canvas('leaderboard.pdf', pagesize=letter)
    pdf.drawString(100, 750, 'Leaderboard - Last 7 Days')
    y = 700
    for line in format_leaderboard_for_pdf(scores):
        pdf.drawString(100, y, line)
        y -= 20
    pdf.save()
    return send_file('leaderboard.pdf', as_attachment=True)

@app.route('/admin')
@login_required
def admin_dashboard():
    if not current_user.is_admin:
        flash('Access denied.')
        return redirect(url_for('index'))
    users = User.query.all()
    return render_template('09_admin.html', users=users)

@app.route('/toggle_theme')
def toggle_theme():
    session['theme'] = 'dark' if session.get('theme') == 'light' else 'light'
    return redirect(request.referrer or url_for('index'))

@app.route('/toggle_digest', methods=['POST'])
@login_required
def toggle_digest():
    current_user.email_digest = not current_user.email_digest
    db.session.commit()
    flash('Email digest preference updated.')
    return redirect(url_for('index'))

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Logged out successfully.')
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=os.getenv('FLASK_ENV') == 'development')
