
# Sudoku • Harsha Enterprises (Upgraded)

This version fixes the "Please try later" login loop and all "Page not found" errors, hardens the database and email flows, and simplifies deployment.

## Highlights

- **No login lockouts** – Rate limiting now applies **only** to OTP requests, never to basic login.
- **Consistent pages** – All routes have matching templates; custom 404/500 pages.
- **Stable DB path** – Uses absolute `DB_PATH` (env var) else `./sudoku.db`. No re‑initialization wipes data.
- **Email is optional** – SMTP failures never block flows. OTP emails/logins still proceed gracefully.
- **Leaderboard** – Fast, correct query based on each user's best time.
- **Weekly PDF digest** – Generates `weekly_digest.pdf` via ReportLab (run by a background scheduler).
- **Health check** – `/healthz` for uptime pings.
- **Admin** – Login with `ADMIN_EMAIL` / `ADMIN_PASSWORD` (env) to see users and total games.

## Quick start (local)

```bash
python -m venv .venv && source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
export SECRET_KEY="change-me"
python main.py
```

Open http://localhost:5000

## Environment

Create a `.env` with e.g.:

```
SECRET_KEY=super-secret
ADMIN_EMAIL=admin@example.com
ADMIN_PASSWORD=StrongPass123
# Optional email:
SMTP_USER=you@gmail.com
SMTP_PASS=your-app-password
FROM_EMAIL=Sudoku <you@gmail.com>
# Optional persistent path:
DB_PATH=/data/sudoku.db
```

## Render deployment

- Attach a persistent disk and set `DB_PATH=/data/sudoku.db`
- `render.yaml` is included. Start command: `gunicorn -w 2 -k gthread -t 120 main:app`

## Known schemas

```
users(id, name, email UNIQUE, password_hash, email_verified, created_at)
password_resets(id, user_id, otp_hash, expires_at, created_at)
otp_rate_limit(email PRIMARY KEY, last_request_ts)
results(id, user_id, seconds, difficulty, created_at)
```

## Notes

- CAPTCHA is a simple math question stored in the session.
- Email is **best‑effort only**; failures are logged to console.
- Weekly digest is scheduled for Monday 09:00 (server’s local time). Adjust in `app.py` if needed.
```
