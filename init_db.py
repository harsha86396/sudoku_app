import os
import psycopg

db_url = os.environ.get("DATABASE_URL")
if not db_url:
    raise ValueError("DATABASE_URL environment variable is not set")
con = psycopg.connect(db_url)
cur = con.cursor()
cur.execute("DROP TABLE IF EXISTS results")
cur.execute("DROP TABLE IF EXISTS users")
cur.execute("DROP TABLE IF EXISTS email_logs")
cur.execute("DROP TABLE IF EXISTS password_resets")
cur.execute("DROP TABLE IF EXISTS otp_rate_limit")
cur.execute("""
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    name TEXT,
    email TEXT UNIQUE,
    password_hash TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)""")
cur.execute("""
CREATE TABLE results (
    id SERIAL PRIMARY KEY,
    user_id INTEGER,
    seconds INTEGER,
    played_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(user_id) REFERENCES users(id)
)""")
cur.execute("""
CREATE TABLE email_logs (
    id SERIAL PRIMARY KEY,
    recipient TEXT,
    subject TEXT,
    status TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)""")
cur.execute("""
CREATE TABLE password_resets (
    id SERIAL PRIMARY KEY,
    user_id INTEGER,
    token TEXT,
    otp_hash TEXT,
    expires_at TIMESTAMP,
    used INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)""")
cur.execute("""
CREATE TABLE otp_rate_limit (
    email TEXT PRIMARY KEY,
    last_request_ts REAL
)""")
con.commit()
con.close()
print("Database initialized")
