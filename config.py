import os
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv
from contextlib import contextmanager

load_dotenv()

DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': os.getenv('DB_PORT', '5432'),
    'dbname': os.getenv('DB_NAME', 'gym_class'),
    'user': os.getenv('DB_USER', 'postgres'),
    'password': os.getenv('DB_PASSWORD', 'postgres'),
}

FREEZE_MINUTES_BEFORE_START = int(os.getenv('FREEZE_MINUTES_BEFORE_START', '60'))
CLASS_DURATION_MINUTES = int(os.getenv('CLASS_DURATION_MINUTES', '60'))
SECRET_KEY = os.getenv('SECRET_KEY', 'change-this-secret-key-in-production')


@contextmanager
def get_db_connection():
    conn = psycopg2.connect(**DB_CONFIG)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_db_cursor(conn):
    return conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)


def query_one(sql, params=None):
    with get_db_connection() as conn:
        cur = get_db_cursor(conn)
        cur.execute(sql, params or ())
        return cur.fetchone()


def query_all(sql, params=None):
    with get_db_connection() as conn:
        cur = get_db_cursor(conn)
        cur.execute(sql, params or ())
        return cur.fetchall()


def execute(sql, params=None):
    with get_db_connection() as conn:
        cur = get_db_cursor(conn)
        cur.execute(sql, params or ())
        return cur.rowcount


def execute_returning(sql, params=None):
    with get_db_connection() as conn:
        cur = get_db_cursor(conn)
        cur.execute(sql, params or ())
        return cur.fetchone()


def generate_code(prefix):
    import uuid
    return f"{prefix}-{uuid.uuid4().hex[:8].upper()}"
