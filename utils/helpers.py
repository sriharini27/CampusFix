"""Constants, workflow rules and small helper functions."""
import os
import re
import uuid
from datetime import datetime, timedelta

from flask import current_app
from pymongo import ReturnDocument
from werkzeug.utils import secure_filename

from utils.database import get_db

CATEGORIES = ["Classroom", "Laboratory", "Hostel", "Electrical", "Internet",
              "Water", "Cleanliness", "Transport", "Canteen", "Other"]
PRIORITIES = ["Low", "Medium", "High", "Critical"]
STATUSES = ["Submitted", "Under Review", "Assigned", "In Progress", "Reopened",
            "Resolved", "Rejected", "Closed"]
WORKFLOW = ["Submitted", "Under Review", "Assigned", "In Progress", "Resolved"]
OPEN_STATUSES = ["Submitted", "Under Review", "Assigned", "In Progress", "Reopened"]
FINAL_STATUSES = ["Resolved", "Rejected", "Closed"]

# Allowed status transitions (the resolution workflow state machine)
TRANSITIONS = {
    "Submitted":    ["Under Review", "Rejected"],
    "Under Review": ["Assigned", "Rejected"],
    "Assigned":     ["In Progress", "Under Review", "Rejected"],
    "In Progress":  ["Resolved", "Assigned"],
    "Resolved":     ["Closed", "Reopened"],        # student (or staff) can reopen
    "Reopened":     ["In Progress", "Assigned"],   # Reopened -> In Progress -> Resolved
    "Rejected":     ["Closed", "Under Review"],
    "Closed":       [],
}

STATUS_BADGE = {
    "Submitted": "secondary", "Under Review": "info", "Assigned": "primary",
    "In Progress": "warning", "Reopened": "reopened", "Resolved": "success",
    "Rejected": "danger", "Closed": "dark",
}
PRIORITY_BADGE = {"Low": "success", "Medium": "info", "High": "warning", "Critical": "danger"}
RATING_LABELS = {1: "Very Poor", 2: "Poor", 3: "Average", 4: "Good", 5: "Excellent"}

DEFAULT_DEPARTMENTS = [
    {"name": "Maintenance", "categories": ["Classroom", "Other"], "description": "Civil works, furniture, doors & windows"},
    {"name": "Electrical", "categories": ["Electrical"], "description": "Power, lights, fans, ACs"},
    {"name": "IT Support", "categories": ["Internet"], "description": "Wi-Fi, LAN, projectors, computers"},
    {"name": "Hostel Administration", "categories": ["Hostel", "Water"], "description": "Hostel rooms, mess, water supply"},
    {"name": "Transport", "categories": ["Transport"], "description": "College buses and parking"},
    {"name": "Canteen", "categories": ["Canteen"], "description": "Food quality, hygiene, pricing"},
    {"name": "Academic/Laboratory", "categories": ["Laboratory"], "description": "Lab equipment and academic facilities"},
    {"name": "Housekeeping", "categories": ["Cleanliness"], "description": "Cleaning, waste and washrooms"},
]


DEFAULT_LOCATIONS = [
    ("Library", "Central library, all floors"),
    ("Computer Lab 1", "CSE block, ground floor"),
    ("Computer Lab 2", "CSE block, first floor"),
    ("Computer Lab 3", "CSE block, second floor"),
    ("Hostel Block A", "Boys hostel"),
    ("Hostel Block B", "Girls hostel"),
    ("Canteen", "Main canteen and dining area"),
    ("Seminar Hall", "Main auditorium / seminar hall"),
    ("Classroom Block", "Lecture halls"),
    ("Parking Area", "Two- and four-wheeler parking"),
]


def now():
    return datetime.now().replace(microsecond=0)


def slugify(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def safe_next(url, role):
    """Only follow a ?next= URL if it is a local path the role is allowed to open."""
    if not url or not url.startswith("/") or url.startswith("//") or "\\" in url:
        return None
    allowed = ("/student", "/complaints") if role == "student" else ("/admin",)
    return url if url.startswith(allowed + ("/notifications", "/profile")) else None


# ---------- Complaint ID ----------
def next_complaint_id():
    """Atomic counter document -> CF-2026-0001 style IDs (never duplicated)."""
    year = now().year
    counter = get_db().counters.find_one_and_update(
        {"_id": f"complaint_{year}"},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    return f"CF-{year}-{counter['seq']:04d}"


# ---------- Smart priority / overdue logic ----------
def overdue_limit(priority):
    return current_app.config["OVERDUE_DAYS"].get(priority, 7)


def enrich(c):
    """Add computed fields (age, SLA, overdue, urgent) used by templates."""
    end = c.get("resolved_at") if c.get("status") in FINAL_STATUSES and c.get("resolved_at") else now()
    age = end - c["created_at"]
    c["age_days"] = age.days
    c["age_text"] = humanize(age)
    c["is_open"] = c.get("status") in OPEN_STATUSES
    c.update(sla_info(c))
    c["is_overdue"] = c["sla_state"] == "breached"
    c["is_urgent"] = c["is_open"] and c.get("priority") == "Critical"
    c["progress"] = workflow_progress(c.get("status"))
    return c


# ---------- SLA monitoring ----------
SLA_STYLE = {   # state -> (label, colour used by the .sla-* CSS classes)
    "ok": ("Within SLA", "green"),
    "warning": ("Approaching deadline", "yellow"),
    "breached": ("BREACHED", "red"),
    "met": ("SLA met", "green"),
    "missed": ("Resolved after deadline", "red"),
    "na": ("Not applicable", "gray"),
}


def sla_info(c):
    """SLA deadline = submission time + target days for the priority."""
    window = timedelta(days=overdue_limit(c.get("priority")))
    deadline = c["created_at"] + window
    status = c.get("status")
    if status == "Rejected" or (status == "Closed" and not c.get("resolved_at")):
        state, text = "na", "Complaint was not resolved (rejected)"
    elif status in ("Resolved", "Closed"):
        late = c["resolved_at"] - deadline
        state = "met" if late <= timedelta(0) else "missed"
        text = ("Resolved within SLA" if state == "met" else f"Resolved {humanize(late)} after the deadline")
    else:
        remaining = deadline - now()
        if remaining < timedelta(0):
            state, text = "breached", f"BREACHED — {humanize(-remaining)} overdue"
        else:
            ratio = current_app.config["SLA_WARNING_RATIO"]
            state = "warning" if remaining <= window * ratio else "ok"
            text = f"{humanize(remaining)} remaining"
    label, colour = SLA_STYLE[state]
    return {"sla_deadline": deadline, "sla_state": state, "sla_label": label,
            "sla_colour": colour, "sla_text": text, "sla_days": window.days}


def overdue_query():
    """MongoDB filter matching open complaints older than their priority's SLA (= SLA breached)."""
    t = now()
    return {
        "status": {"$in": OPEN_STATUSES},
        "$or": [{"priority": p, "created_at": {"$lt": t - timedelta(days=d)}}
                for p, d in current_app.config["OVERDUE_DAYS"].items()],
    }


def approaching_query():
    """Open complaints inside the last SLA_WARNING_RATIO of their SLA window (not yet breached)."""
    t = now()
    ratio = current_app.config["SLA_WARNING_RATIO"]
    return {
        "status": {"$in": OPEN_STATUSES},
        "$or": [{"priority": p, "created_at": {"$gte": t - timedelta(days=d),
                                               "$lt": t - timedelta(days=d * (1 - ratio))}}
                for p, d in current_app.config["OVERDUE_DAYS"].items()],
    }


def workflow_progress(status):
    if status == "Reopened":
        return 60
    if status in ("Resolved", "Closed"):
        return 100
    if status in WORKFLOW:
        return int(WORKFLOW.index(status) / (len(WORKFLOW) - 1) * 100)
    return 0


def humanize(delta):
    secs = abs(int(delta.total_seconds()))
    if secs < 3600:
        return f"{max(secs // 60, 0)} min"
    if secs < 86400:
        return f"{secs // 3600} hr"
    return f"{secs // 86400} day{'s' if secs // 86400 > 1 else ''}"


def suggest_department(category):
    """Rule-based routing: find the department whose embedded categories list has this category."""
    dept = get_db().departments.find_one({"categories": category, "active": True})
    return dept["name"] if dept else None


# ---------- File uploads ----------
SIGNATURES = {
    "png": [b"\x89PNG"], "jpg": [b"\xff\xd8\xff"], "jpeg": [b"\xff\xd8\xff"],
    "gif": [b"GIF87a", b"GIF89a"], "pdf": [b"%PDF"],
}


def save_attachment(file):
    """Validate extension + file signature, then save with a random name.
    Returns (filename, error)."""
    if not file or not file.filename:
        return None, None
    name = secure_filename(file.filename)
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if ext not in current_app.config["ALLOWED_EXTENSIONS"]:
        return None, "Invalid file type. Allowed: PNG, JPG, GIF, PDF."
    head = file.stream.read(8)
    file.stream.seek(0)
    if not any(head.startswith(sig) for sig in SIGNATURES[ext]):
        return None, "The uploaded file content does not match its extension."
    stored = f"{uuid.uuid4().hex[:12]}_{name}"
    os.makedirs(current_app.config["UPLOAD_FOLDER"], exist_ok=True)
    file.save(os.path.join(current_app.config["UPLOAD_FOLDER"], stored))
    return stored, None


def pending_attachment(name):
    """Re-use a file uploaded in the duplicate-warning step (only our own random file names)."""
    if name and re.fullmatch(r"[0-9a-f]{12}_[\w.\-]+", name) and \
            os.path.isfile(os.path.join(current_app.config["UPLOAD_FOLDER"], name)):
        return name
    return None


def clean(value, max_len=200):
    return (value or "").strip()[:max_len]
