"""In-app notification centre: helpers that create notification documents."""
import time

from flask import current_app, session

from utils.database import get_db
from utils.helpers import now, overdue_query

ICONS = {   # type -> Bootstrap icon + colour used in the bell / notifications page
    "submitted": ("bi-send-check", "primary"), "assigned": ("bi-person-check", "primary"),
    "status": ("bi-arrow-repeat", "info"), "resolved": ("bi-check2-circle", "success"),
    "feedback": ("bi-star", "warning"), "reopened": ("bi-arrow-counterclockwise", "reopened"),
    "new": ("bi-envelope-exclamation", "primary"), "critical": ("bi-exclamation-triangle-fill", "danger"),
    "overdue": ("bi-hourglass-split", "danger"), "reassigned": ("bi-shuffle", "info"),
}


def notify(user_ids, title, message, ntype, complaint_id=None, skip_self=True):
    """Insert one notification per recipient (login IDs). The person acting is skipped."""
    me = session.get("login_id") if skip_self else None
    recipients = {u for u in user_ids if u and u != me}
    if not recipients:
        return
    ts = now()
    get_db().notifications.insert_many([{
        "user_id": uid, "title": title, "message": message, "type": ntype,
        "complaint_id": complaint_id, "is_read": False, "created_at": ts,
    } for uid in recipients])


def admin_ids():
    return [u["login_id"] for u in get_db().users.find({"role": "admin"}, {"login_id": 1})]


def staff_ids_in(department):
    if not department:
        return []
    return [u["login_id"] for u in get_db().users.find(
        {"role": "staff", "department": department}, {"login_id": 1})]


def unread_count(user_id):
    return get_db().notifications.count_documents({"user_id": user_id, "is_read": False})


def latest(user_id, limit=6):
    return list(get_db().notifications.find({"user_id": user_id}).sort("created_at", -1).limit(limit))


_last_overdue_check = 0.0


def check_overdue_notifications():
    """There is no background scheduler, so this runs (at most once a minute) when staff browse.
    Each overdue complaint is announced once, then flagged with overdue_notified=True."""
    global _last_overdue_check
    if time.time() - _last_overdue_check < current_app.config["OVERDUE_CHECK_SECONDS"]:
        return
    _last_overdue_check = time.time()
    db = get_db()
    query = {"$and": [overdue_query(), {"overdue_notified": {"$ne": True}}]}
    admins = admin_ids()
    for c in db.complaints.find(query, {"complaint_id": 1, "title": 1, "priority": 1, "assigned_staff": 1}):
        staff = [c["assigned_staff"]["login_id"]] if c.get("assigned_staff") else []
        notify(admins + staff, "SLA breached — complaint overdue",
               f"{c['complaint_id']} ({c['priority']}) \"{c['title']}\" has passed its SLA deadline.",
               "overdue", c["complaint_id"], skip_self=False)
        db.complaints.update_one({"_id": c["_id"]}, {"$set": {"overdue_notified": True}})
