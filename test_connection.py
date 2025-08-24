# test_connection.py
from database import get_db_connection, init_db

def test_connection():
    print("Testing database connection...")
    try:
        init_db()
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Test if users table exists and has data
        try:
            cur.execute("SELECT COUNT(*) FROM users")
            count = cur.fetchone()
            print(f"✓ Users table exists with {count[0]} records")
        except Exception as e:
            print(f"✗ Users table error: {e}")
        
        cur.close()
        conn.close()
        print("✓ Database connection successful")
        
    except Exception as e:
        print(f"✗ Database connection failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_connection()
