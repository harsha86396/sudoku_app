from flask import Flask, render_template, request, redirect, url_for, session, jsonify, send_file
import os, smtplib, ssl, io, random, time as time_mod
from email.mime.text import MIMEText
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv

from utils.sudoku import make_puzzle
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

def send_email(to_email, subject, body, user_id=None):
    if not app.config.get('EMAIL_ENABLED'):
        print('[EMAIL DISABLED]', subject, body)
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
        conn = get_db()
        cur = conn.cursor()
        cur.execute('INSERT INTO sent_emails(user_id,email,subject,body) VALUES(?,?,?,?)',
                    (user_id, to_email, subject, body))
        conn.commit()
        cur.close()
        conn.close()
        return True
    except Exception as e:
        print('Email error:', e)
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
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT last_request_ts FROM otp_rate_limit WHERE email=?', (email,))
    row = cur.fetchone()
    now = time_mod.time()
    if row:
        last = row[0]
        if now - last < app.config.get('OTP_RATE_LIMIT_SECONDS',60):
            conn.close()
            return False, int(app.config.get('OTP_RATE_LIMIT_SECONDS',60) - (now-last))
        cur.execute('UPDATE otp_rate_limit SET last_request_ts=? WHERE email=?', (now,email))
    else:
        cur.execute('INSERT INTO otp_rate_limit(email,last_request_ts) VALUES(?,?)',(email,now))
    conn.commit()
    cur.close()
    conn.close()
    return True, 0

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
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute('SELECT id,name,password_hash FROM users WHERE email=?', (email,))
        row = cur.fetchone()
        
        if row and check_password_hash(row['password_hash'], password):
            session['user_id'] = row['id']
            session['name'] = row['name']
            session['hints_left'] = 3
            return redirect(url_for('dashboard'))
        
        q,t = new_captcha()
        return render_template('login.html', err='Invalid credentials.', captcha_q=q, captcha_t=t)
    
    except Exception as e:
        print(f"Login error: {e}")
        q,t = new_captcha()
        return render_template('login.html', err='An error occurred. Please try again.', captcha_q=q, captcha_t=t)
    
    finally:
        cur.close()
        conn.close()

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
    
    pw_hash = generate_password_hash(password)
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute('INSERT INTO users(name,email,password_hash) VALUES(?,?,?)', (name,email,pw_hash))
        conn.commit()
        send_email(email, 'Welcome to Sudoku', f'Hello {name}, your account has been created.', None)
        q,t = new_captcha()
        return render_template('login.html', msg='Registration successful. Please log in.', captcha_q=q, captcha_t=t)
    except Exception as e:
        print(f"Registration error: {e}")
        q,t = new_captcha()
        return render_template('register.html', err='Email already registered.', captcha_q=q, captcha_t=t)
    finally:
        cur.close()
        conn.close()

@app.route('/guest_login')
def guest_login():
    session.clear()
    session['guest'] = True
    session['name'] = 'Guest'
    session['hints_left'] = 3
    return redirect(url_for('play'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session and 'guest' not in session: 
        return redirect(url_for('index'))
    return render_template('dashboard.html', name=session.get('name', 'User'), title='Dashboard')

def create_and_send_otp(user_id, email, name):
    otp = f"{random.randint(0, 999999):06d}"
    otp_hash = generate_password_hash(otp)
    expires = datetime.utcnow() + timedelta(minutes=app.config.get('OTP_EXP_MINUTES',10))
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute('INSERT INTO password_resets(user_id, otp_hash, expires_at) VALUES(?,?,?)',
                    (user_id, otp_hash, expires))
        conn.commit()
        
        body = f"""Hi {name},
Your OTP code to reset your password is: {otp}
This code expires in {app.config.get('OTP_EXP_MINUTES',10)} minutes.

– Sudoku AI (Harsha Enterprises)"""
        send_email(email, 'Sudoku Password Reset', body, user_id)
        return True
    except Exception as e:
        print(f"OTP creation error: {e}")
        return False
    finally:
        cur.close()
        conn.close()

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
    
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute('SELECT id,name FROM users WHERE email=?', (email,))
        row = cur.fetchone()
        
        if not row:
            q,t = new_captcha()
            return render_template('forgot_password.html', err='Email not found.', email=email, captcha_q=q, captcha_t=t)
        
        create_and_send_otp(row['id'], email, row['name'])
        return render_template('reset_password.html', email=email, msg='OTP sent. Check your inbox.')
    
    except Exception as e:
        print(f"Forgot password error: {e}")
        q,t = new_captcha()
        return render_template('forgot_password.html', err='An error occurred. Please try again.', email=email, captcha_q=q, captcha_t=t)
    
    finally:
        cur.close()
        conn.close()

@app.route('/resend_otp')
def resend_otp():
    email = request.args.get('email','').strip().lower()
    if not email:
        return render_template('reset_password.html', email=email, err='Email is required.')
    
    ok, wait = rate_limit_ok(email)
    if not ok:
        return render_template('reset_password.html', email=email, err=f'Please wait {wait}s before resending OTP.')
    
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute('SELECT id,name FROM users WHERE email=?', (email,))
        row = cur.fetchone()
        
        if not row:
            q,t = new_captcha()
            return render_template('forgot_password.html', err='Email not found.', email=email, captcha_q=q, captcha_t=t)
        
        create_and_send_otp(row['id'], email, row['name'])
        return render_template('reset_password.html', email=email, msg='A new OTP has been sent.')
    
    except Exception as e:
        print(f"Resend OTP error: {e}")
        return render_template('reset_password.html', email=email, err='An error occurred. Please try again.')
    
    finally:
        cur.close()
        conn.close()

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
    
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute('SELECT id,name FROM users WHERE email=?', (email,))
        user = cur.fetchone()
        
        if not user:
            q,t = new_captcha()
            return render_template('forgot_password.html', err='Email not found.', email=email, captcha_q=q, captcha_t=t)
        
        uid, name = user['id'], user['name']
        cur.execute('SELECT id, otp_hash, expires_at FROM password_resets WHERE user_id=? ORDER BY created_at DESC LIMIT 1', (uid,))
        pr = cur.fetchone()
        
        if not pr:
            return render_template('reset_password.html', email=email, err='No active OTP. Please request again.')
        
        pr_id, otp_hash, expires_at = pr['id'], pr['otp_hash'], pr['expires_at']
        
        try:
            exp = datetime.fromisoformat(expires_at) if isinstance(expires_at, str) else expires_at
        except Exception:
            exp = datetime.utcnow() - timedelta(seconds=1)
        
        if datetime.utcnow() > exp:
            return render_template('reset_password.html', email=email, err='OTP expired. Please request a new one.')
        
        if not check_password_hash(otp_hash, otp):
            return render_template('reset_password.html', email=email, err='Invalid OTP.')
        
        new_hash = generate_password_hash(password)
        cur.execute('UPDATE users SET password_hash=? WHERE id=?', (new_hash, uid))
        cur.execute('DELETE FROM password_resets WHERE user_id=?', (uid,))
        conn.commit()
        
        send_email(email, 'Password Changed', f'Hi {name}, your password was reset successfully.', uid)
        q,t = new_captcha()
        return render_template('login.html', msg='Password reset successful. Please log in.', captcha_q=q, captcha_t=t)
    
    except Exception as e:
        print(f"Reset password error: {e}")
        return render_template('reset_password.html', email=email, err='An error occurred. Please try again.')
    
    finally:
        cur.close()
        conn.close()

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
        puzzle, solution = make_puzzle(diff)
        
        # Store puzzle and solution in session
        session['solution'] = solution
        session['puzzle'] = puzzle
        session['hints_left'] = 3
        session['original_puzzle'] = [row[:] for row in puzzle]  # Store original state
        
        return jsonify({'puzzle': puzzle, 'solution': solution})
    
    except Exception as e:
        print(f"New puzzle error: {e}")
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
    
    return jsonify({'r':r,'c':c,'val':val,'hints_left':session['hints_left']})

@app.route('/api/record_result', methods=['POST'])
def record_result():
    if 'guest' in session:
        return jsonify({'error':'Guest mode - results not saved'}), 403
    
    if 'user_id' not in session: 
        return jsonify({'error':'not logged in'}), 403
    
    try:
        seconds = int(request.json.get('seconds',0))
        if seconds <= 0: 
            return jsonify({'error':'invalid time'}), 400
        
        uid = session['user_id']
        conn = get_db()
        cur = conn.cursor()
        
        cur.execute('INSERT INTO results(user_id,seconds) VALUES(?,?)', (uid, seconds))
        conn.commit()
        
        cur.execute('SELECT MIN(seconds) FROM results WHERE user_id=?', (uid,))
        best = cur.fetchone()[0]
        
        cur.execute('''
            SELECT u.id, MIN(r.seconds) as best FROM users u
            JOIN results r ON r.user_id=u.id
            GROUP BY u.id ORDER BY best ASC
        ''')
        rows = cur.fetchall()
        
        rank = 0
        for i, row in enumerate(rows, start=1):
            if row[0] == uid: 
                rank = i
                break
        
        if seconds == best:
            cur.execute('SELECT email,name FROM users WHERE id=?',(uid,))
            user_data = cur.fetchone()
            if user_data:
                em, nm = user_data
                send_email(em, '🎉 New Personal Best!', f'Congrats {nm}! New PB: {best}s. Keep it up!', uid)
        
        return jsonify({'status':'ok','best_time':best,'rank':rank})
    
    except Exception as e:
        print(f"Record result error: {e}")
        return jsonify({'error': 'Failed to record result'}), 500
    
    finally:
        if 'cur' in locals(): cur.close()
        if 'conn' in locals(): conn.close()

@app.route('/leaderboard')
def leaderboard():
    if 'guest' in session:
        return render_template('guest_restricted.html', title='Leaderboard')
    
    conn = get_db()
    cur = conn.cursor()
    
    try:
        cur.execute('''
            SELECT u.name, MIN(r.seconds) as best_time, COUNT(r.id) as games
            FROM users u JOIN results r ON r.user_id=u.id
            GROUP BY u.id ORDER BY best_time ASC LIMIT 25
        ''')
        rows = cur.fetchall()
        return render_template('leaderboard.html', rows=rows, title='Leaderboard')
    
    except Exception as e:
        print(f"Leaderboard error: {e}")
        return render_template('error.html', error='Failed to load leaderboard'), 500
    
    finally:
        cur.close()
        conn.close()

@app.route('/download_history')
def download_history():
    if 'guest' in session:
        return render_template('guest_restricted.html', title='Download History')
    
    if 'user_id' not in session: 
        return redirect(url_for('index'))
    
    uid = session['user_id']
    conn = get_db()
    cur = conn.cursor()
    
    try:
        cur.execute('SELECT email,name FROM users WHERE id=?',(uid,))
        user_data = cur.fetchone()
        
        if not user_data:
            return redirect(url_for('index'))
        
        email, name = user_data
        since = datetime.utcnow() - timedelta(days=7)
        
        cur.execute('SELECT seconds, played_at FROM results WHERE user_id=? AND played_at >= ? ORDER BY played_at DESC', (uid, since))
        rows = cur.fetchall()
        
        buf = io.BytesIO()
        generate_last7_pdf(name, email, rows, buf)
        buf.seek(0)
        
        return send_file(buf, as_attachment=True, download_name='sudoku_last7.pdf', mimetype='application/pdf')
    
    except Exception as e:
        print(f"Download history error: {e}")
        return render_template('error.html', error='Failed to generate download'), 500
    
    finally:
        cur.close()
        conn.close()

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
        return redirect(url_for('admin'))
    
    return render_template('admin_login.html', err='Invalid admin credentials.')

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin', None)
    return redirect(url_for('index'))

@app.route('/admin/users')
def admin_users():
    if not require_admin(): 
        return redirect(url_for('admin'))
    
    conn = get_db()
    cur = conn.cursor()
    
    try:
        cur.execute('''
            SELECT u.id, u.name, u.email, COUNT(r.id) as games, MIN(r.seconds) as best
            FROM users u LEFT JOIN results r ON r.user_id=u.id
            GROUP BY u.id ORDER BY u.id ASC
        ''')
        rows = cur.fetchall()
        return render_template('admin_users.html', rows=rows)
    
    except Exception as e:
        print(f"Admin users error: {e}")
        return render_template('error.html', error='Failed to load users'), 500
    
    finally:
        cur.close()
        conn.close()

@app.route('/admin/emails')
def admin_emails():
    if not require_admin(): 
        return redirect(url_for('admin'))
    
    conn = get_db()
    cur = conn.cursor()
    
    try:
        cur.execute('SELECT id, user_id, email, subject, sent_at FROM sent_emails ORDER BY id DESC LIMIT 200')
        rows = cur.fetchall()
        return render_template('admin_emails.html', rows=rows)
    
    except Exception as e:
        print(f"Admin emails error: {e}")
        return render_template('error.html', error='Failed to load emails'), 500
    
    finally:
        cur.close()
        conn.close()

@app.route('/admin/resets')
def admin_resets():
    if not require_admin(): 
        return redirect(url_for('admin'))
    
    conn = get_db()
    cur = conn.cursor()
    
    try:
        cur.execute('SELECT id, user_id, expires_at, created_at FROM password_resets ORDER BY id DESC LIMIT 200')
        rows = cur.fetchall()
        return render_template('admin_resets.html', rows=rows)
    
    except Exception as e:
        print(f"Admin resets error: {e}")
        return render_template('error.html', error='Failed to load reset attempts'), 500
    
    finally:
        cur.close()
        conn.close()

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
    
    conn = get_db()
    cur = conn.cursor()
    
    try:
        since = datetime.utcnow() - timedelta(days=7)
        cur.execute('SELECT id,name,email FROM users')
        users = cur.fetchall()
        
        for u in users:
            uid, name, email = u['id'], u['name'], u['email']
            cur.execute('SELECT COUNT(*), MIN(seconds), AVG(seconds) FROM results WHERE user_id=? AND played_at >= ?', (uid, since))
            result = cur.fetchone()
            
            if result and result[0] > 0:
                games, best, avg = result
                body = f"""Hi {name},

Your weekly Sudoku progress:
- Games: {games}
- Best: {int(best)}s
- Average: {int(avg)}s

Keep practicing!
"""
                send_email(email, 'Your Weekly Sudoku Progress 📊', body, uid)
    
    except Exception as e:
        print(f"Weekly digest error: {e}")
    
    finally:
        cur.close()
        conn.close()

def scheduler_thread():
    while True:
        try:
            schedule.run_pending()
        except Exception as e:
            print('Scheduler error:', e)
        time_mod.sleep(60)

def setup_schedule():
    schedule.every().sunday.at(app.config.get('DIGEST_IST_TIME','18:00')).do(send_weekly_digest)
    t = threading.Thread(target=scheduler_thread, daemon=True)
    t.start()

@app.errorhandler(404)
def not_found(error):
    return render_template('error.html', error='Page not found'), 404

@app.errorhandler(500)
def internal_error(error):
    return render_template('error.html', error='Internal server error'), 500

if __name__ == '__main__':
    init_db()
    setup_schedule()
    app.run(debug=os.environ.get('DEBUG', False))
