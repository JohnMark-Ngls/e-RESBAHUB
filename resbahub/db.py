"""Database helpers (SQLite). One connection per request, closed automatically."""
import sqlite3
from pathlib import Path

from flask import current_app, g

SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def get_db():
    if "db" not in g:
        conn = sqlite3.connect(current_app.config["DATABASE"], timeout=10)
        conn.row_factory = sqlite3.Row            # rows behave like dicts: row["name"]
        conn.execute("PRAGMA foreign_keys = ON")  # enforce relationships
        g.db = conn
    return g.db


def close_db(exc=None):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def init_db():
    """Create all tables if they do not exist yet."""
    conn = get_db()
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    conn.commit()


def query(sql, args=(), one=False):
    cur = get_db().execute(sql, args)
    rows = cur.fetchall()
    cur.close()
    if one:
        return rows[0] if rows else None
    return rows


def execute(sql, args=(), commit=True):
    conn = get_db()
    cur = conn.execute(sql, args)
    last_id = cur.lastrowid
    cur.close()
    if commit:
        conn.commit()
    return last_id
