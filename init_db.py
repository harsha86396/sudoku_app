import sqlite3
import os

# Stable DB path (same logic as config.py)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.environ.get("DATABASE_PATH") or os.path.join(BASE_DIR, "sudoku.db")

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    # Users table
    c.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # Scores table (linked to users)
    c.execute("""
    CREATE TABLE IF NOT EXISTS scores (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        time_taken INTEGER NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id)
    )
    """)

    # Email logs table
    c.execute("""
    CREATE TABLE IF NOT EXISTS email_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        recipient TEXT NOT NULL,
        subject TEXT NOT NULL,
        status TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # Password resets table
    c.execute("""
    CREATE TABLE IF NOT EXISTS password_resets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT NOT NULL,
        token TEXT NOT NULL,
        expires_at TIMESTAMP NOT NULL,
        used INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    conn.commit()
    conn.close()
    print("✅ Database initialized successfully!")

if __name__ == "__main__":
    init_db()
