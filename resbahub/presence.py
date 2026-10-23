"""Staff on-site status for the resident-facing dashboard."""

from flask import Blueprint, flash, g, redirect, request, url_for

from . import db
from .auth import roles_required
from .utils import STAFF_ROLES, audit

bp = Blueprint("presence", __name__, url_prefix="/presence")


def get_on_site_personnel():
    """Return all active personnel and their current on-duty status."""
    return db.query(
        """
        SELECT u.full_name, u.role, u.position_title,
               COALESCE(p.is_on_site, 0) AS is_on_site,
               p.updated_at
        FROM users u
        LEFT JOIN staff_presence p ON p.user_id = u.id
        WHERE u.is_active = 1
          AND u.role IN ('barangay_staff', 'health_staff')
        ORDER BY u.role, u.full_name
        """
    )


def get_user_presence(user_id):
    """Return whether a staff user has checked in on-site."""
    row = db.query(
        "SELECT is_on_site FROM staff_presence WHERE user_id = ?",
        (user_id,),
        one=True,
    )
    return bool(row and row["is_on_site"])


@bp.route("/update", methods=["POST"])
@roles_required(*STAFF_ROLES, admin=False)
def update():
    value = request.form.get("is_on_site")

    if value not in ("0", "1"):
        flash("Choose a valid on-site status.", "danger")
        return redirect(url_for("auth.home"))

    is_on_site = value == "1"
    db.execute(
        """
        INSERT INTO staff_presence (user_id, is_on_site)
        VALUES (?, ?)
        ON DUPLICATE KEY UPDATE
            is_on_site = VALUES(is_on_site),
            updated_at = CURRENT_TIMESTAMP
        """,
        (g.user["id"], is_on_site),
    )

    status = "checked in on-site" if is_on_site else "checked out"
    audit("staff_presence", f"{g.user['full_name']} {status}")
    flash(f"You are marked as {'on-site' if is_on_site else 'off-site'}.", "success")
    dashboard = {
        "barangay_staff": "staff.dashboard",
        "health_staff": "health.dashboard",
        "admin": "admin.dashboard",
    }[g.user["role"]]
    return redirect(url_for(dashboard))
