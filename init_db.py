import psycopg
from psycopg.rows import dict_row
import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DB_URL = os.environ.get("DATABASE_URL")

def init_db():
    logger.info("Initializing PostgreSQL database")
    con = psycopg.connect(DB_URL, row_factory=dict_row)
    cur = con.cursor()

    # Users
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY,
        name TEXT,
        email TEXT UNIQUE,
        password_hash TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # Results (game plays)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS results (
        id SERIAL PRIMARY KEY,
        user_id INTEGER,
        seconds INTEGER,
        played_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )
    """)

    # Email logs
    cur.execute("""
    CREATE TABLE IF NOT EXISTS email_logs (
        id SERIAL PRIMARY KEY,
        recipient TEXT,
        subject TEXT,
        status TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # Password resets
    cur.execute("""
    CREATE TABLE IF NOT EXISTS password_resets (
        id SERIAL PRIMARY KEY,
        user_id INTEGER,
        token TEXT,
        otp_hash TEXT,
        expires_at TIMESTAMP,
        used INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # OTP rate limit
    cur.execute("""
    CREATE TABLE IF NOT EXISTS otp_rate_limit (
        email TEXT PRIMARY KEY,
        last_request_ts REAL
    )
    """)

    con.commit()
    con.close()
    logger.info("PostgreSQL database initialized successfully")

if __name__ == "__main__":
    init_db()
