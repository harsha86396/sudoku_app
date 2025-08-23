
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, send_file
import os, smtplib, ssl, io, random, time as time_mod, threading, schedule
from email.mime.text import MIMEText
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv

from utils.sudoku import make_puzzle
from utils.pdf_utils import generate_last7_pdf
import config as config
from database import get_db, init_db

load_dotenv()

app = Flask(__name__)
# Config precedence: env -> config.py default
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', getattr(config, 'SECRET_KEY', 'change-me'))
app.config['APP_NAME']   = getattr(config, 'APP_NAME', 'Sudoku')
app.config['ADMIN_EMAIL'] = os.environ.get('ADMIN_EMAIL', getattr(config, 'ADMIN_EMAIL', 'admin@sudoku.local'))
app.config['ADMIN_PASSWORD'] = os.environ.get('ADMIN_PASSWORD', getattr(config, 'ADMIN_PASSWORD', 'admin123'))

# Email config
app.config['EMAIL_ENABLED'] = os.environ.get('EMAIL_ENABLED', str(getattr(config,'EMAIL_ENABLED', False))).lower() == 'true'
app.config['SMTP_SERVER'] = os.environ.get('SMTP_SERVER', getattr(config,'SMTP_SERVER', 'smtp.gmail.com'))
app.config['SMTP_PORT'] = int(os.environ.get('SMTP_PORT', getattr(config,'SMTP_PORT', 587)))
app.config['SMTP_USER'] = os.environ.get('SMTP_USER', getattr(config,'SMTP_USER', ''))
app.config['SMTP_PASS'] = os.environ.get('SMTP_PASS', getattr(config,'SMTP_PASS', ''))
app.config['FROM_EMAIL'] = os.environ.get('FROM_EMAIL', f"{app.config['APP_NAME']} <{app.config['SMTP_USER']}>")

# OTP + digest
app.config['OTP_EXP_MINUTES'] = int(os.environ.get('OTP_EXP_MINUTES', getattr(config,'OTP_EXP_MINUTES', 10)))
app.config['OTP_RATE_LIMIT_SECONDS'] = int(os.environ.get('OTP_RATE_LIMIT_SECONDS', getattr(config,'OTP_RATE_LIMIT_SECONDS', 60)))
app.config['DIGEST_ENABLED'] = os.environ.get('DIGEST_ENABLED', str(getattr(config,'DIGEST_ENABLED', False))).lower() == 'true'
app.config['DIGEST_IST_TIME'] = os.environ.get('DIGEST_IST_TIME', getattr(config,'DIGEST_IST_TIME', '18:00'))

# --- Helpers ---
def send_email(to_email, subject, body, user_id=None):
    # best-effort; never block
    status, detail = 'skipped', 'email disabled'
    if app.config['EMAIL_ENABLED'] and app.config['SMTP_USER'] and app.config['SMTP_PASS']:
        try:
            msg = MIMEText(body)
            msg['Subject'] = subject
            msg['From'] = app.config['FROM_EMAIL']
            msg['To'] = to_email
            context = ssl.create_default_context()
            with smtplib.SMTP(app.config['SMTP_SERVER'], app.config['SMTP_PORT']) as server:
                server.starttls(context=context)
                server.login(app.config['SMTP_USER'], app.config['SMTP_PASS'])
                server.sendmail(app.config['SMTP_USER'], [to_email], msg.as_string())
            status, detail = 'sent', 'ok'
        except Exception as e:
            status, detail = 'error', str(e)
    # log regardless
    try:
        conn = get_db(); cur = conn.cursor()
        cur.execute("INSERT INTO email_logs(user_id, to_email, subject, status, detail) VALUES(?,?,?,?,?)",
                    (user_id, to_email, subject, status, detail))
        conn.commit()
        cur.close(); conn.close()
    except Exception:
        pass

def new_captcha():
    a, b = random.randint(1,9), random.randint(1,9)
    token = str(random.randint(100000,999999))
    session['captcha_'+token] = a + b
    return f"{a} + {b} = ?", token

def check_captcha(token, answer):
    if not token: return False
    key = 'captcha_'+token
    val = session.get(key)
    try:
        del session[key]
    except Exception:
        pass
    try:
        return int(answer) == int(val)
    except Exception:
        return False

def require_login():
    return 'user_id' in session

# --- Routes ---
@app.route('/healthz')
def healthz():
    return jsonify(ok=True, time=datetime.utcnow().isoformat()+'Z')

@app.route('/')
def index():
    return render_template('index.html', app_name=app.config['APP_NAME'])

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'GET':
        q,t = new_captcha()
        return render_template('login.html', captcha_q=q, captcha_t=t)

    email = request.form.get('email','').strip().lower()
    password = request.form.get('password','')
    token = request.form.get('captcha_token')
    answer = request.form.get('captcha_answer')
    if not check_captcha(token, answer):
        q,t = new_captcha()
        return render_template('login.html', err='Invalid captcha.', captcha_q=q, captcha_t=t)

    if email == app.config['ADMIN_EMAIL'] and password == app.config['ADMIN_PASSWORD']:
        session.clear()
        session['admin'] = True
        return redirect(url_for('admin_dashboard'))

    conn = get_db(); cur = conn.cursor()
    try:
        cur.execute("SELECT * FROM users WHERE email=?", (email,))
        row = cur.fetchone()
        if not row or not check_password_hash(row['password_hash'], password):
            q,t = new_captcha()
            return render_template('login.html', err='Invalid credentials.', captcha_q=q, captcha_t=t)
        session.clear()
        session['user_id'] = row['id']
        session['name'] = row['name']
        session['hints_left'] = 3
        return redirect(url_for('dashboard'))
    finally:
        cur.close(); conn.close()

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/register', methods=['GET','POST'])
def register():
    if request.method == 'GET':
        q,t = new_captcha()
        return render_template('register.html', captcha_q=q, captcha_t=t)
    name = request.form.get('name','').strip()
    email = request.form.get('email','').strip().lower()
    password = request.form.get('password','')
    token = request.form.get('captcha_token')
    answer = request.form.get('captcha_answer')
    if not all([name,email,password]) or not check_captcha(token, answer):
        q,t = new_captcha()
        return render_template('register.html', err='Fill all fields and captcha.', captcha_q=q, captcha_t=t)
    conn = get_db(); cur = conn.cursor()
    try:
        cur.execute("SELECT 1 FROM users WHERE email=?", (email,))
        if cur.fetchone():
            q,t = new_captcha()
            return render_template('register.html', err='Email already exists.', captcha_q=q, captcha_t=t)
        cur.execute("INSERT INTO users(name,email,password_hash) VALUES(?,?,?)",
                    (name, email, generate_password_hash(password)))
        conn.commit()
        return redirect(url_for('login'))
    finally:
        cur.close(); conn.close()

@app.route('/dashboard')
def dashboard():
    if not require_login(): return redirect(url_for('login'))
    return render_template('dashboard.html', name=session.get('name'))

@app.route('/play')
def play():
    if not require_login(): return render_template('guest_restricted.html')
    puzzle = make_puzzle()
    return render_template('play.html', puzzle=puzzle, hints_left=session.get('hints_left',3))

@app.route('/api/save_result', methods=['POST'])
def save_result():
    if not require_login():
        return jsonify({'ok': False, 'error': 'not_logged_in'}), 401
    seconds = int(request.json.get('seconds', 0))
    conn = get_db(); cur = conn.cursor()
    try:
        cur.execute("INSERT INTO games(user_id, seconds) VALUES(?,?)", (session['user_id'], seconds))
        conn.commit()
        return jsonify({'ok': True})
    finally:
        cur.close(); conn.close()

@app.route('/leaderboard')
def leaderboard():
    conn = get_db(); cur = conn.cursor()
    try:
        cur.execute(\"\"\"
            SELECT u.name, MIN(g.seconds) AS best_seconds, COUNT(g.id) AS games_played
            FROM users u LEFT JOIN games g ON u.id = g.user_id
            GROUP BY u.id
            HAVING best_seconds IS NOT NULL
            ORDER BY best_seconds ASC
            LIMIT 50
        \"\"\")
        rows = cur.fetchall()
        return render_template('leaderboard.html', rows=rows)
    finally:
        cur.close(); conn.close()

# ---- Password reset with OTP (independent rate-limit) ----
def otp_allowed(email):
    conn = get_db(); cur = conn.cursor()
    try:
        cur.execute("SELECT last_request_ts FROM otp_rate_limit WHERE email=?", (email,))
        row = cur.fetchone()
        now = time_mod.time()
        if row and now - row['last_request_ts'] < app.config['OTP_RATE_LIMIT_SECONDS']:
            return False
        cur.execute("REPLACE INTO otp_rate_limit(email,last_request_ts) VALUES(?,?)", (email, now))
        conn.commit()
        return True
    finally:
        cur.close(); conn.close()

@app.route('/forgot', methods=['GET','POST'])
def forgot_password():
    if request.method == 'GET':
        return render_template('forgot_password.html')
    email = request.form.get('email','').strip().lower()
    conn = get_db(); cur = conn.cursor()
    try:
        cur.execute("SELECT id, name FROM users WHERE email=?", (email,))
        row = cur.fetchone()
        if not row:
            return render_template('forgot_password.html', msg="If the email exists, an OTP will be sent.")
        if not otp_allowed(email):
            return render_template('forgot_password.html', err="Too many requests. Try again shortly.")
        otp = f"{random.randint(100000,999999)}"
        expires = datetime.utcnow() + timedelta(minutes=app.config['OTP_EXP_MINUTES'])
        cur.execute("INSERT INTO password_resets(user_id, otp, expires_at) VALUES(?,?,?)",
                    (row['id'], otp, expires))
        conn.commit()
        body = f"Hi {row['name']},\\nYour OTP is {otp}. It expires in {app.config['OTP_EXP_MINUTES']} minutes."
        send_email(email, "Sudoku Password Reset", body, row['id'])
        return render_template('reset_password.html', email=email)
    finally:
        cur.close(); conn.close()

@app.route('/reset', methods=['POST'])
def reset_password():
    email = request.form.get('email','').strip().lower()
    otp = request.form.get('otp','').strip()
    new_pw = request.form.get('password','')
    conn = get_db(); cur = conn.cursor()
    try:
        cur.execute("SELECT id FROM users WHERE email=?", (email,))
        user = cur.fetchone()
        if not user:
            return render_template('reset_password.html', err="Invalid email/OTP.", email=email)
        cur.execute(\"\"\"
            SELECT id, expires_at, used FROM password_resets 
            WHERE user_id=? AND otp=? ORDER BY created_at DESC LIMIT 1
        \"\"\", (user['id'], otp))
        row = cur.fetchone()
        # Normalize expires_at
        valid = False
        if row and not row['used']:
            try:
                expires_at = row['expires_at']
                # Support both string and datetime
                if isinstance(expires_at, str):
                    expires_at = datetime.fromisoformat(expires_at)
                valid = datetime.utcnow() <= expires_at
            except Exception:
                valid = False
        if not row or not valid:
            return render_template('reset_password.html', err="Invalid or expired OTP.", email=email)
        cur.execute("UPDATE users SET password_hash=? WHERE id=?",
                    (generate_password_hash(new_pw), user['id']))
        cur.execute("UPDATE password_resets SET used=1 WHERE id=?", (row['id'],))
        conn.commit()
        return redirect(url_for('login'))
    finally:
        cur.close(); conn.close()

# ---- Admin ----
def require_admin():
    return session.get('admin', False)

@app.route('/admin')
def admin_dashboard():
    if not require_admin():
        return render_template('admin_login.html')
    conn = get_db(); cur = conn.cursor()
    try:
        cur.execute("SELECT COUNT(*) AS users FROM users")
        users = cur.fetchone()['users']
        cur.execute("SELECT COUNT(*) AS games FROM games")
        games = cur.fetchone()['games']
        cur.execute("SELECT COUNT(*) AS emails FROM email_logs")
        emails = cur.fetchone()['emails']
        return render_template('admin_dashboard.html', users=users, games=games, emails=emails)
    finally:
        cur.close(); conn.close()

@app.route('/admin/login', methods=['POST'])
def admin_login():
    email = request.form.get('email','')
    password = request.form.get('password','')
    if email == app.config['ADMIN_EMAIL'] and password == app.config['ADMIN_PASSWORD']:
        session['admin'] = True
        return redirect(url_for('admin_dashboard'))
    return render_template('admin_login.html', err="Invalid admin credentials.")

@app.route('/admin/users')
def admin_users():
    if not require_admin(): return render_template('admin_login.html')
    conn = get_db(); cur = conn.cursor()
    try:
        cur.execute("SELECT id, name, email, created_at FROM users ORDER BY created_at DESC")
        rows = cur.fetchall()
        return render_template('admin_users.html', rows=rows)
    finally:
        cur.close(); conn.close()

@app.route('/admin/emails')
def admin_emails():
    if not require_admin(): return render_template('admin_login.html')
    conn = get_db(); cur = conn.cursor()
    try:
        cur.execute("SELECT to_email, subject, status, detail, created_at FROM email_logs ORDER BY created_at DESC LIMIT 200")
        rows = cur.fetchall()
        return render_template('admin_emails.html', rows=rows)
    finally:
        cur.close(); conn.close()

@app.route('/admin/resets')
def admin_resets():
    if not require_admin(): return render_template('admin_login.html')
    conn = get_db(); cur = conn.cursor()
    try:
        cur.execute("SELECT u.email, r.otp, r.expires_at, r.used, r.created_at FROM password_resets r JOIN users u ON r.user_id=u.id ORDER BY r.created_at DESC LIMIT 200")
        rows = cur.fetchall()
        return render_template('admin_resets.html', rows=rows)
    finally:
        cur.close(); conn.close()

# ---- Weekly digest (optional) ----
def run_digest_job():
    pass

def setup_schedule():
    if not app.config['DIGEST_ENABLED']:
        return
    def loop():
        while True:
            try:
                schedule.run_pending()
            except Exception:
                pass
            time_mod.sleep(1)
    schedule.every().day.at(app.config['DIGEST_IST_TIME']).do(run_digest_job)
    t = threading.Thread(target=loop, daemon=True)
    t.start()

# ---- Errors ----
@app.errorhandler(404)
def not_found(error):
    return render_template('base.html', body="Page not found"), 404

@app.errorhandler(500)
def internal_error(error):
    return render_template('base.html', body="Internal server error"), 500

# ---- App start ----
init_db()
setup_schedule()
