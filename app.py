from flask import Flask, render_template, request, redirect, url_for, session, jsonify, send_file
import os, smtplib, ssl, io, random, time as time_mod, logging
from email.mime.text import MIMEText
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
from logging.handlers import RotatingFileHandler

from utils.sudoku import generate_sudoku
from utils.pdf_utils import generate_last7_pdf
import threading, schedule
import config as config

# Load environment variables
load_dotenv()

# Import database functions
from database import get_db, init_db

app = Flask(__name__)
app.config.from_object(config)

# Set secret key from environment or config
secret_key = os.environ.get('SECRET_KEY') or config.SECRET_KEY
app.secret_key = secret_key

# Configure logging
def setup_logging():
    logging.basicConfig(level=logging.INFO)
    handler = RotatingFileHandler('app.log', maxBytes=10000, backupCount=3)
    handler.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    app.logger.addHandler(handler)

def get_db_connection():
    """Get database connection with proper error handling"""
    try:
        conn = get_db()
        return conn
    except Exception as e:
        app.logger.error(f"Database connection error: {e}")
        # Try to reconnect or fallback to SQLite
        try:
            init_db()
            return get_db()
        except Exception as e2:
            app.logger.error(f"Failed to reconnect to database: {e2}")
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

def send_email(to_email, subject, body, user_id=None):
    if not app.config.get('EMAIL_ENABLED'):
        app.logger.info(f'[EMAIL DISABLED] To: {to_email}, Subject: {subject}, Body: {body}')
        return False
    try:
        msg = MIMEText(body)
        msg['Subject'] = subject
        msg['From'] = app.config['SMTP_USER']
        msg['To'] = to_email
        ctx = ssl.create_default_context()
        with smtplib.SMTP(app.config['SMTP_SERVER'], app.config['SMTP_PORT']) as s:
            s.starttls(context=ctx)
            s.login(app.config['SMTP_USER'], app.config['SMTP_PASS'])
            s.send_message(msg)
        
        conn = get_db_connection()
        cur = conn.cursor()
        execute_query(cur, 'INSERT INTO sent_emails(user_id,email,subject,body) VALUES(?,?,?,?)',
                    (user_id, to_email, subject, body))
        conn.commit()
        cur.close()
        conn.close()
        return True
    except Exception as e:
        app.logger.error(f'Email error: {e}')
        return False

def new_captcha():
    a, b = random.randint(1,9), random.randint(1,9)
    token = f"{random.randint(100000,999999)}"
    ans = str(a + b)
    session['captcha_' + token] = ans
    return f"{a} + {b} = ?", token

def check_captcha(token, answer):
    key = 'captcha_' + token
    correct = session.get(key)
    if not correct: return False
    ok = correct.strip() == answer.strip()
    session.pop(key, None)
    return ok

def rate_limit_ok(email):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        execute_query(cur, 'SELECT last_request_ts FROM otp_rate_limit WHERE email=?', (email,))
        row = cur.fetchone()
        now = time_mod.time()
        if row:
            last = row[0] if isinstance(row[0], (int, float)) else row['last_request_ts']
            if now - last < app.config.get('OTP_RATE_LIMIT_SECONDS',60):
                conn.close()
                return False, int(app.config.get('OTP_RATE_LIMIT_SECONDS',60) - (now-last))
            execute_query(cur, 'UPDATE otp_rate_limit SET last_request_ts=? WHERE email=?', (now,email))
        else:
            execute_query(cur, 'INSERT INTO otp_rate_limit(email,last_request_ts) VALUES(?,?)',(email,now))
        conn.commit()
        return True, 0
    except Exception as e:
        app.logger.error(f"Rate limit error: {e}")
        return False, 0
    finally:
        cur.close()
        conn.close()

@app.route('/')
def index():
    if 'user_id' in session: 
        return redirect(url_for('dashboard'))
    elif 'guest' in session:
        return redirect(url_for('play'))
    return render_template('index.html', title='Welcome')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'GET':
        if 'user_id' in session: 
            return redirect(url_for('dashboard'))
        elif 'guest' in session:
            return redirect(url_for('play'))
        q,t = new_captcha()
        return render_template('login.html', title='Login', captcha_q=q, captcha_t=t)
    
    # POST request handling
    email = request.form.get('email', '').strip().lower()
    password = request.form.get('password', '')
    
    if not email or not password:
        q,t = new_captcha()
        return render_template('login.html', err='Email and password are required.', captcha_q=q, captcha_t=t)
    
    # Check admin login first
    if email == app.config['ADMIN_EMAIL'] and password == app.config['ADMIN_PASSWORD']:
        session['admin'] = True
        return redirect(url_for('admin'))
    
    # Check regular user login
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        execute_query(cur, 'SELECT id,name,password_hash FROM users WHERE email=?', (email,))
        row = cur.fetchone()
        
        if row and check_password_hash(row['password_hash'], password):
            session['user_id'] = row['id']
            session['name'] = row['name']
            session['hints_left'] = 3
            app.logger.info(f"User {email} logged in successfully")
            return redirect(url_for('dashboard'))
        
        q,t = new_captcha()
        app.logger.warning(f"Failed login attempt for email: {email}")
        return render_template('login.html', err='Invalid credentials.', captcha_q=q, captcha_t=t)
    
    except Exception as e:
        app.logger.error(f"Login error: {e}")
        q,t = new_captcha()
        return render_template('login.html', err='An error occurred. Please try again.', captcha_q=q, captcha_t=t)
    
    finally:
        if conn:
            try:
                cur.close()
                conn.close()
            except:
                pass

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'GET':
        if 'user_id' in session: 
            return redirect(url_for('dashboard'))
        elif 'guest' in session:
            return redirect(url_for('play'))
        q,t = new_captcha()
        return render_template('register.html', title='Register', captcha_q=q, captcha_t=t)
    
    # POST request handling
    name = request.form.get('name', '').strip()
    email = request.form.get('email', '').strip().lower()
    password = request.form.get('password', '')
    cap_ans = request.form.get('captcha_answer', '')
    cap_tok = request.form.get('captcha_token', '')
    
    if not all([name, email, password, cap_ans, cap_tok]):
        q,t = new_captcha()
        return render_template('register.html', err='All fields are required.', captcha_q=q, captcha_t=t)
    
    if not check_captcha(cap_tok, cap_ans):
        q,t = new_captcha()
        return render_template('register.html', err='CAPTCHA incorrect.', captcha_q=q, captcha_t=t)
    
    if len(password) < 6:
        q,t = new_captcha()
        return render_template('register.html', err='Password must be at least 6 characters.', captcha_q=q, captcha_t=t)
    
    pw_hash = generate_password_hash(password)
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        execute_query(cur, 'INSERT INTO users(name,email,password_hash) VALUES(?,?,?)', (name,email,pw_hash))
        conn.commit()
        send_email(email, 'Welcome to Sudoku', f'Hello {name}, your account has been created.', None)
        q,t = new_captcha()
        app.logger.info(f"New user registered: {email}")
        return render_template('login.html', msg='Registration successful. Please log in.', captcha_q=q, captcha_t=t)
    except Exception as e:
        app.logger.error(f"Registration error: {e}")
        q,t = new_captcha()
        return render_template('register.html', err='Email already registered.', captcha_q=q, captcha_t=t)
    finally:
        if conn:
            try:
                cur.close()
                conn.close()
            except:
                pass

@app.route('/guest_login')
def guest_login():
    session.clear()
    session['guest'] = True
    session['name'] = 'Guest'
    session['hints_left'] = 3
    app.logger.info("Guest user logged in")
    return redirect(url_for('play'))

@app.route('/logout')
def logout():
    user_info = f"{session.get('name', 'Unknown')} ({session.get('user_id', 'guest')})"
    session.clear()
    app.logger.info(f"User {user_info} logged out")
    return redirect(url_for('index'))

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session and 'guest' not in session: 
        return redirect(url_for('index'))
    
    # Get user stats for dashboard
    if 'user_id' in session:
        conn = None
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            
            # Get total games played
            execute_query(cur, 'SELECT COUNT(*) FROM results WHERE user_id=?', (session['user_id'],))
            total_games = cur.fetchone()[0] or 0
            
            # Get best time
            execute_query(cur, 'SELECT MIN(seconds) FROM results WHERE user_id=?', (session['user_id'],))
            best_time_result = cur.fetchone()
            best_time = best_time_result[0] if best_time_result and best_time_result[0] is not None else 'N/A'
            
            # Get average time
            execute_query(cur, 'SELECT AVG(seconds) FROM results WHERE user_id=?', (session['user_id'],))
            avg_time_result = cur.fetchone()
            avg_time = avg_time_result[0] if avg_time_result and avg_time_result[0] is not None else 'N/A'
            
            # Get rank
            execute_query(cur, '''
                SELECT u.id, MIN(r.seconds) as best FROM users u
                JOIN results r ON r.user_id=u.id
                GROUP BY u.id ORDER BY best ASC
            ''')
            rows = cur.fetchall()
            
            rank = 0
            for i, row in enumerate(rows, start=1):
                user_id = row[0] if isinstance(row[0], int) else row['id']
                if user_id == session['user_id']: 
                    rank = i
                    break
            
            return render_template('dashboard.html', 
                                  name=session.get('name', 'User'), 
                                  title='Dashboard',
                                  total_games=total_games,
                                  best_time=best_time,
                                  avg_time=int(avg_time) if avg_time != 'N/A' else avg_time,
                                  rank=rank)
        
        except Exception as e:
            app.logger.error(f"Dashboard error: {e}")
            return render_template('dashboard.html', name=session.get('name', 'User'), title='Dashboard')
        
        finally:
            if conn:
                try:
                    cur.close()
                    conn.close()
                except:
                    pass
    
    return render_template('dashboard.html', name=session.get('name', 'User'), title='Dashboard')

def create_and_send_otp(user_id, email, name):
    otp = f"{random.randint(0, 999999):06d}"
    otp_hash = generate_password_hash(otp)
    expires = datetime.utcnow() + timedelta(minutes=app.config.get('OTP_EXP_MINUTES',10))
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        execute_query(cur, 'INSERT INTO password_resets(user_id, otp_hash, expires_at) VALUES(?,?,?)',
                    (user_id, otp_hash, expires))
        conn.commit()
        
        body = f"""Hi {name},
Your OTP code to reset your password is: {otp}
This code expires in {app.config.get('OTP_EXP_MINUTES',10)} minutes.

– Sudoku AI (Harsha Enterprises)"""
        send_email(email, 'Sudoku Password Reset', body, user_id)
        app.logger.info(f"OTP sent to {email} for user {user_id}")
        return True
    except Exception as e:
        app.logger.error(f"OTP creation error: {e}")
        return False
    finally:
        if conn:
            try:
                cur.close()
                conn.close()
            except:
                pass

@app.route('/forgot_password', methods=['GET','POST'])
def forgot_password():
    if request.method == 'GET':
        q,t = new_captcha()
        return render_template('forgot_password.html', captcha_q=q, captcha_t=t)
    
    email = request.form.get('email', '').strip().lower()
    cap_ans = request.form.get('captcha_answer', '')
    cap_tok = request.form.get('captcha_token', '')
    
    if not email or not cap_ans or not cap_tok:
        q,t = new_captcha()
        return render_template('forgot_password.html', err='All fields are required.', email=email, captcha_q=q, captcha_t=t)
    
    if not check_captcha(cap_tok, cap_ans):
        q,t = new_captcha()
        return render_template('forgot_password.html', err='CAPTCHA incorrect.', email=email, captcha_q=q, captcha_t=t)
    
    ok, wait = rate_limit_ok(email)
    if not ok:
        q,t = new_captcha()
        return render_template('forgot_password.html', err=f'Please wait {wait}s before requesting another OTP.', email=email, captcha_q=q, captcha_t=t)
    
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        execute_query(cur, 'SELECT id,name FROM users WHERE email=?', (email,))
        row = cur.fetchone()
        
        if not row:
            q,t = new_captcha()
            return render_template('forgot_password.html', err='Email not found.', email=email, captcha_q=q, captcha_t=t)
        
        create_and_send_otp(row['id'], email, row['name'])
        app.logger.info(f"Password reset requested for {email}")
        return render_template('reset_password.html', email=email, msg='OTP sent. Check your inbox.')
    
    except Exception as e:
        app.logger.error(f"Forgot password error: {e}")
        q,t = new_captcha()
        return render_template('forgot_password.html', err='An error occurred. Please try again.', email=email, captcha_q=q, captcha_t=t)
    
    finally:
        if conn:
            try:
                cur.close()
                conn.close()
            except:
                pass

@app.route('/resend_otp')
def resend_otp():
    email = request.args.get('email','').strip().lower()
    if not email:
        return render_template('reset_password.html', email=email, err='Email is required.')
    
    ok, wait = rate_limit_ok(email)
    if not ok:
        return render_template('reset_password.html', email=email, err=f'Please wait {wait}s before resending OTP.')
    
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        execute_query(cur, 'SELECT id,name FROM users WHERE email=?', (email,))
        row = cur.fetchone()
        
        if not row:
            q,t = new_captcha()
            return render_template('forgot_password.html', err='Email not found.', email=email, captcha_q=q, captcha_t=t)
        
        create_and_send_otp(row['id'], email, row['name'])
        app.logger.info(f"OTP resent to {email}")
        return render_template('reset_password.html', email=email, msg='A new OTP has been sent.')
    
    except Exception as e:
        app.logger.error(f"Resend OTP error: {e}")
        return render_template('reset_password.html', email=email, err='An error occurred. Please try again.')
    
    finally:
        if conn:
            try:
                cur.close()
                conn.close()
            except:
                pass

@app.route('/reset_password', methods=['POST'])
def reset_password():
    email = request.form.get('email', '').strip().lower()
    otp = request.form.get('otp', '').strip()
    password = request.form.get('password', '')
    confirm = request.form.get('confirm', '')
    
    if not all([email, otp, password, confirm]):
        return render_template('reset_password.html', email=email, err='All fields are required.')
    
    if password != confirm:
        return render_template('reset_password.html', email=email, err='Passwords do not match.')
    
    if len(password) < 6:
        return render_template('reset_password.html', email=email, err='Password must be at least 6 characters.')
    
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        execute_query(cur, 'SELECT id,name FROM users WHERE email=?', (email,))
        user = cur.fetchone()
        
        if not user:
            q,t = new_captcha()
            return render_template('forgot_password.html', err='Email not found.', email=email, captcha_q=q, captcha_t=t)
        
        uid = user['id'] if isinstance(user, dict) else user[0]
        name = user['name'] if isinstance(user, dict) else user[1]
        
        execute_query(cur, 'SELECT id, otp_hash, expires_at FROM password_resets WHERE user_id=? ORDER BY created_at DESC LIMIT 1', (uid,))
        pr = cur.fetchone()
        
        if not pr:
            return render_template('reset_password.html', email=email, err='No active OTP. Please request again.')
        
        pr_id = pr['id'] if isinstance(pr, dict) else pr[0]
        otp_hash = pr['otp_hash'] if isinstance(pr, dict) else pr[1]
        expires_at = pr['expires_at'] if isinstance(pr, dict) else pr[2]
        
        try:
            exp = datetime.fromisoformat(str(expires_at).replace('Z', '+00:00')) if isinstance(expires_at, str) else expires_at
        except Exception:
            exp = datetime.utcnow() - timedelta(seconds=1)
        
        if datetime.utcnow() > exp:
            return render_template('reset_password.html', email=email, err='OTP expired. Please request a new one.')
        
        if not check_password_hash(otp_hash, otp):
            return render_template('reset_password.html', email=email, err='Invalid OTP.')
        
        new_hash = generate_password_hash(password)
        execute_query(cur, 'UPDATE users SET password_hash=? WHERE id=?', (new_hash, uid))
        execute_query(cur, 'DELETE FROM password_resets WHERE user_id=?', (uid,))
        conn.commit()
        
        send_email(email, 'Password Changed', f'Hi {name}, your password was reset successfully.', uid)
        q,t = new_captcha()
        app.logger.info(f"Password reset successful for {email}")
        return render_template('login.html', msg='Password reset successful. Please log in.', captcha_q=q, captcha_t=t)
    
    except Exception as e:
        app.logger.error(f"Reset password error: {e}")
        return render_template('reset_password.html', email=email, err='An error occurred. Please try again.')
    
    finally:
        if conn:
            try:
                cur.close()
                conn.close()
            except:
                pass

@app.route('/play')
def play():
    if 'user_id' not in session and 'guest' not in session: 
        return redirect(url_for('index'))
    return render_template('play.html', title='Play')

@app.route('/api/new_puzzle')
def api_new_puzzle():
    if 'user_id' not in session and 'guest' not in session: 
        return jsonify({'error':'not logged in'}), 401
    
    try:
        diff = request.args.get('difficulty','medium')
        puzzle, solution = generate_sudoku(diff)
        
        # Store puzzle and solution in session
        session['solution'] = solution
        session['puzzle'] = puzzle
        session['hints_left'] = 3
        session['original_puzzle'] = [row[:] for row in puzzle]  # Store original state
        
        app.logger.info(f"New puzzle generated for {session.get('name')} with difficulty {diff}")
        return jsonify({'puzzle': puzzle, 'solution': solution})
    
    except Exception as e:
        app.logger.error(f"New puzzle error: {e}")
        return jsonify({'error': 'Failed to generate puzzle'}), 500

@app.route('/api/hint', methods=['POST'])
def api_hint():
    if 'user_id' not in session and 'guest' not in session: 
        return jsonify({'error':'not logged in'}), 401
    
    hints_left = session.get('hints_left',3)
    if hints_left <= 0: 
        return jsonify({'error':'No hints left'}), 400
    
    puzzle = session.get('puzzle')
    solution = session.get('solution')
    
    if not puzzle or not solution:
        return jsonify({'error':'No active puzzle'}), 400
    
    # Find empty cells
    empties = [(r,c) for r in range(9) for c in range(9) if puzzle[r][c]==0]
    
    if not empties: 
        return jsonify({'error':'No empty cells'}), 400
    
    # Get a random empty cell
    r,c = random.choice(empties)
    val = solution[r][c]
    
    # Update the puzzle
    puzzle[r][c] = val
    session['puzzle'] = puzzle
    session['hints_left'] = hints_left - 1
    
    app.logger.info(f"Hint used by {session.get('name')}. Hints left: {session['hints_left']}")
    return jsonify({'r':r,'c':c,'val':val,'hints_left':session['hints_left']})

@app.route('/api/record_result', methods=['POST'])
def record_result():
    if 'guest' in session:
        return jsonify({'error':'Guest mode - results not saved'}), 403
    
    if 'user_id' not in session: 
        return jsonify({'error':'not logged in'}), 403
    
    conn = None
    try:
        seconds = int(request.json.get('seconds',0))
        if seconds <= 0: 
            return jsonify({'error':'invalid time'}), 400
        
        uid = session['user_id']
        conn = get_db_connection()
        cur = conn.cursor()
        
        execute_query(cur, 'INSERT INTO results(user_id,seconds) VALUES(?,?)', (uid, seconds))
        conn.commit()
        
        execute_query(cur, 'SELECT MIN(seconds) FROM results WHERE user_id=?', (uid,))
        best_result = cur.fetchone()
        best = best_result[0] if best_result and best_result[0] is not None else seconds
        
        execute_query(cur, '''
            SELECT u.id, MIN(r.seconds) as best FROM users u
            JOIN results r ON r.user_id=u.id
            GROUP BY u.id ORDER BY best ASC
        ''')
        rows = cur.fetchall()
        
        rank = 0
        for i, row in enumerate(rows, start=1):
            user_id = row[0] if isinstance(row[0], int) else row['id']
            if user_id == uid: 
                rank = i
                break
        
        if seconds == best:
            execute_query(cur, 'SELECT email,name FROM users WHERE id=?',(uid,))
            user_data = cur.fetchone()
            if user_data:
                em = user_data['email'] if isinstance(user_data, dict) else user_data[0]
                nm = user_data['name'] if isinstance(user_data, dict) else user_data[1]
                send_email(em, '🎉 New Personal Best!', f'Congrats {nm}! New PB: {best}s. Keep it up!', uid)
        
        app.logger.info(f"Result recorded for {session.get('name')}: {seconds}s, best: {best}s, rank: {rank}")
        return jsonify({'status':'ok','best_time':best,'rank':rank})
    
    except Exception as e:
        app.logger.error(f"Record result error: {e}")
        return jsonify({'error': 'Failed to record result'}), 500
    
    finally:
        if conn:
            try:
                cur.close()
                conn.close()
            except:
                pass

@app.route('/leaderboard')
def leaderboard():
    if 'guest' in session:
        return render_template('guest_restricted.html', title='Leaderboard')
    
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        execute_query(cur, '''
            SELECT u.name, MIN(r.seconds) as best_time, COUNT(r.id) as games
            FROM users u JOIN results r ON r.user_id=u.id
            GROUP BY u.id ORDER BY best_time ASC LIMIT 25
        ''')
        rows = cur.fetchall()
        
        # Convert to list of tuples for template compatibility
        leaderboard_data = []
        for row in rows:
            if isinstance(row, dict):
                leaderboard_data.append((row['name'], row['best_time'], row['games']))
            else:
                leaderboard_data.append((row[0], row[1], row[2]))
        
        return render_template('leaderboard.html', rows=leaderboard_data, title='Leaderboard')
    
    except Exception as e:
        app.logger.error(f"Leaderboard error: {e}")
        return render_template('error.html', error='Failed to load leaderboard'), 500
    
    finally:
        if conn:
            try:
                cur.close()
                conn.close()
            except:
                pass

@app.route('/download_history')
def download_history():
    if 'guest' in session:
        return render_template('guest_restricted.html', title='Download History')
    
    if 'user_id' not in session: 
        return redirect(url_for('index'))
    
    uid = session['user_id']
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        execute_query(cur, 'SELECT email,name FROM users WHERE id=?',(uid,))
        user_data = cur.fetchone()
        
        if not user_data:
            return redirect(url_for('index'))
        
        email = user_data['email'] if isinstance(user_data, dict) else user_data[0]
        name = user_data['name'] if isinstance(user_data, dict) else user_data[1]
        since = datetime.utcnow() - timedelta(days=7)
        
        execute_query(cur, 'SELECT seconds, played_at FROM results WHERE user_id=? AND played_at >= ? ORDER BY played_at DESC', (uid, since))
        rows = cur.fetchall()
        
        buf = io.BytesIO()
        generate_last7_pdf(name, email, rows, buf)
        buf.seek(0)
        
        app.logger.info(f"History downloaded by {name}")
        return send_file(buf, as_attachment=True, download_name='sudoku_last7.pdf', mimetype='application/pdf')
    
    except Exception as e:
        app.logger.error(f"Download history error: {e}")
        return render_template('error.html', error='Failed to generate download'), 500
    
    finally:
        if conn:
            try:
                cur.close()
                conn.close()
            except:
                pass

def require_admin():
    return session.get('admin', False)

@app.route('/admin', methods=['GET','POST'])
def admin():
    if request.method == 'GET':
        if session.get('admin'): 
            return render_template('admin_dashboard.html')
        return render_template('admin_login.html')
    
    email = request.form.get('email', '').strip().lower()
    pw = request.form.get('password', '')
    
    if not email or not pw:
        return render_template('admin_login.html', err='Email and password are required.')
    
    if email == app.config['ADMIN_EMAIL'] and pw == app.config['ADMIN_PASSWORD']:
        session['admin'] = True
        app.logger.info("Admin logged in")
        return redirect(url_for('admin'))
    
    app.logger.warning(f"Failed admin login attempt: {email}")
    return render_template('admin_login.html', err='Invalid admin credentials.')

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin', None)
    app.logger.info("Admin logged out")
    return redirect(url_for('index'))

@app.route('/admin/users')
def admin_users():
    if not require_admin(): 
        return redirect(url_for('admin'))
    
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        execute_query(cur, '''
            SELECT u.id, u.name, u.email, COUNT(r.id) as games, MIN(r.seconds) as best
            FROM users u LEFT JOIN results r ON r.user_id=u.id
            GROUP BY u.id ORDER BY u.id ASC
        ''')
        rows = cur.fetchall()
        return render_template('admin_users.html', rows=rows)
    
    except Exception as e:
        app.logger.error(f"Admin users error: {e}")
        return render_template('error.html', error='Failed to load users'), 500
    
    finally:
        if conn:
            try:
                cur.close()
                conn.close()
            except:
                pass

@app.route('/admin/emails')
def admin_emails():
    if not require_admin(): 
        return redirect(url_for('admin'))
    
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        execute_query(cur, 'SELECT id, user_id, email, subject, sent_at FROM sent_emails ORDER BY id DESC LIMIT 200')
        rows = cur.fetchall()
        return render_template('admin_emails.html', rows=rows)
    
    except Exception as e:
        app.logger.error(f"Admin emails error: {e}")
        return render_template('error.html', error='Failed to load emails'), 500
    
    finally:
        if conn:
            try:
                cur.close()
                conn.close()
            except:
                pass

@app.route('/admin/resets')
def admin_resets():
    if not require_admin(): 
        return redirect(url_for('admin'))
    
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        execute_query(cur, 'SELECT id, user_id, expires_at, created_at FROM password_resets ORDER BY id DESC LIMIT 200')
        rows = cur.fetchall()
        return render_template('admin_resets.html', rows=rows)
    
    except Exception as e:
        app.logger.error(f"Admin resets error: {e}")
        return render_template('error.html', error='Failed to load reset attempts'), 500
    
    finally:
        if conn:
            try:
                cur.close()
                conn.close()
            except:
                pass

@app.route('/debug/db')
def debug_db():
    """Debug endpoint to check database status"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Check if tables exist
        if is_postgres(conn):
            cur.execute("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public'
            """)
        else:
            cur.execute("""
                SELECT name FROM sqlite_master WHERE type='table'
            """)
            
        tables = cur.fetchall()
        
        # Check users table
        user_count = 0
        try:
            execute_query(cur, "SELECT COUNT(*) FROM users")
            user_count_result = cur.fetchone()
            user_count = user_count_result[0] if user_count_result else 0
        except Exception as e:
            user_count = f"Error: {e}"
            
        cur.close()
        conn.close()
        
        return jsonify({
            'status': 'success',
            'database_type': 'postgresql' if is_postgres(conn) else 'sqlite',
            'tables': [table[0] for table in tables],
            'user_count': user_count
        })
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/sw.js')
def serve_sw():
    try:
        return send_file('sw.js', mimetype='application/javascript')
    except:
        return "Service worker not found", 404

@app.route('/manifest.json')
def serve_manifest():
    try:
        return send_file('manifest.json', mimetype='application/json')
    except:
        return "Manifest not found", 404

def send_weekly_digest():
    if not app.config.get('EMAIL_ENABLED') or not app.config.get('DIGEST_ENABLED'): 
        return
    
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        since = datetime.utcnow() - timedelta(days=7)
        execute_query(cur, 'SELECT id,name,email FROM users')
        users = cur.fetchall()
        
        for u in users:
            uid = u['id'] if isinstance(u, dict) else u[0]
            name = u['name'] if isinstance(u, dict) else u[1]
            email = u['email'] if isinstance(u, dict) else u[2]
            
            execute_query(cur, 'SELECT COUNT(*), MIN(seconds), AVG(seconds) FROM results WHERE user_id=? AND played_at >= ?', (uid, since))
            result = cur.fetchone()
            
            if result and result[0] > 0:
                games = result[0] if isinstance(result[0], int) else result['count']
                best = result[1] if isinstance(result[1], int) else result['min']
                avg = result[2] if isinstance(result[2], (int, float)) else result['avg']
                
                body = f"""Hi {name},

Your weekly Sudoku progress:
- Games: {games}
- Best: {int(best)}s
- Average: {int(avg)}s

Keep practicing!
"""
                send_email(email, 'Your Weekly Sudoku Progress 📊', body, uid)
    
    except Exception as e:
        app.logger.error(f"Weekly digest error: {e}")
    
    finally:
        if conn:
            try:
                cur.close()
                conn.close()
            except:
                pass

def scheduler_thread():
    while True:
        try:
            schedule.run_pending()
        except Exception as e:
            app.logger.error(f'Scheduler error: {e}')
        time_mod.sleep(60)

def setup_schedule():
    schedule.every().sunday.at(app.config.get('DIGEST_IST_TIME','18:00')).do(send_weekly_digest)
    t = threading.Thread(target=scheduler_thread, daemon=True)
    t.start()

@app.errorhandler(404)
def not_found(error):
    app.logger.warning(f"404 error: {error}")
    return render_template('error.html', error='Page not found'), 404

@app.errorhandler(500)
def internal_error(error):
    app.logger.error(f"500 error: {error}")
    return render_template('error.html', error='Internal server error'), 500

if __name__ == '__main__':
    setup_logging()
    app.logger.info("Starting Sudoku Secure Pro application...")
    try:
        init_db()
        app.logger.info("Database initialized successfully")
    except Exception as e:
        app.logger.error(f"Database initialization failed: {e}")
    
    setup_schedule()
    app.logger.info("Scheduler started")
    app.run(debug=os.environ.get('DEBUG', False), host='0.0.0.0', port=5000)
