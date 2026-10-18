"""Create the first administrator (and optional demo data).

    python seed.py                 -> creates the admin account
    python seed.py --demo          -> also creates demo staff, residents, patient, announcement
    python seed.py --admin-password "MyStr0ngPass"

Safe to run more than once: existing usernames are skipped.
"""
import argparse

from werkzeug.security import generate_password_hash

from resbahub import create_app, db

DEFAULT_ADMIN_PASSWORD = "Admin@12345"
DEMO_PASSWORD = "Demo@12345"


def add_user(username, email, full_name, password, role):
    if db.query("SELECT 1 FROM users WHERE username = ?", (username,), one=True):
        print(f"  - {username}: already exists, skipped")
        return None
    uid = db.execute(
        "INSERT INTO users (username, email, full_name, password_hash, role) VALUES (?,?,?,?,?)",
        (username, email, full_name, generate_password_hash(password), role))
    print(f"  + {role:15} {username}")
    return uid


def add_resident(username, email, first, last, birth, sex, verified, address, phone):
    uid = add_user(username, email, f"{first} {last}", DEMO_PASSWORD, "resident")
    if uid is None:
        return
    db.execute(
        "INSERT INTO residents (user_id, first_name, last_name, birthdate, sex, civil_status,"
        " contact_no, address, purok, is_verified, verified_at) VALUES (?,?,?,?,?,?,?,?,?,?,"
        " CASE WHEN ? = 1 THEN datetime('now','localtime') END)",
        (uid, first, last, birth, sex, "Single", phone, address, "Purok 1", verified, verified))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--demo", action="store_true", help="add demo accounts and sample data")
    parser.add_argument("--admin-password", default=DEFAULT_ADMIN_PASSWORD)
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        print("Creating accounts...")
        add_user("admin", "admin@resbahub.local", "System Administrator", args.admin_password, "admin")
        if args.demo:
            add_user("barangay1", "barangay1@resbahub.local", "Maria Santos (Barangay)", DEMO_PASSWORD, "barangay_staff")
            add_user("health1", "health1@resbahub.local", "Nurse Ana Reyes (Health)", DEMO_PASSWORD, "health_staff")
            add_resident("resident1", "resident1@resbahub.local", "Juan", "Dela Cruz", "1995-04-12",
                         "Male", 1, "123 Sampaguita St., Pinaod", "09171234567")
            add_resident("resident2", "resident2@resbahub.local", "Rosa", "Garcia", "2001-09-30",
                         "Female", 0, "45 Narra St., Pinaod", "09181234567")
            if not db.query("SELECT 1 FROM announcements LIMIT 1", one=True):
                db.execute("INSERT INTO announcements (title, body, category) VALUES (?,?,?)",
                           ("Free Anti-Rabies Vaccination",
                            "Bring your pets to the barangay hall this Saturday, 8 AM - 12 NN.", "Health"))
                db.execute("INSERT INTO announcements (title, body, category) VALUES (?,?,?)",
                           ("Barangay Assembly", "All residents are invited to the quarterly barangay assembly.",
                            "Schedule"))
            if not db.query("SELECT 1 FROM patients LIMIT 1", one=True):
                pid = db.execute(
                    "INSERT INTO patients (first_name, last_name, birthdate, sex, contact_no, address)"
                    " VALUES (?,?,?,?,?,?)",
                    ("Pedro", "Villanueva", "1988-02-20", "Male", "09191234567", "9 Mabini St., Pinaod"))
                db.execute("UPDATE patients SET patient_no = ? WHERE id = ?", (f"PT-{pid:05d}", pid))
        print("\nDone.")
        if args.admin_password == DEFAULT_ADMIN_PASSWORD:
            print(f"Admin login: admin / {DEFAULT_ADMIN_PASSWORD}   <-- CHANGE THIS PASSWORD AFTER FIRST LOGIN")
        if args.demo:
            print(f"Demo accounts (barangay1, health1, resident1, resident2) password: {DEMO_PASSWORD}")


if __name__ == "__main__":
    main()
