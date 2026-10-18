
"""Health center personnel: patients, appointments, queue, visits and health services."""

from datetime import date
import math

from flask import (
    Blueprint,
    abort,
    flash,
    g,
    redirect,
    render_template,
    request,
    url_for,
)
from mysql.connector import IntegrityError

from . import db
from .auth import roles_required
from .utils import (
    APPT_STATUSES,
    APPT_TRANSITIONS,
    BLOOD_TYPES,
    BP_RE,
    PHONE_RE,
    SERVICE_TYPES,
    SEX,
    TIME_RE,
    audit,
    like,
    parse_date,
)

bp = Blueprint("health", __name__, url_prefix="/health")
HEALTH = ("health_staff",)


@bp.route("/")
@roles_required(*HEALTH)
def dashboard():
    today = date.today().isoformat()
    month = today[:7]

    appt_counts = {
        row["status"]: row["c"]
        for row in db.query(
            """
            SELECT status, COUNT(*) AS c
            FROM appointments
            WHERE appointment_date = ?
            GROUP BY status
            """,
            (today,),
        )
    }

    queue = db.query(
        """
        SELECT a.*, p.first_name, p.last_name, p.patient_no
        FROM appointments a
        JOIN patients p ON p.id = a.patient_id
        WHERE a.appointment_date = ?
          AND a.status IN ('Scheduled', 'Waiting', 'In Consultation')
        ORDER BY a.queue_no
        """,
        (today,),
    )

    total_patients = db.query(
        "SELECT COUNT(*) AS c FROM patients",
        one=True,
    )["c"]

    visits_month = db.query(
        """
        SELECT COUNT(*) AS c
        FROM visits
        WHERE DATE_FORMAT(visit_date, '%Y-%m') = ?
        """,
        (month,),
        one=True,
    )["c"]

    return render_template(
        "health/dashboard.html",
        appt_counts=appt_counts,
        queue=queue,
        total_patients=total_patients,
        visits_month=visits_month,
    )


# Patients

@bp.route("/patients")
@roles_required(*HEALTH)
def patients():
    q = (request.args.get("q") or "").strip()
    sql = "SELECT * FROM patients"
    args = []

    if q:
        sql += """
            WHERE first_name LIKE ?
               OR last_name LIKE ?
               OR patient_no LIKE ?
               OR contact_no LIKE ?
        """
        args = [like(q)] * 4

    rows = db.query(
        sql + " ORDER BY last_name, first_name LIMIT 200",
        args,
    )

    return render_template("health/patients.html", rows=rows, q=q)


PATIENT_FIELDS = [
    "first_name",
    "middle_name",
    "last_name",
    "birthdate",
    "sex",
    "contact_no",
    "address",
    "guardian_name",
    "blood_type",
    "allergies",
    "notes",
]


def _read_patient_form():
    return {
        key: (request.form.get(key) or "").strip()
        for key in PATIENT_FIELDS
    }


def _validate_patient(data):
    errors = []

    if not data["first_name"] or not data["last_name"]:
        errors.append("First name and last name are required.")

    born = parse_date(data["birthdate"])

    if born is None or born > date.today():
        errors.append("Please enter a valid birthdate.")

    if data["sex"] not in SEX:
        errors.append("Please choose a sex.")

    if data["contact_no"] and not PHONE_RE.match(data["contact_no"]):
        errors.append(
            "Contact number must look like 09123456789 or +639123456789."
        )

    if data["blood_type"] and data["blood_type"] not in BLOOD_TYPES:
        errors.append("Invalid blood type.")

    limits = (
        ("first_name", 50),
        ("middle_name", 50),
        ("last_name", 50),
        ("address", 200),
        ("guardian_name", 100),
        ("allergies", 300),
        ("notes", 1000),
    )

    for key, limit in limits:
        if len(data[key]) > limit:
            errors.append(
                f"{key.replace('_', ' ').capitalize()} "
                f"is too long (max {limit})."
            )

    return errors


def _render_patient_form(
    form,
    *,
    editing=False,
    patient=None,
    found=None,
    rq="",
    resident_id=None,
):
    return render_template(
        "health/patient_form.html",
        form=form,
        editing=editing,
        p=patient,
        found=found or [],
        rq=rq,
        resident_id=resident_id,
        sex_options=SEX,
        blood_types=BLOOD_TYPES,
    )


@bp.route("/patients/new", methods=["GET", "POST"])
@roles_required(*HEALTH)
def patient_new():
    form = {}
    resident_id = request.values.get("resident_id", type=int)
    found = []
    rq = (request.args.get("rq") or "").strip()

    if rq:
        found = db.query(
            """
            SELECT id, first_name, last_name, birthdate
            FROM residents
            WHERE is_verified = 1
              AND (
                  first_name LIKE ?
                  OR last_name LIKE ?
              )
            ORDER BY last_name
            LIMIT 10
            """,
            (like(rq), like(rq)),
        )

    if request.method == "GET" and resident_id:
        resident = db.query(
            "SELECT * FROM residents WHERE id = ?",
            (resident_id,),
            one=True,
        )

        if resident is None:
            abort(404)

        existing_patient = db.query(
            "SELECT id FROM patients WHERE resident_id = ?",
            (resident_id,),
            one=True,
        )

        if existing_patient:
            flash("This resident already has a patient record.", "warning")
            return redirect(
                url_for(
                    "health.patient_detail",
                    patient_id=existing_patient["id"],
                )
            )

        form = {
            "first_name": resident["first_name"],
            "middle_name": resident["middle_name"] or "",
            "last_name": resident["last_name"],
            "birthdate": resident["birthdate"],
            "sex": resident["sex"],
            "contact_no": resident["contact_no"] or "",
            "address": resident["address"] or "",
        }

    if request.method == "POST":
        form = _read_patient_form()
        errors = []

        if resident_id and not db.query(
            "SELECT id FROM residents WHERE id = ? AND is_verified = 1",
            (resident_id,),
            one=True,
        ):
            errors.append("Choose a valid verified resident.")

        errors.extend(_validate_patient(form))

        if resident_id and db.query(
            "SELECT 1 FROM patients WHERE resident_id = ?",
            (resident_id,),
            one=True,
        ):
            errors.append("This resident already has a patient record.")

        if errors:
            for error in errors:
                flash(error, "danger")
        else:
            conn = db.get_db()
            cursor = conn.cursor()

            try:
                cursor.execute(
                    """
                    INSERT INTO patients (
                        resident_id, first_name, middle_name, last_name,
                        birthdate, sex, contact_no, address, guardian_name,
                        blood_type, allergies, notes, created_by
                    )
                    VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                    )
                    """,
                    (
                        resident_id,
                        form["first_name"],
                        form["middle_name"] or None,
                        form["last_name"],
                        form["birthdate"],
                        form["sex"],
                        form["contact_no"] or None,
                        form["address"] or None,
                        form["guardian_name"] or None,
                        form["blood_type"] or None,
                        form["allergies"] or None,
                        form["notes"] or None,
                        g.user["id"],
                    ),
                )

                patient_id = cursor.lastrowid

                cursor.execute(
                    "UPDATE patients SET patient_no = %s WHERE id = %s",
                    (f"PT-{patient_id:05d}", patient_id),
                )

                audit(
                    "patient_create",
                    f"Patient #{patient_id}",
                    commit=False,
                )

                conn.commit()

            except IntegrityError:
                conn.rollback()
                flash(
                    "Could not create the patient record. "
                    "The resident may already have a patient record.",
                    "danger",
                )
                return _render_patient_form(
                    form,
                    found=found,
                    rq=rq,
                    resident_id=resident_id,
                )

            except Exception:
                conn.rollback()
                raise

            finally:
                cursor.close()

            flash("Patient record created.", "success")
            return redirect(
                url_for("health.patient_detail", patient_id=patient_id)
            )

    return _render_patient_form(
        form,
        found=found,
        rq=rq,
        resident_id=resident_id,
    )


def _get_patient(patient_id):
    patient = db.query(
        "SELECT * FROM patients WHERE id = ?",
        (patient_id,),
        one=True,
    )

    if patient is None:
        abort(404)

    return patient


@bp.route("/patients/<int:patient_id>")
@roles_required(*HEALTH)
def patient_detail(patient_id):
    patient = _get_patient(patient_id)

    visits = db.query(
        """
        SELECT v.*, u.full_name AS attended_name
        FROM visits v
        LEFT JOIN users u ON u.id = v.attended_by
        WHERE v.patient_id = ?
        ORDER BY v.visit_date DESC, v.id DESC
        """,
        (patient_id,),
    )

    appointments = db.query(
        """
        SELECT *
        FROM appointments
        WHERE patient_id = ?
        ORDER BY appointment_date DESC, queue_no DESC
        LIMIT 20
        """,
        (patient_id,),
    )

    return render_template(
        "health/patient_detail.html",
        p=patient,
        visits=visits,
        appts=appointments,
    )


@bp.route("/patients/<int:patient_id>/edit", methods=["GET", "POST"])
@roles_required(*HEALTH)
def patient_edit(patient_id):
    patient = _get_patient(patient_id)
    form = dict(patient)

    if request.method == "POST":
        form = _read_patient_form()
        errors = _validate_patient(form)

        if errors:
            for error in errors:
                flash(error, "danger")
        else:
            db.execute(
                """
                UPDATE patients
                SET first_name = ?, middle_name = ?, last_name = ?,
                    birthdate = ?, sex = ?, contact_no = ?, address = ?,
                    guardian_name = ?, blood_type = ?, allergies = ?, notes = ?
                WHERE id = ?
                """,
                (
                    form["first_name"],
                    form["middle_name"] or None,
                    form["last_name"],
                    form["birthdate"],
                    form["sex"],
                    form["contact_no"] or None,
                    form["address"] or None,
                    form["guardian_name"] or None,
                    form["blood_type"] or None,
                    form["allergies"] or None,
                    form["notes"] or None,
                    patient_id,
                ),
            )

            audit("patient_edit", f"Patient #{patient_id}")
            flash("Patient record updated.", "success")

            return redirect(
                url_for("health.patient_detail", patient_id=patient_id)
            )

    return _render_patient_form(
        form,
        editing=True,
        patient=patient,
    )


# Appointments

@bp.route("/appointments")
@roles_required(*HEALTH)
def appointments():
    day = parse_date(request.args.get("date")) or date.today()
    status = request.args.get("status", "")

    sql = """
        SELECT a.*, p.first_name, p.last_name, p.patient_no
        FROM appointments a
        JOIN patients p ON p.id = a.patient_id
        WHERE a.appointment_date = ?
    """
    args = [day.isoformat()]

    if status in APPT_STATUSES:
        sql += " AND a.status = ?"
        args.append(status)

    rows = db.query(sql + " ORDER BY a.queue_no", args)

    return render_template(
        "health/appointments.html",
        rows=rows,
        day=day.isoformat(),
        status=status,
        statuses=APPT_STATUSES,
        transitions=APPT_TRANSITIONS,
    )


@bp.route("/appointments/new", methods=["GET", "POST"])
@roles_required(*HEALTH)
def appointment_new():
    patient_id = request.values.get("patient_id", type=int)
    patient = _get_patient(patient_id) if patient_id else None
    found = []
    pq = (request.args.get("pq") or "").strip()

    if not patient_id and pq:
        found = db.query(
            """
            SELECT id, patient_no, first_name, last_name, birthdate
            FROM patients
            WHERE first_name LIKE ?
               OR last_name LIKE ?
               OR patient_no LIKE ?
            ORDER BY last_name
            LIMIT 10
            """,
            (like(pq), like(pq), like(pq)),
        )

    form = {
        "appointment_date": date.today().isoformat(),
        "service_type": SERVICE_TYPES[0],
    }

    if request.method == "POST":
        form = {
            "appointment_date": (
                request.form.get("appointment_date") or ""
            ).strip(),
            "appointment_time": (
                request.form.get("appointment_time") or ""
            ).strip(),
            "service_type": request.form.get("service_type", ""),
            "notes": (request.form.get("notes") or "").strip(),
        }

        errors = []
        day = parse_date(form["appointment_date"])

        if patient is None:
            errors.append("Choose a valid patient.")

        if day is None or day < date.today():
            errors.append("Please choose today or a future date.")

        if form["service_type"] not in SERVICE_TYPES:
            errors.append("Please choose a health service.")

        if (
            form["appointment_time"]
            and not TIME_RE.match(form["appointment_time"])
        ):
            errors.append("Invalid time.")

        if len(form["notes"]) > 300:
            errors.append("Notes are too long (max 300).")

        if errors:
            for error in errors:
                flash(error, "danger")
        else:
            booked = False

            for _ in range(3):
                next_queue = db.query(
                    """
                    SELECT COALESCE(MAX(queue_no), 0) + 1 AS n
                    FROM appointments
                    WHERE appointment_date = ?
                    """,
                    (form["appointment_date"],),
                    one=True,
                )["n"]

                try:
                    db.execute(
                        """
                        INSERT INTO appointments (
                            patient_id, service_type, appointment_date,
                            appointment_time, queue_no, notes, created_by
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            patient["id"],
                            form["service_type"],
                            form["appointment_date"],
                            form["appointment_time"] or None,
                            next_queue,
                            form["notes"] or None,
                            g.user["id"],
                        ),
                    )

                    audit(
                        "appointment_create",
                        f"Patient #{patient['id']} on "
                        f"{form['appointment_date']} queue {next_queue}",
                    )

                    flash(
                        f"Appointment booked. Queue number: {next_queue}.",
                        "success",
                    )

                    booked = True
                    break

                except IntegrityError:
                    db.rollback()

            if booked:
                return redirect(
                    url_for(
                        "health.appointments",
                        date=form["appointment_date"],
                    )
                )

            flash(
                "Could not assign a queue number. Please try again.",
                "danger",
            )

    return render_template(
        "health/appointment_form.html",
        patient=patient,
        found=found,
        pq=pq,
        form=form,
        service_types=SERVICE_TYPES,
    )


@bp.route("/appointments/<int:appt_id>/status", methods=["POST"])
@roles_required(*HEALTH)
def appointment_status(appt_id):
    appointment = db.query(
        "SELECT * FROM appointments WHERE id = ?",
        (appt_id,),
        one=True,
    )

    if appointment is None:
        abort(404)

    new_status = request.form.get("status", "")

    if new_status not in APPT_TRANSITIONS.get(appointment["status"], []):
        flash(
            f"Cannot change a {appointment['status']} appointment "
            f"to '{new_status}'.",
            "danger",
        )
    else:
        db.execute(
            "UPDATE appointments SET status = ? WHERE id = ?",
            (new_status, appt_id),
        )

        audit(
            "appointment_status",
            f"Appointment #{appt_id} -> {new_status}",
        )

        flash(f"Appointment marked as {new_status}.", "success")

    return redirect(
        url_for(
            "health.appointments",
            date=appointment["appointment_date"],
        )
    )


# Visits

@bp.route("/visits")
@roles_required(*HEALTH)
def visits():
    start = parse_date(request.args.get("from"))
    end = parse_date(request.args.get("to"))
    service = request.args.get("service", "")
    q = (request.args.get("q") or "").strip()

    sql = """
        SELECT v.*, p.first_name, p.last_name, p.patient_no
        FROM visits v
        JOIN patients p ON p.id = v.patient_id
        WHERE 1=1
    """
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
        sql += """
            AND (
                p.first_name LIKE ?
                OR p.last_name LIKE ?
                OR v.purpose LIKE ?
                OR v.services_provided LIKE ?
            )
        """
        args.extend([like(q)] * 4)

    rows = db.query(
        sql + " ORDER BY v.visit_date DESC, v.id DESC LIMIT 200",
        args,
    )

    return render_template(
        "health/visits.html",
        rows=rows,
        start=start.isoformat() if start else "",
        end=end.isoformat() if end else "",
        service=service,
        q=q,
        service_types=SERVICE_TYPES,
    )


@bp.route("/visits/new", methods=["GET", "POST"])
@roles_required(*HEALTH)
def visit_new():
    patient_id = request.values.get("patient_id", type=int)

    if not patient_id:
        flash("Choose a patient first, then record the visit.", "warning")
        return redirect(url_for("health.patients"))

    patient = _get_patient(patient_id)
    appointment_id = request.values.get("appointment_id", type=int)
    appointment = None

    if appointment_id:
        appointment = db.query(
            """
            SELECT *
            FROM appointments
            WHERE id = ? AND patient_id = ?
            """,
            (appointment_id, patient_id),
            one=True,
        )

        if appointment is None:
            abort(404)

    form = {
        "visit_date": date.today().isoformat(),
        "service_type": (
            appointment["service_type"]
            if appointment
            else SERVICE_TYPES[0]
        ),
    }

    if request.method == "POST":
        form = {
            key: (request.form.get(key) or "").strip()
            for key in (
                "visit_date",
                "service_type",
                "purpose",
                "services_provided",
                "findings",
                "blood_pressure",
                "temperature",
                "weight_kg",
                "follow_up_date",
            )
        }

        errors = []
        visit_date = parse_date(form["visit_date"])

        if visit_date is None or visit_date > date.today():
            errors.append("Visit date must be today or earlier.")

        if form["service_type"] not in SERVICE_TYPES:
            errors.append("Please choose a health service.")

        if not (3 <= len(form["purpose"]) <= 300):
            errors.append("Purpose of visit must be 3-300 characters.")

        if (
            len(form["services_provided"]) > 1000
            or len(form["findings"]) > 1000
        ):
            errors.append(
                "Services provided / findings are too long (max 1000)."
            )

        if form["blood_pressure"] and not BP_RE.match(
            form["blood_pressure"]
        ):
            errors.append("Blood pressure must look like 120/80.")

        temperature = None
        weight = None

        try:
            if form["temperature"]:
                temperature = float(form["temperature"])

                if not math.isfinite(temperature) or not 30 <= temperature <= 45:
                    errors.append("Temperature must be between 30 and 45 C.")

            if form["weight_kg"]:
                weight = float(form["weight_kg"])

                if not math.isfinite(weight) or not 0.3 <= weight <= 400:
                    errors.append("Weight must be between 0.3 and 400 kg.")

        except ValueError:
            errors.append("Temperature and weight must be numbers.")

        follow_up = None

        if form["follow_up_date"]:
            follow_up = parse_date(form["follow_up_date"])

            if follow_up is None:
                errors.append("Invalid follow-up date.")

        if errors:
            for error in errors:
                flash(error, "danger")
        else:
            conn = db.get_db()
            cursor = conn.cursor()

            try:
                cursor.execute(
                    """
                    INSERT INTO visits (
                        patient_id, appointment_id, visit_date, service_type,
                        purpose, services_provided, findings, blood_pressure,
                        temperature, weight_kg, follow_up_date, attended_by
                    )
                    VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                    )
                    """,
                    (
                        patient_id,
                        appointment["id"] if appointment else None,
                        form["visit_date"],
                        form["service_type"],
                        form["purpose"],
                        form["services_provided"] or None,
                        form["findings"] or None,
                        form["blood_pressure"] or None,
                        temperature,
                        weight,
                        follow_up.isoformat() if follow_up else None,
                        g.user["id"],
                    ),
                )

                if (
                    appointment
                    and appointment["status"]
                    in ("Scheduled", "Waiting", "In Consultation")
                ):
                    cursor.execute(
                        """
                        UPDATE appointments
                        SET status = 'Completed'
                        WHERE id = %s
                        """,
                        (appointment["id"],),
                    )

                audit(
                    "visit_record",
                    f"Patient #{patient_id} - {form['service_type']}",
                    commit=False,
                )

                conn.commit()

            except Exception:
                conn.rollback()
                raise

            finally:
                cursor.close()

            flash("Visit recorded.", "success")
            return redirect(
                url_for("health.patient_detail", patient_id=patient_id)
            )

    return render_template(
        "health/visit_form.html",
        patient=patient,
        appt=appointment,
        form=form,
        service_types=SERVICE_TYPES,
    )
