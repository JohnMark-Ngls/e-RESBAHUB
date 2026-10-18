
"""Create the first administrator and optional demo data.

Usage:
    python seed.py
    python seed.py --demo
    python seed.py --admin-password "MyStr0ngPass"

Set DB_NAME=eresbahub_test to use the test database.
Existing usernames are skipped.
"""

import argparse
import os
from datetime import datetime

from werkzeug.security import generate_password_hash

from resbahub import create_app, db


DEFAULT_ADMIN_PASSWORD = "Admin@12345"
DEMO_PASSWORD = "Demo@12345"


def add_user(username, email, full_name, password, role):
    """Create a user if the username does not already exist."""
    existing = db.query(
        "SELECT id FROM users WHERE username = ?",
        (username,),
        one=True,
    )

    if existing:
        print(f"  - {username}: already exists, skipped")
        return None

    db.execute(
        """
        INSERT INTO users
            (username, email, full_name, password_hash, role, is_active)
        VALUES (?, ?, ?, ?, ?, 1)
        """,
        (
            username,
            email,
            full_name,
            generate_password_hash(password),
            role,
        ),
    )

    created = db.query(
        "SELECT id FROM users WHERE username = ?",
        (username,),
        one=True,
    )

    if not created:
        raise RuntimeError(f"Failed to create user: {username}")

    print(f"  + {role:15} {username}")
    return created["id"]


def add_resident(
    username,
    email,
    first,
    last,
    birth,
    sex,
    verified,
    address,
    phone,
):
    """Create a demo user and resident profile."""
    user_id = add_user(
        username,
        email,
        f"{first} {last}",
        DEMO_PASSWORD,
        "resident",
    )

    if user_id is None:
        return

    verified_at = datetime.now() if verified else None

    db.execute(
        """
        INSERT INTO residents (
            user_id,
            first_name,
            last_name,
            birthdate,
            sex,
            civil_status,
            contact_no,
            address,
            purok,
            is_verified,
            verified_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            first,
            last,
            birth,
            sex,
            "Single",
            phone,
            address,
            "Purok 1",
            verified,
            verified_at,
        ),
    )


def add_demo_announcements():
    """Insert demo announcements if none exist."""
    existing = db.query(
        "SELECT id FROM announcements LIMIT 1",
        one=True,
    )

    if existing:
        print("  - Announcements already exist, skipped")
        return

    announcements = [
        (
            "Free Anti-Rabies Vaccination",
            "Bring your pets to the barangay hall this Saturday, 8 AM - 12 NN.",
            "Health",
        ),
        (
            "Barangay Assembly",
            "All residents are invited to the quarterly barangay assembly.",
            "Schedule",
        ),
    ]

    for title, body, category in announcements:
        db.execute(
            """
            INSERT INTO announcements (title, body, category)
            VALUES (?, ?, ?)
            """,
            (title, body, category),
        )

    print("  + Demo announcements created")


def add_demo_patient():
    """Insert a demo patient if no patients exist."""
    existing = db.query(
        "SELECT id FROM patients LIMIT 1",
        one=True,
    )

    if existing:
        print("  - Patients already exist, skipped")
        return

    db.execute(
        """
        INSERT INTO patients (
            patient_no,
            first_name,
            last_name,
            birthdate,
            sex,
            contact_no,
            address
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "PT-DEMO-0001",
            "Pedro",
            "Villanueva",
            "1988-02-20",
            "Male",
            "09191234567",
            "9 Mabini St., Pinaod",
        ),
    )

    print("  + Demo patient created")


def main():
    parser = argparse.ArgumentParser(
        description="Initialize e-RESBAHUB administrator and demo data."
    )

    parser.add_argument(
        "--demo",
        action="store_true",
        help="Create demo staff, residents, patient, and announcements.",
    )

    parser.add_argument(
        "--admin-password",
        default=DEFAULT_ADMIN_PASSWORD,
        help="Password for the initial administrator account.",
    )

    args = parser.parse_args()

    if len(args.admin_password) < 8:
        parser.error(
            "The administrator password must contain at least 8 characters."
        )

    app = create_app()

    with app.app_context():
        try:
            print(f"Using database: {app.config.get('DB_NAME', 'eresbahub')}")
            print("Creating accounts...")

            add_user(
                "admin",
                "admin@resbahub.local",
                "System Administrator",
                args.admin_password,
                "admin",
            )

            if args.demo:
                add_user(
                    "barangay1",
                    "barangay1@resbahub.local",
                    "Maria Santos (Barangay)",
                    DEMO_PASSWORD,
                    "barangay_staff",
                )

                add_user(
                    "health1",
                    "health1@resbahub.local",
                    "Nurse Ana Reyes (Health)",
                    DEMO_PASSWORD,
                    "health_staff",
                )

                add_resident(
                    "resident1",
                    "resident1@resbahub.local",
                    "Juan",
                    "Dela Cruz",
                    "1995-04-12",
                    "Male",
                    1,
                    "123 Sampaguita St., Pinaod",
                    "09171234567",
                )

                add_resident(
                    "resident2",
                    "resident2@resbahub.local",
                    "Rosa",
                    "Garcia",
                    "2001-09-30",
                    "Female",
                    0,
                    "45 Narra St., Pinaod",
                    "09181234567",
                )

                add_demo_announcements()
                add_demo_patient()

            print("\nDone.")

            if args.admin_password == DEFAULT_ADMIN_PASSWORD:
                print(
                    "WARNING: The default administrator password is in use. "
                    "Change it immediately after logging in."
                )
                print(f"Admin login: admin / {DEFAULT_ADMIN_PASSWORD}")

            if args.demo:
                print(
                    "Demo accounts: barangay1, health1, resident1, resident2"
                    f" | Password: {DEMO_PASSWORD}"
                )

        except Exception:
            db.rollback()
            raise

        finally:
            db.close_db()


if __name__ == "__main__":
    main()
