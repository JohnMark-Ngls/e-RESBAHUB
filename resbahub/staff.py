"""Barangay personnel: dashboard, request processing, resident verification, announcements."""

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

from . import db
from .auth import roles_required
from .presence import get_user_presence
from .utils import (
    ANNOUNCEMENT_CATEGORIES,
    CIVIL_STATUS,
    REQUEST_STATUSES,
    REQUEST_TRANSITIONS,
    SEX,
    audit,
    display_name,
    like,
    notify,
    read_resident_form,
    validate_resident,
)

bp = Blueprint("staff", __name__, url_prefix="/staff")

BARANGAY = ("barangay_staff",)


@bp.route("/")
@roles_required(*BARANGAY)
def dashboard():
    counts = {
        row["status"]: row["c"]
        for row in db.query(
            "SELECT status, COUNT(*) AS c FROM requests GROUP BY status"
        )
    }

    unverified = db.query(
        "SELECT COUNT(*) AS c FROM residents WHERE is_verified = 0",
        one=True,
    )["c"]

    total_residents = db.query(
        "SELECT COUNT(*) AS c FROM residents",
        one=True,
    )["c"]

    pending = db.query(
        """
        SELECT r.id, r.reference_no, r.created_at,
               s.name AS service_name,
               res.first_name, res.last_name
        FROM requests r
        JOIN services s ON s.id = r.service_id
        JOIN residents res ON res.id = r.resident_id
        WHERE r.status = 'Pending'
        ORDER BY r.id
        LIMIT 10
        """
    )

    return render_template(
        "staff/dashboard.html",
        counts=counts,
        unverified=unverified,
        total_residents=total_residents,
        pending=pending,
        is_on_site=get_user_presence(g.user["id"]),
    )


@bp.route("/requests")
@roles_required(*BARANGAY)
def requests_list():
    status = request.args.get("status", "")
    q = (request.args.get("q") or "").strip()

    sql = """
        SELECT r.id, r.reference_no, r.status, r.created_at,
               s.name AS service_name,
               res.first_name, res.last_name
        FROM requests r
        JOIN services s ON s.id = r.service_id
        JOIN residents res ON res.id = r.resident_id
        WHERE 1 = 1
    """

    args = []

    if status in REQUEST_STATUSES:
        sql += " AND r.status = ?"
        args.append(status)

    if q:
        sql += """
            AND (
                r.reference_no LIKE ? OR
                res.first_name LIKE ? OR
                res.last_name LIKE ? OR
                s.name LIKE ?
            )
        """
        args.extend([like(q)] * 4)

    rows = db.query(sql + " ORDER BY r.id DESC LIMIT 200", args)

    return render_template(
        "staff/requests.html",
        rows=rows,
        status=status,
        q=q,
        statuses=REQUEST_STATUSES,
    )


@bp.route("/requests/<int:request_id>/update", methods=["POST"])
@roles_required(*BARANGAY)
def update_request(request_id):
    row = db.query(
        """
        SELECT r.*, res.user_id AS owner_user_id
        FROM requests r
        JOIN residents res ON res.id = r.resident_id
        WHERE r.id = ?
        """,
        (request_id,),
        one=True,
    )

    if row is None:
        abort(404)

    new_status = request.form.get("status", "")
    remarks = (request.form.get("remarks") or "").strip()

    if new_status not in REQUEST_TRANSITIONS[row["status"]]:
        flash(
            f"A {row['status']} request cannot be changed to '{new_status}'.",
            "danger",
        )
    elif new_status == "Rejected" and not remarks:
        flash(
            "Please write a remark explaining why the request is rejected.",
            "danger",
        )
    elif len(remarks) > 500:
        flash("Remarks are too long (max 500 characters).", "danger")
    else:
        conn = db.get_db()
        cursor = conn.cursor()

        try:
            cursor.execute(
                """
                UPDATE requests
                SET status = %s,
                    remarks = %s,
                    processed_by = %s,
                    updated_at = NOW()
                WHERE id = %s
                """,
                (
                    new_status,
                    remarks or row["remarks"],
                    g.user["id"],
                    request_id,
                ),
            )

            cursor.execute(
                """
                INSERT INTO request_history
                    (request_id, status, remarks, changed_by)
                VALUES (%s, %s, %s, %s)
                """,
                (
                    request_id,
                    new_status,
                    remarks,
                    g.user["id"],
                ),
            )

            message = (
                f"Your request {row['reference_no']} is now {new_status}."
            )

            if remarks:
                message += f" Remarks: {remarks}"

            notify(
                row["owner_user_id"],
                message,
                url_for("resident.request_detail", request_id=request_id),
                commit=False,
            )

            audit(
                "request_update",
                f"{row['reference_no']} -> {new_status}",
                commit=False,
            )

            conn.commit()

        except Exception:
            conn.rollback()
            raise
        finally:
            cursor.close()

        flash(f"Request marked as {new_status}.", "success")

    return redirect(
        url_for("resident.request_detail", request_id=request_id)
    )


# ------------------------------------------------------------------ residents

@bp.route("/residents")
@roles_required(*BARANGAY)
def residents():
    q = (request.args.get("q") or "").strip()
    flt = request.args.get("verified", "")

    sql = """
        SELECT res.*, u.username, u.is_active
        FROM residents res
        JOIN users u ON u.id = res.user_id
        WHERE 1 = 1
    """

    args = []

    if flt in ("0", "1"):
        sql += " AND res.is_verified = ?"
        args.append(int(flt))

    if q:
        sql += """
            AND (
                res.first_name LIKE ? OR
                res.last_name LIKE ? OR
                u.username LIKE ? OR
                res.contact_no LIKE ?
            )
        """
        args.extend([like(q)] * 4)

    rows = db.query(
        sql + """
            ORDER BY res.is_verified, res.last_name, res.first_name
            LIMIT 200
        """,
        args,
    )

    return render_template(
        "staff/residents.html",
        rows=rows,
        q=q,
        flt=flt,
    )


@bp.route("/residents/<int:resident_id>", methods=["GET", "POST"])
@roles_required(*BARANGAY)
def resident_edit(resident_id):
    res = db.query(
        """
        SELECT res.*, u.username, u.email
        FROM residents res
        JOIN users u ON u.id = res.user_id
        WHERE res.id = ?
        """,
        (resident_id,),
        one=True,
    )

    if res is None:
        abort(404)

    form = dict(res)

    if request.method == "POST":
        data = read_resident_form(request.form)
        errors = validate_resident(data)

        if errors:
            for error in errors:
                flash(error, "danger")

            form.update(data)
        else:
            verify = 1 if request.form.get("is_verified") else 0
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
                        resident_id,
                    ),
                )

                cursor.execute(
                    """
                    UPDATE users
                    SET full_name = %s
                    WHERE id = %s
                    """,
                    (
                        display_name(
                            data["first_name"],
                            data["middle_name"],
                            data["last_name"],
                            data["suffix"],
                        ),
                        res["user_id"],
                    ),
                )

                if verify and not res["is_verified"]:
                    cursor.execute(
                        """
                        UPDATE residents
                        SET is_verified = 1,
                            verified_by = %s,
                            verified_at = NOW()
                        WHERE id = %s
                        """,
                        (g.user["id"], resident_id),
                    )

                    notify(
                        res["user_id"],
                        "Your account has been verified. You can now submit "
                        "barangay requests online.",
                        url_for("resident.new_request"),
                        commit=False,
                    )

                    audit(
                        "resident_verify",
                        f"Verified resident #{resident_id}",
                        commit=False,
                    )

                elif not verify and res["is_verified"]:
                    cursor.execute(
                        """
                        UPDATE residents
                        SET is_verified = 0,
                            verified_by = NULL,
                            verified_at = NULL
                        WHERE id = %s
                        """,
                        (resident_id,),
                    )

                    audit(
                        "resident_unverify",
                        f"Removed verification of resident #{resident_id}",
                        commit=False,
                    )

                audit(
                    "resident_edit",
                    f"Edited resident #{resident_id}",
                    commit=False,
                )

                conn.commit()

            except Exception:
                conn.rollback()
                raise
            finally:
                cursor.close()

            flash("Resident record saved.", "success")
            return redirect(url_for("staff.residents"))

    stats = db.query(
        "SELECT COUNT(*) AS c FROM requests WHERE resident_id = ?",
        (resident_id,),
        one=True,
    )

    return render_template(
        "staff/resident_edit.html",
        res=res,
        form=form,
        total_requests=stats["c"],
        sex_options=SEX,
        civil_options=CIVIL_STATUS,
    )


# -------------------------------------------------------------- announcements

@bp.route("/announcements", methods=["GET", "POST"])
@roles_required(*BARANGAY)
def announcements():
    form = {"category": "Announcement"}

    if request.method == "POST":
        form = {
            "title": (request.form.get("title") or "").strip(),
            "body": (request.form.get("body") or "").strip(),
            "category": request.form.get("category", ""),
        }

        errors = []

        if not (3 <= len(form["title"]) <= 120):
            errors.append("Title must be 3-120 characters.")

        if not (5 <= len(form["body"]) <= 2000):
            errors.append("Message must be 5-2000 characters.")

        if form["category"] not in ANNOUNCEMENT_CATEGORIES:
            errors.append("Please choose a category.")

        if errors:
            for error in errors:
                flash(error, "danger")
        else:
            db.execute(
                """
                INSERT INTO announcements (title, body, category, posted_by)
                VALUES (?, ?, ?, ?)
                """,
                (
                    form["title"],
                    form["body"],
                    form["category"],
                    g.user["id"],
                ),
            )

            audit("announcement_post", form["title"])

            flash("Announcement published.", "success")
            return redirect(url_for("staff.announcements"))

    rows = db.query(
        """
        SELECT a.*, u.full_name AS author
        FROM announcements a
        LEFT JOIN users u ON u.id = a.posted_by
        ORDER BY a.created_at DESC, a.id DESC
        LIMIT 100
        """
    )

    return render_template(
        "staff/announcements.html",
        rows=rows,
        form=form,
        categories=ANNOUNCEMENT_CATEGORIES,
    )


@bp.route("/announcements/<int:ann_id>/delete", methods=["POST"])
@roles_required(*BARANGAY)
def delete_announcement(ann_id):
    row = db.query(
        "SELECT title FROM announcements WHERE id = ?",
        (ann_id,),
        one=True,
    )

    if row is None:
        abort(404)

    db.execute(
        "DELETE FROM announcements WHERE id = ?",
        (ann_id,),
    )

    audit("announcement_delete", row["title"])

    flash("Announcement deleted.", "info")

    return redirect(url_for("staff.announcements"))