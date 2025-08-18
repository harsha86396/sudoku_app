import psycopg2
from psycopg2.extras import RealDictCursor
from flask import g
import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DB_URL = os.environ.get("DATABASE_URL")

def get_db():
    if "db" not in g:
        logger.info("Connecting to PostgreSQL database")
        g.db = psycopg2.connect(DB_URL, cursor_factory=RealDictCursor)
    return g.db

def close_db(e=None):
    db = g.pop("db", None)
    if db is not None:
        try:
            db.commit()
        except Exception as e:
            logger.exception("Error committing database: %s", e)
        db.close()
