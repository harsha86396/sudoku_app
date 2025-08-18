import os, sqlite3, random, io, smtplib, ssl, threading, schedule, time as time_mod
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, send_file, g
from werkzeug.security import generate_password_hash, check_password_hash
from email.mime.text import MIMEText

# utils
from utils.sudoku import make_puzzle
from utils.pdf_utils import generate_last7_pdf
import config as config

# ----------------------------
# Persistent DB path (Render safe)
# ----------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INSTANCE_DIR = os.path.join(BASE_DIR, "instance")
os.makedirs(INSTANCE_DIR, exist_ok=True)
DB_PATH = os.path.join(INSTANCE_DIR, "sudoku.db")

# ----------------------------
# Flask app
# ----------------------------
app = Flask(__name__)
app.config.from_object(config)
app.secret_key = config.SECRET_KEY

# ----------------------------
# DB helpers
# ----------------------------
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES)
        g.db.row_factory = sqlite3.Row
    return g.db

def close_db(e=None):
    db = g.pop("db", None)
    if db is not None:
        try:
            db.commit()
        except Exception:
            pass
        db.close()

app.teardown_appcontext(close_db)

# ----------------------------
# Safe init: auto create tables if missing
# ----------------------------
def ensure_schema():
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        email TEXT UNIQUE,
        password_hash TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS results (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        seconds INTEGER,
        played_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )""")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS email_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        recipient TEXT,
        subject TEXT,
        status TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS password_resets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
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
    print("✅ Schema ensured at", DB_PATH)

# ----------------------------
# Email sender
# ----------------------------
def send_email(to_email, subject, body, user_id=None):
    if not app.config.get("EMAIL_ENABLED"):
        print("[EMAIL DISABLED]", subject, body)
        return False
    try:
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = app.config["SMTP_USER"]
        msg["To"] = to_email
        ctx = ssl.create_default_context()
        with smtplib.SMTP(app.config["SMTP_SERVER"], app.config["SMTP_PORT"]) as s:
            s.starttls(context=ctx)
            s.login(app.config["SMTP_USER"], app.config["SMTP_PASS"])
            s.send_message(msg)
        con = get_db(); cur = con.cursor()
        cur.execute("INSERT INTO email_logs(recipient, subject, status) VALUES(?,?,?)",
                    (to_email, subject, "SENT"))
        con.commit()
        return True
    except Exception as e:
        print("Email error:", e)
        return False

# ----------------------------
# Captcha + OTP helpers
# ----------------------------
def new_captcha():
    a, b = random.randint(1, 9), random.randint(1, 9)
    token = f"{random.randint(100000, 999999)}"
    ans = str(a + b)
    session["captcha_" + token] = ans
    return f"{a} + {b} = ?", token

def check_captcha(token, answer):
    key = "captcha_" + token
    correct = session.get(key)
    if not correct:
        return False
    ok = correct.strip() == answer.strip()
    session.pop(key, None)
    return ok

def rate_limit_ok(email):
    con = get_db(); cur = con.cursor()
    cur.execute("SELECT last_request_ts FROM otp_rate_limit WHERE email=?", (email,))
    row = cur.fetchone()
    now = time_mod.time()
    if row:
        last = row[0]
        if now - last < app.config.get("OTP_RATE_LIMIT_SECONDS", 60):
            return False, int(app.config.get("OTP_RATE_LIMIT_SECONDS", 60) - (now - last))
        cur.execute("UPDATE otp_rate_limit SET last_request_ts=? WHERE email=?", (now, email))
    else:
        cur.execute("INSERT INTO otp_rate_limit(email,last_request_ts) VALUES(?,?)", (email, now))
    con.commit()
    return True, 0

def create_and_send_otp(user_id, email, name):
    otp = f"{random.randint(0,999999):06d}"
    otp_hash = generate_password_hash(otp)
    expires = datetime.utcnow() + timedelta(minutes=app.config.get("OTP_EXP_MINUTES",10))
    con = get_db(); cur = con.cursor()
    cur.execute("INSERT INTO password_resets(user_id,otp_hash,expires_at) VALUES(?,?,?)",
                (user_id, otp_hash, expires))
    con.commit()
    body = f"Hi {name},\n\nYour OTP to reset your password is: {otp}\nIt expires in {app.config.get('OTP_EXP_MINUTES',10)} minutes."
    send_email(email, "Sudoku Password Reset", body, user_id)
    return True

# ----------------------------
# Routes: auth
# ----------------------------
@app.route("/")
def index():
    if "user_id" in session: return redirect(url_for("dashboard"))
    q, t = new_captcha()
    return render_template("index.html", captcha_q=q, captcha_t=t)

@app.route("/register", methods=["POST"])
def register():
    name = request.form["name"].strip()
    email = request.form["email"].strip().lower()
    password = request.form["password"]
    cap_ans = request.form["captcha_answer"]; cap_tok = request.form["captcha_token"]
    if not check_captcha(cap_tok, cap_ans):
        q, t = new_captcha()
        return render_template("index.html", err="CAPTCHA incorrect.", captcha_q=q, captcha_t=t)
    pw_hash = generate_password_hash(password)
    con = get_db(); cur = con.cursor()
    try:
        cur.execute("INSERT INTO users(name,email,password_hash) VALUES(?,?,?)", (name, email, pw_hash))
        con.commit()
        send_email(email, "Welcome to Sudoku", f"Hello {name}, your account has been created.")
        q, t = new_captcha()
        return render_template("index.html", msg="Registration successful. Please log in.", captcha_q=q, captcha_t=t)
    except sqlite3.IntegrityError:
        q, t = new_captcha()
        return render_template("index.html", err="Email already registered.", captcha_q=q, captcha_t=t)

@app.route("/login", methods=["POST"])
def login():
    email = request.form["email"].strip().lower()
    password = request.form["password"]
    if email == app.config["ADMIN_EMAIL"] and password == app.config["ADMIN_PASSWORD"]:
        session["admin"] = True
        return redirect(url_for("admin"))
    con = get_db(); cur = con.cursor()
    cur.execute("SELECT id,name,password_hash FROM users WHERE email=?", (email,))
    row = cur.fetchone()
    if row and check_password_hash(row["password_hash"], password):
        session["user_id"] = row["id"]
        session["name"] = row["name"]
        session["hints_left"] = 3
        return redirect(url_for("dashboard"))
    q, t = new_captcha()
    return render_template("index.html", err="Invalid credentials.", captcha_q=q, captcha_t=t)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))

# ----------------------------
# Dashboard & Play
# ----------------------------
@app.route("/dashboard")
def dashboard():
    if "user_id" not in session: return redirect(url_for("index"))
    return render_template("dashboard.html", name=session["name"])

@app.route("/play")
def play():
    if "user_id" not in session: return redirect(url_for("index"))
    return render_template("play.html")

@app.route("/api/new_puzzle")
def api_new_puzzle():
    if "user_id" not in session: return jsonify({"error":"not logged in"}), 401
    diff = request.args.get("difficulty","medium")
    puzzle, solution = make_puzzle(diff)
    session["solution"] = solution
    session["puzzle"] = puzzle
    session["hints_left"] = 3
    return jsonify({"puzzle": puzzle, "solution": solution})

@app.route("/api/hint", methods=["POST"])
def api_hint():
    if "user_id" not in session: return jsonify({"error":"not logged in"}), 401
    hints_left = session.get("hints_left",3)
    if hints_left <= 0: return jsonify({"error":"No hints left"}), 400
    puzzle = session.get("puzzle"); solution = session.get("solution")
    empties = [(r,c) for r in range(9) for c in range(9) if puzzle[r][c]==0]
    if not empties: return jsonify({"error":"No empty cells"}), 400
    r,c = random.choice(empties)
    val = solution[r][c]
    puzzle[r][c] = val
    session["puzzle"] = puzzle
    session["hints_left"] = hints_left - 1
    return jsonify({"r":r,"c":c,"val":val,"hints_left":session["hints_left"]})

@app.route("/api/record_result", methods=["POST"])
def record_result():
    if "user_id" not in session: return jsonify({"error":"not logged in"}), 403
    seconds = int(request.json.get("seconds",0))
    if seconds <= 0: return jsonify({"error":"invalid time"}), 400
    uid = session["user_id"]
    con = get_db(); cur = con.cursor()
    cur.execute("INSERT INTO results(user_id,seconds) VALUES(?,?)", (uid, seconds))
    con.commit()
    cur.execute("SELECT MIN(seconds) FROM results WHERE user_id=?", (uid,))
    best = cur.fetchone()[0]
    cur.execute("""SELECT u.id, MIN(r.seconds) as best FROM users u
                   JOIN results r ON r.user_id=u.id
                   GROUP BY u.id ORDER BY best ASC""")
    rows = cur.fetchall()
    rank = 0
    for i, row in enumerate(rows, start=1):
        if row[0] == uid: rank = i; break
    con.close()
    return jsonify({"status":"ok","best_time":best,"rank":rank})

@app.route("/leaderboard")
def leaderboard():
    con = get_db(); cur = con.cursor()
    cur.execute("""SELECT u.name, MIN(r.seconds) as best_time, COUNT(r.id) as games
                   FROM users u JOIN results r ON r.user_id=u.id
                   GROUP BY u.id ORDER BY best_time ASC LIMIT 25""")
    rows = cur.fetchall(); con.close()
    return render_template("leaderboard.html", rows=rows)

# ----------------------------
# Password reset
# ----------------------------
@app.route("/forgot_password", methods=["GET","POST"])
def forgot_password():
    if request.method == "GET":
        q,t = new_captcha()
        return render_template("forgot_password.html", captcha_q=q, captcha_t=t)
    email = request.form["email"].strip().lower()
    cap_ans = request.form["captcha_answer"]; cap_tok = request.form["captcha_token"]
    if not check_captcha(cap_tok, cap_ans):
        q,t = new_captcha()
        return render_template("forgot_password.html", err="CAPTCHA incorrect.", email=email, captcha_q=q, captcha_t=t)
    ok, wait = rate_limit_ok(email)
    if not ok:
        return render_template("forgot_password.html", err=f"Please wait {wait}s before requesting another OTP.", email=email)
    con = get_db(); cur = con.cursor()
    cur.execute("SELECT id,name FROM users WHERE email=?", (email,))
    row = cur.fetchone()
    if not row:
        return render_template("forgot_password.html", err="Email not found.", email=email)
    create_and_send_otp(row["id"], email, row["name"])
    return render_template("reset_password.html", email=email, msg="OTP sent.")

@app.route("/reset_password", methods=["POST"])
def reset_password():
    email = request.form["email"].strip().lower()
    otp = request.form["otp"].strip()
    password = request.form["password"]
    confirm = request.form["confirm"]
    if password != confirm:
        return render_template("reset_password.html", email=email, err="Passwords do not match.")
    con = get_db(); cur = con.cursor()
    cur.execute("SELECT id,name FROM users WHERE email=?", (email,))
    user = cur.fetchone()
    if not user:
        return render_template("forgot_password.html", err="Email not found.", email=email)
    uid, name = user["id"], user["name"]
    cur.execute("SELECT otp_hash,expires_at FROM password_resets WHERE user_id=? ORDER BY created_at DESC LIMIT 1", (uid,))
    pr = cur.fetchone()
    if not pr: return render_template("reset_password.html", email=email, err="No OTP found.")
    otp_hash, expires_at = pr["otp_hash"], pr["expires_at"]
    exp = datetime.fromisoformat(expires_at) if isinstance(expires_at,str) else expires_at
    if datetime.utcnow() > exp:
        return render_template("reset_password.html", email=email, err="OTP expired.")
    if not check_password_hash(otp_hash, otp):
        return render_template("reset_password.html", email=email, err="Invalid OTP.")
    new_hash = generate_password_hash(password)
    cur.execute("UPDATE users SET password_hash=? WHERE id=?", (new_hash, uid))
    cur.execute("DELETE FROM password_resets WHERE user_id=?", (uid,))
    con.commit(); con.close()
    send_email(email, "Password Changed", f"Hi {name}, your password was reset successfully.", uid)
    q,t = new_captcha()
    return render_template("index.html", msg="Password reset successful. Please log in.", captcha_q=q, captcha_t=t)

# ----------------------------
# Admin
# ----------------------------
@app.route("/admin", methods=["GET","POST"])
def admin():
    if request.method == "GET":
        if session.get("admin"): return render_template("admin_dashboard.html")
        return render_template("admin_login.html")
    email = request.form["email"].strip().lower()
    pw = request.form["password"]
    if email == app.config["ADMIN_EMAIL"] and pw == app.config["ADMIN_PASSWORD"]:
        session["admin"] = True
        return redirect(url_for("admin"))
    return render_template("admin_login.html", err="Invalid admin credentials.")

@app.route("/admin/users")
def admin_users():
    if not session.get("admin"): return redirect(url_for("admin"))
    db = get_db(); cur = db.cursor()
    users = []
    try:
        cur.execute("SELECT id,name,email,created_at FROM users ORDER BY created_at DESC")
        users = cur.fetchall()
    except Exception as e:
        app.logger.exception("Admin users query failed: %s", e)
    return render_template("admin_users.html", users=users)

@app.route("/admin/email_logs")
def admin_email_logs():
    if not session.get("admin"): return redirect(url_for("admin"))
    db = get_db(); cur = db.cursor()
    logs = []
    try:
        cur.execute("SELECT id,recipient,subject,status,created_at FROM email_logs ORDER BY created_at DESC")
        logs = cur.fetchall()
    except Exception as e:
        app.logger.exception("Admin email logs query failed: %s", e)
    return render_template("admin_email_logs.html", logs=logs)

@app.route("/admin/password_resets")
def admin_password_resets():
    if not session.get("admin"): return redirect(url_for("admin"))
    db = get_db(); cur = db.cursor()
    resets = []
    try:
        cur.execute("SELECT id,user_id,expires_at,created_at FROM password_resets ORDER BY created_at DESC")
        resets = cur.fetchall()
    except Exception as e:
        app.logger.exception("Admin password resets query failed: %s", e)
    return render_template("admin_password_resets.html", resets=resets)

# ----------------------------
# Weekly digest
# ----------------------------
def send_weekly_digest():
    if not app.config.get("EMAIL_ENABLED") or not app.config.get("DIGEST_ENABLED"): return
    con = get_db(); cur = con.cursor()
    since = datetime.utcnow() - timedelta(days=7)
    cur.execute("SELECT id,name,email FROM users")
    users = cur.fetchall()
    for u in users:
        uid, name, email = u["id"], u["name"], u["email"]
        cur.execute("SELECT COUNT(*),MIN(seconds),AVG(seconds) FROM results WHERE user_id=? AND played_at>=?", (uid,since))
        games,best,avg = cur.fetchone()
        if games and games>0:
            body = f"Hi {name},\n\nWeekly Sudoku stats:\nGames: {games}\nBest: {int(best)}s\nAvg: {int(avg)}s"
            send_email(email,"Your Weekly Sudoku Progress",body,uid)
    con.close()

def scheduler_thread():
    while True:
        try:
            schedule.run_pending()
        except Exception as e:
            print("Scheduler error:", e)
        time_mod.sleep(60)

# ----------------------------
# Startup
# ----------------------------
ensure_schema()
if not os.environ.get("DISABLE_SCHEDULER"):
    schedule.every().sunday.at(app.config.get("DIGEST_IST_TIME","18:00")).do(send_weekly_digest)
    threading.Thread(target=scheduler_thread, daemon=True).start()

if __name__ == "__main__":
    app.run(debug=True)
