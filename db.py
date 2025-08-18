import psycopg
from psycopg.rows import dict_row
from flask import g
import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DB_URL = os.environ.get("DATABASE_URL")

def get_db():
    if "db" not in g:
        logger.info("Connecting to PostgreSQL database")
        g.db = psycopg.connect(DB_URL, row_factory=dict_row)
    return g.db

def close_db(e=None):
    db = g.pop("db", None)
    if db is not None:
        try:
            db.commit()
        except Exception as e:
            logger.exception("Error committing database: %s", e)
        db.close()
