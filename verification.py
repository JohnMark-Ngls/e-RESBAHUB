import io
from flask import Blueprint, current_app, render_template, send_file, url_for
from . import db

bp = Blueprint("verification", __name__, url_prefix="/verify")


@bp.route("/<token>")
def verify_certificate(token):
    certificate = db.query(
        """
        SELECT
            cv.verification_token,
            cv.is_revoked,
            cv.issued_at,
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

    if not certificate:
        return render_template(
            "verification/result.html",
            result_status="INVALID",
            message="Certificate verification record was not found.",
            certificate=None,
        ), 404

    if certificate["is_revoked"]:
        result_status = "REVOKED"
        message = "This certificate has been revoked."
    elif certificate["status"] != "Completed":
        result_status = "INVALID"
        message = "This request is not marked as completed."
    else:
        result_status = "VALID"
        message = "Certificate verification successful."

    return render_template(
        "verification/result.html",
        result_status=result_status,
        message=message,
        certificate=certificate,
    )


@bp.route("/<token>/qr.png")
def certificate_qr(token):
    # Confirm that the token exists before generating its QR code.
    certificate = db.query(
        """
        SELECT id
        FROM certificate_verifications
        WHERE verification_token = ?
        LIMIT 1
        """,
        (token,),
        one=True,
    )

    if not certificate:
        return "Verification record not found.", 404

    try:
        import qrcode
    except ImportError:
        return "QR package missing. Install it using: pip install 'qrcode[pil]'", 500

    verify_url = url_for(
        "verification.verify_certificate",
        token=token,
        _external=True,
    )

    image = qrcode.make(verify_url)
    image_bytes = io.BytesIO()
    image.save(image_bytes, format="PNG")
    image_bytes.seek(0)

    return send_file(
        image_bytes,
        mimetype="image/png",
        download_name="certificate-qr.png",
    )