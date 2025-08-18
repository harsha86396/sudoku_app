from flask import Flask, render_template, request, redirect, url_for, session, jsonify, send_file, g
import sqlite3, os, smtplib, ssl, io, random, time as time_mod
from email.mime.text import MIMEText
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash

from utils.sudoku import make_puzzle
from utils.pdf_utils import generate_last7_pdf
import threading, schedule
import config as config

# ---------------------
# Database helpers
# ---------------------
DB_PATH = getattr(config, "DATABASE", None)
if not DB_PATH:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    DB_PATH = os.path.join(BASE_DIR, "sudoku.db")

def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES)
        g.db.row_factory = sqlite3.Row
    return g.db

def close_db(e=None):
    db = g.pop('db', None)
    if db is not None:
        try:
            db.commit()
        except Exception:
            pass
        db.close()

# ---------------------
# Flask app setup
# ---------------------
app = Flask(__name__)
app.config.from_object(config)
app.secret_key = config.SECRET_KEY
app.teardown_appcontext(close_db)

# ---------------------
# Safe init_db (no data loss)
# ---------------------
def init_db():
    con = get_db()
    cur = con.cursor()

    # --- Users ---
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        email TEXT UNIQUE,
        password_hash TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    cur.execute("PRAGMA table_info(users)")
    cols = [row[1] for row in cur.fetchall()]
    if "password_hash" not in cols:
        cur.execute("ALTER TABLE users ADD COLUMN password_hash TEXT")
    if "created_at" not in cols:
        cur.execute("ALTER TABLE users ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")

    # --- Results ---
    cur.execute("""
    CREATE TABLE IF NOT EXISTS results (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        seconds INTEGER,
        played_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id)
    )
    """)

    # --- Email logs ---
    cur.execute("""
    CREATE TABLE IF NOT EXISTS email_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        recipient TEXT NOT NULL,
        subject TEXT NOT NULL,
        status TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # --- Password resets ---
    cur.execute("""
    CREATE TABLE IF NOT EXISTS password_resets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT NOT NULL,
        token TEXT,
        otp_hash TEXT,
        expires_at TIMESTAMP NOT NULL,
        used INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # --- OTP rate limit ---
    cur.execute("""
    CREATE TABLE IF NOT EXISTS otp_rate_limit (
        email TEXT PRIMARY KEY,
        last_request_ts REAL
    )
    """)

    con.commit()
    con.close()
    print("✅ Database initialized / upgraded")

# ---------------------
# Email sender
# ---------------------
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

        # log email
        con = get_db(); cur = con.cursor()
        cur.execute(
            'INSERT INTO email_logs(recipient,subject,status) VALUES(?,?,?)',
            (to_email, subject, 'sent')
        )
        con.commit(); con.close()
        return True
    except Exception as e:
        print('Email error:', e)
        return False

# ---------------------
# Helpers
# ---------------------
def new_captcha():
    a, b = random.randint(1,9), random.randint(1,9)
    token = f"{random.randint(100000,999999)}"
    ans = str(a + b)
    session['captcha_' + token] = ans
    return f"{a} + {b} = ?", token

def check_captcha(token, answer):
    key = 'captcha_' + token
    correct = session.get(key)
    if not correct: return False
    ok = correct.strip() == answer.strip()
    session.pop(key, None)
    return ok

def rate_limit_ok(email):
    con = get_db(); cur = con.cursor()
    cur.execute('SELECT last_request_ts FROM otp_rate_limit WHERE email=?', (email,))
    row = cur.fetchone()
    now = time_mod.time()
    if row:
        last = row[0]
        if now - last < app.config.get('OTP_RATE_LIMIT_SECONDS',60):
            con.close()
            return False, int(app.config.get('OTP_RATE_LIMIT_SECONDS',60) - (now-last))
        cur.execute('UPDATE otp_rate_limit SET last_request_ts=? WHERE email=?', (now,email))
    else:
        cur.execute('INSERT INTO otp_rate_limit(email,last_request_ts) VALUES(?,?)',(email,now))
    con.commit(); con.close()
    return True, 0

# ---------------------
# Routes
# ---------------------
@app.route('/')
def index():
    if 'user_id' in session: return redirect(url_for('dashboard'))
    q,t = new_captcha()
    return render_template('index.html', title='Welcome', captcha_q=q, captcha_t=t)

@app.route('/register', methods=['POST'])
def register():
    name = request.form['name'].strip()
    email = request.form['email'].strip().lower()
    password = request.form['password']
    cap_ans = request.form['captcha_answer']; cap_tok = request.form['captcha_token']
    if not check_captcha(cap_tok, cap_ans):
        q,t = new_captcha()
        return render_template('index.html', err='CAPTCHA incorrect.', captcha_q=q, captcha_t=t)
    pw_hash = generate_password_hash(password)
    con = get_db(); cur = con.cursor()
    try:
        cur.execute('INSERT INTO users(name,email,password_hash) VALUES(?,?,?)', (name,email,pw_hash))
        con.commit()
        send_email(email, 'Welcome to Sudoku', f'Hello {name}, your account has been created.', None)
        q,t = new_captcha()
        return render_template('index.html', msg='Registration successful. Please log in.', captcha_q=q, captcha_t=t)
    except sqlite3.IntegrityError:
        q,t = new_captcha()
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
    row = cur.fetchone(); con.close()
    if row and check_password_hash(row['password_hash'], password):
        session['user_id'] = row['id']
        session['name'] = row['name']
        session['hints_left'] = 3
        return redirect(url_for('dashboard'))
    q,t = new_captcha()
    return render_template('index.html', err='Invalid credentials.', captcha_q=q, captcha_t=t)

@app.route('/logout')
def logout():
    session.clear(); return redirect(url_for('index'))

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session: return redirect(url_for('index'))
    return render_template('dashboard.html', name=session['name'], title='Dashboard')

# ---------------------
# Game
# ---------------------
@app.route('/play')
def play():
    if 'user_id' not in session: return redirect(url_for('index'))
    return render_template('play.html', title='Play')

@app.route('/api/new_puzzle')
def api_new_puzzle():
    if 'user_id' not in session: return jsonify({'error':'not logged in'}), 401
    diff = request.args.get('difficulty','medium')
    puzzle, solution = make_puzzle(diff)
    session['solution'] = solution
    session['puzzle'] = puzzle
    session['hints_left'] = 3
    return jsonify({'puzzle': puzzle, 'solution': solution})

@app.route('/api/hint', methods=['POST'])
def api_hint():
    if 'user_id' not in session: return jsonify({'error':'not logged in'}), 401
    hints_left = session.get('hints_left',3)
    if hints_left <= 0: return jsonify({'error':'No hints left'}), 400
    puzzle = session.get('puzzle'); solution = session.get('solution')
    empties = [(r,c) for r in range(9) for c in range(9) if puzzle[r][c]==0]
    if not empties: return jsonify({'error':'No empty cells'}), 400
    r,c = random.choice(empties)
    val = solution[r][c]
    puzzle[r][c] = val
    session['puzzle'] = puzzle
    session['hints_left'] = hints_left - 1
    return jsonify({'r':r,'c':c,'val':val,'hints_left':session['hints_left']})

@app.route('/api/record_result', methods=['POST'])
def record_result():
    if 'user_id' not in session: return jsonify({'error':'not logged in'}), 403
    seconds = int(request.json.get('seconds',0))
    if seconds <= 0: return jsonify({'error':'invalid time'}), 400
    uid = session['user_id']
    con = get_db(); cur = con.cursor()
    cur.execute('INSERT INTO results(user_id,seconds) VALUES(?,?)', (uid, seconds))
    con.commit()
    cur.execute('SELECT MIN(seconds) FROM results WHERE user_id=?', (uid,))
    best = cur.fetchone()[0]
    cur.execute('''
        SELECT u.id, MIN(r.seconds) as best FROM users u
        JOIN results r ON r.user_id=u.id
        GROUP BY u.id ORDER BY best ASC
    ''')
    rows = cur.fetchall()
    rank = 0
    for i, row in enumerate(rows, start=1):
        if row[0] == uid: rank = i; break
    con.close()
    return jsonify({'status':'ok','best_time':best,'rank':rank})

@app.route('/leaderboard')
def leaderboard():
    con = get_db(); cur = con.cursor()
    cur.execute('''
        SELECT u.name, MIN(r.seconds) as best_time, COUNT(r.id) as games
        FROM users u JOIN results r ON r.user_id=u.id
        GROUP BY u.id ORDER BY best_time ASC LIMIT 25
    ''')
    rows = cur.fetchall(); con.close()
    return render_template('leaderboard.html', rows=rows, title='Leaderboard')

# ---------------------
# Admin
# ---------------------
@app.route('/admin', methods=['GET','POST'])
def admin():
    if request.method == 'GET':
        if session.get('admin'): return render_template('admin_dashboard.html')
        return render_template('admin_login.html')
    email = request.form['email'].strip().lower()
    pw = request.form['password']
    if email == app.config['ADMIN_EMAIL'] and pw == app.config['ADMIN_PASSWORD']:
        session['admin'] = True
        return redirect(url_for('admin'))
    return render_template('admin_login.html', err='Invalid admin credentials.')

@app.route("/admin/users")
def admin_users():
    db = get_db(); cur = db.cursor()
    try:
        cur.execute("SELECT id, name, email, created_at FROM users ORDER BY created_at DESC")
        users = cur.fetchall()
    except Exception as e:
        app.logger.exception("Admin users query failed: %s", e)
        users = []
    return render_template("admin_users.html", users=users)

@app.route("/admin/email_logs")
def admin_email_logs():
    db = get_db(); cur = db.cursor()
    try:
        cur.execute("SELECT id, recipient, subject, status, created_at FROM email_logs ORDER BY created_at DESC")
        logs = cur.fetchall()
    except Exception as e:
        app.logger.exception("Admin email logs query failed: %s", e)
        logs = []
    return render_template("admin_email_logs.html", logs=logs)

@app.route("/admin/password_resets")
def admin_password_resets():
    db = get_db(); cur = db.cursor()
    try:
        cur.execute("SELECT id, email, token, expires_at, used, created_at FROM password_resets ORDER BY created_at DESC")
        resets = cur.fetchall()
    except Exception as e:
        app.logger.exception("Admin password resets query failed: %s", e)
        resets = []
    return render_template("admin_password_resets.html", resets=resets)

# ---------------------
# Scheduler
# ---------------------
def send_weekly_digest():
    if not app.config.get('EMAIL_ENABLED') or not app.config.get('DIGEST_ENABLED'): return
    con = get_db(); cur = con.cursor()
    since = datetime.utcnow() - timedelta(days=7)
    cur.execute('SELECT id,name,email FROM users'); users = cur.fetchall()
    for u in users:
        uid, name, email = u['id'], u['name'], u['email']
        cur.execute('SELECT COUNT(*), MIN(seconds), AVG(seconds) FROM results WHERE user_id=? AND played_at >= ?', (uid, since))
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
    con.close()

def scheduler_thread():
    while True:
        try:
            schedule.run_pending()
        except Exception as e:
            print('Scheduler error:', e)
        time_mod.sleep(60)

def setup_schedule():
    schedule.every().sunday.at(app.config.get('DIGEST_IST_TIME','18:00')).do(send_weekly_digest)
    t = threading.Thread(target=scheduler_thread, daemon=True); t.start()

# ---------------------
# Init
# ---------------------
try:
    init_db()
except Exception as e:
    print("init_db error:", e)

if not os.environ.get("DISABLE_SCHEDULER"):
    try:
        setup_schedule()
    except Exception as e:
        print("setup_schedule error:", e)

if __name__ == '__main__':
    init_db()
    setup_schedule()
    app.run(debug=True)
