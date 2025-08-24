# test_db.py
from database import init_db, get_db

def test_database():
    print("Testing database connection...")
    try:
        # Initialize database
        init_db()
        print("✓ Database initialized successfully")
        
        # Test connection
        conn = get_db()
        print("✓ Database connection successful")
        
        # Test basic query
        cur = conn.cursor()
        if hasattr(conn, 'pgconn'):
            cur.execute("SELECT version()")
        else:
            cur.execute("SELECT sqlite_version()")
        version = cur.fetchone()
        print(f"✓ Database version: {version[0]}")
        
        # Check tables
        if hasattr(conn, 'pgconn'):
            cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
        else:
            cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = cur.fetchall()
        print("✓ Tables found:", [table[0] for table in tables])
        
        cur.close()
        conn.close()
        print("✓ All tests passed!")
        
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_database()
