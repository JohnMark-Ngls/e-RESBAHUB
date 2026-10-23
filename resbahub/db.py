
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
    """Verify the database and create tables added by application upgrades."""
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

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS medicine_inventory (
                id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(120) NOT NULL UNIQUE,
                condition_name VARCHAR(120) NULL,
                strength VARCHAR(60) NULL,
                form VARCHAR(20) NULL,
                description VARCHAR(255) NULL,
                stock_quantity INT UNSIGNED NOT NULL DEFAULT 0,
                is_active TINYINT(1) NOT NULL DEFAULT 1,
                updated_by INT UNSIGNED NULL,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                    ON UPDATE CURRENT_TIMESTAMP,
                FOREIGN KEY (updated_by)
                    REFERENCES users(id) ON DELETE SET NULL
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """
        )
        medicine_columns = (
            ("condition_name", "VARCHAR(120) NULL"),
            ("strength", "VARCHAR(60) NULL"),
            ("form", "VARCHAR(20) NULL"),
            ("description", "VARCHAR(255) NULL"),
        )
        for column, definition in medicine_columns:
            cursor.execute(
                f"SHOW COLUMNS FROM medicine_inventory LIKE '{column}'"
            )
            if cursor.fetchone() is None:
                cursor.execute(
                    f"ALTER TABLE medicine_inventory "
                    f"ADD COLUMN {column} {definition}"
                )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS staff_presence (
                user_id INT UNSIGNED PRIMARY KEY,
                is_on_site TINYINT(1) NOT NULL DEFAULT 0,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                    ON UPDATE CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id)
                    REFERENCES users(id) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """
        )
        cursor.execute("SHOW COLUMNS FROM users LIKE 'position_title'")
        if cursor.fetchone() is None:
            cursor.execute(
                "ALTER TABLE users ADD COLUMN position_title VARCHAR(100) NULL"
            )
        conn.commit()
    finally:
        cursor.close()
