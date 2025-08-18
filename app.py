import os
import psycopg2
from psycopg2.extras import RealDictCursor
import random
import io
import smtplib
import ssl
import threading
import schedule
import time as time_mod
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, send_file, g
from werkzeug.security import generate_password_hash, check_password_hash
from email.mime.text import MIMEText
import logging

# utils
from utils.sudoku import make_puzzle
from utils.pdf_utils import generate_last7_pdf
import config as config
from db import get_db, close_db

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Flask app
app = Flask(__name__)
app.config.from_object(config)
app.secret_key = config.SECRET_KEY
app.teardown_appcontext(close_db)

# Safe init: auto create tables if missing
def ensure_schema():
    logger.info("Ensuring schema for PostgreSQL database")
    con = psycopg2.connect(os.environ.get("DATABASE_URL"), cursor_factory=RealDictCursor)
    cur = con.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY,
        name TEXT,
        email TEXT UNIQUE,
        password_hash TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS results (
        id SERIAL PRIMARY KEY,
        user_id INTEGER,
        seconds INTEGER,
        played_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )""")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS email_logs (
        id SERIAL PRIMARY KEY,
        recipient TEXT,
        subject TEXT,
        status TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS password_resets (
        id SERIAL PRIMARY KEY,
        user_id INTEGER,
        token TEXT,
        otp_hash TEXT,
        expires_at TIMESTAMP,
        used INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS otp_rate_limit (
        email TEXT PRIMARY KEY,
        last_request_ts REAL
    )""")
    con.commit()
    con.close()
    logger.info("Database schema ensured")

# Routes
@app.route('/')
def index():
    msg = session.pop('msg', None)
    err = session.pop('err', None)
    captcha_q = f"{random.randint(1,10)} + {random.randint(1,10)}"
    session['captcha'] = str(eval(captcha_q))
    return render_template('index.html', msg=msg, err=err, captcha_q=captcha_q)

@app.route('/register', methods=['POST'])
def register():
    name = request.form.get('name')
    email = request.form.get('email')
    password = request.form.get('password')
    captcha = request.form.get('captcha')
    if not (name and email and password and captcha):
        session['err'] = 'All fields are required'
        return redirect(url_for('index'))
    if captcha != session.get('captcha'):
        session['err'] = 'Invalid CAPTCHA'
        return redirect(url_for('index'))
    try:
        db = get_db()
        cur = db.cursor()
        password_hash = generate_password_hash(password)
        cur.execute("INSERT INTO users (name, email, password_hash) VALUES (%s, %s, %s)", (name, email, password_hash))
        db.commit()
        session['msg'] = 'Registration successful! Please log in.'
        return redirect(url_for('index'))
    except psycopg2.IntegrityError:
        session['err'] = 'Email already registered'
        return redirect(url_for('index'))
    except Exception as e:
        logger.exception("Registration failed: %s", e)
        session['err'] = 'Registration failed'
        return redirect(url_for('index'))

@app.route('/login', methods=['POST'])
def login():
    email = request.form.get('email')
    password = request.form.get('password')
    if not (email and password):
        session['err'] = 'Email and password are required'
        return redirect(url_for('index'))
    try:
        db = get_db()
        cur = db.cursor()
        cur.execute("SELECT id, name, password_hash FROM users WHERE email = %s", (email,))
        user = cur.fetchone()
        if user and check_password_hash(user['password_hash'], password):
            session['user_id'] = user['id']
            session['name'] = user['name']
            session['hints_left'] = 3
            return redirect(url_for('dashboard'))
        session['err'] = 'Invalid email or password'
        return redirect(url_for('index'))
    except Exception as e:
        logger.exception("Login failed: %s", e)
        session['err'] = 'Login failed'
        return redirect(url_for('index'))

@app.route('/dashboard')
def dashboard():
    if not session.get('user_id'):
        return redirect(url_for('index'))
    return render_template('dashboard.html', name=session.get('name'))

@app.route('/play', methods=['GET', 'POST'])
def play():
    if not session.get('user_id'):
        return redirect(url_for('index'))
    if request.method == 'POST':
        difficulty = request.form.get('difficulty', 'medium')
        puzzle, solution = make_puzzle(difficulty)
        session['puzzle'] = puzzle
        session['solution'] = solution
        session['hints_left'] = 3
        session['start_time'] = time_mod.time()
        return redirect(url_for('play'))
    return render_template('play.html')

@app.route('/hint', methods=['POST'])
def hint():
    if not session.get('user_id') or session.get('hints_left', 0) <= 0:
        return jsonify({'error': 'No hints left or not logged in'})
    puzzle = session.get('puzzle')
    solution = session.get('solution')
    if not (puzzle and solution):
        return jsonify({'error': 'No active puzzle'})
    empty = [(r, c) for r in range(9) for c in range(9) if puzzle[r][c] == 0]
    if not empty:
        return jsonify({'error': 'No empty cells'})
    r, c = random.choice(empty)
    session['hints_left'] -= 1
    session['puzzle'][r][c] = solution[r][c]
    return jsonify({'row': r, 'col': c, 'value': solution[r][c], 'hints_left': session['hints_left']})

@app.route('/submit', methods=['POST'])
def submit():
    if not session.get('user_id'):
        return jsonify({'error': 'Not logged in'})
    puzzle = session.get('puzzle')
    solution = session.get('solution')
    start_time = session.get('start_time')
    if not (puzzle and solution and start_time):
        return jsonify({'error': 'No active puzzle'})
    seconds = int(time_mod.time() - start_time)
    try:
        db = get_db()
        cur = db.cursor()
        cur.execute("INSERT INTO results (user_id, seconds) VALUES (%s, %s)", (session['user_id'], seconds))
        db.commit()
        session.pop('puzzle', None)
        session.pop('solution', None)
        session.pop('start_time', None)
        session.pop('hints_left', None)
        return jsonify({'success': True, 'seconds': seconds})
    except Exception as e:
        logger.exception("Submit failed: %s", e)
        return jsonify({'error': 'Failed to save result'})

@app.route('/leaderboard')
def leaderboard():
    db = get_db()
    cur = db.cursor()
    cur.execute("""
        SELECT u.name, MIN(r.seconds) as best, COUNT(r.id) as games
        FROM users u LEFT JOIN results r ON u.id = r.user_id
        GROUP BY u.id ORDER BY best ASC LIMIT 10
    """)
    rows = cur.fetchall()
    return render_template('leaderboard.html', rows=rows)

@app.route('/download_pdf')
def download_pdf():
    if not session.get('user_id'):
        return redirect(url_for('index'))
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT name, email FROM users WHERE id = %s", (session['user_id'],))
    user = cur.fetchone()
    since = datetime.utcnow() - timedelta(days=7)
    cur.execute("SELECT seconds, played_at FROM results WHERE user_id = %s AND played_at >= %s", (session['user_id'], since))
    rows = cur.fetchall()
    out_stream = io.BytesIO()
    generate_last7_pdf(user['name'], user['email'], rows, out_stream)
    out_stream.seek(0)
    return send_file(out_stream, download_name=f"sudoku_{user['name']}_last7.pdf", as_attachment=True)

@app.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email')
        captcha = request.form.get('captcha')
        if not (email and captcha):
            session['err'] = 'Email and CAPTCHA are required'
            return redirect(url_for('forgot_password'))
        if captcha != session.get('captcha'):
            session['err'] = 'Invalid CAPTCHA'
            return redirect(url_for('forgot_password'))
        db = get_db()
        cur = db.cursor()
        cur.execute("SELECT last_request_ts FROM otp_rate_limit WHERE email = %s", (email,))
        last_request = cur.fetchone()
        now = time_mod.time()
        if last_request and now - last_request['last_request_ts'] < config.OTP_RATE_LIMIT_SECONDS:
            session['err'] = 'Please wait before requesting another OTP'
            return redirect(url_for('forgot_password'))
        cur.execute("SELECT id FROM users WHERE email = %s", (email,))
        user = cur.fetchone()
        if not user:
            session['err'] = 'Email not found'
            return redirect(url_for('forgot_password'))
        otp = ''.join([str(random.randint(0,9)) for _ in range(6)])
        otp_hash = generate_password_hash(otp)
        expires_at = datetime.utcnow() + timedelta(minutes=config.OTP_EXP_MINUTES)
        token = os.urandom(16).hex()
        try:
            cur.execute("INSERT INTO password_resets (user_id, token, otp_hash, expires_at) VALUES (%s, %s, %s, %s)", 
                        (user['id'], token, otp_hash, expires_at))
            cur.execute("INSERT INTO otp_rate_limit (email, last_request_ts) VALUES (%s, %s) ON CONFLICT (email) UPDATE SET last_request_ts = %s", 
                        (email, now, now))
            db.commit()
            if app.config.get('EMAIL_ENABLED'):
                body = f"Your OTP for password reset is {otp}. It expires in {config.OTP_EXP_MINUTES} minutes."
                send_email(email, "Sudoku Password Reset OTP", body, user['id'])
            session['reset_email'] = email
            session['reset_token'] = token
            session['msg'] = 'OTP sent to your email'
            return redirect(url_for('reset_password'))
        except Exception as e:
            logger.exception("Forgot password failed: %s", e)
            session['err'] = 'Failed to send OTP'
            return redirect(url_for('forgot_password'))
    captcha_q = f"{random.randint(1,10)} + {random.randint(1,10)}"
    session['captcha'] = str(eval(captcha_q))
    return render_template('forgot_password.html', captcha_q=captcha_q)

@app.route('/reset_password', methods=['GET', 'POST'])
def reset_password():
    if request.method == 'POST':
        email = session.get('reset_email')
        token = session.get('reset_token')
        otp = request.form.get('otp')
        password = request.form.get('password')
        confirm = request.form.get('confirm')
        if not (email and token and otp and password and confirm):
            session['err'] = 'All fields are required'
            return redirect(url_for('reset_password'))
        if password != confirm:
            session['err'] = 'Passwords do not match'
            return redirect(url_for('reset_password'))
        db = get_db()
        cur = db.cursor()
        cur.execute("SELECT user_id, otp_hash, expires_at FROM password_resets WHERE token = %s AND used = 0", (token,))
        reset = cur.fetchone()
        if not reset or reset['expires_at'] < datetime.utcnow():
            session['err'] = 'Invalid or expired OTP'
            return redirect(url_for('reset_password'))
        if not check_password_hash(reset['otp_hash'], otp):
            session['err'] = 'Invalid OTP'
            return redirect(url_for('reset_password'))
        try:
            password_hash = generate_password_hash(password)
            cur.execute("UPDATE users SET password_hash = %s WHERE id = %s", (password_hash, reset['user_id']))
            cur.execute("UPDATE password_resets SET used = 1 WHERE token = %s", (token,))
            db.commit()
            session.pop('reset_email', None)
            session.pop('reset_token', None)
            session['msg'] = 'Password reset successfully! Please log in.'
            return redirect(url_for('index'))
        except Exception as e:
            logger.exception("Reset password failed: %s", e)
            session['err'] = 'Failed to reset password'
            return redirect(url_for('reset_password'))
    if not session.get('reset_email'):
        return redirect(url_for('forgot_password'))
    return render_template('reset_password.html', email=session.get('reset_email'))

@app.route('/resend_otp', methods=['POST'])
def resend_otp():
    email = session.get('reset_email')
    if not email:
        return redirect(url_for('forgot_password'))
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT last_request_ts FROM otp_rate_limit WHERE email = %s", (email,))
    last_request = cur.fetchone()
    now = time_mod.time()
    if last_request and now - last_request['last_request_ts'] < config.OTP_RATE_LIMIT_SECONDS:
        session['err'] = 'Please wait before requesting another OTP'
        return redirect(url_for('reset_password'))
    cur.execute("SELECT id FROM users WHERE email = %s", (email,))
    user = cur.fetchone()
    if not user:
        session['err'] = 'Email not found'
        return redirect(url_for('forgot_password'))
    otp = ''.join([str(random.randint(0,9)) for _ in range(6)])
    otp_hash = generate_password_hash(otp)
    expires_at = datetime.utcnow() + timedelta(minutes=config.OTP_EXP_MINUTES)
    token = os.urandom(16).hex()
    try:
        cur.execute("UPDATE password_resets SET used = 1 WHERE user_id = %s AND used = 0", (user['id'],))
        cur.execute("INSERT INTO password_resets (user_id, token, otp_hash, expires_at) VALUES (%s, %s, %s, %s)", 
                    (user['id'], token, otp_hash, expires_at))
        cur.execute("INSERT INTO otp_rate_limit (email, last_request_ts) VALUES (%s, %s) ON CONFLICT (email) UPDATE SET last_request_ts = %s", 
                    (email, now, now))
        db.commit()
        if app.config.get('EMAIL_ENABLED'):
            body = f"Your new OTP for password reset is {otp}. It expires in {config.OTP_EXP_MINUTES} minutes."
            send_email(email, "Sudoku Password Reset OTP", body, user['id'])
        session['reset_token'] = token
        session['msg'] = 'New OTP sent to your email'
        return redirect(url_for('reset_password'))
    except Exception as e:
        logger.exception("Resend OTP failed: %s", e)
        session['err'] = 'Failed to resend OTP'
        return redirect(url_for('reset_password'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/admin', methods=['GET', 'POST'])
def admin():
    if session.get('admin'):
        return redirect(url_for('admin_users'))
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        if email == app.config.get('ADMIN_EMAIL') and password == app.config.get('ADMIN_PASSWORD'):
            session['admin'] = True
            return redirect(url_for('admin_users'))
        session['err'] = 'Invalid admin credentials'
        return redirect(url_for('admin'))
    return render_template('admin_login.html')

@app.route('/admin/users')
def admin_users():
    if not session.get('admin'):
        return redirect(url_for('admin'))
    db = get_db()
    cur = db.cursor()
    cur.execute("""
        SELECT u.id, u.name, u.email, COUNT(r.id) as games, MIN(r.seconds) as best
        FROM users u LEFT JOIN results r ON u.id = r.user_id
        GROUP BY u.id ORDER BY games DESC
    """)
    rows = cur.fetchall()
    return render_template('admin_users.html', rows=rows)

@app.route('/admin/email_logs')
def admin_email_logs():
    if not session.get('admin'):
        return redirect(url_for('admin'))
    db = get_db()
    cur = db.cursor()
    logs = []
    try:
        cur.execute("SELECT id, recipient, subject, status, created_at FROM email_logs ORDER BY created_at DESC")
        logs = cur.fetchall()
    except Exception as e:
        logger.exception("Admin email logs query failed: %s", e)
    return render_template('admin_emails.html', logs=logs)

@app.route('/admin/password_resets')
def admin_password_resets():
    if not session.get('admin'):
        return redirect(url_for('admin'))
    db = get_db()
    cur = db.cursor()
    resets = []
    try:
        cur.execute("SELECT id, user_id, expires_at, created_at FROM password_resets ORDER BY created_at DESC")
        resets = cur.fetchall()
    except Exception as e:
        logger.exception("Admin password resets query failed: %s", e)
    return render_template('admin_resets.html', resets=resets)

# Debug endpoint
@app.route('/debug/db_check')
def debug_db_check():
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT count(*) as user_count FROM users")
    user_count = cur.fetchone()['user_count']
    return jsonify({
        'db_url': os.environ.get("DATABASE_URL", "Not set"),
        'user_count': user_count
    })

# Email sending
def send_email(recipient, subject, body, user_id):
    if not app.config.get('EMAIL_ENABLED'):
        return
    msg = MIMEText(body)
    msg['Subject'] = subject
    msg['From'] = app.config.get('SMTP_USER')
    msg['To'] = recipient
    try:
        context = ssl.create_default_context()
        with smtplib.SMTP(app.config.get('SMTP_SERVER'), app.config.get('SMTP_PORT')) as server:
            server.starttls(context=context)
            server.login(app.config.get('SMTP_USER'), app.config.get('SMTP_PASS'))
            server.sendmail(app.config.get('SMTP_USER'), recipient, msg.as_string())
        db = get_db()
        cur = db.cursor()
        cur.execute("INSERT INTO email_logs (recipient, subject, status) VALUES (%s, %s, %s)", (recipient, subject, 'sent'))
        db.commit()
    except Exception as e:
        logger.exception("Email sending failed for %s: %s", recipient, e)
        db = get_db()
        cur = db.cursor()
        cur.execute("INSERT INTO email_logs (recipient, subject, status) VALUES (%s, %s, %s)", (recipient, subject, 'failed'))
        db.commit()

# Weekly digest
def send_weekly_digest():
    if not app.config.get("EMAIL_ENABLED") or not app.config.get("DIGEST_ENABLED"):
        return
    con = get_db()
    cur = con.cursor()
    since = datetime.utcnow() - timedelta(days=7)
    cur.execute("SELECT id, name, email FROM users")
    users = cur.fetchall()
    for u in users:
        uid, name, email = u["id"], u["name"], u["email"]
        cur.execute("SELECT COUNT(*), MIN(seconds), AVG(seconds) FROM results WHERE user_id = %s AND played_at >= %s", (uid, since))
        games, best, avg = cur.fetchone()
        if games and games > 0:
            body = f"Hi {name},\n\nWeekly Sudoku stats:\nGames: {games}\nBest: {int(best)}s\nAvg: {int(avg)}s"
            send_email(email, "Your Weekly Sudoku Progress", body, uid)
    con.close()

def scheduler_thread():
    while True:
        try:
            schedule.run_pending()
        except Exception as e:
            logger.exception("Scheduler error: %s", e)
        time_mod.sleep(60)

# Startup
ensure_schema()
if not os.environ.get("DISABLE_SCHEDULER"):
    schedule.every().sunday.at(app.config.get("DIGEST_IST_TIME", "18:00")).do(send_weekly_digest)
    threading.Thread(target=scheduler_thread, daemon=True).start()

if __name__ == "__main__":
    app.run(debug=True)
