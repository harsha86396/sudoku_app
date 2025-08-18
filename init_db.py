# init_db.py
import sqlite3, os

DB_FILE = os.path.join(os.path.dirname(__file__), "sudoku.db")

def init_db():
    con = sqlite3.connect(DB_FILE, detect_types=sqlite3.PARSE_DECLTYPES)
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
    print(f"✅ Database initialized / upgraded at {DB_FILE}")

if __name__ == "__main__":
    init_db()
