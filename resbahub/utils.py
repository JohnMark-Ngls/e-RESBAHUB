
"""Shared constants, validation helpers, notifications, audit log and file-upload helpers."""

import os
import re
import uuid
from datetime import date, datetime

from flask import current_app, g

from . import db


# -----------------------------------------------------------------
# Constants
# -----------------------------------------------------------------

ROLE_LABELS = {
    "resident": "Resident",
    "barangay_staff": "Barangay Personnel",
    "health_staff": "Health Center Personnel",
    "admin": "Administrator",
}

STAFF_ROLES = ("barangay_staff", "health_staff", "admin")

SEX = ["Male", "Female"]
CIVIL_STATUS = ["Single", "Married", "Widowed", "Separated", "Divorced"]
BLOOD_TYPES = ["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"]

ANNOUNCEMENT_CATEGORIES = [
    "Announcement",
    "Schedule",
    "Reminder",
    "Health",
]

SERVICE_TYPES = [
    "Consultation",
    "Immunization",
    "Maternal and Child Health",
    "Health Monitoring",
    "Other Health Service",
]

REQUEST_STATUSES = [
    "Pending",
    "Processing",
    "Approved",
    "Rejected",
    "Completed",
    "Cancelled",
]

REQUEST_TRANSITIONS = {
    "Pending": ["Processing", "Approved", "Rejected"],
    "Processing": ["Approved", "Rejected"],
    "Approved": ["Completed"],
    "Rejected": [],
    "Completed": [],
    "Cancelled": [],
}

ACTIVE_REQUEST_STATUSES = ("Pending", "Processing")

APPT_STATUSES = [
    "Scheduled",
    "Waiting",
    "In Consultation",
    "Completed",
    "Cancelled",
    "No Show",
]

APPT_TRANSITIONS = {
    "Scheduled": ["Waiting", "Cancelled", "No Show"],
    "Waiting": ["In Consultation", "Cancelled", "No Show"],
    "In Consultation": ["Completed", "Cancelled"],
    "Completed": [],
    "Cancelled": [],
    "No Show": [],
}

PHONE_RE = re.compile(r"^(09\d{9}|\+639\d{9})$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
USERNAME_RE = re.compile(r"^[A-Za-z0-9_.]{4,30}$")
BP_RE = re.compile(r"^\d{2,3}/\d{2,3}$")
TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


# -----------------------------------------------------------------
# General helpers
# -----------------------------------------------------------------

def parse_date(value):
    """Parse a YYYY-MM-DD date. Return None if invalid."""
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def display_name(first, middle, last, suffix=None):
    """Build a full name from the available name parts."""
    parts = [first, middle, last, suffix]

    return " ".join(
        part.strip()
        for part in parts
        if part and part.strip()
    )


def like(text):
    """Build a safe LIKE pattern. Use with LIKE ? ESCAPE '\\'."""
    escaped = (
        text.replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_")
    )

    return f"%{escaped}%"


def password_problem(pw):
    """Return a validation message if the password is too weak."""
    if len(pw) < 8:
        return "Password must be at least 8 characters long."

    if not re.search(r"[A-Za-z]", pw) or not re.search(r"\d", pw):
        return "Password must contain at least one letter and one number."

    return None


# -----------------------------------------------------------------
# Resident form validation
# -----------------------------------------------------------------

RESIDENT_FIELDS = [
    "first_name",
    "middle_name",
    "last_name",
    "suffix",
    "birthdate",
    "sex",
    "civil_status",
    "contact_no",
    "address",
    "purok",
    "occupation",
]

_LIMITS = {
    "first_name": 50,
    "middle_name": 50,
    "last_name": 50,
    "suffix": 10,
    "contact_no": 20,
    "address": 200,
    "purok": 50,
    "occupation": 80,
}


def read_resident_form(form):
    """Read resident fields from a Flask form."""
    return {
        key: (form.get(key) or "").strip()
        for key in RESIDENT_FIELDS
    }


def validate_resident(data, identity=True):
    """
    Validate resident profile fields.

    identity=False skips name, birthdate, and sex checks.
    """
    errors = []

    for key, limit in _LIMITS.items():
        if len(data.get(key, "")) > limit:
            field_name = key.replace("_", " ").capitalize()
            errors.append(
                f"{field_name} is too long (max {limit} characters)."
            )

    if identity:
        if not data["first_name"]:
            errors.append("First name is required.")

        if not data["last_name"]:
            errors.append("Last name is required.")

        born = parse_date(data["birthdate"])

        if born is None:
            errors.append("Please enter a valid birthdate.")
        elif (
            born > date.today()
            or (date.today().year - born.year) > 120
        ):
            errors.append("Birthdate is not realistic.")

        if data["sex"] not in SEX:
            errors.append("Please choose a sex.")

    if data["civil_status"] not in CIVIL_STATUS:
        errors.append("Please choose a civil status.")

    if not PHONE_RE.fullmatch(data["contact_no"]):
        errors.append(
            "Contact number must look like 09123456789 or +639123456789."
        )

    if not data["address"]:
        errors.append("Address is required.")

    return errors


# -----------------------------------------------------------------
# Notifications and audit log
# -----------------------------------------------------------------

def notify(user_id, message, link=None, commit=True):
    """Insert a notification and optionally commit the transaction."""
    db.execute(
        """
        INSERT INTO notifications (user_id, message, link)
        VALUES (?, ?, ?)
        """,
        (user_id, message, link),
        commit=commit,
    )


def audit(action, detail="", user_id=None, commit=True):
    """Insert an audit log entry and optionally commit the transaction."""
    if user_id is None and g.get("user") is not None:
        user_id = g.user["id"]

    db.execute(
        """
        INSERT INTO audit_log (user_id, action, detail)
        VALUES (?, ?, ?)
        """,
        (user_id, action, detail),
        commit=commit,
    )


# -----------------------------------------------------------------
# File uploads
# -----------------------------------------------------------------

_MAGIC = {
    "pdf": [b"%PDF"],
    "png": [b"\x89PNG\r\n\x1a\n"],
    "jpg": [b"\xff\xd8\xff"],
    "jpeg": [b"\xff\xd8\xff"],
}


def _ext(filename):
    """Return a lowercase file extension without the dot."""
    return filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


def upload_problem(fs):
    """Return an error if the uploaded file is unacceptable, else None."""
    name = fs.filename or ""
    ext = _ext(name)

    if ext not in current_app.config["ALLOWED_EXTENSIONS"]:
        return f'"{name}" is not allowed. Upload PDF, PNG or JPG files only.'

    head = fs.stream.read(8)
    fs.stream.seek(0)

    if not any(head.startswith(signature) for signature in _MAGIC[ext]):
        return f'"{name}" is not a valid {ext.upper()} file.'

    return None


def save_upload(fs):
    """Save the file under a random name and return the stored name."""
    extension = _ext(fs.filename or "")
    stored = f"{uuid.uuid4().hex}.{extension}"

    fs.save(
        os.path.join(
            current_app.config["UPLOAD_FOLDER"],
            stored,
        )
    )

    return stored
