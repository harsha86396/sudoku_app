# database.py
import sqlite3
import os
from urllib.parse import urlparse

def get_db():
    # Use PostgreSQL if DATABASE_URL is set (production)
    if os.environ.get('DATABASE_URL'):
        import psycopg2
        import psycopg2.extras
        
        result = urlparse(os.environ['DATABASE_URL'])
        username = result.username
        password = result.password
        database = result.path[1:]
        hostname = result.hostname
        port = result.port
        
        conn = psycopg2.connect(
            database=database,
            user=username,
            password=password,
            host=hostname,
            port=port
        )
        # Use DictCursor for PostgreSQL to match SQLite's row_factory behavior
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        return conn
    else:
        # Use SQLite for development
        conn = sqlite3.connect("sudoku.db")
        conn.row_factory = sqlite3.Row
        return conn

def init_db():
    conn = get_db()
    cur = conn.cursor()
    
    # Check if we're using PostgreSQL
    is_postgres = os.environ.get('DATABASE_URL') is not None
    
    if is_postgres:
        # PostgreSQL table creation
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users(
                id SERIAL PRIMARY KEY,
                name TEXT,
                email TEXT UNIQUE,
                password_hash TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        cur.execute("""
            CREATE TABLE IF NOT EXISTS results(
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id),
                seconds INTEGER,
                played_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        cur.execute("""
            CREATE TABLE IF NOT EXISTS sent_emails(
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id),
                email TEXT,
                subject TEXT,
                body TEXT,
                sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        cur.execute("""
            CREATE TABLE IF NOT EXISTS password_resets(
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id),
                otp_hash TEXT,
                expires_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        cur.execute("""
            CREATE TABLE IF NOT EXISTS otp_rate_limit(
                email TEXT PRIMARY KEY,
                last_request_ts DOUBLE PRECISION
            )
        """)
    else:
        # SQLite table creation
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                email TEXT UNIQUE,
                password_hash TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        cur.execute("""
            CREATE TABLE IF NOT EXISTS results(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                seconds INTEGER,
                played_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
        """)
        
        cur.execute("""
            CREATE TABLE IF NOT EXISTS sent_emails(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                email TEXT,
                subject TEXT,
                body TEXT,
                sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
        """)
        
        cur.execute("""
            CREATE TABLE IF NOT EXISTS password_resets(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                otp_hash TEXT,
                expires_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
        """)
        
        cur.execute("""
            CREATE TABLE IF NOT EXISTS otp_rate_limit(
                email TEXT PRIMARY KEY,
                last_request_ts REAL
            )
        """)
    
    conn.commit()
    cur.close()
    conn.close()
