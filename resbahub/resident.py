"""Resident-facing pages: dashboard, profile, barangay requests, tracking, announcements,
notifications, and the shared request-detail / document-download pages."""

from datetime import date

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    g,
    redirect,
    render_template,
    request,
    send_from_directory,
    url_for,
)
from mysql.connector import IntegrityError

from . import db
from .auth import login_required, roles_required
from .presence import get_on_site_personnel
from .utils import (
    ACTIVE_REQUEST_STATUSES,
    ANNOUNCEMENT_CATEGORIES,
    CIVIL_STATUS,
    EMAIL_RE,
    REQUEST_STATUSES,
    REQUEST_TRANSITIONS,
    SEX,
    audit,
    display_name,
    read_resident_form,
    save_upload,
    upload_problem,
    validate_resident,
)

bp = Blueprint("resident", __name__)

MAX_FILES = 3


def get_resident():
    """Return the resident profile belonging to the logged-in user."""
    row = db.query(
        "SELECT * FROM residents WHERE user_id = ?",
        (g.user["id"],),
        one=True,
    )

    if row is None:
        abort(403)

    return row


@bp.route("/dashboard")
@roles_required("resident", admin=False)
def dashboard():
    resident = get_resident()

    counts = {
        row["status"]: row["c"]
        for row in db.query(
            """
            SELECT status, COUNT(*) AS c
            FROM requests
            WHERE resident_id = ?
            GROUP BY status
            """,
            (resident["id"],),
        )
    }

    recent = db.query(
        """
        SELECT r.id, r.reference_no, r.status, r.created_at,
               s.name AS service_name
        FROM requests r
        JOIN services s ON s.id = r.service_id
        WHERE r.resident_id = ?
        ORDER BY r.id DESC
        LIMIT 5
        """,
        (resident["id"],),
    )

    announcements = db.query(
        """
        SELECT *
        FROM announcements
        ORDER BY created_at DESC, id DESC
        LIMIT 3
        """
    )
    on_site_personnel = get_on_site_personnel()
    available_medicines = db.query(
        """
        SELECT name
        FROM medicine_inventory
        WHERE is_active = 1 AND stock_quantity > 0
        ORDER BY name
        """
    )

    return render_template(
        "resident/dashboard.html",
        resident=resident,
        counts=counts,
        recent=recent,
        announcements=announcements,
        on_site_personnel=on_site_personnel,
        available_medicines=available_medicines,
    )


@bp.route("/profile", methods=["GET", "POST"])
@roles_required("resident", admin=False)
def profile():
    resident = get_resident()
    unlocked = not resident["is_verified"]

    user = db.query(
        "SELECT email FROM users WHERE id = ?",
        (g.user["id"],),
        one=True,
    )

    form = dict(resident)
    form["email"] = user["email"]

    if request.method == "POST":
        data = read_resident_form(request.form)

        if not unlocked:
            for key in (
                "first_name",
                "middle_name",
                "last_name",
                "suffix",
                "birthdate",
                "sex",
            ):
                data[key] = resident[key] or ""

        data["email"] = (request.form.get("email") or "").strip()

        errors = validate_resident(data, identity=unlocked)

        if not EMAIL_RE.match(data["email"]):
            errors.append("Please enter a valid email address.")
        elif db.query(
            "SELECT 1 FROM users WHERE email = ? AND id != ?",
            (data["email"], g.user["id"]),
            one=True,
        ):
            errors.append("That email is already used by another account.")

        if errors:
            for error in errors:
                flash(error, "danger")

            form.update(data)
        else:
            conn = db.get_db()
            cursor = conn.cursor()

            try:
                cursor.execute(
                    """
                    UPDATE residents
                    SET first_name = %s,
                        middle_name = %s,
                        last_name = %s,
                        suffix = %s,
                        birthdate = %s,
                        sex = %s,
                        civil_status = %s,
                        contact_no = %s,
                        address = %s,
                        purok = %s,
                        occupation = %s
                    WHERE id = %s
                    """,
                    (
                        data["first_name"],
                        data["middle_name"],
                        data["last_name"],
                        data["suffix"],
                        data["birthdate"],
                        data["sex"],
                        data["civil_status"],
                        data["contact_no"],
                        data["address"],
                        data["purok"],
                        data["occupation"],
                        resident["id"],
                    ),
                )

                cursor.execute(
                    """
                    UPDATE users
                    SET email = %s, full_name = %s
                    WHERE id = %s
                    """,
                    (
                        data["email"],
                        display_name(
                            data["first_name"],
                            data["middle_name"],
                            data["last_name"],
                            data["suffix"],
                        ),
                        g.user["id"],
                    ),
                )

                audit(
                    "profile_update",
                    "Resident updated own profile",
                    commit=False,
                )

                conn.commit()

            except Exception:
                conn.rollback()
                raise
            finally:
                cursor.close()

            flash("Profile updated.", "success")
            return redirect(url_for("resident.profile"))

    return render_template(
        "resident/profile.html",
        resident=resident,
        form=form,
        unlocked=unlocked,
        sex_options=SEX,
        civil_options=CIVIL_STATUS,
    )


# ------------------------------------------------------------------- requests

@bp.route("/requests")
@roles_required("resident", admin=False)
def my_requests():
    resident = get_resident()
    status = request.args.get("status", "")

    sql = (
        "SELECT r.id, r.reference_no, r.status, r.created_at, "
        "r.updated_at, r.remarks, s.name AS service_name "
        "FROM requests r "
        "JOIN services s ON s.id = r.service_id "
        "WHERE r.resident_id = ?"
    )

    args = [resident["id"]]

    if status in REQUEST_STATUSES:
        sql += " AND r.status = ?"
        args.append(status)

    rows = db.query(sql + " ORDER BY r.id DESC", args)

    return render_template(
        "resident/requests.html",
        rows=rows,
        status=status,
        statuses=REQUEST_STATUSES,
    )


@bp.route("/requests/new", methods=["GET", "POST"])
@roles_required("resident", admin=False)
def new_request():
    resident = get_resident()

    if (
        current_app.config["REQUIRE_VERIFIED_FOR_REQUESTS"]
        and not resident["is_verified"]
    ):
        flash(
            "Your account must be verified by barangay personnel before you "
            "can submit requests. Please wait for verification or visit the "
            "barangay hall.",
            "warning",
        )
        return redirect(url_for("resident.dashboard"))

    services = db.query(
        "SELECT * FROM services WHERE is_active = 1 ORDER BY name"
    )

    form = {}

    if request.method == "POST":
        form = {
            "service_id": (request.form.get("service_id") or "").strip(),
            "purpose": (request.form.get("purpose") or "").strip(),
        }

        service = None

        if form["service_id"].isdigit():
            service = db.query(
                "SELECT * FROM services WHERE id = ? AND is_active = 1",
                (int(form["service_id"]),),
                one=True,
            )

        files = [
            file
            for file in request.files.getlist("documents")
            if file and file.filename
        ]

        errors = []

        if service is None:
            errors.append("Please choose a service.")

        if not (5 <= len(form["purpose"]) <= 500):
            errors.append("Purpose must be between 5 and 500 characters.")

        if len(files) > MAX_FILES:
            errors.append(f"You can upload at most {MAX_FILES} files.")

        if service is not None and service["requires_document"] and not files:
            errors.append(
                f"{service['name']} needs at least one supporting document "
                "(for example a valid ID or proof of residency)."
            )

        for file in files:
            problem = upload_problem(file)
            if problem:
                errors.append(problem)

        if service is not None and not errors:
            placeholders = ",".join(["?"] * len(ACTIVE_REQUEST_STATUSES))

            active_request = db.query(
                f"""
                SELECT 1
                FROM requests
                WHERE resident_id = ?
                  AND service_id = ?
                  AND status IN ({placeholders})
                """,
                (
                    resident["id"],
                    service["id"],
                    *ACTIVE_REQUEST_STATUSES,
                ),
                one=True,
            )

            if active_request:
                errors.append(
                    "You already have an active request for this service. "
                    "Please wait for it to be processed."
                )

        if errors:
            for error in errors:
                flash(error, "danger")
        else:
            conn = db.get_db()
            cursor = conn.cursor()

            try:
                cursor.execute(
                    """
                    INSERT INTO requests (resident_id, service_id, purpose)
                    VALUES (%s, %s, %s)
                    """,
                    (
                        resident["id"],
                        service["id"],
                        form["purpose"],
                    ),
                )

                request_id = cursor.lastrowid
                reference = f"REQ-{date.today().year}-{request_id:05d}"

                cursor.execute(
                    """
                    UPDATE requests
                    SET reference_no = %s
                    WHERE id = %s
                    """,
                    (reference, request_id),
                )

                cursor.execute(
                    """
                    INSERT INTO request_history
                        (request_id, status, remarks, changed_by)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (
                        request_id,
                        "Pending",
                        "Request submitted",
                        g.user["id"],
                    ),
                )

                for file in files:
                    original_name = (
                        file.filename.replace("\\", "/").split("/")[-1][:120]
                    )

                    cursor.execute(
                        """
                        INSERT INTO request_documents
                            (request_id, original_name, stored_name)
                        VALUES (%s, %s, %s)
                        """,
                        (
                            request_id,
                            original_name,
                            save_upload(file),
                        ),
                    )

                audit(
                    "request_submit",
                    f"{reference} - {service['name']}",
                    commit=False,
                )

                conn.commit()

            except Exception:
                conn.rollback()
                raise
            finally:
                cursor.close()

            flash(
                f"Request submitted. Your reference number is {reference}.",
                "success",
            )

            return redirect(
                url_for(
                    "resident.request_detail",
                    request_id=request_id,
                )
            )

    return render_template(
        "resident/request_new.html",
        services=services,
        form=form,
        max_files=MAX_FILES,
    )


def _load_request(request_id):
    row = db.query(
        """
        SELECT r.*, s.name AS service_name, s.fee,
               res.user_id AS owner_user_id,
               res.first_name, res.middle_name, res.last_name,
               res.suffix, res.contact_no, res.address, res.is_verified,
               u.full_name AS processed_by_name
        FROM requests r
        JOIN services s ON s.id = r.service_id
        JOIN residents res ON res.id = r.resident_id
        LEFT JOIN users u ON u.id = r.processed_by
        WHERE r.id = ?
        """,
        (request_id,),
        one=True,
    )

    if row is None:
        abort(404)

    role = g.user["role"]

    if role == "resident":
        if row["owner_user_id"] != g.user["id"]:
            abort(404)
    elif role not in ("barangay_staff", "admin"):
        abort(403)

    return row


@bp.route("/requests/<int:request_id>")
@login_required
def request_detail(request_id):
    row = _load_request(request_id)

    docs = db.query(
        "SELECT * FROM request_documents WHERE request_id = ? ORDER BY id",
        (request_id,),
    )

    history = db.query(
        """
        SELECT h.*, u.full_name AS who
        FROM request_history h
        LEFT JOIN users u ON u.id = h.changed_by
        WHERE h.request_id = ?
        ORDER BY h.id DESC
        """,
        (request_id,),
    )

    is_staff = g.user["role"] in ("barangay_staff", "admin")

    return render_template(
        "resident/request_detail.html",
        r=row,
        docs=docs,
        history=history,
        is_staff=is_staff,
        next_statuses=REQUEST_TRANSITIONS[row["status"]],
    )


@bp.route("/requests/<int:request_id>/cancel", methods=["POST"])
@roles_required("resident", admin=False)
def cancel_request(request_id):
    row = _load_request(request_id)

    if row["status"] != "Pending":
        flash("Only pending requests can be cancelled.", "warning")
    else:
        conn = db.get_db()
        cursor = conn.cursor()

        try:
            cursor.execute(
                """
                UPDATE requests
                SET status = 'Cancelled', updated_at = NOW()
                WHERE id = %s
                """,
                (request_id,),
            )

            cursor.execute(
                """
                INSERT INTO request_history
                    (request_id, status, remarks, changed_by)
                VALUES (%s, %s, %s, %s)
                """,
                (
                    request_id,
                    "Cancelled",
                    "Cancelled by resident",
                    g.user["id"],
                ),
            )

            audit(
                "request_cancel",
                row["reference_no"],
                commit=False,
            )

            conn.commit()

        except Exception:
            conn.rollback()
            raise
        finally:
            cursor.close()

        flash("Request cancelled.", "info")

    return redirect(
        url_for("resident.request_detail", request_id=request_id)
    )


@bp.route("/documents/<int:doc_id>")
@login_required
def download_document(doc_id):
    doc = db.query(
        "SELECT * FROM request_documents WHERE id = ?",
        (doc_id,),
        one=True,
    )

    if doc is None:
        abort(404)

    _load_request(doc["request_id"])

    return send_from_directory(
        current_app.config["UPLOAD_FOLDER"],
        doc["stored_name"],
        as_attachment=True,
        download_name=doc["original_name"],
    )


# -------------------------------------------------- announcements / notifications

@bp.route("/announcements")
@login_required
def announcements():
    category = request.args.get("category", "")

    sql = (
        "SELECT a.*, u.full_name AS author "
        "FROM announcements a "
        "LEFT JOIN users u ON u.id = a.posted_by"
    )

    args = []

    if category in ANNOUNCEMENT_CATEGORIES:
        sql += " WHERE a.category = ?"
        args.append(category)

    rows = db.query(
        sql + " ORDER BY a.created_at DESC, a.id DESC LIMIT 100",
        args,
    )

    return render_template(
        "resident/announcements.html",
        rows=rows,
        category=category,
        categories=ANNOUNCEMENT_CATEGORIES,
    )


@bp.route("/notifications")
@roles_required("resident", admin=False)
def notifications():
    rows = list(
        db.query(
            """
            SELECT *
            FROM notifications
            WHERE user_id = ?
            ORDER BY id DESC
            LIMIT 50
            """,
            (g.user["id"],),
        )
    )

    db.execute(
        "UPDATE notifications SET is_read = 1 WHERE user_id = ?",
        (g.user["id"],),
    )

    return render_template(
        "resident/notifications.html",
        rows=rows,
    )