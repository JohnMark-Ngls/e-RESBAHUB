
from resbahub import create_app
from resbahub import db

app = create_app()

with app.app_context():
    admins = db.query(
        """
        SELECT id, username, email, full_name, role, is_active
        FROM users
        WHERE role = ?
        """,
        ("admin",),
    )

    if admins:
        print("Existing administrator accounts:")
        for admin in admins:
            print(dict(admin))
    else:
        print("No administrator account found.")
