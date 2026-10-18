
"""Database helpers for e-RESBAHUB using MariaDB."""

import mysql.connector
from flask import current_app, g


def get_db():
    """Return the current MariaDB connection."""
    if "db" not in g:
        config = current_app.config

        g.db = mysql.connector.connect(
            host=config.get("DB_HOST", "127.0.0.1"),
            port=int(config.get("DB_PORT", 3306)),
            user=config.get("DB_USER", "root"),
            password=config.get("DB_PASSWORD", ""),
            database=config.get("DB_NAME", "eresbahub"),
            charset="utf8mb4",
            autocommit=False,
        )

    return g.db


def execute(sql, params=(), commit=True):
    """Execute a SQL statement and optionally commit it."""
    conn = get_db()
    cursor = conn.cursor(dictionary=True)

    try:
        sql = sql.replace("?", "%s")
        cursor.execute(sql, params)

        if commit:
            conn.commit()

        return cursor

    except Exception:
        cursor.close()
        conn.rollback()
        raise


def query(sql, params=(), one=False):
    """Run a SELECT query and return rows."""
    conn = get_db()
    cursor = conn.cursor(dictionary=True)

    try:
        sql = sql.replace("?", "%s")
        cursor.execute(sql, params)

        if one:
            return cursor.fetchone()

        return cursor.fetchall()

    finally:
        cursor.close()


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
        try:
            if exc is not None:
                conn.rollback()
        finally:
            conn.close()


def init_db():
    """Verify the MariaDB connection and required tables."""
    conn = get_db()
    cursor = conn.cursor()

    try:
        cursor.execute("SHOW TABLES")
        tables = cursor.fetchall()

        if not tables:
            raise RuntimeError(
                "No tables found in the eresbahub database. "
                "Import the schema using phpMyAdmin first."
            )
    finally:
        cursor.close()
