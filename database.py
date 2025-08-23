
import sqlite3
import os
from config import Config

def get_db():
    conn = sqlite3.connect(Config.DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cur = conn.cursor()

    # Users
    cur.execute(
        "CREATE TABLE IF NOT EXISTS users ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "name TEXT NOT NULL,"
        "email TEXT NOT NULL UNIQUE,"
        "password_hash TEXT NOT NULL,"
        "email_verified INTEGER DEFAULT 0,"
        "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
        ")"
    )

    # Password reset OTPs
    cur.execute(
        "CREATE TABLE IF NOT EXISTS password_resets ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "user_id INTEGER NOT NULL,"
        "otp_hash TEXT NOT NULL,"
        "expires_at REAL NOT NULL,"
        "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,"
        "FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE"
        ")"
    )

    # OTP rate limit
    cur.execute(
        "CREATE TABLE IF NOT EXISTS otp_rate_limit ("
        "email TEXT PRIMARY KEY,"
        "last_request_ts REAL"
        ")"
    )

    # Game results
    cur.execute(
        "CREATE TABLE IF NOT EXISTS results ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "user_id INTEGER NOT NULL,"
        "seconds INTEGER NOT NULL,"
        "difficulty TEXT NOT NULL,"
        "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,"
        "FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE"
        ")"
    )

    conn.commit()
    cur.close()
    conn.close()
