"""Profile management routes for e-RESBAHUB."""

import os
import re
import secrets

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
from mysql.connector.errors import IntegrityError
from werkzeug.exceptions import RequestEntityTooLarge
from werkzeug.utils import secure_filename

from . import db


bp = Blueprint("profile", __name__, url_prefix="/profile")

ALLOWED_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg"}
MAX_PROFILE_IMAGE_SIZE = 2 * 1024 * 1024

# Roles permitted to edit Position/Title.
POSITION_EDIT_ROLES = {
    "admin",
    "barangay_staff",
    "health_staff",
}


def _profile_folder():
    """Return the directory used to store profile pictures."""
    folder = os.path.join(
        current_app.config["UPLOAD_FOLDER"],
        "profiles",
    )
    os.makedirs(folder, exist_ok=True)
    return folder


def _allowed_image(filename):
    """Check whether the uploaded file has an allowed extension."""
    return (
        bool(filename)
        and "." in filename
        and filename.rsplit(".", 1)[1].lower()
        in ALLOWED_IMAGE_EXTENSIONS
    )


def _current_user_id():
    """Return the signed-in user's ID."""
    user = g.get("user")

    if user is None:
        abort(403)

    return user["id"]


def _get_profile_user():
    """Retrieve the signed-in user's profile."""
    user_id = _current_user_id()

    user = db.query(
        """
        SELECT
            id,
            username,
            email,
            full_name,
            role,
            position_title,
            profile_picture
        FROM users
        WHERE id = ?
        """,
        (user_id,),
        one=True,
    )

    if user is None:
        abort(404)

    return user


def _can_edit_position(user):
    """Return whether the user may edit Position/Title."""
    return user.get("role") in POSITION_EDIT_ROLES


def _redirect_to_edit():
    """Redirect back to the profile edit form."""
    return redirect(url_for("profile.edit"))


@bp.route("/", methods=["GET"])
def index():
    """Display the signed-in user's profile."""
    user = _get_profile_user()

    return render_template(
        "profile.html",
        user=user,
        edit_mode=False,
    )


@bp.route("/edit", methods=["GET", "POST"])
def edit():
    """Display and save the signed-in user's profile details."""
    user = _get_profile_user()
    can_edit_position = _can_edit_position(user)

    if request.method == "GET":
        return render_template(
            "profile.html",
            user=user,
            edit_mode=True,
        )

    full_name = request.form.get("full_name", "").strip()
    username = request.form.get("username", "").strip()
    email = request.form.get("email", "").strip()

    # Required fields.
    if not full_name or not username or not email:
        flash(
            "Full name, username, and email are required.",
            "error",
        )
        return _redirect_to_edit()

    # Validate database column lengths.
    if len(full_name) > 150:
        flash(
            "Full name must not exceed 150 characters.",
            "error",
        )
        return _redirect_to_edit()

    if not 1 <= len(username) <= 30:
        flash(
            "Username must be between 1 and 30 characters.",
            "error",
        )
        return _redirect_to_edit()

    if len(email) > 120:
        flash(
            "Email must not exceed 120 characters.",
            "error",
        )
        return _redirect_to_edit()

    # Basic email validation.
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        flash(
            "Please enter a valid email address.",
            "error",
        )
        return _redirect_to_edit()

    # Check username uniqueness.
    existing_username = db.query(
        """
        SELECT id
        FROM users
        WHERE username = ? AND id <> ?
        LIMIT 1
        """,
        (username, user["id"]),
        one=True,
    )

    if existing_username:
        flash(
            "That username is already in use.",
            "error",
        )
        return _redirect_to_edit()

    # Check email uniqueness.
    existing_email = db.query(
        """
        SELECT id
        FROM users
        WHERE email = ? AND id <> ?
        LIMIT 1
        """,
        (email, user["id"]),
        one=True,
    )

    if existing_email:
        flash(
            "That email address is already in use.",
            "error",
        )
        return _redirect_to_edit()

    # Only authorized roles may submit Position/Title changes.
    if can_edit_position:
        position_title = request.form.get(
            "position_title",
            user.get("position_title") or "",
        ).strip()

        if len(position_title) > 100:
            flash(
                "Position/Title must not exceed 100 characters.",
                "error",
            )
            return _redirect_to_edit()

    try:
        if can_edit_position:
            # Admin and staff may update their own Position/Title.
            cursor = db.execute(
                """
                UPDATE users
                SET full_name = ?,
                    username = ?,
                    email = ?,
                    position_title = ?
                WHERE id = ?
                """,
                (
                    full_name,
                    username,
                    email,
                    position_title or None,
                    user["id"],
                ),
            )
        else:
            # Residents cannot change Position/Title,
            # even if they manually submit that field.
            cursor = db.execute(
                """
                UPDATE users
                SET full_name = ?,
                    username = ?,
                    email = ?
                WHERE id = ?
                """,
                (
                    full_name,
                    username,
                    email,
                    user["id"],
                ),
            )

        cursor.close()

    except IntegrityError:
        db.rollback()
        flash(
            "The username or email is already being used "
            "by another account.",
            "error",
        )
        return _redirect_to_edit()

    flash(
        "Your profile details have been updated successfully.",
        "success",
    )
    return redirect(url_for("profile.index"))


@bp.route("/upload", methods=["POST"])
def upload():
    """Upload or replace the signed-in user's profile picture."""
    user_id = _current_user_id()
    image_file = request.files.get("profile_picture")

    if image_file is None or not image_file.filename:
        flash(
            "Please select an image to upload.",
            "error",
        )
        return redirect(url_for("profile.index"))

    safe_original_name = secure_filename(image_file.filename)

    if not _allowed_image(safe_original_name):
        flash(
            "Only PNG, JPG, and JPEG images are allowed.",
            "error",
        )
        return redirect(url_for("profile.index"))

    image_file.stream.seek(0, os.SEEK_END)
    file_size = image_file.stream.tell()
    image_file.stream.seek(0)

    if file_size > MAX_PROFILE_IMAGE_SIZE:
        flash(
            "The profile picture must not exceed 2 MB.",
            "error",
        )
        return redirect(url_for("profile.index"))

    extension = safe_original_name.rsplit(".", 1)[1].lower()
    filename = f"{secrets.token_hex(16)}.{extension}"

    folder = _profile_folder()
    destination = os.path.join(folder, filename)

    old_user = db.query(
        """
        SELECT profile_picture
        FROM users
        WHERE id = ?
        """,
        (user_id,),
        one=True,
    )

    if old_user is None:
        abort(404)

    try:
        image_file.save(destination)

        cursor = db.execute(
            """
            UPDATE users
            SET profile_picture = ?
            WHERE id = ?
            """,
            (filename, user_id),
        )
        cursor.close()

    except Exception:
        if os.path.exists(destination):
            os.remove(destination)
        raise

    old_filename = old_user.get("profile_picture")

    if old_filename and old_filename != filename:
        old_path = os.path.join(
            folder,
            os.path.basename(old_filename),
        )

        if os.path.isfile(old_path):
            try:
                os.remove(old_path)
            except OSError:
                current_app.logger.warning(
                    "Could not remove an old profile picture."
                )

    flash(
        "Profile picture updated successfully.",
        "success",
    )
    return redirect(url_for("profile.index"))


@bp.route("/remove", methods=["POST"])
def remove():
    """Remove the signed-in user's profile picture."""
    user_id = _current_user_id()

    user = db.query(
        """
        SELECT profile_picture
        FROM users
        WHERE id = ?
        """,
        (user_id,),
        one=True,
    )

    if user is None:
        abort(404)

    filename = user.get("profile_picture")

    cursor = db.execute(
        """
        UPDATE users
        SET profile_picture = NULL
        WHERE id = ?
        """,
        (user_id,),
    )
    cursor.close()

    if filename:
        path = os.path.join(
            _profile_folder(),
            os.path.basename(filename),
        )

        if os.path.isfile(path):
            try:
                os.remove(path)
            except OSError:
                current_app.logger.warning(
                    "Could not remove the profile picture file."
                )

    flash(
        "Profile picture removed.",
        "success",
    )
    return redirect(url_for("profile.index"))


@bp.route("/image/<filename>", methods=["GET"])
def image(filename):
    """Serve a profile picture from the upload directory."""
    safe_filename = secure_filename(filename)

    if safe_filename != filename or not _allowed_image(filename):
        abort(404)

    return send_from_directory(
        _profile_folder(),
        safe_filename,
    )


@bp.app_errorhandler(RequestEntityTooLarge)
def handle_profile_upload_too_large(error):
    """Show a friendly message when an upload exceeds the app limit."""
    flash(
        "The uploaded file is too large.",
        "error",
    )
    return redirect(url_for("profile.index"))