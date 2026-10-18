
"""Database helpers (SQLite). One connection per request, closed automatically."""

import sqlite3
from pathlib import Path

from flask import current_app, g

SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def get_db():
    """Return the current request's SQLite connection."""
    if "db" not in g:
        database_path = current_app.config["DATABASE"]

        # Ensure the parent directory exists before opening the database.
        Path(database_path).parent.mkdir(parents=True, exist_ok=True)

        conn = sqlite3.connect(database_path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")

        g.db = conn

    return g.db


def close_db(exc=None):
    """Close the database connection at the end of the request."""
    conn = g.pop("db", None)

    if conn is not None:
        conn.close()


def init_db():
    """Create the database tables if they do not exist."""
    conn = get_db()

    schema = SCHEMA_PATH.read_text(encoding="utf-8")
    conn.executescript(schema)
    conn.commit()


def query(sql, args=(), one=False):
    """Execute a SELECT query and return rows."""
    cur = get_db().execute(sql, args)

    try:
        rows = cur.fetchall()
    finally:
        cur.close()

    if one:
        return rows[0] if rows else None

    return rows


def execute(sql, args=(), commit=True):
    """Execute an INSERT, UPDATE, or DELETE statement."""
    conn = get_db()
    cur = conn.execute(sql, args)

    try:
        last_id = cur.lastrowid

        if commit:
            conn.commit()

        return last_id
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
