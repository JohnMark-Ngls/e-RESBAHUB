"""Administrator: users, services and the audit log."""
import sqlite3

from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for
from werkzeug.security import generate_password_hash

from . import db
from .auth import roles_required
from .utils import (EMAIL_RE, ROLE_LABELS, USERNAME_RE, audit, like, password_problem)

bp = Blueprint("admin", __name__, url_prefix="/admin")
STAFF_CHOICES = ["barangay_staff", "health_staff", "admin"]


@bp.route("/")
@roles_required()
def dashboard():
    by_role = {r["role"]: r["c"] for r in db.query(
        "SELECT role, COUNT(*) AS c FROM users WHERE is_active = 1 GROUP BY role")}
    inactive = db.query("SELECT COUNT(*) AS c FROM users WHERE is_active = 0", one=True)["c"]
    recent = db.query("SELECT a.*, u.username FROM audit_log a LEFT JOIN users u ON u.id = a.user_id "
                      "ORDER BY a.id DESC LIMIT 10")
    return render_template("admin/dashboard.html", by_role=by_role, inactive=inactive, recent=recent)


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
        sql += (" AND (username LIKE ? ESCAPE '\\' OR full_name LIKE ? ESCAPE '\\'"
                " OR email LIKE ? ESCAPE '\\')")
        args += [like(q)] * 3
    rows = db.query(sql + " ORDER BY role, full_name LIMIT 300", args)
    return render_template("admin/users.html", rows=rows, q=q, role=role, roles=ROLE_LABELS)


@bp.route("/users/new", methods=["GET", "POST"])
@roles_required()
def user_new():
    form = {"role": "barangay_staff"}
    if request.method == "POST":
        form = {k: (request.form.get(k) or "").strip() for k in ("username", "email", "full_name", "role")}
        password = request.form.get("password") or ""
        errors = []
        if not USERNAME_RE.match(form["username"]):
            errors.append("Username must be 4-30 characters: letters, numbers, dot or underscore.")
        if not EMAIL_RE.match(form["email"]):
            errors.append("Please enter a valid email.")
        if not (2 <= len(form["full_name"]) <= 100):
            errors.append("Full name must be 2-100 characters.")
        if form["role"] not in STAFF_CHOICES:
            errors.append("Please choose a role.")
        problem = password_problem(password)
        if problem:
            errors.append(problem)
        if not errors and (db.query("SELECT 1 FROM users WHERE username = ?", (form["username"],), one=True)
                           or db.query("SELECT 1 FROM users WHERE email = ?", (form["email"],), one=True)):
            errors.append("That username or email already exists.")
        if errors:
            for e in errors:
                flash(e, "danger")
        else:
            db.execute("INSERT INTO users (username, email, full_name, password_hash, role)"
                       " VALUES (?,?,?,?,?)",
                       (form["username"], form["email"], form["full_name"],
                        generate_password_hash(password), form["role"]))
            audit("user_create", f"{form['username']} ({form['role']})")
            flash("User account created.", "success")
            return redirect(url_for("admin.users"))
    return render_template("admin/user_form.html", form=form, editing=False, is_self=False,
                           choice_pairs=[(c, ROLE_LABELS[c]) for c in STAFF_CHOICES], roles=ROLE_LABELS)


@bp.route("/users/<int:user_id>", methods=["GET", "POST"])
@roles_required()
def user_edit(user_id):
    u = db.query("SELECT * FROM users WHERE id = ?", (user_id,), one=True)
    if u is None:
        abort(404)
    is_self = u["id"] == g.user["id"]
    form = dict(u)
    if request.method == "POST":
        form = {"email": (request.form.get("email") or "").strip(),
                "full_name": (request.form.get("full_name") or "").strip(),
                "role": request.form.get("role", u["role"]),
                "is_active": 1 if request.form.get("is_active") else 0}
        new_password = request.form.get("password") or ""
        errors = []
        if not EMAIL_RE.match(form["email"]):
            errors.append("Please enter a valid email.")
        if not (2 <= len(form["full_name"]) <= 100):
            errors.append("Full name must be 2-100 characters.")
        if u["role"] == "resident":
            form["role"] = "resident"            # resident accounts keep their role
        elif form["role"] not in STAFF_CHOICES:
            errors.append("Please choose a role.")
        if is_self and (not form["is_active"] or form["role"] != u["role"]):
            errors.append("You cannot deactivate your own account or change your own role.")
        if new_password and password_problem(new_password):
            errors.append(password_problem(new_password))
        if db.query("SELECT 1 FROM users WHERE email = ? AND id != ?", (form["email"], user_id), one=True):
            errors.append("That email is used by another account.")
        if errors:
            for e in errors:
                flash(e, "danger")
        else:
            conn = db.get_db()
            conn.execute("UPDATE users SET email=?, full_name=?, role=?, is_active=? WHERE id=?",
                         (form["email"], form["full_name"], form["role"], form["is_active"], user_id))
            if new_password:
                conn.execute("UPDATE users SET password_hash=? WHERE id=?",
                             (generate_password_hash(new_password), user_id))
            audit("user_edit", f"{u['username']} (password reset)" if new_password else u["username"],
                  commit=False)
            conn.commit()
            flash("User updated.", "success")
            return redirect(url_for("admin.users"))
    return render_template("admin/user_form.html", form=form, editing=True, u=u, is_self=is_self,
                           choice_pairs=[(c, ROLE_LABELS[c]) for c in STAFF_CHOICES], roles=ROLE_LABELS)


@bp.route("/services", methods=["GET", "POST"])
@roles_required()
def services():
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        desc = (request.form.get("description") or "").strip()
        needs = 1 if request.form.get("requires_document") else 0
        try:
            fee = float(request.form.get("fee") or 0)
        except ValueError:
            fee = -1
        if not (3 <= len(name) <= 80) or fee < 0 or len(desc) > 300:
            flash("Enter a service name (3-80 characters), a valid fee and a short description.", "danger")
        else:
            try:
                db.execute("INSERT INTO services (name, description, requires_document, fee)"
                           " VALUES (?,?,?,?)", (name, desc, needs, fee))
                audit("service_create", name)
                flash("Service added.", "success")
            except sqlite3.IntegrityError:
                flash("A service with that name already exists.", "danger")
        return redirect(url_for("admin.services"))
    rows = db.query("SELECT * FROM services ORDER BY is_active DESC, name")
    return render_template("admin/services.html", rows=rows)


@bp.route("/services/<int:service_id>/toggle", methods=["POST"])
@roles_required()
def service_toggle(service_id):
    s = db.query("SELECT * FROM services WHERE id = ?", (service_id,), one=True)
    if s is None:
        abort(404)
    db.execute("UPDATE services SET is_active = ? WHERE id = ?", (0 if s["is_active"] else 1, service_id))
    audit("service_toggle", s["name"])
    flash(f"{s['name']} is now {'disabled' if s['is_active'] else 'active'}.", "info")
    return redirect(url_for("admin.services"))


@bp.route("/audit")
@roles_required()
def audit_log():
    rows = db.query("SELECT a.*, u.username FROM audit_log a LEFT JOIN users u ON u.id = a.user_id "
                    "ORDER BY a.id DESC LIMIT 300")
    return render_template("admin/audit.html", rows=rows)
