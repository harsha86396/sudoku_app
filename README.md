# Sudoku Secure Pro (with OTP Reset, Rate Limit, Theme Toggle, CAPTCHA, Admin)

Features:
- Register/Login (hashed passwords)
- Forgot password with OTP email (expires in 10 minutes)
- Resend OTP + rate limit (60s per email)
- CAPTCHA on register and forgot password (simple math)
- Light/Dark theme toggle
- Play Sudoku in browser (easy/medium/hard), 3 hints
- Timer + auto submit result to leaderboard
- Leaderboard (best time + games)
- Download last 7 days PDF
- Weekly email digest (optional)
- Admin dashboard (view users, emails, reset attempts)

## Run
```bash
pip install -r requirements.txt
python app.py
```
Open http://127.0.0.1:5000

Admin login at /admin with credentials in config.py.
