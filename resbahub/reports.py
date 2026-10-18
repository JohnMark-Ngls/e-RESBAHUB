"""Reports (summaries + CSV export) and global search."""
import csv
import io
from datetime import date

from flask import Blueprint, Response, abort, g, render_template, request

from . import db
from .auth import roles_required
from .utils import audit, like, parse_date

bp = Blueprint("reports", __name__)
STAFF = ("barangay_staff", "health_staff")        # the admin is always allowed as well


def _range():
    today = date.today()
    start = parse_date(request.args.get("from")) or today.replace(day=1)
    end = parse_date(request.args.get("to")) or today
    if start > end:
        start, end = end, start
    return start.isoformat(), end.isoformat()


def _can_barangay():
    return g.user["role"] in ("barangay_staff", "admin")


def _can_health():
    return g.user["role"] in ("health_staff", "admin")


@bp.route("/reports")
@roles_required(*STAFF)
def reports():
    start, end = _range()
    rng = (start, end)
    data = {}
    if _can_barangay():
        data["req_status"] = db.query(
            "SELECT status, COUNT(*) AS c FROM requests WHERE date(created_at) BETWEEN ? AND ? "
            "GROUP BY status ORDER BY c DESC", rng)
        data["req_service"] = db.query(
            "SELECT s.name, COUNT(*) AS c FROM requests r JOIN services s ON s.id = r.service_id "
            "WHERE date(r.created_at) BETWEEN ? AND ? GROUP BY s.name ORDER BY c DESC", rng)
        data["req_total"] = sum(r["c"] for r in data["req_status"])
        data["new_residents"] = db.query(
            "SELECT COUNT(*) AS c FROM residents WHERE date(created_at) BETWEEN ? AND ?",
            rng, one=True)["c"]
        data["verified"] = db.query("SELECT COUNT(*) AS c FROM residents WHERE is_verified = 1",
                                    one=True)["c"]
        data["unverified"] = db.query("SELECT COUNT(*) AS c FROM residents WHERE is_verified = 0",
                                      one=True)["c"]
    if _can_health():
        data["visit_service"] = db.query(
            "SELECT service_type, COUNT(*) AS c FROM visits WHERE visit_date BETWEEN ? AND ? "
            "GROUP BY service_type ORDER BY c DESC", rng)
        data["visit_total"] = sum(r["c"] for r in data["visit_service"])
        data["unique_patients"] = db.query(
            "SELECT COUNT(DISTINCT patient_id) AS c FROM visits WHERE visit_date BETWEEN ? AND ?",
            rng, one=True)["c"]
        data["appt_status"] = db.query(
            "SELECT status, COUNT(*) AS c FROM appointments WHERE appointment_date BETWEEN ? AND ? "
            "GROUP BY status ORDER BY c DESC", rng)
        data["new_patients"] = db.query(
            "SELECT COUNT(*) AS c FROM patients WHERE date(created_at) BETWEEN ? AND ?",
            rng, one=True)["c"]
    if g.user["role"] == "admin":
        data["activity"] = db.query(
            "SELECT action, COUNT(*) AS c FROM audit_log WHERE date(created_at) BETWEEN ? AND ? "
            "GROUP BY action ORDER BY c DESC", rng)
    return render_template("reports.html", start=start, end=end, d=data,
                           can_barangay=_can_barangay(), can_health=_can_health())


def _safe_cell(value):
    """Stop spreadsheet formula injection when the CSV is opened in Excel."""
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@"):
        return "'" + value
    return value


@bp.route("/reports/export/<kind>.csv")
@roles_required(*STAFF)
def export_csv(kind):
    start, end = _range()
    if kind == "requests" and _can_barangay():
        header = ["Reference", "Service", "Resident", "Status", "Remarks", "Submitted", "Updated"]
        rows = db.query(
            "SELECT r.reference_no, s.name, res.first_name || ' ' || res.last_name, r.status, "
            "COALESCE(r.remarks,''), r.created_at, r.updated_at FROM requests r "
            "JOIN services s ON s.id = r.service_id JOIN residents res ON res.id = r.resident_id "
            "WHERE date(r.created_at) BETWEEN ? AND ? ORDER BY r.id", (start, end))
    elif kind == "visits" and _can_health():
        header = ["Date", "Patient No", "Patient", "Service", "Purpose", "Services Provided",
                  "BP", "Temp (C)", "Weight (kg)"]
        rows = db.query(
            "SELECT v.visit_date, p.patient_no, p.first_name || ' ' || p.last_name, v.service_type, "
            "v.purpose, COALESCE(v.services_provided,''), COALESCE(v.blood_pressure,''), "
            "COALESCE(v.temperature,''), COALESCE(v.weight_kg,'') FROM visits v "
            "JOIN patients p ON p.id = v.patient_id WHERE v.visit_date BETWEEN ? AND ? "
            "ORDER BY v.visit_date, v.id", (start, end))
    elif kind == "appointments" and _can_health():
        header = ["Date", "Time", "Queue No", "Patient No", "Patient", "Service", "Status"]
        rows = db.query(
            "SELECT a.appointment_date, COALESCE(a.appointment_time,''), a.queue_no, p.patient_no, "
            "p.first_name || ' ' || p.last_name, a.service_type, a.status FROM appointments a "
            "JOIN patients p ON p.id = a.patient_id WHERE a.appointment_date BETWEEN ? AND ? "
            "ORDER BY a.appointment_date, a.queue_no", (start, end))
    else:
        abort(404)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(header)
    for row in rows:
        writer.writerow([_safe_cell(v) for v in tuple(row)])
    audit("report_export", f"{kind} {start} to {end}")
    return Response("\ufeff" + buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment; filename={kind}_{start}_to_{end}.csv"})


@bp.route("/search")
@roles_required(*STAFF)
def search():
    q = (request.args.get("q") or "").strip()
    results = {}
    if len(q) >= 2:
        p = like(q)
        if _can_barangay():
            results["residents"] = db.query(
                "SELECT res.id, res.first_name, res.last_name, res.contact_no, res.is_verified "
                "FROM residents res JOIN users u ON u.id = res.user_id WHERE "
                "res.first_name LIKE ? ESCAPE '\\' OR res.last_name LIKE ? ESCAPE '\\' "
                "OR u.username LIKE ? ESCAPE '\\' OR res.contact_no LIKE ? ESCAPE '\\' "
                "ORDER BY res.last_name LIMIT 25", (p, p, p, p))
            results["requests"] = db.query(
                "SELECT r.id, r.reference_no, r.status, s.name AS service_name, res.first_name, "
                "res.last_name FROM requests r JOIN services s ON s.id = r.service_id "
                "JOIN residents res ON res.id = r.resident_id WHERE r.reference_no LIKE ? ESCAPE '\\' "
                "OR res.first_name LIKE ? ESCAPE '\\' OR res.last_name LIKE ? ESCAPE '\\' "
                "ORDER BY r.id DESC LIMIT 25", (p, p, p))
        if _can_health():
            results["patients"] = db.query(
                "SELECT * FROM patients WHERE first_name LIKE ? ESCAPE '\\' OR last_name LIKE ? ESCAPE '\\' "
                "OR patient_no LIKE ? ESCAPE '\\' OR contact_no LIKE ? ESCAPE '\\' "
                "ORDER BY last_name LIMIT 25", (p, p, p, p))
            results["visits"] = db.query(
                "SELECT v.id, v.visit_date, v.service_type, v.purpose, p.id AS patient_id, "
                "p.first_name, p.last_name FROM visits v JOIN patients p ON p.id = v.patient_id "
                "WHERE p.first_name LIKE ? ESCAPE '\\' OR p.last_name LIKE ? ESCAPE '\\' "
                "OR v.purpose LIKE ? ESCAPE '\\' OR v.services_provided LIKE ? ESCAPE '\\' "
                "ORDER BY v.visit_date DESC LIMIT 25", (p, p, p, p))
            results["appointments"] = db.query(
                "SELECT a.id, a.appointment_date, a.queue_no, a.status, a.service_type, "
                "p.first_name, p.last_name FROM appointments a JOIN patients p ON p.id = a.patient_id "
                "WHERE p.first_name LIKE ? ESCAPE '\\' OR p.last_name LIKE ? ESCAPE '\\' "
                "OR a.appointment_date LIKE ? ESCAPE '\\' ORDER BY a.appointment_date DESC LIMIT 25",
                (p, p, p))
    return render_template("search.html", q=q, results=results, searched=len(q) >= 2)
