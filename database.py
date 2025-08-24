# database.py
import sqlite3
import os
from urllib.parse import urlparse

def get_db():
    """Get database connection with proper error handling"""
    # Use PostgreSQL if DATABASE_URL is set (production)
    if os.environ.get('DATABASE_URL'):
        try:
            import psycopg2
            from psycopg2.extras import RealDictCursor
            
            # Parse the database URL
            result = urlparse(os.environ['DATABASE_URL'])
            username = result.username
            password = result.password
            database = result.path[1:]
            hostname = result.hostname
            port = result.port
            
            # Connect to PostgreSQL
            conn = psycopg2.connect(
                database=database,
                user=username,
                password=password,
                host=hostname,
                port=port,
                sslmode='require'
            )
            
            # Create a cursor that returns dictionaries
            cur = conn.cursor(cursor_factory=RealDictCursor)
            return conn
            
        except ImportError:
            print("PostgreSQL dependencies not found. Falling back to SQLite.")
            return get_sqlite_db()
        except Exception as e:
            print(f"PostgreSQL connection failed: {e}. Falling back to SQLite.")
            return get_sqlite_db()
    else:
        # Use SQLite for development
        return get_sqlite_db()

def get_sqlite_db():
    """Get SQLite database connection"""
    try:
        conn = sqlite3.connect("sudoku.db")
        conn.row_factory = sqlite3.Row
        return conn
    except Exception as e:
        print(f"SQLite connection failed: {e}")
        raise

def init_db():
    conn = None
    try:
        conn = get_db()
        cur = conn.cursor()
        
        # Check if we're using PostgreSQL by trying to detect it
        is_postgres = False
        try:
            # Try to execute a PostgreSQL-specific function
            cur.execute("SELECT version()")
            is_postgres = True
            print("✓ PostgreSQL database detected")
        except:
            print("✓ SQLite database detected")
        
        # Create tables
        if is_postgres:
            # PostgreSQL table creation
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users(
                    id SERIAL PRIMARY KEY,
                    name TEXT NOT NULL,
                    email TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            cur.execute("""
                CREATE TABLE IF NOT EXISTS results(
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER REFERENCES users(id),
                    seconds INTEGER NOT NULL,
                    played_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            cur.execute("""
                CREATE TABLE IF NOT EXISTS sent_emails(
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER REFERENCES users(id),
                    email TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    body TEXT NOT NULL,
                    sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            cur.execute("""
                CREATE TABLE IF NOT EXISTS password_resets(
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER REFERENCES users(id),
                    otp_hash TEXT NOT NULL,
                    expires_at TIMESTAMP NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            cur.execute("""
                CREATE TABLE IF NOT EXISTS otp_rate_limit(
                    email TEXT PRIMARY KEY,
                    last_request_ts DOUBLE PRECISION NOT NULL
                )
            """)
        else:
            # SQLite table creation
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    email TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            cur.execute("""
                CREATE TABLE IF NOT EXISTS results(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    seconds INTEGER NOT NULL,
                    played_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(user_id) REFERENCES users(id)
                )
            """)
            
            cur.execute("""
                CREATE TABLE IF NOT EXISTS sent_emails(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    email TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    body TEXT NOT NULL,
                    sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(user_id) REFERENCES users(id)
                )
            """)
            
            cur.execute("""
                CREATE TABLE IF NOT EXISTS password_resets(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    otp_hash TEXT NOT NULL,
                    expires_at TIMESTAMP NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(user_id) REFERENCES users(id)
                )
            """)
            
            cur.execute("""
                CREATE TABLE IF NOT EXISTS otp_rate_limit(
                    email TEXT PRIMARY KEY,
                    last_request_ts REAL NOT NULL
                )
            """)
        
        conn.commit()
        print("✓ Database tables created successfully")
        
    except Exception as e:
        print(f"✗ Database initialization error: {e}")
        if conn:
            conn.rollback()
        raise
    finally:
        if conn:
            conn.close()

# Helper function for app.py to use
def get_db_connection():
    """Get database connection with proper error handling"""
    try:
        conn = get_db()
        return conn
    except Exception as e:
        print(f"Database connection error: {e}")
        # Try to reconnect or fallback to SQLite
        try:
            init_db()
            return get_db()
        except Exception as e2:
            print(f"Failed to reconnect to database: {e2}")
            raise Exception("Database connection failed")

def is_postgres(conn):
    """Check if connection is PostgreSQL"""
    return hasattr(conn, 'pgconn') or 'psycopg2' in str(type(conn))

def execute_query(cur, query, params=None):
    """Execute query with proper parameter formatting for database type"""
    if params is None:
        params = ()
    
    # Check if we're using PostgreSQL by looking at cursor type
    is_pg = hasattr(cur, 'pgcursor') or 'psycopg2' in str(type(cur))
    
    if is_pg:
        # Convert SQLite ? placeholders to %s for PostgreSQL
        if '?' in query:
            query = query.replace('?', '%s')
        cur.execute(query, params)
    else:
        cur.execute(query, params)
    
    return cur
