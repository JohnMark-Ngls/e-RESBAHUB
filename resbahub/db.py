
"""Database helpers for e-RESBAHUB."""

import sqlite3
from pathlib import Path

from flask import current_app, g

SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def get_db():
    """Return the current SQLite connection."""
    if "db" not in g:
        database_path = Path(current_app.config["DATABASE"])
        database_path.parent.mkdir(parents=True, exist_ok=True)

        conn = sqlite3.connect(
            str(database_path),
            timeout=20,
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = DELETE")

        g.db = conn

    return g.db


def execute(sql, params=(), commit=True):
    """Execute a SQL statement and optionally commit it."""
    conn = get_db()
    cursor = conn.execute(sql, params)

    if commit:
        conn.commit()

    return cursor


def query(sql, params=(), one=False):
    """Run a SELECT query and return rows."""
    cursor = get_db().execute(sql, params)

    if one:
        return cursor.fetchone()

    return cursor.fetchall()


def commit():
    """Commit the current database transaction."""
    get_db().commit()


def rollback():
    """Roll back the current database transaction."""
    get_db().rollback()


def close_db(exc=None):
    """Close the connection at the end of the request."""
    conn = g.pop("db", None)

    if conn is not None:
        if exc is not None:
            conn.rollback()

        conn.close()


def init_db():
    """Create database tables if they do not exist."""
    conn = get_db()
    schema = SCHEMA_PATH.read_text(encoding="utf-8")

    conn.executescript(schema)
    conn.commit()
