"""Health center personnel: patients, appointments and queue, visits / health services."""
import sqlite3
from datetime import date

from flask import (Blueprint, abort, flash, g, redirect, render_template, request, url_for)

from . import db
from .auth import roles_required
from .utils import (APPT_STATUSES, APPT_TRANSITIONS, BLOOD_TYPES, BP_RE, PHONE_RE, SERVICE_TYPES,
                    SEX, TIME_RE, audit, like, parse_date)

bp = Blueprint("health", __name__, url_prefix="/health")
HEALTH = ("health_staff",)           # the admin is always allowed as well


@bp.route("/")
@roles_required(*HEALTH)
def dashboard():
    today = date.today().isoformat()
    month = today[:7]
    appt_counts = {r["status"]: r["c"] for r in db.query(
        "SELECT status, COUNT(*) AS c FROM appointments WHERE appointment_date = ? "
        "GROUP BY status", (today,))}
    queue = db.query(
        "SELECT a.*, p.first_name, p.last_name, p.patient_no FROM appointments a "
        "JOIN patients p ON p.id = a.patient_id WHERE a.appointment_date = ? "
        "AND a.status IN ('Scheduled','Waiting','In Consultation') ORDER BY a.queue_no", (today,))
    total_patients = db.query("SELECT COUNT(*) AS c FROM patients", one=True)["c"]
    visits_month = db.query("SELECT COUNT(*) AS c FROM visits WHERE substr(visit_date,1,7) = ?",
                            (month,), one=True)["c"]
    return render_template("health/dashboard.html", appt_counts=appt_counts, queue=queue,
                           total_patients=total_patients, visits_month=visits_month)


# ------------------------------------------------------------------- patients
@bp.route("/patients")
@roles_required(*HEALTH)
def patients():
    q = (request.args.get("q") or "").strip()
    sql = "SELECT * FROM patients"
    args = []
    if q:
        sql += (" WHERE first_name LIKE ? ESCAPE '\\' OR last_name LIKE ? ESCAPE '\\'"
                " OR patient_no LIKE ? ESCAPE '\\' OR contact_no LIKE ? ESCAPE '\\'")
        args = [like(q)] * 4
    rows = db.query(sql + " ORDER BY last_name, first_name LIMIT 200", args)
    return render_template("health/patients.html", rows=rows, q=q)


PATIENT_FIELDS = ["first_name", "middle_name", "last_name", "birthdate", "sex", "contact_no",
                  "address", "guardian_name", "blood_type", "allergies", "notes"]


def _read_patient_form():
    return {k: (request.form.get(k) or "").strip() for k in PATIENT_FIELDS}


def _validate_patient(d):
    errors = []
    if not d["first_name"] or not d["last_name"]:
        errors.append("First name and last name are required.")
    born = parse_date(d["birthdate"])
    if born is None or born > date.today():
        errors.append("Please enter a valid birthdate.")
    if d["sex"] not in SEX:
        errors.append("Please choose a sex.")
    if d["contact_no"] and not PHONE_RE.match(d["contact_no"]):
        errors.append("Contact number must look like 09123456789 or +639123456789.")
    if d["blood_type"] and d["blood_type"] not in BLOOD_TYPES:
        errors.append("Invalid blood type.")
    for key, limit in (("first_name", 50), ("middle_name", 50), ("last_name", 50),
                       ("address", 200), ("guardian_name", 100), ("allergies", 300),
                       ("notes", 1000)):
        if len(d[key]) > limit:
            errors.append(f"{key.replace('_', ' ').capitalize()} is too long (max {limit}).")
    return errors


@bp.route("/patients/new", methods=["GET", "POST"])
@roles_required(*HEALTH)
def patient_new():
    form = {}
    resident_id = request.values.get("resident_id", type=int)
    found = []
    # Optional: search registered residents and pre-fill the form from one of them.
    rq = (request.args.get("rq") or "").strip()
    if rq:
        found = db.query(
            "SELECT id, first_name, last_name, birthdate FROM residents WHERE is_verified = 1 AND "
            "(first_name LIKE ? ESCAPE '\\' OR last_name LIKE ? ESCAPE '\\') "
            "ORDER BY last_name LIMIT 10", (like(rq), like(rq)))
    if request.method == "GET" and resident_id:
        res = db.query("SELECT * FROM residents WHERE id = ?", (resident_id,), one=True)
        if res is None:
            abort(404)
        form = {"first_name": res["first_name"], "middle_name": res["middle_name"] or "",
                "last_name": res["last_name"], "birthdate": res["birthdate"], "sex": res["sex"],
                "contact_no": res["contact_no"], "address": res["address"]}
    if request.method == "POST":
        form = _read_patient_form()
        errors = _validate_patient(form)
        if resident_id and db.query("SELECT 1 FROM patients WHERE resident_id = ?",
                                    (resident_id,), one=True):
            errors.append("This resident already has a patient record.")
        if errors:
            for e in errors:
                flash(e, "danger")
        else:
            conn = db.get_db()
            cur = conn.execute(
                "INSERT INTO patients (resident_id, first_name, middle_name, last_name, birthdate,"
                " sex, contact_no, address, guardian_name, blood_type, allergies, notes, created_by)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (resident_id, form["first_name"], form["middle_name"], form["last_name"],
                 form["birthdate"], form["sex"], form["contact_no"], form["address"],
                 form["guardian_name"], form["blood_type"], form["allergies"], form["notes"],
                 g.user["id"]))
            pid = cur.lastrowid
            conn.execute("UPDATE patients SET patient_no = ? WHERE id = ?", (f"PT-{pid:05d}", pid))
            audit("patient_create", f"Patient #{pid}", commit=False)
            conn.commit()
            flash("Patient record created.", "success")
            return redirect(url_for("health.patient_detail", patient_id=pid))
    return render_template("health/patient_form.html", form=form, editing=False, found=found,
                           rq=rq, resident_id=resident_id, sex_options=SEX,
                           blood_types=BLOOD_TYPES)


def _get_patient(patient_id):
    p = db.query("SELECT * FROM patients WHERE id = ?", (patient_id,), one=True)
    if p is None:
        abort(404)
    return p


@bp.route("/patients/<int:patient_id>")
@roles_required(*HEALTH)
def patient_detail(patient_id):
    p = _get_patient(patient_id)
    visits = db.query("SELECT v.*, u.full_name AS attended_name FROM visits v "
                      "LEFT JOIN users u ON u.id = v.attended_by WHERE v.patient_id = ? "
                      "ORDER BY v.visit_date DESC, v.id DESC", (patient_id,))
    appts = db.query("SELECT * FROM appointments WHERE patient_id = ? "
                     "ORDER BY appointment_date DESC, queue_no DESC LIMIT 20", (patient_id,))
    return render_template("health/patient_detail.html", p=p, visits=visits, appts=appts)


@bp.route("/patients/<int:patient_id>/edit", methods=["GET", "POST"])
@roles_required(*HEALTH)
def patient_edit(patient_id):
    p = _get_patient(patient_id)
    form = dict(p)
    if request.method == "POST":
        form = _read_patient_form()
        errors = _validate_patient(form)
        if errors:
            for e in errors:
                flash(e, "danger")
        else:
            db.execute(
                "UPDATE patients SET first_name=?, middle_name=?, last_name=?, birthdate=?, sex=?,"
                " contact_no=?, address=?, guardian_name=?, blood_type=?, allergies=?, notes=?"
                " WHERE id=?",
                (form["first_name"], form["middle_name"], form["last_name"], form["birthdate"],
                 form["sex"], form["contact_no"], form["address"], form["guardian_name"],
                 form["blood_type"], form["allergies"], form["notes"], patient_id))
            audit("patient_edit", f"Patient #{patient_id}")
            flash("Patient record updated.", "success")
            return redirect(url_for("health.patient_detail", patient_id=patient_id))
    return render_template("health/patient_form.html", form=form, editing=True, p=p, found=[],
                           rq="", resident_id=None, sex_options=SEX, blood_types=BLOOD_TYPES)


# ---------------------------------------------------------------- appointments
@bp.route("/appointments")
@roles_required(*HEALTH)
def appointments():
    day = parse_date(request.args.get("date")) or date.today()
    status = request.args.get("status", "")
    sql = ("SELECT a.*, p.first_name, p.last_name, p.patient_no FROM appointments a "
           "JOIN patients p ON p.id = a.patient_id WHERE a.appointment_date = ?")
    args = [day.isoformat()]
    if status in APPT_STATUSES:
        sql += " AND a.status = ?"
        args.append(status)
    rows = db.query(sql + " ORDER BY a.queue_no", args)
    return render_template("health/appointments.html", rows=rows, day=day.isoformat(),
                           status=status, statuses=APPT_STATUSES, transitions=APPT_TRANSITIONS)


@bp.route("/appointments/new", methods=["GET", "POST"])
@roles_required(*HEALTH)
def appointment_new():
    patient_id = request.values.get("patient_id", type=int)
    patient = None
    found = []
    pq = (request.args.get("pq") or "").strip()
    if patient_id:
        patient = _get_patient(patient_id)
    elif pq:
        found = db.query(
            "SELECT id, patient_no, first_name, last_name, birthdate FROM patients WHERE "
            "first_name LIKE ? ESCAPE '\\' OR last_name LIKE ? ESCAPE '\\' "
            "OR patient_no LIKE ? ESCAPE '\\' ORDER BY last_name LIMIT 10",
            (like(pq), like(pq), like(pq)))
    form = {"appointment_date": date.today().isoformat(), "service_type": SERVICE_TYPES[0]}
    if request.method == "POST" and patient is not None:
        form = {"appointment_date": (request.form.get("appointment_date") or "").strip(),
                "appointment_time": (request.form.get("appointment_time") or "").strip(),
                "service_type": request.form.get("service_type", ""),
                "notes": (request.form.get("notes") or "").strip()}
        errors = []
        day = parse_date(form["appointment_date"])
        if day is None or day < date.today():
            errors.append("Please choose today or a future date.")
        if form["service_type"] not in SERVICE_TYPES:
            errors.append("Please choose a health service.")
        if form["appointment_time"] and not TIME_RE.match(form["appointment_time"]):
            errors.append("Invalid time.")
        if len(form["notes"]) > 300:
            errors.append("Notes are too long (max 300).")
        if errors:
            for e in errors:
                flash(e, "danger")
        else:
            for _ in range(3):        # retry in the rare case two people book at the same moment
                nxt = db.query("SELECT COALESCE(MAX(queue_no), 0) + 1 AS n FROM appointments "
                               "WHERE appointment_date = ?", (form["appointment_date"],),
                               one=True)["n"]
                try:
                    db.execute(
                        "INSERT INTO appointments (patient_id, service_type, appointment_date,"
                        " appointment_time, queue_no, notes, created_by) VALUES (?,?,?,?,?,?,?)",
                        (patient["id"], form["service_type"], form["appointment_date"],
                         form["appointment_time"] or None, nxt, form["notes"], g.user["id"]))
                except sqlite3.IntegrityError:
                    continue
                audit("appointment_create", f"Patient #{patient['id']} on "
                      f"{form['appointment_date']} queue {nxt}")
                flash(f"Appointment booked. Queue number: {nxt}.", "success")
                return redirect(url_for("health.appointments", date=form["appointment_date"]))
            flash("Could not assign a queue number. Please try again.", "danger")
    return render_template("health/appointment_form.html", patient=patient, found=found, pq=pq,
                           form=form, service_types=SERVICE_TYPES)


@bp.route("/appointments/<int:appt_id>/status", methods=["POST"])
@roles_required(*HEALTH)
def appointment_status(appt_id):
    a = db.query("SELECT * FROM appointments WHERE id = ?", (appt_id,), one=True)
    if a is None:
        abort(404)
    new = request.form.get("status", "")
    if new not in APPT_TRANSITIONS[a["status"]]:
        flash(f"Cannot change a {a['status']} appointment to '{new}'.", "danger")
    else:
        db.execute("UPDATE appointments SET status = ? WHERE id = ?", (new, appt_id))
        audit("appointment_status", f"Appointment #{appt_id} -> {new}")
        flash(f"Appointment marked as {new}.", "success")
    return redirect(url_for("health.appointments", date=a["appointment_date"]))


# ---------------------------------------------------------------------- visits
@bp.route("/visits")
@roles_required(*HEALTH)
def visits():
    start = parse_date(request.args.get("from"))
    end = parse_date(request.args.get("to"))
    service = request.args.get("service", "")
    q = (request.args.get("q") or "").strip()
    sql = ("SELECT v.*, p.first_name, p.last_name, p.patient_no FROM visits v "
           "JOIN patients p ON p.id = v.patient_id WHERE 1=1")
    args = []
    if start:
        sql += " AND v.visit_date >= ?"
        args.append(start.isoformat())
    if end:
        sql += " AND v.visit_date <= ?"
        args.append(end.isoformat())
    if service in SERVICE_TYPES:
        sql += " AND v.service_type = ?"
        args.append(service)
    if q:
        sql += (" AND (p.first_name LIKE ? ESCAPE '\\' OR p.last_name LIKE ? ESCAPE '\\'"
                " OR v.purpose LIKE ? ESCAPE '\\' OR v.services_provided LIKE ? ESCAPE '\\')")
        args += [like(q)] * 4
    rows = db.query(sql + " ORDER BY v.visit_date DESC, v.id DESC LIMIT 200", args)
    return render_template("health/visits.html", rows=rows, start=start.isoformat() if start else "",
                           end=end.isoformat() if end else "", service=service, q=q,
                           service_types=SERVICE_TYPES)


@bp.route("/visits/new", methods=["GET", "POST"])
@roles_required(*HEALTH)
def visit_new():
    patient_id = request.values.get("patient_id", type=int)
    if not patient_id:
        flash("Choose a patient first, then record the visit.", "warning")
        return redirect(url_for("health.patients"))
    patient = _get_patient(patient_id)
    appt_id = request.values.get("appointment_id", type=int)
    appt = None
    if appt_id:
        appt = db.query("SELECT * FROM appointments WHERE id = ? AND patient_id = ?",
                        (appt_id, patient_id), one=True)
    form = {"visit_date": date.today().isoformat(),
            "service_type": appt["service_type"] if appt else SERVICE_TYPES[0]}
    if request.method == "POST":
        form = {k: (request.form.get(k) or "").strip() for k in
                ("visit_date", "service_type", "purpose", "services_provided", "findings",
                 "blood_pressure", "temperature", "weight_kg", "follow_up_date")}
        errors = []
        vdate = parse_date(form["visit_date"])
        if vdate is None or vdate > date.today():
            errors.append("Visit date must be today or earlier.")
        if form["service_type"] not in SERVICE_TYPES:
            errors.append("Please choose a health service.")
        if not (3 <= len(form["purpose"]) <= 300):
            errors.append("Purpose of visit must be 3-300 characters.")
        if len(form["services_provided"]) > 1000 or len(form["findings"]) > 1000:
            errors.append("Services provided / findings are too long (max 1000).")
        if form["blood_pressure"] and not BP_RE.match(form["blood_pressure"]):
            errors.append("Blood pressure must look like 120/80.")
        temp = weight = None
        try:
            if form["temperature"]:
                temp = float(form["temperature"])
                if not 30 <= temp <= 45:
                    errors.append("Temperature must be between 30 and 45 C.")
            if form["weight_kg"]:
                weight = float(form["weight_kg"])
                if not 0.3 <= weight <= 400:
                    errors.append("Weight must be between 0.3 and 400 kg.")
        except ValueError:
            errors.append("Temperature and weight must be numbers.")
        follow = None
        if form["follow_up_date"]:
            follow = parse_date(form["follow_up_date"])
            if follow is None:
                errors.append("Invalid follow-up date.")
        if errors:
            for e in errors:
                flash(e, "danger")
        else:
            conn = db.get_db()
            conn.execute(
                "INSERT INTO visits (patient_id, appointment_id, visit_date, service_type, purpose,"
                " services_provided, findings, blood_pressure, temperature, weight_kg,"
                " follow_up_date, attended_by) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (patient_id, appt["id"] if appt else None, form["visit_date"],
                 form["service_type"], form["purpose"], form["services_provided"],
                 form["findings"], form["blood_pressure"] or None, temp, weight,
                 follow.isoformat() if follow else None, g.user["id"]))
            if appt and appt["status"] in ("Scheduled", "Waiting", "In Consultation"):
                conn.execute("UPDATE appointments SET status='Completed' WHERE id = ?", (appt["id"],))
            audit("visit_record", f"Patient #{patient_id} - {form['service_type']}", commit=False)
            conn.commit()
            flash("Visit recorded.", "success")
            return redirect(url_for("health.patient_detail", patient_id=patient_id))
    return render_template("health/visit_form.html", patient=patient, appt=appt, form=form,
                           service_types=SERVICE_TYPES)
