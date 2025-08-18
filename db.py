# db.py
import sqlite3
import os
from flask import g

# Stable DB path (matches config.py & init_db.py)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("DATABASE_PATH") or os.path.join(BASE_DIR, "sudoku.db")

def get_db():
    """
    Returns a database connection for the current request.
    Uses Flask's 'g' so it's reused within a single request.
    """
    if 'db' not in g:
        g.db = sqlite3.connect(DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES)
        g.db.row_factory = sqlite3.Row  # results behave like dicts
    return g.db

def close_db(e=None):
    """
    Closes the database connection at the end of a request.
    Flask will call this automatically if registered in app.py.
    """
    db = g.pop('db', None)
    if db is not None:
        try:
            db.commit()
        except Exception:
            pass
        db.close()
