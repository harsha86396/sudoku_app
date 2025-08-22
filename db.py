import os
from flask import g
from psycopg_pool import ConnectionPool

# Connection pool
pool = ConnectionPool(os.environ.get("DATABASE_URL"), min_size=1, max_size=10)

def get_db():
    if 'db' not in g:
        g.db = pool.getconn()
        g.db.row_factory = dict_row
    return g.db

def close_db(e=None):
    db = g.pop('db', None)
    if db is not None:
        pool.putconn(db)
