
"""Create the first e-RESBAHUB administrator account."""

from getpass import getpass

from werkzeug.security import generate_password_hash

from resbahub import create_app, db


def main():
    app = create_app()

    # Safety check: this script must target the main database.
    database_name = app.config.get("DB_NAME")

    if database_name != "eresbahub":
        raise RuntimeError(
            "Wrong database selected. Expected 'eresbahub', "
            f"but the application selected {database_name!r}. "
            "Check your application configuration first."
        )

    username = input("Admin username: ").strip()
    email = input("Admin email: ").strip()
    full_name = input("Admin full name: ").strip()

    if not username or not email or not full_name:
        raise ValueError("Username, email, and full name are required.")

    password = getpass("New admin password: ")
    confirm = getpass("Confirm admin password: ")

    if password != confirm:
        raise ValueError("Passwords do not match.")

    if len(password) < 12:
        raise ValueError("Use a password with at least 12 characters.")

    with app.app_context():
        existing = db.query(
            """
            SELECT id
            FROM users
            WHERE username = ? OR email = ?
            LIMIT 1
            """,
            (username, email),
            one=True,
        )

        if existing:
            raise ValueError(
                "That username or email already exists. "
                "Choose another one or recover the existing account."
            )

        db.execute(
            """
            INSERT INTO users (
                username,
                email,
                full_name,
                password_hash,
                role,
                is_active
            )
            VALUES (?, ?, ?, ?, 'admin', 1)
            """,
            (
                username,
                email,
                full_name,
                generate_password_hash(password),
            ),
        )
        db.commit()
        db.close_db()

    print("\nAdmin account created successfully.")
    print(f"Username: {username}")
    print("You can now log in using the password you entered.")


if __name__ == "__main__":
    main()
