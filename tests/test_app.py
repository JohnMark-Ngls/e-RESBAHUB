
"""End-to-end tests for e-RESBAHUB.

Run from the project folder with:
    python -m unittest -v
"""

import io
import os
import shutil
import tempfile
import unittest
from datetime import date, timedelta

from werkzeug.security import generate_password_hash

from resbahub import create_app, db
from resbahub import auth


PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 50
PDF = b"%PDF-1.4\n" + b"0" * 50
PW = "Passw0rd!"
TEST_DATABASE = "eresbahub_test"


def test_database_config(upload_folder, testing=True):
    """Build a MariaDB configuration for tests."""
    return {
        "TESTING": testing,
        "SECRET_KEY": "test",
        "DB_HOST": os.environ.get("DB_HOST", "127.0.0.1"),
        "DB_PORT": int(os.environ.get("DB_PORT", "3306")),
        "DB_USER": os.environ.get("DB_USER", "root"),
        "DB_PASSWORD": os.environ.get("DB_PASSWORD", ""),
        "DB_NAME": TEST_DATABASE,
        "UPLOAD_FOLDER": upload_folder,
    }



class Base(unittest.TestCase):
    def setUp(self):
        auth.reset_throttle()
        self.tmp = tempfile.mkdtemp()

        self.app = create_app(
            test_database_config(
                os.path.join(self.tmp, "uploads")
            )
        )

        # Safety check: never clean the main database.
        if self.app.config.get("DB_NAME") != TEST_DATABASE:
            self.fail(
                "Safety check failed: tests must use "
                "eresbahub_test, not the main database."
            )

        os.makedirs(
            self.app.config["UPLOAD_FOLDER"],
            exist_ok=True,
        )

        with self.app.app_context():
            self.reset_test_database()

            for username, role in (
                ("admin1", "admin"),
                ("brgy1", "barangay_staff"),
                ("health1", "health_staff"),
            ):
                db.execute(
                    """
                    INSERT INTO users (
                        username,
                        email,
                        full_name,
                        password_hash,
                        role
                    )
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        username,
                        f"{username}@x.ph",
                        username.title(),
                        generate_password_hash(PW),
                        role,
                    ),
                )

            db.commit()

    def reset_test_database(self):
        """Clear test records and restore predictable IDs and services."""
        if self.app.config.get("DB_NAME") != TEST_DATABASE:
            raise RuntimeError(
                "Refusing to reset a database other than eresbahub_test."
            )

        # Delete child records before their parent records.
        tables_to_clear = (
            "request_documents",
            "request_history",
            "visits",
            "appointments",
            "requests",
            "notifications",
            "patients",
            "announcements",
            "audit_log",
            "residents",
            "users",
        )

        for table in tables_to_clear:
            # Table names come only from the fixed list above.
            db.execute(f"DELETE FROM `{table}`")

        # Restore predictable IDs for tests that use hardcoded IDs.
        for table in tables_to_clear:
            db.execute(f"ALTER TABLE `{table}` AUTO_INCREMENT = 1")

        # Reset services too, because tests expect service IDs 1 and 4.
        db.execute("DELETE FROM services")
        db.execute("ALTER TABLE services AUTO_INCREMENT = 1")

        default_services = (
            (
                "Barangay Clearance",
                "Clearance for employment, business, travel and other legal purposes.",
                1,
                50.00,
            ),
            (
                "Certificate of Indigency",
                "Proof that the resident belongs to an indigent family (for assistance, scholarships, medical aid).",
                1,
                0.00,
            ),
            (
                "Certificate of Residency",
                "Proof that the resident lives in the barangay.",
                1,
                50.00,
            ),
            (
                "Barangay Certificate",
                "General certification issued by the barangay.",
                0,
                50.00,
            ),
            (
                "Other Barangay Service",
                "Other barangay-approved service. Describe it in the purpose field.",
                0,
                0.00,
            ),
        )

        for name, description, requires_document, fee in default_services:
            db.execute(
                """
                INSERT INTO services (
                    name,
                    description,
                    requires_document,
                    fee,
                    is_active
                )
                VALUES (?, ?, ?, ?, 1)
                """,
                (name, description, requires_document, fee),
            )

        db.commit()

    def tearDown(self):
        try:
            with self.app.app_context():
                db.close_db()
        finally:
            shutil.rmtree(self.tmp, ignore_errors=True)

    # Test helpers ---------------------------------------------------------

    def client(self):
        client = self.app.test_client()

        with client.session_transaction() as session:
            session["csrf_token"] = "tok"

        return client

    def post(self, client, url, data=None, **kwargs):
        data = dict(data or {})
        data["csrf_token"] = "tok"
        return client.post(url, data=data, **kwargs)

    def login(self, username, password=PW):
        client = self.client()

        response = self.post(
            client,
            "/login",
            {
                "username": username,
                "password": password,
            },
        )

        self.assertEqual(
            response.status_code,
            302,
            response.get_data(as_text=True)[:300],
        )

        with client.session_transaction() as session:
            session["csrf_token"] = "tok"

        return client

    def register(self, username="juan", **overrides):
        client = self.client()

        data = {
            "first_name": "Juan",
            "middle_name": "",
            "last_name": "Cruz",
            "suffix": "",
            "birthdate": "1990-01-02",
            "sex": "Male",
            "civil_status": "Single",
            "contact_no": "09171234567",
            "address": "1 Rizal St",
            "purok": "1",
            "occupation": "",
            "username": username,
            "email": f"{username}@x.ph",
            "password": PW,
            "confirm": PW,
            "consent": "1",
        }

        data.update(overrides)
        return client, self.post(client, "/register", data)

    def make_verified_resident(self, username="juan"):
        self.register(username)

        with self.app.app_context():
            db.execute(
                """
                UPDATE residents
                SET is_verified = 1
                WHERE user_id = (
                    SELECT id
                    FROM users
                    WHERE username = ?
                )
                """,
                (username,),
            )
            db.commit()

        return self.login(username)

class AuthTests(Base):
    def test_public_pages(self):
        client = self.client()

        for url in ("/", "/login", "/register"):
            with self.subTest(url=url):
                self.assertEqual(client.get(url).status_code, 200)

    def test_register_and_login(self):
        _, response = self.register()
        self.assertEqual(response.status_code, 302)

        client = self.login("juan")
        self.assertEqual(client.get("/dashboard").status_code, 200)

    def test_register_validation(self):
        _, response = self.register(
            password="short",
            confirm="short",
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"at least 8", response.data)

        _, response = self.register(contact_no="123")
        self.assertIn(b"Contact number", response.data)

        self.register("dupuser")
        _, response = self.register("dupuser")
        self.assertIn(b"already taken", response.data)

        _, response = self.register("nocons", consent="")
        self.assertIn(b"Data Privacy", response.data)

    def test_bad_login_and_throttle(self):
        client = self.client()

        for _ in range(5):
            response = self.post(
                client,
                "/login",
                {
                    "username": "admin1",
                    "password": "wrong",
                },
            )
            self.assertEqual(response.status_code, 200)

        response = self.post(
            client,
            "/login",
            {
                "username": "admin1",
                "password": PW,
            },
        )
        self.assertEqual(response.status_code, 429)

    def test_open_redirect_blocked(self):
        client = self.client()

        response = self.post(
            client,
            "/login?next=//evil.com",
            {
                "username": "admin1",
                "password": PW,
            },
        )

        self.assertNotIn("evil.com", response.headers["Location"])

    def test_csrf_required(self):
        client = self.app.test_client()

        response = client.post(
            "/login",
            data={
                "username": "admin1",
                "password": PW,
            },
        )

        self.assertEqual(response.status_code, 400)

    def test_logout_and_protected(self):
        client = self.login("admin1")
        self.post(client, "/logout")

        response = client.get("/admin/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.headers["Location"])

    def test_change_password(self):
        client = self.login("brgy1")

        response = self.post(
            client,
            "/account/password",
            {
                "current": PW,
                "new": "NewPass123",
                "confirm": "NewPass123",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.login("brgy1", "NewPass123")


class AccessTests(Base):
    def test_role_walls(self):
        resident = self.make_verified_resident()

        for url in (
            "/staff/",
            "/health/",
            "/admin/",
            "/reports",
            "/search",
            "/staff/requests",
        ):
            with self.subTest(url=url):
                self.assertEqual(resident.get(url).status_code, 403)

        barangay_staff = self.login("brgy1")
        self.assertEqual(barangay_staff.get("/staff/").status_code, 200)
        self.assertEqual(barangay_staff.get("/health/").status_code, 403)
        self.assertEqual(barangay_staff.get("/admin/").status_code, 403)
        self.assertEqual(barangay_staff.get("/dashboard").status_code, 403)

        health_staff = self.login("health1")
        self.assertEqual(health_staff.get("/health/").status_code, 200)
        self.assertEqual(health_staff.get("/staff/").status_code, 403)
        self.assertEqual(
            health_staff.get("/staff/residents").status_code,
            403,
        )

    def test_admin_sees_all(self):
        admin = self.login("admin1")

        urls = (
            "/admin/",
            "/admin/users",
            "/admin/users/new",
            "/admin/services",
            "/admin/audit",
            "/staff/",
            "/staff/requests",
            "/staff/residents",
            "/staff/announcements",
            "/health/",
            "/health/patients",
            "/health/appointments",
            "/health/visits",
            "/health/patients/new",
            "/health/appointments/new",
            "/reports",
            "/search?q=ab",
            "/announcements",
            "/",
        )

        for url in urls:
            with self.subTest(url=url):
                response = admin.get(url)
                self.assertIn(response.status_code, (200, 302), url)
                self.assertNotEqual(response.status_code, 500, url)


class ResidentFlowTests(Base):
    def submit(
        self,
        client,
        service_id=1,
        files=True,
        purpose="For job application",
    ):
        data = {
            "service_id": str(service_id),
            "purpose": purpose,
            "csrf_token": "tok",
        }

        if files:
            data["documents"] = (
                io.BytesIO(PNG),
                "id.png",
            )

        return client.post(
            "/requests/new",
            data=data,
            content_type="multipart/form-data",
        )

    def test_unverified_cannot_request(self):
        self.register()
        client = self.login("juan")

        response = client.get("/requests/new")
        self.assertEqual(response.status_code, 302)

    def test_full_request_lifecycle(self):
        client = self.make_verified_resident()

        self.assertEqual(client.get("/requests/new").status_code, 200)

        response = self.submit(client)
        self.assertEqual(
            response.status_code,
            302,
            response.get_data(as_text=True)[:400],
        )

        detail = client.get(response.headers["Location"])
        self.assertEqual(detail.status_code, 200)
        self.assertIn(b"REQ-", detail.data)

        duplicate = self.submit(client)
        self.assertEqual(duplicate.status_code, 200)
        self.assertIn(b"active request", duplicate.data)

        staff = self.login("brgy1")
        self.assertEqual(staff.get("/staff/requests").status_code, 200)
        self.assertEqual(
            staff.get("/staff/requests?status=Pending&q=juan").status_code,
            200,
        )

        with self.app.app_context():
            request_row = db.query(
                "SELECT id FROM requests ORDER BY id DESC LIMIT 1",
                one=True,
            )
            request_id = request_row["id"]

        self.assertEqual(
            staff.get(f"/requests/{request_id}").status_code,
            200,
        )

        response = self.post(
            staff,
            f"/staff/requests/{request_id}/update",
            {"status": "Rejected", "remarks": ""},
        )
        self.assertEqual(response.status_code, 302)

        with self.app.app_context():
            self.assertEqual(
                db.query(
                    "SELECT status FROM requests WHERE id = ?",
                    (request_id,),
                    one=True,
                )["status"],
                "Pending",
            )

        self.post(
            staff,
            f"/staff/requests/{request_id}/update",
            {"status": "Approved", "remarks": "Ready tomorrow"},
        )
        self.post(
            staff,
            f"/staff/requests/{request_id}/update",
            {"status": "Completed", "remarks": ""},
        )

        with self.app.app_context():
            self.assertEqual(
                db.query(
                    "SELECT status FROM requests WHERE id = ?",
                    (request_id,),
                    one=True,
                )["status"],
                "Completed",
            )

        self.post(
            staff,
            f"/staff/requests/{request_id}/update",
            {"status": "Pending", "remarks": ""},
        )

        with self.app.app_context():
            self.assertEqual(
                db.query(
                    "SELECT status FROM requests WHERE id = ?",
                    (request_id,),
                    one=True,
                )["status"],
                "Completed",
            )

        self.assertEqual(client.get("/notifications").status_code, 200)
        self.assertIn(b"Completed", client.get("/notifications").data)
        self.assertEqual(client.get("/requests").status_code, 200)
        self.assertEqual(client.get("/dashboard").status_code, 200)
        self.assertEqual(
            client.get(f"/documents/{request_id}").status_code,
            200,
        )
        self.assertEqual(
            staff.get(f"/documents/{request_id}").status_code,
            200,
        )

    def test_cannot_see_other_residents_request(self):
        client1 = self.make_verified_resident("juan")
        self.submit(client1)

        client2 = self.make_verified_resident("maria")
        self.assertEqual(client2.get("/requests/1").status_code, 404)
        self.assertEqual(client2.get("/documents/1").status_code, 404)
        self.assertEqual(
            self.post(client2, "/requests/1/cancel").status_code,
            404,
        )

        health_staff = self.login("health1")
        self.assertEqual(
            health_staff.get("/requests/1").status_code,
            403,
        )

    def test_upload_rules(self):
        client = self.make_verified_resident()

        response = self.submit(client, files=False)
        self.assertIn(b"supporting document", response.data)

        bad = client.post(
            "/requests/new",
            data={
                "service_id": "1",
                "purpose": "For work",
                "csrf_token": "tok",
                "documents": (
                    io.BytesIO(b"MZ fake exe"),
                    "virus.exe",
                ),
            },
            content_type="multipart/form-data",
        )
        self.assertIn(b"not allowed", bad.data)

        fake = client.post(
            "/requests/new",
            data={
                "service_id": "1",
                "purpose": "For work",
                "csrf_token": "tok",
                "documents": (
                    io.BytesIO(b"not a pdf at all"),
                    "x.pdf",
                ),
            },
            content_type="multipart/form-data",
        )
        self.assertIn(b"not a valid PDF", fake.data)

        valid = client.post(
            "/requests/new",
            data={
                "service_id": "1",
                "purpose": "For work",
                "csrf_token": "tok",
                "documents": (io.BytesIO(PDF), "x.pdf"),
            },
            content_type="multipart/form-data",
        )
        self.assertEqual(valid.status_code, 302)

        no_document_service = self.submit(
            client,
            service_id=4,
            files=False,
        )
        self.assertEqual(no_document_service.status_code, 302)

    def test_cancel(self):
        client = self.make_verified_resident()
        self.submit(client)

        self.assertEqual(
            self.post(client, "/requests/1/cancel").status_code,
            302,
        )

        with self.app.app_context():
            self.assertEqual(
                db.query(
                    "SELECT status FROM requests WHERE id = 1",
                    one=True,
                )["status"],
                "Cancelled",
            )

    def test_profile_locking(self):
        self.register()
        client = self.login("juan")
        self.assertEqual(client.get("/profile").status_code, 200)

        data = {
            "first_name": "Johnny",
            "middle_name": "",
            "last_name": "Cruz",
            "suffix": "",
            "birthdate": "1990-01-02",
            "sex": "Male",
            "civil_status": "Married",
            "contact_no": "09179999999",
            "address": "New address",
            "purok": "2",
            "occupation": "Driver",
            "email": "juan@x.ph",
        }

        self.assertEqual(self.post(client, "/profile", data).status_code, 302)

        with self.app.app_context():
            self.assertEqual(
                db.query(
                    "SELECT first_name FROM residents",
                    one=True,
                )["first_name"],
                "Johnny",
            )
            db.execute("UPDATE residents SET is_verified = 1")

        data["first_name"] = "Hacker"
        data["contact_no"] = "09170000000"
        self.post(client, "/profile", data)

        with self.app.app_context():
            row = db.query(
                "SELECT first_name, contact_no FROM residents",
                one=True,
            )
            self.assertEqual(row["first_name"], "Johnny")
            self.assertEqual(row["contact_no"], "09170000000")

    def test_staff_verify_resident_and_announce(self):
        self.register()
        staff = self.login("brgy1")

        self.assertEqual(
            staff.get("/staff/residents?verified=0").status_code,
            200,
        )
        self.assertEqual(
            staff.get("/staff/residents/1").status_code,
            200,
        )

        data = {
            "first_name": "Juan",
            "middle_name": "",
            "last_name": "Cruz",
            "suffix": "",
            "birthdate": "1990-01-02",
            "sex": "Male",
            "civil_status": "Single",
            "contact_no": "09171234567",
            "address": "1 Rizal St",
            "purok": "1",
            "occupation": "",
            "is_verified": "1",
        }

        self.assertEqual(
            self.post(staff, "/staff/residents/1", data).status_code,
            302,
        )

        with self.app.app_context():
            self.assertEqual(
                db.query(
                    "SELECT is_verified FROM residents",
                    one=True,
                )["is_verified"],
                1,
            )

        response = self.post(
            staff,
            "/staff/announcements",
            {
                "title": "Clean-up Drive",
                "body": "Saturday 6AM",
                "category": "Schedule",
            },
        )
        self.assertEqual(response.status_code, 302)

        client = self.login("juan")
        self.assertIn(b"Clean-up Drive", client.get("/announcements").data)
        self.assertIn(
            b"Clean-up Drive",
            client.get("/announcements?category=Schedule").data,
        )
        self.assertIn(b"verified", client.get("/notifications").data)

        self.assertEqual(
            self.post(staff, "/staff/announcements/1/delete").status_code,
            302,
        )

    def test_xss_escaped(self):
        client = self.make_verified_resident()
        self.submit(
            client,
            purpose="<script>alert(1)</script> test",
        )

        response = client.get("/requests/1")
        self.assertNotIn(b"<script>alert(1)</script>", response.data)
        self.assertIn(b"&lt;script&gt;", response.data)


class HealthFlowTests(Base):
    def patient_data(self, **overrides):
        data = {
            "first_name": "Pedro",
            "middle_name": "",
            "last_name": "Santos",
            "birthdate": "2015-05-05",
            "sex": "Male",
            "contact_no": "",
            "address": "Purok 3",
            "guardian_name": "Ana Santos",
            "blood_type": "O+",
            "allergies": "",
            "notes": "",
        }
        data.update(overrides)
        return data

    def test_patient_appointment_visit_flow(self):
        health = self.login("health1")
        response = self.post(
            health,
            "/health/patients/new",
            self.patient_data(),
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            health.get(response.headers["Location"]).status_code,
            200,
        )
        self.assertEqual(
            health.get("/health/patients?q=ped").status_code,
            200,
        )
        self.assertIn(b"Pedro", health.get("/health/patients?q=ped").data)
        self.assertEqual(
            health.get("/health/patients/1/edit").status_code,
            200,
        )
        self.assertEqual(
            self.post(
                health,
                "/health/patients/1/edit",
                self.patient_data(notes="updated"),
            ).status_code,
            302,
        )

        self.assertEqual(
            health.get("/health/appointments/new?pq=ped").status_code,
            200,
        )
        self.assertEqual(
            health.get("/health/appointments/new?patient_id=1").status_code,
            200,
        )

        today = date.today().isoformat()

        for _ in range(2):
            response = self.post(
                health,
                "/health/appointments/new",
                {
                    "patient_id": "1",
                    "appointment_date": today,
                    "appointment_time": "09:30",
                    "service_type": "Immunization",
                    "notes": "",
                },
            )
            self.assertEqual(
                response.status_code,
                302,
                response.get_data(as_text=True)[:300],
            )

        with self.app.app_context():
            queue_numbers = [
                row["queue_no"]
                for row in db.query(
                    "SELECT queue_no FROM appointments ORDER BY id"
                )
            ]
            self.assertEqual(queue_numbers, [1, 2])

        yesterday = (date.today() - timedelta(days=1)).isoformat()
        response = self.post(
            health,
            "/health/appointments/new",
            {
                "patient_id": "1",
                "appointment_date": yesterday,
                "service_type": "Consultation",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(health.get("/health/appointments").status_code, 200)

        self.assertEqual(
            self.post(
                health,
                "/health/appointments/1/status",
                {"status": "Waiting"},
            ).status_code,
            302,
        )
        self.assertEqual(
            self.post(
                health,
                "/health/appointments/1/status",
                {"status": "Completed"},
            ).status_code,
            302,
        )

        with self.app.app_context():
            self.assertEqual(
                db.query(
                    "SELECT status FROM appointments WHERE id = 1",
                    one=True,
                )["status"],
                "Waiting",
            )

        self.assertEqual(
            health.get(
                "/health/visits/new?patient_id=1&appointment_id=1"
            ).status_code,
            200,
        )

        response = self.post(
            health,
            "/health/visits/new",
            {
                "patient_id": "1",
                "appointment_id": "1",
                "visit_date": today,
                "service_type": "Immunization",
                "purpose": "BCG vaccine",
                "services_provided": "BCG given",
                "findings": "",
                "blood_pressure": "",
                "temperature": "36.6",
                "weight_kg": "18.5",
                "follow_up_date": "",
            },
        )
        self.assertEqual(
            response.status_code,
            302,
            response.get_data(as_text=True)[:400],
        )

        with self.app.app_context():
            self.assertEqual(
                db.query(
                    "SELECT status FROM appointments WHERE id = 1",
                    one=True,
                )["status"],
                "Completed",
            )

        response = self.post(
            health,
            "/health/visits/new",
            {
                "patient_id": "1",
                "visit_date": today,
                "service_type": "Consultation",
                "purpose": "Checkup",
                "temperature": "99",
                "blood_pressure": "abc",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(health.get("/health/visits").status_code, 200)
        self.assertEqual(
            health.get(
                f"/health/visits?from={today}&to={today}"
                "&service=Immunization&q=bcg"
            ).status_code,
            200,
        )
        self.assertIn(b"BCG", health.get("/health/patients/1").data)

    def test_patient_from_resident(self):
        self.make_verified_resident()
        health = self.login("health1")

        self.assertIn(
            b"Cruz",
            health.get("/health/patients/new?rq=cru").data,
        )

        page = health.get("/health/patients/new?resident_id=1")
        self.assertIn(b'value="Juan"', page.data)

        data = self.patient_data(
            first_name="Juan",
            last_name="Cruz",
            birthdate="1990-01-02",
        )
        data["resident_id"] = "1"

        self.assertEqual(
            self.post(health, "/health/patients/new", data).status_code,
            302,
        )

        response = self.post(health, "/health/patients/new", data)
        self.assertIn(b"already has a patient record", response.data)

    def test_patient_validation(self):
        health = self.login("health1")

        response = self.post(
            health,
            "/health/patients/new",
            self.patient_data(
                birthdate="2999-01-01",
                contact_no="12",
            ),
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"valid birthdate", response.data)


class ReportsAdminTests(Base):
    def test_reports_search_export(self):
        self.make_verified_resident()

        health = self.login("health1")
        self.post(
            health,
            "/health/patients/new",
            {
                "first_name": "Pedro",
                "middle_name": "",
                "last_name": "Santos",
                "birthdate": "2015-05-05",
                "sex": "Male",
                "contact_no": "",
                "address": "",
                "guardian_name": "",
                "blood_type": "",
                "allergies": "",
                "notes": "",
            },
        )

        today = date.today().isoformat()
        self.post(
            health,
            "/health/visits/new",
            {
                "patient_id": "1",
                "visit_date": today,
                "service_type": "Consultation",
                "purpose": "=cmd|' /C calc'!A0",
            },
        )

        staff = self.login("brgy1")
        cases = (
            (
                staff,
                [
                    "/reports",
                    "/search?q=juan",
                    f"/reports?from={today}&to={today}",
                    "/reports/export/requests.csv",
                ],
            ),
            (
                health,
                [
                    "/reports",
                    "/search?q=pedro",
                    "/reports/export/visits.csv",
                    "/reports/export/appointments.csv",
                ],
            ),
        )

        for client, urls in cases:
            for url in urls:
                with self.subTest(url=url):
                    self.assertEqual(client.get(url).status_code, 200)

        self.assertEqual(
            staff.get("/reports/export/visits.csv").status_code,
            404,
        )
        self.assertEqual(
            health.get("/reports/export/requests.csv").status_code,
            404,
        )

        csv_text = health.get(
            "/reports/export/visits.csv"
        ).get_data(as_text=True)
        self.assertIn("'=cmd", csv_text)

        self.assertEqual(health.get("/search?q=a").status_code, 200)
        self.assertEqual(
            self.login("admin1").get("/reports").status_code,
            200,
        )

    def test_admin_user_management(self):
        admin = self.login("admin1")

        data = {
            "username": "nurse2",
            "email": "n2@x.ph",
            "full_name": "Nurse Two",
            "role": "health_staff",
            "password": "Staff1234",
        }

        self.assertEqual(
            self.post(admin, "/admin/users/new", data).status_code,
            302,
        )
        self.assertEqual(
            self.post(admin, "/admin/users/new", data).status_code,
            200,
        )

        self.login("nurse2", "Staff1234")

        with self.app.app_context():
            user_id = db.query(
                "SELECT id FROM users WHERE username = 'nurse2'",
                one=True,
            )["id"]
            admin_id = db.query(
                "SELECT id FROM users WHERE username = 'admin1'",
                one=True,
            )["id"]

        self.assertEqual(admin.get(f"/admin/users/{user_id}").status_code, 200)

        response = self.post(
            admin,
            f"/admin/users/{user_id}",
            {
                "email": "n2@x.ph",
                "full_name": "Nurse Two",
                "role": "barangay_staff",
                "password": "",
            },
        )
        self.assertEqual(response.status_code, 302)

        client = self.client()
        response = self.post(
            client,
            "/login",
            {
                "username": "nurse2",
                "password": "Staff1234",
            },
        )
        self.assertEqual(response.status_code, 200)

        response = self.post(
            admin,
            f"/admin/users/{admin_id}",
            {
                "email": "admin1@x.ph",
                "full_name": "Admin1",
                "role": "admin",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            admin.get(
                "/admin/users?q=nurse&role=barangay_staff"
            ).status_code,
            200,
        )
        self.assertEqual(admin.get(f"/admin/users/{admin_id}").status_code, 200)

    def test_services_admin(self):
        admin = self.login("admin1")

        response = self.post(
            admin,
            "/admin/services",
            {
                "name": "Business Permit Endorsement",
                "fee": "100",
                "description": "Endorsement",
                "requires_document": "1",
            },
        )
        self.assertEqual(response.status_code, 302)

        self.post(admin, "/admin/services/1/toggle")

        with self.app.app_context():
            self.assertEqual(
                db.query(
                    "SELECT is_active FROM services WHERE id = 1",
                    one=True,
                )["is_active"],
                0,
            )

    def test_errors(self):
        client = self.client()
        self.assertEqual(client.get("/nope").status_code, 404)

        admin = self.login("admin1")
        self.assertEqual(admin.get("/admin/users/9999").status_code, 404)
        self.assertEqual(
            admin.get("/health/patients/9999").status_code,
            404,
        )

    def test_upload_too_large(self):
        client = self.make_verified_resident()
        big = io.BytesIO(PDF + b"0" * (6 * 1024 * 1024))

        response = client.post(
            "/requests/new",
            data={
                "service_id": "1",
                "purpose": "For work",
                "csrf_token": "tok",
                "documents": (big, "big.pdf"),
            },
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 413)


class SeedTests(unittest.TestCase):
    def test_schema_idempotent_and_services(self):
        tmp = tempfile.mkdtemp()

        try:
            config = test_database_config(
                os.path.join(tmp, "uploads")
            )

            app = create_app(config)
            app2 = create_app(config)

            self.assertEqual(
                app2.config["DB_NAME"],
                TEST_DATABASE,
            )

            with app2.app_context():
                result = db.query(
                    "SELECT COUNT(*) AS c FROM services",
                    one=True,
                )
                self.assertEqual(result["c"], 5)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
