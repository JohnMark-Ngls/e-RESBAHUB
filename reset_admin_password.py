
"""Safely reset the password of an existing e-RESBAHUB admin account."""

from getpass import getpass

from werkzeug.security import generate_password_hash

from resbahub import create_app, db


def main():
    app = create_app()

    with app.app_context():
        # Find the existing admin account.
        admin = db.query(
            """
            SELECT id, username, role
            FROM users
            WHERE username = ? AND role = ?
            """,
            ("admin", "admin"),
            one=True,
        )

        if admin is None:
            print("ERROR: No admin account with username 'admin' was found.")
            print("The password has not been changed.")
            return

        print("Existing admin account found.")
        print(f"Username: {admin['username']}")
        print("Enter a new password. Your input will not be displayed.")

        while True:
            password = getpass("New admin password (minimum 12 characters): ")

            if len(password) < 12:
                print("Password is too short. Use at least 12 characters.")
                continue

            confirmation = getpass("Confirm new password: ")

            if password != confirmation:
                print("Passwords do not match. Please try again.")
                continue

            break

        # Generate a secure password hash.
        password_hash = generate_password_hash(password)

        try:
            # Update only the existing admin account's password.
            db.execute(
                """
                UPDATE users
                SET password_hash = ?
                WHERE id = ? AND role = ?
                """,
                (password_hash, admin["id"], "admin"),
                commit=False,
            )

            db.commit()

            print("\nSUCCESS: The local admin password has been reset.")
            print("Username: admin")
            print("You can now log in using your new password.")

        except Exception:
            db.rollback()
            print("\nERROR: The password could not be updated.")
            print("Check the error details before trying again.")
            raise


if __name__ == "__main__":
    main()

