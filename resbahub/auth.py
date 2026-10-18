"""Login, registration, logout, password change and role-based access control."""
import sqlite3
import time
from functools import wraps
from urllib.parse import urlparse

from flask import (Blueprint, abort, flash, g, redirect, render_template,
                   request, session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

from . import db
from .utils import (CIVIL_STATUS, EMAIL_RE, SEX, USERNAME_RE, audit, display_name,
                    parse_date, password_problem, read_resident_form,
                    validate_resident, notify)

bp = Blueprint("auth", __name__)

ROLE_HOME = {
    "resident": "resident.dashboard",
    "barangay_staff": "staff.dashboard",
    "health_staff": "health.dashboard",
    "admin": "admin.dashboard",
}


# ------------------------------------------------------ access-control helpers
def roles_required(*roles, admin=True):
    """Allow only the listed roles. The admin may open everything unless admin=False."""
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if g.user is None:
                flash("Please log in to continue.", "warning")
                nxt = request.full_path.rstrip("?") if request.method == "GET" else None
                return redirect(url_for("auth.login", next=nxt))
            role = g.user["role"]
            if role in roles or (admin and role == "admin"):
                return view(*args, **kwargs)
            abort(403)
        return wrapped
    return decorator


def login_required(view):
    return roles_required("resident", "barangay_staff", "health_staff", "admin")(view)


def safe_next(target):
    """Only allow redirects to paths inside this website."""
    if not target:
        return None
    parts = urlparse(target)
    if parts.scheme or parts.netloc or not target.startswith("/") \
            or target.startswith("//") or "\\" in target:
        return None
    return target


# ------------------------------------------------- simple brute-force throttle
_FAILS = {}
MAX_FAILS = 5
WINDOW_SECONDS = 300


def reset_throttle():
    _FAILS.clear()


def _throttle_key(username):
    return (request.remote_addr, username.lower())


def _is_locked(key):
    now = time.time()
    hits = [t for t in _FAILS.get(key, []) if now - t < WINDOW_SECONDS]
    _FAILS[key] = hits
    return len(hits) >= MAX_FAILS


# ----------------------------------------------------------------------- views
@bp.route("/")
def home():
    if g.user is not None:
        return redirect(url_for(ROLE_HOME[g.user["role"]]))
    announcements = db.query(
        "SELECT * FROM announcements ORDER BY created_at DESC, id DESC LIMIT 3")
    return render_template("index.html", announcements=announcements)


@bp.route("/login", methods=["GET", "POST"])
def login():
    if g.user is not None:
        return redirect(url_for("auth.home"))
    if request.method == "POST":
        identifier = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        key = _throttle_key(identifier)
        if _is_locked(key):
            flash("Too many failed attempts. Please wait 5 minutes and try again.", "danger")
            return render_template("login.html"), 429
        user = db.query("SELECT * FROM users WHERE username = ? OR email = ?",
                        (identifier, identifier), one=True)
        if user is None or not check_password_hash(user["password_hash"], password):
            _FAILS.setdefault(key, []).append(time.time())
            flash("Invalid username or password.", "danger")
        elif not user["is_active"]:
            flash("This account has been deactivated. Please contact the barangay office.", "danger")
        else:
            _FAILS.pop(key, None)
            session.clear()
            session["user_id"] = user["id"]
            session.permanent = True
            db.execute("UPDATE users SET last_login = datetime('now','localtime') WHERE id = ?",
                       (user["id"],))
            audit("login", f"{user['username']} logged in", user_id=user["id"])
            nxt = safe_next(request.args.get("next"))
            return redirect(nxt or url_for(ROLE_HOME[user["role"]]))
    return render_template("login.html")


@bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("auth.login"))


@bp.route("/register", methods=["GET", "POST"])
def register():
    if g.user is not None:
        return redirect(url_for("auth.home"))
    form = {}
    if request.method == "POST":
        form = read_resident_form(request.form)
        form["username"] = (request.form.get("username") or "").strip()
        form["email"] = (request.form.get("email") or "").strip()
        password = request.form.get("password") or ""
        confirm = request.form.get("confirm") or ""
        errors = validate_resident(form)
        if not USERNAME_RE.match(form["username"]):
            errors.append("Username must be 4-30 characters: letters, numbers, dot or underscore.")
        if not EMAIL_RE.match(form["email"]) or len(form["email"]) > 120:
            errors.append("Please enter a valid email address.")
        problem = password_problem(password)
        if problem:
            errors.append(problem)
        if password != confirm:
            errors.append("Passwords do not match.")
        if not request.form.get("consent"):
            errors.append("You must agree to the Data Privacy notice to register.")
        if not errors:
            if db.query("SELECT 1 FROM users WHERE username = ?", (form["username"],), one=True):
                errors.append("That username is already taken.")
            if db.query("SELECT 1 FROM users WHERE email = ?", (form["email"],), one=True):
                errors.append("That email is already registered.")
        if errors:
            for e in errors:
                flash(e, "danger")
        else:
            conn = db.get_db()
            try:
                cur = conn.execute(
                    "INSERT INTO users (username, email, full_name, password_hash, role) "
                    "VALUES (?,?,?,?,?)",
                    (form["username"], form["email"],
                     display_name(form["first_name"], form["middle_name"],
                                  form["last_name"], form["suffix"]),
                     generate_password_hash(password), "resident"))
                user_id = cur.lastrowid
                conn.execute(
                    "INSERT INTO residents (user_id, first_name, middle_name, last_name, suffix,"
                    " birthdate, sex, civil_status, contact_no, address, purok, occupation)"
                    " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (user_id, form["first_name"], form["middle_name"], form["last_name"],
                     form["suffix"], form["birthdate"], form["sex"], form["civil_status"],
                     form["contact_no"], form["address"], form["purok"], form["occupation"]))
                notify(user_id, "Welcome to e-RESBAHUB! Barangay personnel will verify your "
                                "account shortly. You can submit requests once verified.",
                       commit=False)
                audit("register", f"New resident account {form['username']}",
                      user_id=user_id, commit=False)
                conn.commit()
            except sqlite3.IntegrityError:
                conn.rollback()
                flash("That username or email is already in use.", "danger")
            else:
                flash("Registration successful! You can now log in.", "success")
                return redirect(url_for("auth.login"))
    return render_template("register.html", form=form, sex_options=SEX,
                           civil_options=CIVIL_STATUS)


@bp.route("/account/password", methods=["GET", "POST"])
@login_required
def change_password():
    if request.method == "POST":
        current = request.form.get("current") or ""
        new = request.form.get("new") or ""
        confirm = request.form.get("confirm") or ""
        row = db.query("SELECT password_hash FROM users WHERE id = ?", (g.user["id"],), one=True)
        problem = password_problem(new)
        if not check_password_hash(row["password_hash"], current):
            flash("Your current password is incorrect.", "danger")
        elif problem:
            flash(problem, "danger")
        elif new != confirm:
            flash("New passwords do not match.", "danger")
        else:
            db.execute("UPDATE users SET password_hash = ? WHERE id = ?",
                       (generate_password_hash(new), g.user["id"]))
            audit("password_change", "User changed own password")
            flash("Password updated.", "success")
            return redirect(url_for("auth.home"))
    return render_template("password.html")
