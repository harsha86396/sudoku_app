import os
import smtplib
import ssl
import random
from datetime import datetime, timedelta

from flask import (
    Flask, render_template, request, redirect,
    url_for, session, jsonify, send_file, flash
)
from email.mime.text import MIMEText
from werkzeug.security import generate_password_hash, check_password_hash

import psycopg2
import psycopg2.extras

from config import (
    SECRET_KEY,
    OTP_EXPIRY,          # seconds (e.g., 300)
    SMTP_SERVER, SMTP_PORT, EMAIL_ADDRESS, EMAIL_PASSWORD
)
from database import get_db, close_db, init_db


# ---------- App Setup ----------
app = Flask(__name__)
app.secret_key = SECRET_KEY

APP_NAME = os.getenv("APP_NAME", "Sudoku powered by Harsha Enterprises")
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "admin@sudoku.local")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")


# ---------- Helpers ----------
def dict_cursor(conn):
    """Create a cursor that returns dict rows."""
    return conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

def send_email(to_email: str, subject: str, body: str):
    """Best-effort email (never blocks app flow)."""
    if not (EMAIL_ADDRESS and EMAIL_PASSWORD and SMTP_SERVER and SMTP_PORT):
        return False, "email not configured"

    try:
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = EMAIL_ADDRESS
        msg["To"] = to_email

        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT, context=context) as server:
            server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
            server.sendmail(EMAIL_ADDRESS, [to_email], msg.as_string())
        return True, "sent"
    except Exception as e:
        # Log to stderr; do not raise
        print(f"[email] error: {e}")
        return False, str(e)

def require_login():
    return "user_id" in session

def new_captcha():
    """Simple arithmetic captcha to reduce brute force."""
    a, b = random.randint(1, 9), random.randint(1, 9)
    token = str(random.randint(100000, 999999))
    session[f"captcha_{token}"] = a + b
    return f"{a} + {b} = ?", token

def check_captcha(token: str, answer: str):
    key = f"captcha_{token}"
    expected = session.pop(key, None)
    try:
        return expected is not None and int(answer) == int(expected)
    except Exception:
        return False


# ---------- Health ----------
@app.route("/healthz")
def healthz():
    return jsonify(ok=True, app=APP_NAME, time=datetime.utcnow().isoformat() + "Z")


# ---------- Home ----------
@app.route("/")
def index():
    return render_template("index.html", app_name=APP_NAME)


# ---------- Auth ----------
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        q, t = new_captcha()
        return render_template("register.html", captcha_q=q, captcha_t=t, app_name=APP_NAME)

    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")
    token = request.form.get("captcha_token")
    answer = request.form.get("captcha_answer", "")

    if not all([name, email, password]):
        q, t = new_captcha()
        return render_template("register.html", err="All fields are required.", captcha_q=q, captcha_t=t, app_name=APP_NAME)

    if not check_captcha(token, answer):
        q, t = new_captcha()
        return render_template("register.html", err="Invalid captcha.", captcha_q=q, captcha_t=t, app_name=APP_NAME)

    conn = get_db()
    cur = dict_cursor(conn)
    try:
        cur.execute("SELECT 1 FROM users WHERE email = %s", (email,))
        if cur.fetchone():
            q, t = new_captcha()
            return render_template("register.html", err="Email already registered.", captcha_q=q, captcha_t=t, app_name=APP_NAME)

        cur.execute(
            "INSERT INTO users (username, email, password_hash, verified) VALUES (%s, %s, %s, %s) RETURNING id",
            (name, email, generate_password_hash(password), True)
        )
        conn.commit()
        flash("Registration successful. Please login.")
        return redirect(url_for("login"))
    finally:
        cur.close()


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        q, t = new_captcha()
        return render_template("login.html", captcha_q=q, captcha_t=t, app_name=APP_NAME)

    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")
    token = request.form.get("captcha_token")
    answer = request.form.get("captcha_answer", "")

    if not check_captcha(token, answer):
        q, t = new_captcha()
        return render_template("login.html", err="Invalid captcha.", captcha_q=q, captcha_t=t, app_name=APP_NAME)

    # Admin bypass
    if email == ADMIN_EMAIL and password == ADMIN_PASSWORD:
        session.clear()
        session["admin"] = True
        return redirect(url_for("admin_dashboard"))

    conn = get_db()
    cur = dict_cursor(conn)
    try:
        cur.execute("SELECT id, username, email, password_hash FROM users WHERE email = %s", (email,))
        user = cur.fetchone()
        if not user or not check_password_hash(user["password_hash"], password):
            q, t = new_captcha()
            return render_template("login.html", err="Invalid email or password.", captcha_q=q, captcha_t=t, app_name=APP_NAME)

        session.clear()
        session["user_id"] = user["id"]
        session["name"] = user["username"]
        flash("Login successful.")
        return redirect(url_for("dashboard"))
    finally:
        cur.close()


@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out.")
    return redirect(url_for("index"))


# ---------- Dashboard ----------
@app.route("/dashboard")
def dashboard():
    if not require_login():
        return redirect(url_for("login"))
    return render_template("dashboard.html", name=session.get("name"), app_name=APP_NAME)


# ---------- Leaderboard ----------
@app.route("/leaderboard")
def leaderboard():
    conn = get_db()
    cur = dict_cursor(conn)
    try:
        # Expect a 'leaderboard' table with username, score
        cur.execute("""
            SELECT username, score, created_at
            FROM leaderboard
            ORDER BY score DESC, created_at ASC
            LIMIT 50
        """)
        rows = cur.fetchall() or []
        return render_template("leaderboard.html", rows=rows, app_name=APP_NAME)
    finally:
        cur.close()


# ---------- OTP Password Reset ----------
@app.route("/forgot", methods=["GET", "POST"])
def forgot_password():
    if request.method == "GET":
        return render_template("forgot_password.html", app_name=APP_NAME)

    email = request.form.get("email", "").strip().lower()
    if not email:
        return render_template("forgot_password.html", err="Enter your email.", app_name=APP_NAME)

    conn = get_db()
    cur = dict_cursor(conn)
    try:
        cur.execute("SELECT id, username FROM users WHERE email = %s", (email,))
        user = cur.fetchone()
        # Avoid leaking whether email exists
        if not user:
            return render_template("reset_password.html", email=email, msg="If the email exists, an OTP has been sent.", app_name=APP_NAME)

        otp = f"{random.randint(100000, 999999)}"
        expires = datetime.utcnow() + timedelta(seconds=int(OTP_EXPIRY))
        cur.execute(
            "INSERT INTO otps (email, otp, expiry) VALUES (%s, %s, %s)",
            (email, otp, expires)
        )
        conn.commit()

        body = f"Hi {user['username']},\n\nYour OTP is {otp}. It expires in {int(OTP_EXPIRY)//60} minutes.\n\n— {APP_NAME}"
        send_email(email, f"{APP_NAME} Password Reset", body)
        return render_template("reset_password.html", email=email, msg="If the email exists, an OTP has been sent.", app_name=APP_NAME)
    finally:
        cur.close()


@app.route("/reset", methods=["POST"])
def reset_password():
    email = request.form.get("email", "").strip().lower()
    otp = request.form.get("otp", "").strip()
    new_pw = request.form.get("password", "")

    if not all([email, otp, new_pw]):
        return render_template("reset_password.html", email=email, err="Fill all fields.", app_name=APP_NAME)

    conn = get_db()
    cur = dict_cursor(conn)
    try:
        cur.execute("SELECT id FROM users WHERE email = %s", (email,))
        user = cur.fetchone()
        if not user:
            return render_template("reset_password.html", email=email, err="Invalid email/OTP.", app_name=APP_NAME)

        cur.execute("""
            SELECT id, expiry
            FROM otps
            WHERE email = %s AND otp = %s
            ORDER BY created_at DESC
            LIMIT 1
        """, (email, otp))
        row = cur.fetchone()
        if not row:
            return render_template("reset_password.html", email=email, err="Invalid or expired OTP.", app_name=APP_NAME)

        try:
            expires_at = row["expiry"]
            if isinstance(expires_at, str):
                # If stored as text in some deployments
                expires_at = datetime.fromisoformat(expires_at)
        except Exception:
            return render_template("reset_password.html", email=email, err="Invalid or expired OTP.", app_name=APP_NAME)

        if datetime.utcnow() > expires_at:
            return render_template("reset_password.html", email=email, err="OTP expired.", app_name=APP_NAME)

        cur.execute(
            "UPDATE users SET password_hash = %s WHERE id = %s",
            (generate_password_hash(new_pw), user["id"])
        )
        conn.commit()
        flash("Password updated. Please login.")
        return redirect(url_for("login"))
    finally:
        cur.close()


# ---------- Admin ----------
def require_admin():
    return session.get("admin") is True

@app.route("/admin")
def admin_dashboard():
    if not require_admin():
        return render_template("admin_login.html", app_name=APP_NAME)

    conn = get_db()
    cur = dict_cursor(conn)
    try:
        cur.execute("SELECT COUNT(*) AS users FROM users")
        users = cur.fetchone()["users"]
        cur.execute("SELECT COUNT(*) AS rows FROM leaderboard")
        leaderboard_rows = cur.fetchone()["rows"]
        cur.execute("SELECT COUNT(*) AS resets FROM otps")
        resets = cur.fetchone()["resets"]
        return render_template("admin_dashboard.html", users=users, leaderboard_rows=leaderboard_rows, resets=resets, app_name=APP_NAME)
    finally:
        cur.close()

@app.route("/admin/login", methods=["POST"])
def admin_login():
    email = request.form.get("email", "")
    password = request.form.get("password", "")
    if email == ADMIN_EMAIL and password == ADMIN_PASSWORD:
        session["admin"] = True
        return redirect(url_for("admin_dashboard"))
    return render_template("admin_login.html", err="Invalid admin credentials.", app_name=APP_NAME)

@app.route("/admin/users")
def admin_users():
    if not require_admin():
        return render_template("admin_login.html", app_name=APP_NAME)
    conn = get_db()
    cur = dict_cursor(conn)
    try:
        cur.execute("SELECT id, username, email, created_at FROM users ORDER BY created_at DESC")
        rows = cur.fetchall()
        return render_template("admin_users.html", rows=rows, app_name=APP_NAME)
    finally:
        cur.close()

@app.route("/admin/otps")
def admin_otps():
    if not require_admin():
        return render_template("admin_login.html", app_name=APP_NAME)
    conn = get_db()
    cur = dict_cursor(conn)
    try:
        cur.execute("SELECT email, otp, expiry, created_at FROM otps ORDER BY created_at DESC LIMIT 200")
        rows = cur.fetchall()
        return render_template("admin_resets.html", rows=rows, app_name=APP_NAME)
    finally:
        cur.close()


# ---------- Error Pages ----------
@app.errorhandler(404)
def not_found(e):
    # Render a soft 404 that still includes your base layout
    try:
        return render_template("404.html", app_name=APP_NAME), 404
    except Exception:
        return ("Page not found.", 404)

@app.errorhandler(500)
def internal_error(e):
    try:
        return render_template("500.html", app_name=APP_NAME), 500
    except Exception:
        return ("Internal server error.", 500)


# ---------- Teardown ----------
@app.teardown_appcontext
def teardown_db(exception):
    close_db(exception)


# ---------- App bootstrap ----------
# Ensure tables exist on boot (idempotent)
with app.app_context():
    init_db()


# ---------- Dev entry ----------
if __name__ == "__main__":
    # Local testing only — production should use: gunicorn app:app
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=bool(int(os.getenv("DEBUG", "0"))))
