
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
        # Check that the selected database already has its base schema.
        cursor.execute("SHOW TABLES")
        tables = cursor.fetchall()

        if not tables:
            raise RuntimeError(
                "No tables found in the configured database. "
                "Import the e-RESBAHUB schema using phpMyAdmin first."
            )

        # Medicine inventory table.
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

        # Add newer medicine columns to an existing installation.
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

        # Staff presence table.
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

        # Add position_title to older users tables if missing.
        cursor.execute("SHOW COLUMNS FROM users LIKE 'position_title'")

        if cursor.fetchone() is None:
            cursor.execute(
                "ALTER TABLE users ADD COLUMN position_title VARCHAR(100) NULL"
            )

        # QR certificate verification table.
        # Foreign key types must match the existing database schema.
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS certificate_verifications (
                id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
                request_id INT UNSIGNED NOT NULL UNIQUE,
                verification_token VARCHAR(100) NOT NULL UNIQUE,
                issued_by INT UNSIGNED NULL,
                issued_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                is_revoked TINYINT(1) NOT NULL DEFAULT 0,
                revoked_at DATETIME NULL,
                INDEX idx_cv_token (verification_token),
                CONSTRAINT fk_cv_request
                    FOREIGN KEY (request_id)
                    REFERENCES requests(id)
                    ON DELETE CASCADE,
                CONSTRAINT fk_cv_issuer
                    FOREIGN KEY (issued_by)
                    REFERENCES users(id)
                    ON DELETE SET NULL
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """
        )

        # Medicine requests table.
        # Stores requests submitted by residents for available medicines.
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS medicine_requests (
                id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
                reference_no VARCHAR(40) NOT NULL UNIQUE,
                resident_id INT UNSIGNED NOT NULL,
                medicine_id INT UNSIGNED NOT NULL,
                quantity INT UNSIGNED NOT NULL,
                purpose VARCHAR(500) NOT NULL,
                status VARCHAR(30) NOT NULL DEFAULT 'Pending',
                remarks VARCHAR(500) NULL,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                    ON UPDATE CURRENT_TIMESTAMP,

                INDEX idx_mr_resident (resident_id),
                INDEX idx_mr_status (status),
                INDEX idx_mr_medicine (medicine_id),

                CONSTRAINT fk_mr_resident
                    FOREIGN KEY (resident_id)
                    REFERENCES residents(id)
                    ON DELETE CASCADE,

                CONSTRAINT fk_mr_medicine
                    FOREIGN KEY (medicine_id)
                    REFERENCES medicine_inventory(id)
                    ON DELETE RESTRICT
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """
        )

        conn.commit()

    except Exception:
        conn.rollback()
        raise

    finally:
        cursor.close()
