"""End-to-end tests. Run from the project folder with:   python -m unittest -v"""
import io
import os
import shutil
import sqlite3
import tempfile
import unittest
from datetime import date, timedelta

from werkzeug.security import generate_password_hash

from resbahub import create_app, db
from resbahub import auth

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 50
PDF = b"%PDF-1.4\n" + b"0" * 50
PW = "Passw0rd!"


class Base(unittest.TestCase):
    def setUp(self):
        auth.reset_throttle()
        self.tmp = tempfile.mkdtemp()
        self.app = create_app({
            "TESTING": True, "SECRET_KEY": "test",
            "DATABASE": os.path.join(self.tmp, "t.db"),
            "UPLOAD_FOLDER": os.path.join(self.tmp, "up"),
        })
        os.makedirs(self.app.config["UPLOAD_FOLDER"], exist_ok=True)
        with self.app.app_context():
            for u, role in (("admin1", "admin"), ("brgy1", "barangay_staff"), ("health1", "health_staff")):
                db.execute("INSERT INTO users (username,email,full_name,password_hash,role) VALUES (?,?,?,?,?)",
                           (u, f"{u}@x.ph", u.title(), generate_password_hash(PW), role))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # helpers ---------------------------------------------------------------
    def client(self):
        c = self.app.test_client()
        with c.session_transaction() as s:
            s["csrf_token"] = "tok"
        return c

    def post(self, c, url, data=None, **kw):
        data = dict(data or {})
        data["csrf_token"] = "tok"
        return c.post(url, data=data, **kw)

    def login(self, username, password=PW):
        c = self.client()
        r = self.post(c, "/login", {"username": username, "password": password})
        self.assertEqual(r.status_code, 302, r.get_data(as_text=True)[:300])
        with c.session_transaction() as s:      # login resets the session; restore the test token
            s["csrf_token"] = "tok"
        return c

    def register(self, username="juan", **over):
        c = self.client()
        data = dict(first_name="Juan", middle_name="", last_name="Cruz", suffix="", birthdate="1990-01-02",
                    sex="Male", civil_status="Single", contact_no="09171234567", address="1 Rizal St",
                    purok="1", occupation="", username=username, email=f"{username}@x.ph",
                    password=PW, confirm=PW, consent="1")
        data.update(over)
        return c, self.post(c, "/register", data)

    def make_verified_resident(self, username="juan"):
        self.register(username)
        with self.app.app_context():
            db.execute("UPDATE residents SET is_verified=1 WHERE user_id=(SELECT id FROM users WHERE username=?)",
                       (username,))
        return self.login(username)


class AuthTests(Base):
    def test_public_pages(self):
        c = self.client()
        for url in ("/", "/login", "/register"):
            self.assertEqual(c.get(url).status_code, 200, url)

    def test_register_and_login(self):
        _, r = self.register()
        self.assertEqual(r.status_code, 302)
        c = self.login("juan")
        self.assertEqual(c.get("/dashboard").status_code, 200)

    def test_register_validation(self):
        _, r = self.register(password="short", confirm="short")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"at least 8", r.data)
        _, r = self.register(contact_no="123")
        self.assertIn(b"Contact number", r.data)
        self.register("dupuser")
        _, r = self.register("dupuser")
        self.assertIn(b"already taken", r.data)
        _, r = self.register("nocons", consent="")
        self.assertIn(b"Data Privacy", r.data)

    def test_bad_login_and_throttle(self):
        c = self.client()
        for _ in range(5):
            r = self.post(c, "/login", {"username": "admin1", "password": "wrong"})
            self.assertEqual(r.status_code, 200)
        r = self.post(c, "/login", {"username": "admin1", "password": PW})
        self.assertEqual(r.status_code, 429)

    def test_open_redirect_blocked(self):
        c = self.client()
        r = self.post(c, "/login?next=//evil.com", {"username": "admin1", "password": PW})
        self.assertNotIn("evil.com", r.headers["Location"])

    def test_csrf_required(self):
        c = self.app.test_client()
        r = c.post("/login", data={"username": "admin1", "password": PW})
        self.assertEqual(r.status_code, 400)

    def test_logout_and_protected(self):
        c = self.login("admin1")
        self.post(c, "/logout")
        r = c.get("/admin/")
        self.assertEqual(r.status_code, 302)
        self.assertIn("/login", r.headers["Location"])

    def test_change_password(self):
        c = self.login("brgy1")
        r = self.post(c, "/account/password", {"current": PW, "new": "NewPass123", "confirm": "NewPass123"})
        self.assertEqual(r.status_code, 302)
        self.login("brgy1", "NewPass123")


class AccessTests(Base):
    def test_role_walls(self):
        res = self.make_verified_resident()
        for url in ("/staff/", "/health/", "/admin/", "/reports", "/search", "/staff/requests"):
            self.assertEqual(res.get(url).status_code, 403, url)
        brgy = self.login("brgy1")
        self.assertEqual(brgy.get("/staff/").status_code, 200)
        self.assertEqual(brgy.get("/health/").status_code, 403)
        self.assertEqual(brgy.get("/admin/").status_code, 403)
        self.assertEqual(brgy.get("/dashboard").status_code, 403)
        health = self.login("health1")
        self.assertEqual(health.get("/health/").status_code, 200)
        self.assertEqual(health.get("/staff/").status_code, 403)
        self.assertEqual(health.get("/staff/residents").status_code, 403)

    def test_admin_sees_all(self):
        a = self.login("admin1")
        for url in ("/admin/", "/admin/users", "/admin/users/new", "/admin/services", "/admin/audit",
                    "/staff/", "/staff/requests", "/staff/residents", "/staff/announcements",
                    "/health/", "/health/patients", "/health/appointments", "/health/visits",
                    "/health/patients/new", "/health/appointments/new", "/reports", "/search?q=ab",
                    "/announcements", "/"):
            self.assertIn(a.get(url).status_code, (200, 302), url)
            self.assertNotEqual(a.get(url).status_code, 500, url)


class ResidentFlowTests(Base):
    def submit(self, c, service_id=1, files=True, purpose="For job application"):
        data = {"service_id": str(service_id), "purpose": purpose, "csrf_token": "tok"}
        if files:
            data["documents"] = (io.BytesIO(PNG), "id.png")
        return c.post("/requests/new", data=data, content_type="multipart/form-data")

    def test_unverified_cannot_request(self):
        self.register()
        c = self.login("juan")
        r = c.get("/requests/new")
        self.assertEqual(r.status_code, 302)

    def test_full_request_lifecycle(self):
        c = self.make_verified_resident()
        self.assertEqual(c.get("/requests/new").status_code, 200)
        r = self.submit(c)
        self.assertEqual(r.status_code, 302, r.get_data(as_text=True)[:400])
        detail = c.get(r.headers["Location"])
        self.assertEqual(detail.status_code, 200)
        self.assertIn(b"REQ-", detail.data)
        # duplicate active request blocked
        r2 = self.submit(c)
        self.assertEqual(r2.status_code, 200)
        self.assertIn(b"active request", r2.data)
        # staff processes it
        b = self.login("brgy1")
        self.assertEqual(b.get("/staff/requests").status_code, 200)
        self.assertEqual(b.get("/staff/requests?status=Pending&q=juan").status_code, 200)
        rid = 1
        self.assertEqual(b.get(f"/requests/{rid}").status_code, 200)
        r = self.post(b, f"/staff/requests/{rid}/update", {"status": "Rejected", "remarks": ""})
        self.assertEqual(r.status_code, 302)
        with self.app.app_context():
            self.assertEqual(db.query("SELECT status FROM requests WHERE id=1", one=True)["status"], "Pending")
        self.post(b, f"/staff/requests/{rid}/update", {"status": "Approved", "remarks": "Ready tomorrow"})
        self.post(b, f"/staff/requests/{rid}/update", {"status": "Completed", "remarks": ""})
        with self.app.app_context():
            self.assertEqual(db.query("SELECT status FROM requests WHERE id=1", one=True)["status"], "Completed")
            # invalid jump blocked
        self.post(b, f"/staff/requests/{rid}/update", {"status": "Pending", "remarks": ""})
        with self.app.app_context():
            self.assertEqual(db.query("SELECT status FROM requests WHERE id=1", one=True)["status"], "Completed")
        # resident sees notifications and history
        n = c.get("/notifications")
        self.assertEqual(n.status_code, 200)
        self.assertIn(b"Completed", n.data)
        self.assertEqual(c.get("/requests").status_code, 200)
        self.assertEqual(c.get("/dashboard").status_code, 200)
        # document download works for owner and staff
        self.assertEqual(c.get("/documents/1").status_code, 200)
        self.assertEqual(b.get("/documents/1").status_code, 200)

    def test_cannot_see_other_residents_request(self):
        c1 = self.make_verified_resident("juan")
        self.submit(c1)
        c2 = self.make_verified_resident("maria")
        self.assertEqual(c2.get("/requests/1").status_code, 404)
        self.assertEqual(c2.get("/documents/1").status_code, 404)
        self.assertEqual(self.post(c2, "/requests/1/cancel").status_code, 404)
        h = self.login("health1")
        self.assertEqual(h.get("/requests/1").status_code, 403)

    def test_upload_rules(self):
        c = self.make_verified_resident()
        r = self.submit(c, files=False)             # clearance needs a document
        self.assertIn(b"supporting document", r.data)
        bad = c.post("/requests/new", data={"service_id": "1", "purpose": "For work", "csrf_token": "tok",
                     "documents": (io.BytesIO(b"MZ fake exe"), "virus.exe")}, content_type="multipart/form-data")
        self.assertIn(b"not allowed", bad.data)
        fake = c.post("/requests/new", data={"service_id": "1", "purpose": "For work", "csrf_token": "tok",
                      "documents": (io.BytesIO(b"not a pdf at all"), "x.pdf")}, content_type="multipart/form-data")
        self.assertIn(b"not a valid PDF", fake.data)
        ok = c.post("/requests/new", data={"service_id": "1", "purpose": "For work", "csrf_token": "tok",
                    "documents": (io.BytesIO(PDF), "x.pdf")}, content_type="multipart/form-data")
        self.assertEqual(ok.status_code, 302)
        # service that needs no document
        ok2 = self.submit(c, service_id=4, files=False)
        self.assertEqual(ok2.status_code, 302)

    def test_cancel(self):
        c = self.make_verified_resident()
        self.submit(c)
        self.assertEqual(self.post(c, "/requests/1/cancel").status_code, 302)
        with self.app.app_context():
            self.assertEqual(db.query("SELECT status FROM requests WHERE id=1", one=True)["status"], "Cancelled")

    def test_profile_locking(self):
        self.register()
        c = self.login("juan")
        self.assertEqual(c.get("/profile").status_code, 200)
        data = dict(first_name="Johnny", middle_name="", last_name="Cruz", suffix="", birthdate="1990-01-02",
                    sex="Male", civil_status="Married", contact_no="09179999999", address="New address",
                    purok="2", occupation="Driver", email="juan@x.ph")
        self.assertEqual(self.post(c, "/profile", data).status_code, 302)
        with self.app.app_context():
            self.assertEqual(db.query("SELECT first_name FROM residents", one=True)["first_name"], "Johnny")
            db.execute("UPDATE residents SET is_verified=1")
        data["first_name"] = "Hacker"
        data["contact_no"] = "09170000000"
        self.post(c, "/profile", data)
        with self.app.app_context():
            row = db.query("SELECT first_name, contact_no FROM residents", one=True)
            self.assertEqual(row["first_name"], "Johnny")      # locked after verification
            self.assertEqual(row["contact_no"], "09170000000")  # still editable

    def test_staff_verify_resident_and_announce(self):
        self.register()
        b = self.login("brgy1")
        self.assertEqual(b.get("/staff/residents?verified=0").status_code, 200)
        self.assertEqual(b.get("/staff/residents/1").status_code, 200)
        data = dict(first_name="Juan", middle_name="", last_name="Cruz", suffix="", birthdate="1990-01-02",
                    sex="Male", civil_status="Single", contact_no="09171234567", address="1 Rizal St",
                    purok="1", occupation="", is_verified="1")
        self.assertEqual(self.post(b, "/staff/residents/1", data).status_code, 302)
        with self.app.app_context():
            self.assertEqual(db.query("SELECT is_verified FROM residents", one=True)["is_verified"], 1)
        r = self.post(b, "/staff/announcements", {"title": "Clean-up Drive", "body": "Saturday 6AM", "category": "Schedule"})
        self.assertEqual(r.status_code, 302)
        c = self.login("juan")
        self.assertIn(b"Clean-up Drive", c.get("/announcements").data)
        self.assertIn(b"Clean-up Drive", c.get("/announcements?category=Schedule").data)
        self.assertIn(b"verified", c.get("/notifications").data)
        self.assertEqual(self.post(b, "/staff/announcements/1/delete").status_code, 302)

    def test_xss_escaped(self):
        c = self.make_verified_resident()
        self.submit(c, purpose="<script>alert(1)</script> test")
        r = c.get("/requests/1")
        self.assertNotIn(b"<script>alert(1)</script>", r.data)
        self.assertIn(b"&lt;script&gt;", r.data)


class HealthFlowTests(Base):
    def patient_data(self, **o):
        d = dict(first_name="Pedro", middle_name="", last_name="Santos", birthdate="2015-05-05", sex="Male",
                 contact_no="", address="Purok 3", guardian_name="Ana Santos", blood_type="O+",
                 allergies="", notes="")
        d.update(o)
        return d

    def test_patient_appointment_visit_flow(self):
        h = self.login("health1")
        r = self.post(h, "/health/patients/new", self.patient_data())
        self.assertEqual(r.status_code, 302)
        self.assertEqual(h.get(r.headers["Location"]).status_code, 200)
        self.assertEqual(h.get("/health/patients?q=ped").status_code, 200)
        self.assertIn(b"Pedro", h.get("/health/patients?q=ped").data)
        self.assertEqual(h.get("/health/patients/1/edit").status_code, 200)
        self.assertEqual(self.post(h, "/health/patients/1/edit", self.patient_data(notes="updated")).status_code, 302)
        # appointments + queue numbers
        self.assertEqual(h.get("/health/appointments/new?pq=ped").status_code, 200)
        self.assertEqual(h.get("/health/appointments/new?patient_id=1").status_code, 200)
        today = date.today().isoformat()
        for _ in range(2):
            r = self.post(h, "/health/appointments/new", {"patient_id": "1", "appointment_date": today,
                          "appointment_time": "09:30", "service_type": "Immunization", "notes": ""})
            self.assertEqual(r.status_code, 302, r.get_data(as_text=True)[:300])
        with self.app.app_context():
            q = [r["queue_no"] for r in db.query("SELECT queue_no FROM appointments ORDER BY id")]
            self.assertEqual(q, [1, 2])
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        r = self.post(h, "/health/appointments/new", {"patient_id": "1", "appointment_date": yesterday,
                      "service_type": "Consultation"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(h.get("/health/appointments").status_code, 200)
        self.assertEqual(self.post(h, "/health/appointments/1/status", {"status": "Waiting"}).status_code, 302)
        self.assertEqual(self.post(h, "/health/appointments/1/status", {"status": "Completed"}).status_code, 302)
        with self.app.app_context():
            self.assertEqual(db.query("SELECT status FROM appointments WHERE id=1", one=True)["status"], "Waiting")
        self.assertEqual(h.get("/health/").status_code, 200)
        # visit
        self.assertEqual(h.get("/health/visits/new?patient_id=1&appointment_id=1").status_code, 200)
        r = self.post(h, "/health/visits/new", {"patient_id": "1", "appointment_id": "1", "visit_date": today,
                      "service_type": "Immunization", "purpose": "BCG vaccine", "services_provided": "BCG given",
                      "findings": "", "blood_pressure": "", "temperature": "36.6", "weight_kg": "18.5",
                      "follow_up_date": ""})
        self.assertEqual(r.status_code, 302, r.get_data(as_text=True)[:400])
        with self.app.app_context():
            self.assertEqual(db.query("SELECT status FROM appointments WHERE id=1", one=True)["status"], "Completed")
        bad = self.post(h, "/health/visits/new", {"patient_id": "1", "visit_date": today, "service_type": "Consultation",
                        "purpose": "Checkup", "temperature": "99", "blood_pressure": "abc"})
        self.assertEqual(bad.status_code, 200)
        self.assertEqual(h.get("/health/visits").status_code, 200)
        self.assertEqual(h.get(f"/health/visits?from={today}&to={today}&service=Immunization&q=bcg").status_code, 200)
        self.assertIn(b"BCG", h.get("/health/patients/1").data)

    def test_patient_from_resident(self):
        self.make_verified_resident()
        h = self.login("health1")
        self.assertIn(b"Cruz", h.get("/health/patients/new?rq=cru").data)
        page = h.get("/health/patients/new?resident_id=1")
        self.assertIn(b'value="Juan"', page.data)
        data = self.patient_data(first_name="Juan", last_name="Cruz", birthdate="1990-01-02")
        data["resident_id"] = "1"
        self.assertEqual(self.post(h, "/health/patients/new", data).status_code, 302)
        again = self.post(h, "/health/patients/new", data)
        self.assertIn(b"already has a patient record", again.data)

    def test_patient_validation(self):
        h = self.login("health1")
        r = self.post(h, "/health/patients/new", self.patient_data(birthdate="2999-01-01", contact_no="12"))
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"valid birthdate", r.data)


class ReportsAdminTests(Base):
    def test_reports_search_export(self):
        self.make_verified_resident()
        h = self.login("health1")
        self.post(h, "/health/patients/new", dict(first_name="Pedro", middle_name="", last_name="Santos",
                  birthdate="2015-05-05", sex="Male", contact_no="", address="", guardian_name="", blood_type="",
                  allergies="", notes=""))
        today = date.today().isoformat()
        self.post(h, "/health/visits/new", {"patient_id": "1", "visit_date": today, "service_type": "Consultation",
                  "purpose": "=cmd|' /C calc'!A0"})
        b = self.login("brgy1")
        for c, urls in ((b, ["/reports", "/search?q=juan", f"/reports?from={today}&to={today}",
                              "/reports/export/requests.csv"]),
                        (h, ["/reports", "/search?q=pedro", "/reports/export/visits.csv",
                             "/reports/export/appointments.csv"])):
            for u in urls:
                self.assertEqual(c.get(u).status_code, 200, u)
        self.assertEqual(b.get("/reports/export/visits.csv").status_code, 404)
        self.assertEqual(h.get("/reports/export/requests.csv").status_code, 404)
        csv_text = h.get("/reports/export/visits.csv").get_data(as_text=True)
        self.assertIn("'=cmd", csv_text)               # formula injection neutralised
        self.assertEqual(h.get("/search?q=a").status_code, 200)
        self.assertEqual(self.login("admin1").get("/reports").status_code, 200)

    def test_admin_user_management(self):
        a = self.login("admin1")
        data = dict(username="nurse2", email="n2@x.ph", full_name="Nurse Two", role="health_staff", password="Staff1234")
        self.assertEqual(self.post(a, "/admin/users/new", data).status_code, 302)
        self.assertEqual(self.post(a, "/admin/users/new", data).status_code, 200)   # duplicate
        self.login("nurse2", "Staff1234")
        with self.app.app_context():
            uid = db.query("SELECT id FROM users WHERE username='nurse2'", one=True)["id"]
            me = db.query("SELECT id FROM users WHERE username='admin1'", one=True)["id"]
        self.assertEqual(a.get(f"/admin/users/{uid}").status_code, 200)
        r = self.post(a, f"/admin/users/{uid}", dict(email="n2@x.ph", full_name="Nurse Two", role="barangay_staff",
                      password="", ))                       # is_active unticked -> disabled
        self.assertEqual(r.status_code, 302)
        t = self.client()
        r = self.post(t, "/login", {"username": "nurse2", "password": "Staff1234"})
        self.assertEqual(r.status_code, 200)               # disabled account cannot log in
        # admin cannot deactivate self
        r = self.post(a, f"/admin/users/{me}", dict(email="admin1@x.ph", full_name="Admin1", role="admin"))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(a.get("/admin/users?q=nurse&role=barangay_staff").status_code, 200)
        self.assertEqual(a.get(f"/admin/users/{me}").status_code, 200)

    def test_services_admin(self):
        a = self.login("admin1")
        r = self.post(a, "/admin/services", {"name": "Business Permit Endorsement", "fee": "100",
                      "description": "Endorsement", "requires_document": "1"})
        self.assertEqual(r.status_code, 302)
        self.post(a, "/admin/services/1/toggle")
        with self.app.app_context():
            self.assertEqual(db.query("SELECT is_active FROM services WHERE id=1", one=True)["is_active"], 0)

    def test_errors(self):
        c = self.client()
        self.assertEqual(c.get("/nope").status_code, 404)
        a = self.login("admin1")
        self.assertEqual(a.get("/admin/users/9999").status_code, 404)
        self.assertEqual(a.get("/health/patients/9999").status_code, 404)

    def test_upload_too_large(self):
        c = self.make_verified_resident()
        big = io.BytesIO(PDF + b"0" * (6 * 1024 * 1024))
        r = c.post("/requests/new", data={"service_id": "1", "purpose": "For work", "csrf_token": "tok",
                   "documents": (big, "big.pdf")}, content_type="multipart/form-data")
        self.assertEqual(r.status_code, 413)


class SeedTests(unittest.TestCase):
    def test_schema_idempotent_and_services(self):
        tmp = tempfile.mkdtemp()
        try:
            cfg = {"TESTING": True, "SECRET_KEY": "x", "DATABASE": os.path.join(tmp, "a.db"),
                   "UPLOAD_FOLDER": os.path.join(tmp, "u")}
            app = create_app(cfg)
            app2 = create_app(cfg)                     # second start must not fail or duplicate data
            with app2.app_context():
                self.assertEqual(db.query("SELECT COUNT(*) c FROM services", one=True)["c"], 5)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
