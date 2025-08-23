import os
import psycopg2
from psycopg2.extras import RealDictCursor
from urllib.parse import urlparse

def get_db():
    # Get database URL from environment variable
    database_url = os.environ.get('DATABASE_URL')
    if not database_url:
        # Fallback to SQLite for local development
        import sqlite3
        conn = sqlite3.connect("sudoku.db")
        conn.row_factory = sqlite3.Row
        return conn
    
    # Parse the database URL for PostgreSQL
    result = urlparse(database_url)
    
    # Connect to the database
    conn = psycopg2.connect(
        database=result.path[1:],
        user=result.username,
        password=result.password,
        host=result.hostname,
        port=result.port,
        sslmode='require'
    )
    conn.autocommit = True
    return conn

def init_db():
    conn = get_db()
    cur = conn.cursor()
    
    # Check if we're using PostgreSQL or SQLite
    is_postgres = hasattr(conn, 'pgconn')
    
    if is_postgres:
        # Create tables if they don't exist for PostgreSQL
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
                user_id INTEGER,
                seconds INTEGER,
                played_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        cur.execute("""
            CREATE TABLE IF NOT EXISTS sent_emails(
                id SERIAL PRIMARY KEY,
                user_id INTEGER,
                email TEXT,
                subject TEXT,
                body TEXT,
                sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        cur.execute("""
            CREATE TABLE IF NOT EXISTS password_resets(
                id SERIAL PRIMARY KEY,
                user_id INTEGER,
                otp_hash TEXT,
                expires_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        cur.execute("""
            CREATE TABLE IF NOT EXISTS otp_rate_limit(
                email TEXT PRIMARY KEY,
                last_request_ts REAL
            )
        """)
    else:
        # SQLite table creation
        cur.execute("""CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            email TEXT UNIQUE,
            password_hash TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
    
    cur.close()
    if not is_postgres:
        conn.commit()
    conn.close()
