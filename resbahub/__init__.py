
"""e-RESBAHUB application factory."""

import os
import secrets
from datetime import date, datetime, timedelta

from flask import Flask, abort, g, render_template, request, session

from . import db
from .utils import ROLE_LABELS


def _secret_key(instance_path):
    """Use SECRET_KEY from the environment or create a persistent local key."""
    env = os.environ.get("SECRET_KEY")

    if env:
        return env

    os.makedirs(instance_path, exist_ok=True)
    path = os.path.join(instance_path, "secret_key")

    if os.path.exists(path):
        with open(path, encoding="utf-8") as file:
            key = file.read().strip()

        if key:
            return key

    key = secrets.token_hex(32)

    with open(path, "w", encoding="utf-8") as file:
        file.write(key)

    return key


def create_app(test_config=None):
    """Create and configure the Flask application."""
    app = Flask(__name__, instance_relative_config=True)

    is_vercel = bool(os.environ.get("VERCEL"))

    if not is_vercel:
        os.makedirs(app.instance_path, exist_ok=True)

    upload_path = (
        "/tmp/e-resbahub-uploads"
        if is_vercel
        else os.path.join(app.instance_path, "uploads")
    )

    app.config.from_mapping(
        DB_HOST=os.environ.get("DB_HOST", "127.0.0.1"),
        DB_PORT=int(os.environ.get("DB_PORT", "3306")),
        DB_USER=os.environ.get("DB_USER", "root"),
        DB_PASSWORD=os.environ.get("DB_PASSWORD", ""),
        DB_NAME=os.environ.get("DB_NAME", "eresbahub"),
        UPLOAD_FOLDER=upload_path,
        MAX_CONTENT_LENGTH=5 * 1024 * 1024,
        ALLOWED_EXTENSIONS={"pdf", "png", "jpg", "jpeg"},
        REQUIRE_VERIFIED_FOR_REQUESTS=True,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
        BARANGAY_NAME=os.environ.get(
            "BARANGAY_NAME",
            "Barangay Hall, San Miguel, Bulacan",
        ),
    )

    if test_config:
        app.config.update(test_config)

    # Protect the main database from automated tests.
    if app.config.get("TESTING"):
        requested_db = (test_config or {}).get("DB_NAME")

        if requested_db not in (None, "eresbahub_test"):
            raise RuntimeError(
                "TESTING mode may only use the eresbahub_test database."
            )

        app.config["DB_NAME"] = "eresbahub_test"

    if not app.config.get("SECRET_KEY"):
        if is_vercel:
            raise RuntimeError(
                "Set the SECRET_KEY environment variable in Vercel."
            )

        app.config["SECRET_KEY"] = _secret_key(app.instance_path)

    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    app.teardown_appcontext(db.close_db)

    from . import admin, auth, health, reports, resident, staff

    for module in (auth, resident, staff, health, admin, reports):
        app.register_blueprint(module.bp)

    @app.before_request
    def load_user():
        g.user = None

        if request.endpoint == "static":
            return

        user_id = session.get("user_id")

        if user_id is not None:
            user = db.query(
                """
                SELECT id, username, email, full_name, role, is_active
                FROM users
                WHERE id = ?
                """,
                (user_id,),
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
    def security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:"
        )

        if request.endpoint != "static":
            response.headers["Cache-Control"] = "no-store"

        return response

    def csrf_token():
        """Create and return a CSRF token for the current session."""
        if "csrf_token" not in session:
            session["csrf_token"] = secrets.token_hex(16)

        return session["csrf_token"]

    app.jinja_env.globals["csrf_token"] = csrf_token

    @app.context_processor
    def inject_globals():
        """Make common user and application values available to templates."""
        user = g.get("user")
        unread = 0

        if user is not None and user["role"] == "resident":
            result = db.query(
                """
                SELECT COUNT(*) AS c
                FROM notifications
                WHERE user_id = ? AND is_read = 0
                """,
                (user["id"],),
                one=True,
            )
            unread = result["c"]

        return {
            "current_user": user,
            "unread_count": unread,
            "barangay_name": app.config["BARANGAY_NAME"],
            "ROLE_LABELS": ROLE_LABELS,
            "today": date.today().isoformat(),
        }

    @app.template_filter("dt")
    def fmt_datetime(value):
        """Format database date and datetime values for display."""
        if not value:
            return "-"

        formats = (
            ("%Y-%m-%d %H:%M:%S", "%b %d, %Y %I:%M %p"),
            ("%Y-%m-%d", "%b %d, %Y"),
        )

        for input_format, output_format in formats:
            try:
                return datetime.strptime(
                    str(value), input_format
                ).strftime(output_format)
            except (ValueError, TypeError):
                continue

        return value

    @app.template_filter("age")
    def fmt_age(value):
        """Calculate age from a YYYY-MM-DD birthdate."""
        try:
            born = datetime.strptime(str(value), "%Y-%m-%d").date()
        except (ValueError, TypeError):
            return "-"

        today = date.today()

        return (
            today.year
            - born.year
            - ((today.month, today.day) < (born.month, born.day))
        )

    titles = {
        400: "Bad request",
        403: "Access denied",
        404: "Page not found",
        405: "Method not allowed",
        413: "File too large",
        500: "Something went wrong",
    }

    def handle_error(error):
        """Render a consistent page for common HTTP errors."""
        code = getattr(error, "code", 500) or 500
        message = getattr(error, "description", "")

        if code == 413:
            message = (
                "The upload is too large. "
                "The maximum total size is 5 MB."
            )
        elif code == 403:
            message = "You do not have permission to open this page."
        elif code == 500:
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

    # Verify the configured database and required tables at startup.
    with app.app_context():
        db.init_db()

    return app
