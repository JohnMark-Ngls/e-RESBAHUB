
"""Public QR-code verification for issued e-RESBAHUB certificates."""

from flask import Blueprint, abort, current_app, render_template
from markupsafe import escape

from . import db

bp = Blueprint("verification", __name__, url_prefix="/verify")


@bp.route("/<token>")
def verify_certificate(token):
    """Show whether a certificate token is valid or revoked."""

    if not token or len(token) > 64:
        abort(404)

    record = db.query(
        """
        SELECT
            cv.verification_token,
            cv.issued_at,
            cv.is_revoked,
            cv.revoked_at,
            r.reference_no,
            r.status,
            s.name AS service_name
        FROM certificate_verifications AS cv
        JOIN requests AS r ON r.id = cv.request_id
        JOIN services AS s ON s.id = r.service_id
        WHERE cv.verification_token = ?
        LIMIT 1
        """,
        (token,),
        one=True,
    )

    if record is None:
        return render_template(
            "verification/result.html",
            result_status="INVALID",
            message="No matching certificate was found.",
            certificate=None,
        ), 404

    if record["is_revoked"]:
        result_status = "REVOKED"
        message = "This certificate has been revoked."
    elif record["status"] != "Completed":
        result_status = "INVALID"
        message = "This request is not marked as completed."
    else:
        result_status = "VALID"
        message = "The certificate verification record is valid."

    # Only show limited information on this public page.
    certificate = {
        "reference_no": record["reference_no"],
        "service_name": record["service_name"],
        "issued_at": record["issued_at"],
    }

    return render_template(
        "verification/result.html",
        result_status=result_status,
        message=message,
        certificate=certificate,
    )


@bp.route("/<token>/qr.png")
def certificate_qr(token):
    """Generate a QR image that points to the public verification page."""

    if not token or len(token) > 64:
        abort(404)

    record = db.query(
        """
        SELECT verification_token
        FROM certificate_verifications
        WHERE verification_token = ?
          AND is_revoked = 0
        LIMIT 1
        """,
        (token,),
        one=True,
    )

    if record is None:
        abort(404)

    try:
        import qrcode
    except ImportError:
        current_app.logger.exception(
            "QR library is missing. Install qrcode[pil]."
        )
        abort(500)

    verification_url = (
        current_app.config.get("PUBLIC_BASE_URL", "").rstrip("/")
        + current_app.config.get("APPLICATION_ROOT", "").rstrip("/")
        + "/verify/"
        + record["verification_token"]
    )

    if not current_app.config.get("PUBLIC_BASE_URL"):
        verification_url = (
            # _external creates a full URL using the current request.
            # Set PUBLIC_BASE_URL when running behind a proxy or in production.
            __import__("flask").url_for(
                "verification.verify_certificate",
                token=record["verification_token"],
                _external=True,
            )
        )

    image = qrcode.make(verification_url)

    from io import BytesIO

    output = BytesIO()
    image.save(output, format="PNG")
    output.seek(0)

    from flask import send_file

    return send_file(
        output,
        mimetype="image/png",
        download_name="certificate-qr.png",
        max_age=0,
    )
