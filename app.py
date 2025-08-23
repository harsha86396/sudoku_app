
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, send_file
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
import os, smtplib, ssl, io, random, time as time_mod, threading
try:
    import schedule
except Exception:
    class _Sched:
        def every(self): return self
        def monday(self): return self
        def at(self, *_): return self
        def do(self, *_): return self
        def run_pending(self): pass
    schedule = _Sched()
from email.mime.text import MIMEText
from datetime import datetime, timedelta

from config import Config
from database import get_db, init_db
from utils.sudoku import make_puzzle
from utils.pdf_utils import generate_last7_pdf

load_dotenv()

app = Flask(__name__)
app.config.from_object(Config)

# ---------- helpers ----------

def send_email(to_email: str, subject: str, html_body: str):
    host = app.config['SMTP_HOST']
    user = app.config['SMTP_USER']
    pw   = app.config['SMTP_PASS']
    port = app.config['SMTP_PORT']
    if not user or not pw:
        # Email is optional; log and continue.
        print(f"[email disabled] To={to_email} Subject={subject}")
        return True
    try:
        msg = MIMEText(html_body, "html")
        msg['Subject'] = subject
        msg['From'] = app.config['FROM_EMAIL']
        msg['To'] = to_email
        ctx = ssl.create_default_context()
        with smtplib.SMTP(host, port) as s:
            if app.config['SMTP_USE_TLS']:
                s.starttls(context=ctx)
            s.login(user, pw)
            s.sendmail(msg['From'], [to_email], msg.as_string())
        return True
    except Exception as e:
        print("Email send failed:", e)
        # Do not block login/flows
        return False

def new_captcha():
    a, b = random.randint(1,9), random.randint(1,9)
    token = f"{random.randint(100000,999999)}"
    ans = str(a + b)
    session['captcha_' + token] = ans
    return f"{a} + {b} = ?", token

def check_captcha(token, answer):
    key = 'captcha_' + str(token)
    if session.get(key) and str(answer).strip() == str(session.get(key)):
        session.pop(key, None)
        return True
    return False

def rate_limit_ok(email):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT last_request_ts FROM otp_rate_limit WHERE email=?", (email,))
    row = cur.fetchone()
    now = time_mod.time()
    if row:
        last = row[0]
        if now - last < app.config['OTP_RATE_LIMIT_SECONDS']:
            cur.close()
            conn.close()
            return False, int(app.config['OTP_RATE_LIMIT_SECONDS'] - (now - last))
        cur.execute("UPDATE otp_rate_limit SET last_request_ts=? WHERE email=?", (now, email))
    else:
        cur.execute("INSERT INTO otp_rate_limit(email,last_request_ts) VALUES(?,?)", (email, now))
    conn.commit()
    cur.close()
    conn.close()
    return True, 0

# ---------- routes ----------

@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return render_template('index.html', brand=app.config['BRAND'])

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'GET':
        q,t = new_captcha()
        return render_template('login.html', captcha_q=q, captcha_t=t, brand=app.config['BRAND'])
    email = request.form.get('email','').strip().lower()
    password = request.form.get('password','')
    capt = request.form.get('captcha','').strip()
    token = request.form.get('captcha_token','')
    if not email or not password:
        q,t = new_captcha()
        return render_template('login.html', err="Email and password are required.", captcha_q=q, captcha_t=t, brand=app.config['BRAND'])
    if not check_captcha(token, capt):
        q,t = new_captcha()
        return render_template('login.html', err="CAPTCHA incorrect.", captcha_q=q, captcha_t=t, brand=app.config['BRAND'])

    # Admin bypass
    if email == app.config['ADMIN_EMAIL'] and password == app.config['ADMIN_PASSWORD']:
        session.clear()
        session['admin'] = True
        return redirect(url_for('admin'))

    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("SELECT id, name, password_hash, email_verified FROM users WHERE email=?", (email,))
        u = cur.fetchone()
        if not u or not check_password_hash(u['password_hash'], password):
            q,t = new_captcha()
            return render_template('login.html', err="Invalid email or password.", captcha_q=q, captcha_t=t, brand=app.config['BRAND'])
        session.clear()
        session['user_id'] = u['id']
        session['name'] = u['name']
        return redirect(url_for('dashboard'))
    except Exception as e:
        print("Login error:", e)
        q,t = new_captcha()
        return render_template('login.html', err="An error occurred. Please try again.", captcha_q=q, captcha_t=t, brand=app.config['BRAND'])
    finally:
        cur.close()
        conn.close()

@app.route('/register', methods=['GET','POST'])
def register():
    if request.method == 'GET':
        q,t = new_captcha()
        return render_template('register.html', captcha_q=q, captcha_t=t, brand=app.config['BRAND'])
    name = request.form.get('name','').strip()
    email = request.form.get('email','').strip().lower()
    password = request.form.get('password','')
    capt = request.form.get('captcha','').strip()
    token = request.form.get('captcha_token','')
    if not all([name,email,password]):
        q,t = new_captcha()
        return render_template('register.html', err="All fields are required.", captcha_q=q, captcha_t=t, brand=app.config['BRAND'])
    if not check_captcha(token, capt):
        q,t = new_captcha()
        return render_template('register.html', err="CAPTCHA incorrect.", captcha_q=q, captcha_t=t, brand=app.config['BRAND'])
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("SELECT id FROM users WHERE email=?", (email,))
        if cur.fetchone():
            q,t = new_captcha()
            return render_template('register.html', err="Email already registered.", captcha_q=q, captcha_t=t, brand=app.config['BRAND'])
        pw_hash = generate_password_hash(password)
        cur.execute("INSERT INTO users(name,email,password_hash,email_verified) VALUES(?,?,?,1)", (name, email, pw_hash))
        conn.commit()
        session.clear()
        session['user_id'] = cur.lastrowid
        session['name'] = name
        send_email(email, "Welcome to Sudoku", f"<p>Hi {name}, welcome to {app.config['BRAND']}!</p>")
        return redirect(url_for('dashboard'))
    except Exception as e:
        print("Register error:", e)
        q,t = new_captcha()
        return render_template('register.html', err="An error occurred. Please try again.", captcha_q=q, captcha_t=t, brand=app.config['BRAND'])
    finally:
        cur.close()
        conn.close()

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    # Fetch best time and recent games
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT MIN(seconds) as best FROM results WHERE user_id=?", (session['user_id'],))
    row = cur.fetchone()
    best = row['best'] if row and row['best'] is not None else None
    cur.execute("SELECT difficulty, seconds, created_at FROM results WHERE user_id=? ORDER BY created_at DESC LIMIT 10", (session['user_id'],))
    recent = cur.fetchall()
    cur.close()
    conn.close()
    return render_template('dashboard.html', best=best, recent=recent, brand=app.config['BRAND'])

@app.route('/play')
def play():
    # Everyone can play, including guests
    difficulty = request.args.get('difficulty','easy')
    puz, sol = make_puzzle(difficulty)
    return render_template('play.html', puzzle=puz, solution=sol, difficulty=difficulty, brand=app.config['BRAND'])

@app.route('/leaderboard')
def leaderboard():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT u.name, MIN(r.seconds) as best FROM results r JOIN users u ON u.id=r.user_id GROUP BY r.user_id ORDER BY best ASC LIMIT 50")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return render_template('leaderboard.html', rows=rows, brand=app.config['BRAND'])

@app.route('/admin')
def admin():
    if not session.get('admin'):
        return redirect(url_for('login'))
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id, name, email, email_verified, created_at FROM users ORDER BY created_at DESC LIMIT 100")
    users = cur.fetchall()
    cur.execute("SELECT COUNT(1) FROM results")
    total_games = cur.fetchone()[0]
    cur.close()
    conn.close()
    return render_template('admin.html', users=users, total_games=total_games, brand=app.config['BRAND'])

@app.route('/forgot_password', methods=['GET','POST'])
def forgot_password():
    if request.method == 'GET':
        q,t = new_captcha()
        return render_template('forgot_password.html', captcha_q=q, captcha_t=t, brand=app.config['BRAND'])
    email = request.form.get('email','').strip().lower()
    capt = request.form.get('captcha','').strip()
    token = request.form.get('captcha_token','')
    if not email:
        q,t = new_captcha()
        return render_template('forgot_password.html', err="Email is required.", captcha_q=q, captcha_t=t, brand=app.config['BRAND'])
    if not check_captcha(token, capt):
        q,t = new_captcha()
        return render_template('forgot_password.html', err="CAPTCHA incorrect.", captcha_q=q, captcha_t=t, brand=app.config['BRAND'])

    ok, wait = rate_limit_ok(email)
    if not ok:
        q,t = new_captcha()
        return render_template('forgot_password.html', err=f"Please wait {wait}s before requesting another OTP.", captcha_q=q, captcha_t=t, brand=app.config['BRAND'])

    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("SELECT id, name FROM users WHERE email=?", (email,))
        u = cur.fetchone()
        if not u:
            q,t = new_captcha()
            return render_template('forgot_password.html', err="Email not found.", captcha_q=q, captcha_t=t, brand=app.config['BRAND'])
        uid, name = u['id'], u['name']
        otp = f"{random.randint(100000,999999)}"
        otp_hash = generate_password_hash(otp)
        expires_at = time_mod.time() + app.config['OTP_EXPIRE_MINUTES']*60
        # Remove existing OTPs
        cur.execute("DELETE FROM password_resets WHERE user_id=?", (uid,))
        cur.execute("INSERT INTO password_resets(user_id, otp_hash, expires_at) VALUES(?,?,?)", (uid, otp_hash, expires_at))
        conn.commit()
        send_email(email, "Your Sudoku OTP", f"<p>Hi {name}, your OTP is <b>{otp}</b>. It expires in {app.config['OTP_EXPIRE_MINUTES']} minutes.</p>")
        return render_template('reset_password.html', email=email, brand=app.config['BRAND'])
    except Exception as e:
        print("Forgot password error:", e)
        q,t = new_captcha()
        return render_template('forgot_password.html', err="An error occurred. Please try again.", captcha_q=q, captcha_t=t, brand=app.config['BRAND'])
    finally:
        cur.close()
        conn.close()

@app.route('/reset_password', methods=['POST'])
def reset_password():
    email = request.form.get('email','').strip().lower()
    otp = request.form.get('otp','').strip()
    password = request.form.get('password','')
    confirm = request.form.get('confirm','')
    if not all([email, otp, password, confirm]):
        return render_template('reset_password.html', email=email, err="All fields are required.", brand=app.config['BRAND'])
    if password != confirm:
        return render_template('reset_password.html', email=email, err="Passwords do not match.", brand=app.config['BRAND'])
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("SELECT id, name FROM users WHERE email=?", (email,))
        u = cur.fetchone()
        if not u:
            return render_template('reset_password.html', email=email, err="Email not found.", brand=app.config['BRAND'])
        uid, name = u['id'], u['name']
        cur.execute("SELECT id, otp_hash, expires_at FROM password_resets WHERE user_id=? ORDER BY created_at DESC LIMIT 1", (uid,))
        pr = cur.fetchone()
        if not pr:
            return render_template('reset_password.html', email=email, err="No active OTP. Please request again.", brand=app.config['BRAND'])
        if time_mod.time() > pr['expires_at']:
            return render_template('reset_password.html', email=email, err="OTP expired. Please request again.", brand=app.config['BRAND'])
        if not check_password_hash(pr['otp_hash'], otp):
            return render_template('reset_password.html', email=email, err="OTP incorrect.", brand=app.config['BRAND'])
        new_hash = generate_password_hash(password)
        cur.execute("UPDATE users SET password_hash=? WHERE id=?", (new_hash, uid))
        cur.execute("DELETE FROM password_resets WHERE user_id=?", (uid,))
        conn.commit()
        send_email(email, "Password changed", f"<p>Hi {name}, your password was reset successfully.</p>")
        q,t = new_captcha()
        return render_template('login.html', msg="Password reset successful. Please log in.", captcha_q=q, captcha_t=t, brand=app.config['BRAND'])
    except Exception as e:
        print("Reset password error:", e)
        return render_template('reset_password.html', email=email, err="An error occurred. Please try again.", brand=app.config['BRAND'])
    finally:
        cur.close()
        conn.close()

@app.route('/api/record_result', methods=['POST'])
def record_result():
    if 'user_id' not in session:
        return jsonify({"error":"not authenticated"}), 401
    seconds = int(request.form.get('seconds','0'))
    difficulty = request.form.get('difficulty','easy')
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("INSERT INTO results(user_id, seconds, difficulty) VALUES(?,?,?)", (session['user_id'], seconds, difficulty))
        conn.commit()
        # compute new best and rank
        cur.execute("SELECT MIN(seconds) FROM results WHERE user_id=?", (session['user_id'],))
        best = cur.fetchone()[0] or seconds
        cur.execute("SELECT COUNT(*)+1 FROM (SELECT MIN(seconds) as best FROM results GROUP BY user_id) x WHERE x.best < ?", (best,))
        rank = cur.fetchone()[0]
        return jsonify({"status":"ok","best":best, "rank":rank})
    except Exception as e:
        print("Record result error:", e)
        return jsonify({"error":"failed"}), 500
    finally:
        cur.close()
        conn.close()

@app.route('/healthz')
def healthz():
    return "ok", 200

# Errors
@app.errorhandler(404)
def not_found(e):
    return render_template('error.html', error="Page not found"), 404

@app.errorhandler(500)
def internal(e):
    return render_template('error.html', error="Internal server error"), 500

# --------- background weekly digest ---------

def weekly_digest_job():
    try:
        conn = get_db()
        cur = conn.cursor()
        # last 7 days
        cur.execute("SELECT COUNT(*) FROM users WHERE created_at >= datetime('now','-7 day')")
        new_users = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM results WHERE created_at >= datetime('now','-7 day')")
        games = cur.fetchone()[0]
        cur.execute("SELECT u.name, MIN(r.seconds) as best FROM results r JOIN users u ON u.id=r.user_id WHERE r.created_at >= datetime('now','-7 day') GROUP BY r.user_id ORDER BY best ASC LIMIT 1")
        row = cur.fetchone()
        top_player = row['name'] if row else None
        top_time = row['best'] if row else None
        cur.close()
        conn.close()
        pdf_path = os.path.join(app.root_path, "weekly_digest.pdf")
        generate_last7_pdf(pdf_path, {"new_users":new_users, "games_played":games, "top_player":top_player, "top_time":top_time})
        print("Weekly digest generated.")
    except Exception as e:
        print("Weekly digest job error:", e)

def schedule_thread():
    # Every Monday 09:00 IST equivalent in server timezone is not handled here; run daily 03:30 UTC and rely on platform TZ if needed
    schedule.every().monday.at("09:00").do(weekly_digest_job)
    while True:
        schedule.run_pending()
        time_mod.sleep(1)

def start_scheduler():
    t = threading.Thread(target=schedule_thread, daemon=True)
    t.start()

# Main factory
def create_app():
    with app.app_context():
        init_db()
    start_scheduler()
    return app

if __name__ == "__main__":
    create_app().run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
