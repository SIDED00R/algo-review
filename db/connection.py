import os
from pathlib import Path
from contextlib import contextmanager
from dotenv import load_dotenv

load_dotenv()

USE_POSTGRES = os.environ.get("DB_TYPE", "sqlite").lower() == "postgres"


def get_connection():
    if USE_POSTGRES:
        import psycopg2
        unix_socket = os.environ.get("DB_SOCKET")
        if unix_socket:
            return psycopg2.connect(
                dbname=os.environ.get("DB_NAME", "boj_review"),
                user=os.environ.get("DB_USER", "boj_user"),
                password=os.environ.get("DB_PASSWORD", ""),
                host=unix_socket,
            )
        return psycopg2.connect(
            dbname=os.environ.get("DB_NAME", "boj_review"),
            user=os.environ.get("DB_USER", "boj_user"),
            password=os.environ.get("DB_PASSWORD", ""),
            host=os.environ.get("DB_HOST", "localhost"),
            port=os.environ.get("DB_PORT", "5432"),
        )
    else:
        import sqlite3
        _db_env = os.environ.get("DB_PATH")
        db_path = Path(_db_env) if _db_env else Path(__file__).parent.parent / "coding_recommend.db"
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        return conn


@contextmanager
def db_cursor(commit: bool = False):
    """커넥션·커서 수명을 관리한다. commit=True면 정상 종료 시 커밋. (postgres만 cursor.close 필요)"""
    conn = get_connection()
    cur = conn.cursor()
    try:
        yield cur
        if commit:
            conn.commit()
    finally:
        if USE_POSTGRES:
            cur.close()
        conn.close()


def _ph():
    return "%s" if USE_POSTGRES else "?"


def _rows_to_dicts(cur, rows):
    if USE_POSTGRES:
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in rows]
    return [dict(r) for r in rows]
