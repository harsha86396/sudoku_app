import os
import psycopg
from psycopg.rows import dict_row
import random
import io
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, send_file, g
from flask_mail import Mail, Message
from werkzeug.security import generate_password_hash, check_password_hash
import threading
import schedule
import time as time_mod
from datetime import datetime, timedelta
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

# Flask-Mail configuration
app.config['MAIL_SERVER'] = config.SMTP_SERVER
app.config['MAIL_PORT'] = config.SMTP_PORT
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = config.SMTP_USER
app.config['MAIL_PASSWORD'] = config.SMTP_PASS
app.config['MAIL_DEFAULT_SENDER'] = config.SMTP_USER
mail = Mail(app)

# Safe init: auto create tables if missing
def ensure_schema():
    logger.info("Ensuring schema for PostgreSQL database")
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        logger.error("DATABASE_URL environment variable is not set")
        raise ValueError("DATABASE_URL environment variable is not set")
    con = psycopg.connect(db_url, row_factory=dict_row)
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
    logger.info("Generated CAPTCHA: %s, session_captcha=%s", captcha_q, session['captcha'])
    return render_template('index.html', msg=msg, err=err, captcha_q=captcha_q)

@app.route('/register', methods=['POST'])
def register():
    name = request.form.get('name', '').strip()
    email = request.form.get('email', '').strip()
    password = request.form.get('password', '').strip()
    captcha = request.form.get('captcha', '').strip()
    logger.info("Register attempt: name='%s', email='%s', password='%s', captcha='%s', session_captcha='%s', session=%s", 
                name, email, '***' if password else '', captcha, session.get('captcha'), dict(session))
    if not (name and email and password and captcha):
        session['err'] = 'All fields are required'
        logger.warning("Registration failed: missing fields - name=%s, email=%s, password=%s, captcha=%s", 
                       name, email, '***' if password else '', captcha)
        return redirect(url_for('index'))
    if captcha != session.get('captcha'):
        session['err'] = 'Invalid CAPTCHA'
        logger.warning("Registration failed: invalid CAPTCHA - received=%s, expected=%s", captcha, session.get('captcha'))
        return redirect(url_for('index'))
    try:
        db = get_db()
        cur = db.cursor()
        password_hash = generate_password_hash(password)
        cur.execute("INSERT INTO users (name, email, password_hash) VALUES (%s, %s, %s)", (name, email, password_hash))
        db.commit()
        session.pop('err', None)  # Clear any existing error
        session['msg'] = 'Registration successful! Please log in.'
        logger.info("Registration successful for %s", email)
        return redirect(url_for('index'))
    except psycopg.IntegrityError:
        session['err'] = 'Email already registered'
        logger.warning("Registration failed: email %s already registered", email)
        return redirect(url_for('index'))
    except Exception as e:
        logger.exception("Registration failed: %s", e)
        session['err'] = 'Registration failed'
        return redirect(url_for('index'))

@app.route('/login', methods=['POST'])
def login():
    email = request.form.get('email', '').strip()
    password = request.form.get('password', '').strip()
    logger.info("Login attempt: email='%s', password='%s'", email, '***' if password else '')
    if not (email and password):
        session['err'] = 'Email and password are required'
        logger.warning("Login failed: missing fields - email=%s, password=%s", email, '***' if password else '')
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
            session.pop('err', None)  # Clear any existing error
            logger.info("Login successful for %s", email)
            return redirect(url_for('dashboard'))
        session['err'] = 'Invalid email or password'
        logger.warning("Login failed: invalid email or password for %s", email)
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
    rows = []
    try:
        cur.execute("""
            SELECT u.name, MIN(r.seconds) as best, COUNT(r.id) as games
            FROM users u LEFT JOIN results r ON u.id = r.user_id
            GROUP BY u.name
            HAVING COUNT(r.id) > 0
            ORDER BY best ASC NULLS LAST LIMIT 10
        """)
        rows = cur.fetchall()
        logger.info("Fetched %d leaderboard rows: %s", len(rows), rows)
    except Exception as e:
        logger.exception("Leaderboard query failed: %s", e)
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
    rows = [(row['seconds'], row['played_at']) for row in cur.fetchall()]  # Convert to list of tuples
    logger.info("Fetched %d results for PDF for user_id=%s: %s", len(rows), session['user_id'], rows)
    out_stream = io.BytesIO()
    generate_last7_pdf(user['name'], user['email'], rows, out_stream)
    out_stream.seek(0)
    return send_file(out_stream, download_name=f"sudoku_{user['name']}_last7.pdf", as_attachment=True)

@app.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        captcha = request.form.get('captcha', '').strip()
        logger.info("Forgot password attempt: email='%s', captcha='%s', session_captcha='%s'", email, captcha, session.get('captcha'))
        if not (email and captcha):
            session['err'] = 'Email and CAPTCHA are required'
            logger.warning("Forgot password failed: missing fields - email=%s, captcha=%s", email, captcha)
            return redirect(url_for('forgot_password'))
        if captcha != session.get('captcha'):
            session['err'] = 'Invalid CAPTCHA'
            logger.warning("Forgot password failed: invalid CAPTCHA - received=%s, expected=%s", captcha, session.get('captcha'))
            return redirect(url_for('forgot_password'))
        try:
            db = get_db()
            cur = db.cursor()
            cur.execute("SELECT last_request_ts FROM otp_rate_limit WHERE email = %s", (email,))
            last_request = cur.fetchone()
            now = time_mod.time()
            if last_request and now - last_request['last_request_ts'] < config.OTP_RATE_LIMIT_SECONDS:
                session['err'] = 'Please wait before requesting another OTP'
                logger.warning("Forgot password failed: rate limit exceeded for %s", email)
                return redirect(url_for('forgot_password'))
            cur.execute("SELECT id FROM users WHERE email = %s", (email,))
            user = cur.fetchone()
            if not user:
                session['err'] = 'Email not found'
                logger.warning("Forgot password failed: email not found - %s", email)
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
                    msg = Message("Sudoku Password Reset OTP", recipients=[email])
                    msg.body = f"Your OTP for password reset is {otp}. It expires in {config.OTP_EXP_MINUTES} minutes."
                    logger.info("Attempting to send OTP email to %s", email)
                    mail.send(msg)
                    cur.execute("INSERT INTO email_logs (recipient, subject, status) VALUES (%s, %s, %s)", 
                                (email, "Sudoku Password Reset OTP", 'sent'))
                    db.commit()
                    logger.info("OTP email sent to %s", email)
                else:
                    logger.warning("EMAIL_ENABLED is False, skipping email for %s", email)
                session['reset_email'] = email
                session['reset_token'] = token
                session['msg'] = 'OTP sent to your email'
                logger.info("Forgot password successful: redirecting to reset_password for %s", email)
                return redirect(url_for('reset_password'))
            except Exception as e:
                db.rollback()
                logger.exception("Forgot password failed: %s", e)
                cur.execute("INSERT INTO email_logs (recipient, subject, status) VALUES (%s, %s, %s)", 
                            (email, "Sudoku Password Reset OTP", f'failed: {str(e)}'))
                db.commit()
                session['err'] = 'Failed to send OTP'
                return redirect(url_for('forgot_password'))
        except Exception as e:
            logger.exception("Forgot password query failed: %s", e)
            session['err'] = 'Failed to process request'
            return redirect(url_for('forgot_password'))
    captcha_q = f"{random.randint(1,10)} + {random.randint(1,10)}"
    session['captcha'] = str(eval(captcha_q))
    logger.info("Generated CAPTCHA for forgot_password: %s, session_captcha=%s", captcha_q, session['captcha'])
    return render_template('forgot_password.html', captcha_q=captcha_q)

@app.route('/reset_password', methods=['GET', 'POST'])
def reset_password():
    if request.method == 'POST':
        email = session.get('reset_email')
        token = session.get('reset_token')
        otp = request.form.get('otp')
        password = request.form.get('password')
        confirm = request.form.get('confirm')
        logger.info("Reset password attempt: email='%s', otp='%s'", email, otp)
        if not (email and token and otp and password and confirm):
            session['err'] = 'All fields are required'
            logger.warning("Reset password failed: missing fields")
            return redirect(url_for('reset_password'))
        if password != confirm:
            session['err'] = 'Passwords do not match'
            logger.warning("Reset password failed: passwords do not match")
            return redirect(url_for('reset_password'))
        db = get_db()
        cur = db.cursor()
        cur.execute("SELECT user_id, otp_hash, expires_at FROM password_resets WHERE token = %s AND used = 0", (token,))
        reset = cur.fetchone()
        if not reset or reset['expires_at'] < datetime.utcnow():
            session['err'] = 'Invalid or expired OTP'
            logger.warning("Reset password failed: invalid or expired token")
            return redirect(url_for('reset_password'))
        if not check_password_hash(reset['otp_hash'], otp):
            session['err'] = 'Invalid OTP'
            logger.warning("Reset password failed: invalid OTP")
            return redirect(url_for('reset_password'))
        try:
            password_hash = generate_password_hash(password)
            cur.execute("UPDATE users SET password_hash = %s WHERE id = %s", (password_hash, reset['user_id']))
            cur.execute("UPDATE password_resets SET used = 1 WHERE token = %s", (token,))
            db.commit()
            session.pop('reset_email', None)
            session.pop('reset_token', None)
            session['msg'] = 'Password reset successfully! Please log in.'
            logger.info("Password reset successful for %s", email)
            return redirect(url_for('index'))
        except Exception as e:
            logger.exception("Reset password failed: %s", e)
            session['err'] = 'Failed to reset password'
            return redirect(url_for('reset_password'))
    if not session.get('reset_email'):
        logger.warning("Reset password accessed without reset_email in session")
        return redirect(url_for('forgot_password'))
    return render_template('reset_password.html', email=session.get('reset_email'))

@app.route('/resend_otp', methods=['POST'])
def resend_otp():
    email = session.get('reset_email')
    if not email:
        logger.warning("Resend OTP accessed without reset_email in session")
        return redirect(url_for('forgot_password'))
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT last_request_ts FROM otp_rate_limit WHERE email = %s", (email,))
    last_request = cur.fetchone()
    now = time_mod.time()
    if last_request and now - last_request['last_request_ts'] < config.OTP_RATE_LIMIT_SECONDS:
        session['err'] = 'Please wait before requesting another OTP'
        logger.warning("Resend OTP failed: rate limit exceeded for %s", email)
        return redirect(url_for('reset_password'))
    cur.execute("SELECT id FROM users WHERE email = %s", (email,))
    user = cur.fetchone()
    if not user:
        session['err'] = 'Email not found'
        logger.warning("Resend OTP failed: email not found - %s", email)
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
            msg = Message("Sudoku Password Reset OTP", recipients=[email])
            msg.body = f"Your new OTP for password reset is {otp}. It expires in {config.OTP_EXP_MINUTES} minutes."
            logger.info("Attempting to resend OTP email to %s", email)
            mail.send(msg)
            cur.execute("INSERT INTO email_logs (recipient, subject, status) VALUES (%s, %s, %s)", 
                        (email, "Sudoku Password Reset OTP", 'sent'))
            db.commit()
            logger.info("Resent OTP email to %s", email)
        else:
            logger.warning("EMAIL_ENABLED is False, skipping resend email for %s", email)
        session['reset_token'] = token
        session['msg'] = 'New OTP sent to your email'
        logger.info("Resend OTP successful for %s", email)
        return redirect(url_for('reset_password'))
    except Exception as e:
        db.rollback()
        logger.exception("Resend OTP failed: %s", e)
        cur.execute("INSERT INTO email_logs (recipient, subject, status) VALUES (%s, %s, %s)", 
                    (email, "Sudoku Password Reset OTP", f'failed: {str(e)}'))
        db.commit()
        session['err'] = 'Failed to resend OTP'
        return redirect(url_for('reset_password'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/admin', methods=['GET', 'POST'])
def admin():
    if session.get('admin'):
        return redirect(url_for('admin_dashboard'))
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        logger.info("Admin login attempt: email=%s", email)
        if email == app.config.get('ADMIN_EMAIL') and password == app.config.get('ADMIN_PASSWORD'):
            session['admin'] = True
            logger.info("Admin login successful")
            return redirect(url_for('admin_dashboard'))
        session['err'] = 'Invalid admin credentials'
        logger.warning("Admin login failed: invalid credentials")
        return redirect(url_for('admin'))
    return render_template('admin_login.html')

@app.route('/admin/dashboard')
def admin_dashboard():
    if not session.get('admin'):
        logger.warning("Unauthorized access to /admin/dashboard")
        return redirect(url_for('admin'))
    return render_template('admin_dashboard.html')

@app.route('/admin/users')
def admin_users():
    if not session.get('admin'):
        logger.warning("Unauthorized access to /admin/users")
        return redirect(url_for('admin'))
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute("""
            SELECT u.id, u.name, u.email, COUNT(r.id) as games, MIN(r.seconds) as best
            FROM users u LEFT JOIN results r ON u.id = r.user_id
            GROUP BY u.id ORDER BY games DESC
        """)
        rows = cur.fetchall()
        logger.info("Fetched %d users for admin dashboard", len(rows))
    except Exception as e:
        logger.exception("Admin users query failed: %s", e)
        rows = []
    return render_template('admin_users.html', rows=rows)

@app.route('/admin/email_logs')
def admin_email_logs():
    if not session.get('admin'):
        logger.warning("Unauthorized access to /admin/email_logs")
        return redirect(url_for('admin'))
    db = get_db()
    cur = db.cursor()
    logs = []
    try:
        cur.execute("SELECT id, recipient, subject, status, created_at FROM email_logs ORDER BY created_at DESC")
        logs = cur.fetchall()
        logger.info("Fetched %d email logs for admin dashboard", len(logs))
    except Exception as e:
        logger.exception("Admin email logs query failed: %s", e)
    return render_template('admin_emails.html', logs=logs)

@app.route('/admin/password_resets')
def admin_password_resets():
    if not session.get('admin'):
        logger.warning("Unauthorized access to /admin/password_resets")
        return redirect(url_for('admin'))
    db = get_db()
    cur = db.cursor()
    resets = []
    try:
        cur.execute("SELECT id, user_id, expires_at, created_at FROM password_resets ORDER BY created_at DESC")
        resets = cur.fetchall()
        logger.info("Fetched %d password resets for admin dashboard", len(resets))
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
        'user_count': user_count,
        'session': dict(session)
    })

# Email sending
def send_email(recipient, subject, body, user_id):
    if not app.config.get('EMAIL_ENABLED'):
        logger.warning("Email sending skipped: EMAIL_ENABLED is False")
        return
    try:
        msg = Message(subject, recipients=[recipient])
        msg.body = body
        mail.send(msg)
        db = get_db()
        cur = db.cursor()
        cur.execute("INSERT INTO email_logs (recipient, subject, status) VALUES (%s, %s, %s)", (recipient, subject, 'sent'))
        db.commit()
        logger.info("Email sent to %s: %s", recipient, subject)
    except Exception as e:
        logger.exception("Email sending failed for %s: %s", recipient, e)
        db = get_db()
        cur = db.cursor()
        cur.execute("INSERT INTO email_logs (recipient, subject, status) VALUES (%s, %s, %s)", 
                    (recipient, subject, f'failed: {str(e)}'))
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
