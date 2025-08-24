# create_test_user.py
from database import get_db_connection, init_db
from werkzeug.security import generate_password_hash

def create_test_user():
    print("Creating test user...")
    try:
        init_db()
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Create test user
        email = "test@example.com"
        password = "password123"
        name = "Test User"
        
        # Check if user already exists
        try:
            cur.execute("SELECT id FROM users WHERE email = ?", (email,))
        except:
            cur.execute("SELECT id FROM users WHERE email = %s", (email,))
            
        existing_user = cur.fetchone()
        
        if existing_user:
            print("✓ Test user already exists")
        else:
            # Create new user
            pw_hash = generate_password_hash(password)
            try:
                cur.execute(
                    "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
                    (name, email, pw_hash)
                )
            except:
                cur.execute(
                    "INSERT INTO users (name, email, password_hash) VALUES (%s, %s, %s)",
                    (name, email, pw_hash)
                )
            
            conn.commit()
            print("✓ Test user created successfully")
            print(f"  Email: {email}")
            print(f"  Password: {password}")
        
        cur.close()
        conn.close()
        
    except Exception as e:
        print(f"✗ Error creating test user: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    create_test_user()
