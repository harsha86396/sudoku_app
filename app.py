# app.py
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, send_file, g
import sqlite3, os, smtplib, ssl, io, random, time as time_mod
from email.mime.text import MIMEText
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash

from utils.sudoku import make_puzzle
from utils.pdf_utils import generate_last7_pdf

# ---- Optional scheduler (won't crash if not installed) ----
try:
    import schedule  # type: ignore
except Exception:
    schedule = None

import threading
import config as config

DB = "sudoku.db"

app = Flask(__name__)
app.config.from_object(config)
app.secret_key = config.SECRET_KEY


# ----------------- DB helpers -----------------
def get_db():
    """
    One sqlite connection per request (stored in flask.g).
    check_same_thread=False allows using the same connection in Flask threads.
    """
    if "db" not in g:
        g.db = sqlite3.connect(
            DB,
            detect_types=sqlite3.PARSE_DECLTYPES,
            check_same_thread=False
        )
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()

def init_db():
    con = get_db()
    cur = con.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        email TEXT UNIQUE,
        password_hash TEXT
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS results(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        seconds INTEGER,
        played_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS sent_emails(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        email TEXT,
        subject TEXT,
        body TEXT,
        sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS password_resets(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        otp_hash TEXT,
        expires_at TIMESTAMP,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS otp_rate_limit(
        email TEXT PRIMARY KEY,
        last_request_ts REAL
    )""")
    con.commit()


# ----------------- Email -----------------
def send_email(to_email, subject, body, user_id=None):
    if not app.config.get('EMAIL_ENABLED'):
        print('[EMAIL DISABLED]', subject, body)
        return False
    try:
        msg = MIMEText(body)
        msg['Subject'] = subject
        msg['From'] = app.config['SMTP_USER']
        msg['To'] = to_email
        ctx = ssl.create_default_context()
        with smtplib.SMTP(app.config['SMTP_SERVER'], app.config['SMTP_PORT']) as s:
            s.starttls(context=ctx)
            s.login(app.config['SMTP_USER'], app.config['SMTP_PASS'])
            s.send_message(msg)
        con = get_db(); cur = con.cursor()
        cur.execute('INSERT INTO sent_emails(user_id,email,subject,body) VALUES(?,?,?,?)',
                    (user_id, to_email, subject, body))
        con.commit()
        return True
    except Exception as e:
        print('Email error:', e)
        return False


# ----------------- Helpers -----------------
def new_captcha():
    a, b = random.randint(1,9), random.randint(1,9)
    token = f"{random.randint(100000,999999)}"
    ans = str(a + b)
    session['captcha_' + token] = ans
    return f"{a} + {b} = ?", token

def check_captcha(token, answer):
    key = 'captcha_' + token
    correct = session.get(key)
    if not correct:
        return False
    ok = correct.strip() == str(answer).strip()
    session.pop(key, None)  # one-time
    return ok

def rate_limit_ok(email):
    con = get_db(); cur = con.cursor()
    cur.execute('SELECT last_request_ts FROM otp_rate_limit WHERE email=?', (email,))
    row = cur.fetchone()
    now = time_mod.time()
    if row:
        last = row[0]
        wait_s = app.config.get('OTP_RATE_LIMIT_SECONDS', 60)
        if now - last < wait_s:
            return False, int(wait_s - (now - last))
        cur.execute('UPDATE otp_rate_limit SET last_request_ts=? WHERE email=?', (now, email))
    else:
        cur.execute('INSERT INTO otp_rate_limit(email,last_request_ts) VALUES(?,?)', (email, now))
    con.commit()
    return True, 0


# ----------------- Routes -----------------
@app.route('/health')
def health():
    return "ok", 200

@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    q, t = new_captcha()
    return render_template('index.html', title='Welcome', captcha_q=q, captcha_t=t)

@app.route('/register', methods=['POST'])
def register():
    name = request.form['name'].strip()
    email = request.form['email'].strip().lower()
    password = request.form['password']
    cap_ans = request.form['captcha_answer']; cap_tok = request.form['captcha_token']
    if not check_captcha(cap_tok, cap_ans):
        q, t = new_captcha()
        return render_template('index.html', err='CAPTCHA incorrect.', captcha_q=q, captcha_t=t)
    pw_hash = generate_password_hash(password)
    con = get_db(); cur = con.cursor()
    try:
        cur.execute('INSERT INTO users(name,email,password_hash) VALUES(?,?,?)', (name, email, pw_hash))
        con.commit()
        send_email(email, 'Welcome to Sudoku', f'Hello {name}, your account has been created.', None)
        q, t = new_captcha()
        return render_template('index.html', msg='Registration successful. Please log in.', captcha_q=q, captcha_t=t)
    except sqlite3.IntegrityError:
        q, t = new_captcha()
        return render_template('index.html', err='Email already registered.', captcha_q=q, captcha_t=t)

@app.route('/login', methods=['POST'])
def login():
    email = request.form['email'].strip().lower()
    password = request.form['password']
    if email == app.config['ADMIN_EMAIL'] and password == app.config['ADMIN_PASSWORD']:
        session['admin'] = True
        return redirect(url_for('admin'))
    con = get_db(); cur = con.cursor()
    cur.execute('SELECT id,name,password_hash FROM users WHERE email=?', (email,))
    row = cur.fetchone()
    if row and check_password_hash(row['password_hash'], password):
        session['user_id'] = row['id']
        session['name'] = row['name']
        session['hints_left'] = 3
        return redirect(url_for('dashboard'))
    q, t = new_captcha()
    return render_template('index.html', err='Invalid credentials.', captcha_q=q, captcha_t=t)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    return render_template('dashboard.html', name=session['name'], title='Dashboard')


# ---------- Forgot / Reset Password (OTP + rate limit + resend) ----------
def create_and_send_otp(user_id, email, name):
    otp = f"{random.randint(0, 999999):06d}"
    otp_hash = generate_password_hash(otp)
    expires = datetime.utcnow() + timedelta(minutes=app.config.get('OTP_EXP_MINUTES',10))
    con = get_db(); cur = con.cursor()
    cur.execute('INSERT INTO password_resets(user_id, otp_hash, expires_at) VALUES(?,?,?)',
                (user_id, otp_hash, expires))
    con.commit()
    body = f"""Hi {name},
Your OTP code to reset your password is: {otp}
This code expires in {app.config.get('OTP_EXP_MINUTES',10)} minutes.

– Sudoku AI (Harsha Enterprises)"""
    send_email(email, 'Sudoku Password Reset', body, user_id)
    return True

@app.route('/forgot_password', methods=['GET','POST'])
def forgot_password():
    if request.method == 'GET':
        q, t = new_captcha()
        return render_template('forgot_password.html', captcha_q=q, captcha_t=t)
    email = request.form['email'].strip().lower()
    cap_ans = request.form['captcha_answer']; cap_tok = request.form['captcha_token']
    if not check_captcha(cap_tok, cap_ans):
        q, t = new_captcha()
        return render_template('forgot_password.html', err='CAPTCHA incorrect.', email=email, captcha_q=q, captcha_t=t)
    ok, wait = rate_limit_ok(email)
    if not ok:
        q, t = new_captcha()
        return render_template('forgot_password.html', err=f'Please wait {wait}s before requesting another OTP.', email=email, captcha_q=q, captcha_t=t)
    con = get_db(); cur = con.cursor()
    cur.execute('SELECT id,name FROM users WHERE email=?', (email,))
    row = cur.fetchone()
    if not row:
        q, t = new_captcha()
        return render_template('forgot_password.html', err='Email not found.', email=email, captcha_q=q, captcha_t=t)
    create_and_send_otp(row['id'], email, row['name'])
    return render_template('reset_password.html', email=email, msg='OTP sent. Check your inbox.')

@app.route('/resend_otp')
def resend_otp():
    email = request.args.get('email','').strip().lower()
    ok, wait = rate_limit_ok(email)
    if not ok:
        return render_template('reset_password.html', email=email, err=f'Please wait {wait}s before resending OTP.')
    con = get_db(); cur = con.cursor()
    cur.execute('SELECT id,name FROM users WHERE email=?', (email,))
    row = cur.fetchone()
    if not row:
        q, t = new_captcha()
        return render_template('forgot_password.html', err='Email not found.', email=email, captcha_q=q, captcha_t=t)
    create_and_send_otp(row['id'], email, row['name'])
    return render_template('reset_password.html', email=email, msg='A new OTP has been sent.')

@app.route('/reset_password', methods=['POST'])
def reset_password():
    email = request.form['email'].strip().lower()
    otp = request.form['otp'].strip()
    password = request.form['password']
    confirm = request.form['confirm']
    if password != confirm:
        return render_template('reset_password.html', email=email, err='Passwords do not match.')
    con = get_db(); cur = con.cursor()
    cur.execute('SELECT id,name FROM users WHERE email=?', (email,))
    user = cur.fetchone()
    if not user:
        q, t = new_captcha()
        return render_template('forgot_password.html', err='Email not found.', email=email, captcha_q=q, captcha_t=t)
    uid, name = user['id'], user['name']
    cur.execute('SELECT id, otp_hash, expires_at FROM password_resets WHERE user_id=? ORDER BY created_at DESC LIMIT 1', (uid,))
    pr = cur.fetchone()
    if not pr:
        return render_template('reset_password.html', email=email, err='No active OTP. Please request again.')
    pr_id, otp_hash, expires_at = pr['id'], pr['otp_hash'], pr['expires_at']
    try:
        exp = datetime.fromisoformat(expires_at) if isinstance(expires_at, str) else expires_at
    except Exception:
        exp = datetime.utcnow() - timedelta(seconds=1)
    if datetime.utcnow() > exp:
        return render_template('reset_password.html', email=email, err='OTP expired. Please request a new one.')
    if not check_password_hash(otp_hash, otp):
        return render_template('reset_password.html', email=email, err='Invalid OTP.')
    new_hash = generate_password_hash(password)
    cur.execute('UPDATE users SET password_hash=? WHERE id=?', (new_hash, uid))
    cur.execute('DELETE FROM password_resets WHERE user_id=?', (uid,))
    con.commit()
    send_email(email, 'Password Changed', f'Hi {name}, your password was reset successfully.', uid)
    q, t = new_captcha()
    return render_template('index.html', msg='Password reset successful. Please log in.', captcha_q=q, captcha_t=t)


# ----------------- Game & APIs -----------------
@app.route('/play')
def play():
    if 'user_id' not in session: 
        return redirect(url_for('index'))
    return render_template('play.html', title='Play')

@app.route('/api/new_puzzle')
def api_new_puzzle():
    if 'user_id' not in session: 
        return jsonify({'error':'not logged in'}), 401
    diff = request.args.get('difficulty','medium')
    puzzle, solution = make_puzzle(diff)
    session['solution'] = solution
    session['puzzle'] = puzzle
    session['hints_left'] = 3
    return jsonify({'puzzle': puzzle, 'solution': solution})

@app.route('/api/hint', methods=['POST'])
def api_hint():
    if 'user_id' not in session: 
        return jsonify({'error':'not logged in'}), 401
    hints_left = session.get('hints_left',3)
    if hints_left <= 0: 
        return jsonify({'error':'No hints left'}), 400
    puzzle = session.get('puzzle'); solution = session.get('solution')
    empties = [(r,c) for r in range(9) for c in range(9) if puzzle[r][c]==0]
    if not empties: 
        return jsonify({'error':'No empty cells'}), 400
    r,c = random.choice(empties)
    val = solution[r][c]
    puzzle[r][c] = val
    session['puzzle'] = puzzle
    session['hints_left'] = hints_left - 1
    return jsonify({'r':r,'c':c,'val':val,'hints_left':session['hints_left']})

@app.route('/api/record_result', methods=['POST'])
def record_result():
    if 'user_id' not in session: 
        return jsonify({'error':'not logged in'}), 403
    seconds = int(request.json.get('seconds',0))
    if seconds <= 0: 
        return jsonify({'error':'invalid time'}), 400
    uid = session['user_id']
    con = get_db(); cur = con.cursor()
    cur.execute('INSERT INTO results(user_id,seconds) VALUES(?,?)', (uid, seconds))
    con.commit()
    cur.execute('SELECT MIN(seconds) FROM results WHERE user_id=?', (uid,))
    best = cur.fetchone()[0]
    cur.execute('''
        SELECT u.id, MIN(r.seconds) as best 
        FROM users u
        JOIN results r ON r.user_id=u.id
        GROUP BY u.id ORDER BY best ASC
    ''')
    rows = cur.fetchall()
    rank = 0
    for i, row in enumerate(rows, start=1):
        if row[0] == uid:
            rank = i
            break
    if seconds == best:
        cur.execute('SELECT email,name FROM users WHERE id=?', (uid,))
        em, nm = cur.fetchone()
        send_email(em, '🎉 New Personal Best!', f'Congrats {nm}! New PB: {best}s. Keep it up!', uid)
    return jsonify({'status':'ok','best_time':best,'rank':rank})

@app.route("/leaderboard")
def leaderboard():
    conn = get_db_connection()
    rows = conn.execute("""
        SELECT u.username, MIN(s.time_taken) AS best_time, COUNT(s.id) AS games
        FROM users u
        JOIN scores s ON u.id = s.user_id
        GROUP BY u.id
        HAVING best_time IS NOT NULL
        ORDER BY best_time ASC
        LIMIT 10
    """).fetchall()
    conn.close()
    return render_template("leaderboard.html", rows=rows)


@app.route('/download_history')
def download_history():
    if 'user_id' not in session: 
        return redirect(url_for('index'))
    uid = session['user_id']
    con = get_db(); cur = con.cursor()
    cur.execute('SELECT email,name FROM users WHERE id=?', (uid,))
    email, name = cur.fetchone()
    since = datetime.utcnow() - timedelta(days=7)
    cur.execute('''
        SELECT seconds, played_at 
        FROM results 
        WHERE user_id=? AND played_at >= ? 
        ORDER BY played_at DESC
    ''', (uid, since))
    rows = cur.fetchall()
    buf = io.BytesIO()
    generate_last7_pdf(name, email, rows, buf)
    buf.seek(0)
    return send_file(buf, as_attachment=True, download_name='sudoku_last7.pdf', mimetype='application/pdf')


# ----------------- Admin -----------------
def require_admin():
    return bool(session.get('admin'))

@app.route('/admin', methods=['GET','POST'])
def admin():
    if request.method == 'GET':
        if session.get('admin'):
            return render_template('admin_dashboard.html')
        return render_template('admin_login.html')
    email = request.form['email'].strip().lower()
    pw = request.form['password']
    if email == app.config['ADMIN_EMAIL'] and pw == app.config['ADMIN_PASSWORD']:
        session['admin'] = True
        return redirect(url_for('admin'))
    return render_template('admin_login.html', err='Invalid admin credentials.')

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin', None)
    return redirect(url_for('index'))

@app.route('/admin/users')
def admin_users():
    if not require_admin(): 
        return redirect(url_for('admin'))
    con = get_db(); cur = con.cursor()
    cur.execute('''
        SELECT u.id, u.name, u.email, COUNT(r.id) as games, MIN(r.seconds) as best
        FROM users u 
        LEFT JOIN results r ON r.user_id=u.id
        GROUP BY u.id 
        ORDER BY u.id ASC
    ''')
    rows = cur.fetchall()
    return render_template('admin_users.html', rows=rows)

@app.route('/admin/emails')
def admin_emails():
    if not require_admin(): 
        return redirect(url_for('admin'))
    con = get_db(); cur = con.cursor()
    cur.execute('SELECT id, user_id, email, subject, sent_at FROM sent_emails ORDER BY id DESC LIMIT 200')
    rows = cur.fetchall()
    return render_template('admin_emails.html', rows=rows)

@app.route('/admin/resets')
def admin_resets():
    if not require_admin(): 
        return redirect(url_for('admin'))
    con = get_db(); cur = con.cursor()
    cur.execute('SELECT id, user_id, expires_at, created_at FROM password_resets ORDER BY id DESC LIMIT 200')
    rows = cur.fetchall()
    return render_template('admin_resets.html', rows=rows)


# ----------------- Weekly digest scheduler -----------------
def send_weekly_digest():
    if not app.config.get('EMAIL_ENABLED') or not app.config.get('DIGEST_ENABLED'):
        return
    con = get_db(); cur = con.cursor()
    since = datetime.utcnow() - timedelta(days=7)
    cur.execute('SELECT id,name,email FROM users')
    users = cur.fetchall()
    for u in users:
        uid, name, email = u['id'], u['name'], u['email']
        cur.execute(
            'SELECT COUNT(*), MIN(seconds), AVG(seconds) FROM results WHERE user_id=? AND played_at >= ?',
            (uid, since)
        )
        games, best, avg = cur.fetchone()
        if games and games > 0:
            body = f"""Hi {name},

Your weekly Sudoku progress:
- Games: {games}
- Best: {int(best)}s
- Average: {int(avg)}s

Keep practicing!
"""
            send_email(email, 'Your Weekly Sudoku Progress 📊', body, uid)

def scheduler_thread():
    while True:
        try:
            if schedule:
                schedule.run_pending()
        except Exception as e:
            print('Scheduler error:', e)
        time_mod.sleep(60)

def setup_schedule():
    # Only set up if schedule exists and not disabled
    if schedule and not os.environ.get("DISABLE_SCHEDULER"):
        # Time is server local time; configure via DIGEST_IST_TIME if you like
        schedule.every().sunday.at(app.config.get('DIGEST_IST_TIME','18:00')).do(send_weekly_digest)
        t = threading.Thread(target=scheduler_thread, daemon=True)
        t.start()


# ----------------- App startup -----------------
with app.app_context():
    try:
        init_db()
    except Exception as e:
        print("init_db error:", e)

# Start scheduler if applicable
try:
    setup_schedule()
except Exception as e:
    print("setup_schedule error:", e)

if __name__ == '__main__':
    # Running locally: ensure DB exists and scheduler started
    with app.app_context():
        init_db()
    setup_schedule()
    # Respect PORT env (Render/Heroku), else default 5000
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=True)
