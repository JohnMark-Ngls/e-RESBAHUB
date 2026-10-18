
"""e-RESBAHUB application factory."""
import os
import secrets
from datetime import date, datetime, timedelta

from flask import Flask, abort, g, render_template, request, session

from . import db
from .utils import ROLE_LABELS


def _secret_key(instance_path):
    """Use SECRET_KEY from the environment, else create/read instance/secret_key."""
    env = os.environ.get("SECRET_KEY")
    if env:
        return env

    path = os.path.join(instance_path, "secret_key")

    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            return fh.read().strip()

    key = secrets.token_hex(32)

    with open(path, "w", encoding="utf-8") as fh:
        fh.write(key)

    return key


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)

    os.makedirs(app.instance_path, exist_ok=True)

    app.config.from_mapping(
        DATABASE=os.path.join(app.instance_path, "resbahub.db"),

        # Use temporary storage on Vercel.
        # Local development continues to use instance/uploads.
        UPLOAD_FOLDER=(
            "/tmp/e-resbahub-uploads"
            if os.environ.get("VERCEL")
            else os.path.join(app.instance_path, "uploads")
        ),

        MAX_CONTENT_LENGTH=5 * 1024 * 1024,
        ALLOWED_EXTENSIONS={"pdf", "png", "jpg", "jpeg"},
        REQUIRE_VERIFIED_FOR_REQUESTS=True,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
        BARANGAY_NAME=os.environ.get(
            "BARANGAY_NAME",
            "Barangay Hall, San Ildefonso, Bulacan",
        ),
    )

    if test_config:
        app.config.update(test_config)

    if not app.config.get("SECRET_KEY"):
        app.config["SECRET_KEY"] = _secret_key(app.instance_path)

    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    app.teardown_appcontext(db.close_db)

    with app.app_context():
        db.init_db()

    # -----------------------------------------------------------
    # Blueprints
    # -----------------------------------------------------------
    from . import admin, auth, health, reports, resident, staff

    for module in (auth, resident, staff, health, admin, reports):
        app.register_blueprint(module.bp)

    # -----------------------------------------------------------
    # Request hooks
    # -----------------------------------------------------------
    @app.before_request
    def load_user():
        g.user = None

        if request.endpoint == "static":
            return

        uid = session.get("user_id")

        if uid is not None:
            user = db.query(
                """
                SELECT id, username, email, full_name, role, is_active
                FROM users
                WHERE id = ?
                """,
                (uid,),
                one=True,
            )

            if user is not None and user["is_active"]:
                g.user = user
            else:
                session.pop("user_id", None)

    @app.before_request
    def csrf_protect():
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            expected = session.get("csrf_token")

            sent = (
                request.form.get("csrf_token")
                or request.headers.get("X-CSRF-Token")
            )

            if (
                not expected
                or not sent
                or not secrets.compare_digest(expected, sent)
            ):
                abort(
                    400,
                    "Your session form token is missing or expired. "
                    "Please go back, refresh the page and try again.",
                )

    @app.after_request
    def security_headers(resp):
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["Referrer-Policy"] = "same-origin"

        resp.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:"
        )

        if request.endpoint != "static":
            resp.headers["Cache-Control"] = "no-store"

        return resp

    # -----------------------------------------------------------
    # Templating and CSRF token
    # -----------------------------------------------------------
    def csrf_token():
        if "csrf_token" not in session:
            session["csrf_token"] = secrets.token_hex(16)

        return session["csrf_token"]

    app.jinja_env.globals["csrf_token"] = csrf_token

    @app.context_processor
    def inject_globals():
        user = g.get("user")
        unread = 0

        if user is not None and user["role"] == "resident":
            unread = db.query(
                """
                SELECT COUNT(*) AS c
                FROM notifications
                WHERE user_id = ? AND is_read = 0
                """,
                (user["id"],),
                one=True,
            )["c"]

        return {
            "current_user": user,
            "unread_count": unread,
            "barangay_name": app.config["BARANGAY_NAME"],
            "ROLE_LABELS": ROLE_LABELS,
            "today": date.today().isoformat(),
        }

    # -----------------------------------------------------------
    # Template filters
    # -----------------------------------------------------------
    @app.template_filter("dt")
    def fmt_datetime(value):
        if not value:
            return "-"

        formats = (
            ("%Y-%m-%d %H:%M:%S", "%b %d, %Y %I:%M %p"),
            ("%Y-%m-%d", "%b %d, %Y"),
        )

        for fmt, output_format in formats:
            try:
                return datetime.strptime(value, fmt).strftime(output_format)
            except ValueError:
                continue

        return value

    @app.template_filter("age")
    def fmt_age(value):
        try:
            born = datetime.strptime(value, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            return "-"

        today = date.today()

        return (
            today.year
            - born.year
            - ((today.month, today.day) < (born.month, born.day))
        )

    # -----------------------------------------------------------
    # Error pages
    # -----------------------------------------------------------
    titles = {
        400: "Bad request",
        403: "Access denied",
        404: "Page not found",
        405: "Method not allowed",
        413: "File too large",
        500: "Something went wrong",
    }

    def handle_error(err):
        code = getattr(err, "code", 500) or 500
        message = getattr(err, "description", "")

        if code == 413:
            message = (
                "The upload is too large. "
                "The maximum total size is 5 MB."
            )

        if code == 403:
            message = "You do not have permission to open this page."

        if code == 500:
            message = (
                "An unexpected error occurred. "
                "Please try again or contact the administrator."
            )

        return (
            render_template(
                "error.html",
                code=code,
                title=titles.get(code, "Error"),
                message=message,
            ),
            code,
        )

    for code in titles:
        app.register_error_handler(code, handle_error)

    return app
