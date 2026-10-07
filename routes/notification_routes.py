"""Notification centre — every logged-in user sees only their own notifications."""
from bson import ObjectId
from bson.errors import InvalidId
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, abort

from utils.auth import login_required
from utils.database import get_db
from utils.notifications import ICONS

notification_bp = Blueprint("notification", __name__, url_prefix="/notifications")


def complaint_link(cid):
    if not cid:
        return None
    endpoint = "complaint.details" if session["role"] == "student" else "admin.complaint_details"
    return url_for(endpoint, cid=cid)


@notification_bp.route("/")
@login_required
def index():
    show = request.args.get("show", "all")
    query = {"user_id": session["login_id"]}
    if show == "unread":
        query["is_read"] = False
    items = list(get_db().notifications.find(query).sort("created_at", -1).limit(100))
    return render_template("notifications.html", items=items, show=show, icons=ICONS)


@notification_bp.route("/read/<nid>", methods=["GET", "POST"])
@login_required
def read(nid):
    """Mark one notification as read, then open the related complaint."""
    try:
        oid = ObjectId(nid)
    except InvalidId:
        abort(404)
    n = get_db().notifications.find_one_and_update(
        {"_id": oid, "user_id": session["login_id"]},     # users can only touch their own
        {"$set": {"is_read": True}})
    if not n:
        abort(404)
    return redirect(complaint_link(n.get("complaint_id")) or url_for("notification.index"))


@notification_bp.route("/read-all", methods=["POST"])
@login_required
def read_all():
    res = get_db().notifications.update_many({"user_id": session["login_id"], "is_read": False},
                                             {"$set": {"is_read": True}})
    flash(f"{res.modified_count} notification{'s' if res.modified_count != 1 else ''} marked as read.", "info")
    back = request.referrer or ""
    return redirect(back if back.startswith(request.host_url) else url_for("notification.index"))
