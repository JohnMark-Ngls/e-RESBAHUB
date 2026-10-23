"""Administrator: users, services and the audit log."""

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
from werkzeug.security import generate_password_hash

from . import db
from .auth import roles_required
from .presence import get_user_presence
from .utils import (
    EMAIL_RE,
    ROLE_LABELS,
    USERNAME_RE,
    audit,
    like,
    password_problem,
)

bp = Blueprint("admin", __name__, url_prefix="/admin")

STAFF_CHOICES = ["barangay_staff", "health_staff", "admin"]


@bp.route("/")
@roles_required()
def dashboard():
    by_role = {
        row["role"]: row["c"]
        for row in db.query(
            """
            SELECT role, COUNT(*) AS c
            FROM users
            WHERE is_active = 1
            GROUP BY role
            """
        )
    }

    inactive = db.query(
        "SELECT COUNT(*) AS c FROM users WHERE is_active = 0",
        one=True,
    )["c"]

    recent = db.query(
        """
        SELECT a.*, u.username
        FROM audit_log a
        LEFT JOIN users u ON u.id = a.user_id
        ORDER BY a.id DESC
        LIMIT 10
        """
    )

    return render_template(
        "admin/dashboard.html",
        by_role=by_role,
        inactive=inactive,
        recent=recent,
        is_on_site=get_user_presence(g.user["id"]),
    )


@bp.route("/users")
@roles_required()
def users():
    q = (request.args.get("q") or "").strip()
    role = request.args.get("role", "")

    sql = "SELECT * FROM users WHERE 1=1"
    args = []

    if role in ROLE_LABELS:
        sql += " AND role = ?"
        args.append(role)

    if q:
        sql += (
            " AND (username LIKE ?"
            " OR full_name LIKE ?"
            " OR email LIKE ?"
            " OR position_title LIKE ?)"
        )
        args.extend([like(q)] * 4)

    rows = db.query(
        sql + " ORDER BY role, full_name LIMIT 300",
        args,
    )

    return render_template(
        "admin/users.html",
        rows=rows,
        q=q,
        role=role,
        roles=ROLE_LABELS,
    )


@bp.route("/users/new", methods=["GET", "POST"])
@roles_required()
def user_new():
    form = {"role": "barangay_staff", "position_title": ""}

    if request.method == "POST":
        form = {
            key: (request.form.get(key) or "").strip()
            for key in (
                "username",
                "email",
                "full_name",
                "position_title",
                "role",
            )
        }

        password = request.form.get("password") or ""
        errors = []

        if not USERNAME_RE.fullmatch(form["username"]):
            errors.append(
                "Username must be 4-30 characters: "
                "letters, numbers, dot or underscore."
            )

        if not EMAIL_RE.fullmatch(form["email"]):
            errors.append("Please enter a valid email.")

        if not (2 <= len(form["full_name"]) <= 100):
            errors.append("Full name must be 2-100 characters.")

        if form["role"] not in STAFF_CHOICES:
            errors.append("Please choose an access level.")

        if not form["position_title"] or len(form["position_title"]) > 100:
            errors.append("Enter a role or position title up to 100 characters.")

        problem = password_problem(password)
        if problem:
            errors.append(problem)

        if not errors:
            username_exists = db.query(
                "SELECT 1 FROM users WHERE username = ?",
                (form["username"],),
                one=True,
            )

            email_exists = db.query(
                "SELECT 1 FROM users WHERE email = ?",
                (form["email"],),
                one=True,
            )

            if username_exists or email_exists:
                errors.append("That username or email already exists.")

        if errors:
            for error in errors:
                flash(error, "danger")
        else:
            try:
                db.execute(
                    """
                    INSERT INTO users (
                        username, email, full_name, position_title,
                        password_hash, role
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        form["username"],
                        form["email"],
                        form["full_name"],
                        form["position_title"],
                        generate_password_hash(password),
                        form["role"],
                    ),
                )

                audit(
                    "user_create",
                    f"{form['username']} ({form['position_title']}; access: {form['role']})",
                )

                flash("User account created.", "success")
                return redirect(url_for("admin.users"))

            except IntegrityError:
                db.rollback()
                flash(
                    "That username or email already exists.",
                    "danger",
                )

    return render_template(
        "admin/user_form.html",
        form=form,
        editing=False,
        is_self=False,
        choice_pairs=[
            (choice, ROLE_LABELS[choice])
            for choice in STAFF_CHOICES
        ],
        roles=ROLE_LABELS,
    )


@bp.route("/users/<int:user_id>", methods=["GET", "POST"])
@roles_required()
def user_edit(user_id):
    user = db.query(
        "SELECT * FROM users WHERE id = ?",
        (user_id,),
        one=True,
    )

    if user is None:
        abort(404)

    is_self = user["id"] == g.user["id"]
    form = dict(user)

    if request.method == "POST":
        form = {
            "email": (request.form.get("email") or "").strip(),
            "full_name": (request.form.get("full_name") or "").strip(),
            "position_title": (
                request.form.get(
                    "position_title",
                    user.get("position_title") or "",
                ) or ""
            ).strip(),
            "role": request.form.get("role", user["role"]),
            "is_active": 1 if request.form.get("is_active") else 0,
        }

        new_password = request.form.get("password") or ""
        errors = []

        if not EMAIL_RE.fullmatch(form["email"]):
            errors.append("Please enter a valid email.")

        if not (2 <= len(form["full_name"]) <= 100):
            errors.append("Full name must be 2-100 characters.")

        if user["role"] == "resident":
            form["role"] = "resident"
        elif form["role"] not in STAFF_CHOICES:
            errors.append("Please choose an access level.")

        if len(form["position_title"]) > 100:
            errors.append("Role or position title must be 100 characters or fewer.")

        if is_self and (
            not form["is_active"] or form["role"] != user["role"]
        ):
            errors.append(
                "You cannot deactivate your own account "
                "or change your own role."
            )

        if new_password:
            problem = password_problem(new_password)
            if problem:
                errors.append(problem)

        email_exists = db.query(
            "SELECT 1 FROM users WHERE email = ? AND id != ?",
            (form["email"], user_id),
            one=True,
        )

        if email_exists:
            errors.append("That email is used by another account.")

        if errors:
            for error in errors:
                flash(error, "danger")
        else:
            conn = db.get_db()
            cursor = conn.cursor()

            try:
                cursor.execute(
                    """
                    UPDATE users
                    SET email = %s,
                        full_name = %s,
                        position_title = NULLIF(%s, ''),
                        role = %s,
                        is_active = %s
                    WHERE id = %s
                    """,
                    (
                        form["email"],
                        form["full_name"],
                        form["position_title"],
                        form["role"],
                        form["is_active"],
                        user_id,
                    ),
                )

                if new_password:
                    cursor.execute(
                        """
                        UPDATE users
                        SET password_hash = %s
                        WHERE id = %s
                        """,
                        (
                            generate_password_hash(new_password),
                            user_id,
                        ),
                    )

                audit(
                    "user_edit",
                    (
                        f"{user['username']} (password reset)"
                        if new_password
                        else user["username"]
                    ),
                    commit=False,
                )

                conn.commit()

            except IntegrityError:
                conn.rollback()
                flash(
                    "That email is already used by another account.",
                    "danger",
                )
                return render_template(
                    "admin/user_form.html",
                    form=form,
                    editing=True,
                    u=user,
                    is_self=is_self,
                    choice_pairs=[
                        (choice, ROLE_LABELS[choice])
                        for choice in STAFF_CHOICES
                    ],
                    roles=ROLE_LABELS,
                )

            except Exception:
                conn.rollback()
                raise

            finally:
                cursor.close()

            flash("User updated.", "success")
            return redirect(url_for("admin.users"))

    return render_template(
        "admin/user_form.html",
        form=form,
        editing=True,
        u=user,
        is_self=is_self,
        choice_pairs=[
            (choice, ROLE_LABELS[choice])
            for choice in STAFF_CHOICES
        ],
        roles=ROLE_LABELS,
    )


@bp.route("/users/<int:user_id>/delete", methods=["POST"])
@roles_required()
def user_delete(user_id):
    user = db.query(
        "SELECT id, username, full_name, role, is_active FROM users WHERE id = ?",
        (user_id,),
        one=True,
    )

    if user is None or user["role"] == "resident":
        abort(404)

    if user["id"] == g.user["id"]:
        flash("You cannot delete your own account.", "danger")
        return redirect(url_for("admin.users"))

    if user["role"] == "admin" and user["is_active"]:
        active_admins = db.query(
            """
            SELECT COUNT(*) AS c
            FROM users
            WHERE role = 'admin' AND is_active = 1
            """,
            one=True,
        )["c"]
        if active_admins <= 1:
            flash("You cannot delete the last active administrator.", "danger")
            return redirect(url_for("admin.users"))

    conn = db.get_db()
    cursor = conn.cursor()

    try:
        audit(
            "user_delete",
            f"Deleted {user['username']} ({user['full_name']}; {user['role']})",
            commit=False,
        )
        cursor.execute("DELETE FROM users WHERE id = %s", (user_id,))
        if cursor.rowcount != 1:
            raise RuntimeError("The selected user could not be deleted.")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()

    flash(f"Account {user['username']} was deleted.", "success")
    return redirect(url_for("admin.users"))


@bp.route("/services", methods=["GET", "POST"])
@roles_required()
def services():
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        description = (request.form.get("description") or "").strip()
        requires_document = (
            1 if request.form.get("requires_document") else 0
        )

        try:
            fee = float(request.form.get("fee") or 0)
        except (TypeError, ValueError):
            fee = -1

        if (
            not (3 <= len(name) <= 80)
            or fee < 0
            or len(description) > 300
        ):
            flash(
                "Enter a service name (3-80 characters), "
                "a valid fee and a short description.",
                "danger",
            )
        else:
            try:
                db.execute(
                    """
                    INSERT INTO services (
                        name, description, requires_document, fee
                    )
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        name,
                        description,
                        requires_document,
                        fee,
                    ),
                )

                audit("service_create", name)
                flash("Service added.", "success")

            except IntegrityError:
                db.rollback()
                flash(
                    "A service with that name already exists.",
                    "danger",
                )

        return redirect(url_for("admin.services"))

    rows = db.query(
        "SELECT * FROM services ORDER BY is_active DESC, name"
    )

    return render_template("admin/services.html", rows=rows)


@bp.route("/services/<int:service_id>/toggle", methods=["POST"])
@roles_required()
def service_toggle(service_id):
    service = db.query(
        "SELECT * FROM services WHERE id = ?",
        (service_id,),
        one=True,
    )

    if service is None:
        abort(404)

    db.execute(
        "UPDATE services SET is_active = ? WHERE id = ?",
        (
            0 if service["is_active"] else 1,
            service_id,
        ),
    )

    audit("service_toggle", service["name"])

    flash(
        f"{service['name']} is now "
        f"{'disabled' if service['is_active'] else 'active'}.",
        "info",
    )

    return redirect(url_for("admin.services"))


@bp.route("/audit")
@roles_required()
def audit_log():
    rows = db.query(
        """
        SELECT a.*, u.username
        FROM audit_log a
        LEFT JOIN users u ON u.id = a.user_id
        ORDER BY a.id DESC
        LIMIT 300
        """
    )

    return render_template("admin/audit.html", rows=rows)