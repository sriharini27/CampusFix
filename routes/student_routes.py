"""Module 1 (student side): dashboard."""
from flask import Blueprint, render_template, session

from utils.auth import student_required
from utils.database import get_db
from utils.analytics import status_counts
from utils.helpers import enrich, OPEN_STATUSES

student_bp = Blueprint("student", __name__, url_prefix="/student")


@student_bp.route("/dashboard")
@student_required
def dashboard():
    sid = session["login_id"]
    counts = status_counts({"student_id": sid})          # aggregation filtered by $match
    stats = {
        "total": sum(counts.values()),
        "pending": counts["Submitted"] + counts["Under Review"],
        "progress": counts["Assigned"] + counts["In Progress"] + counts["Reopened"],
        "resolved": counts["Resolved"] + counts["Closed"],
        "rejected": counts["Rejected"],
    }
    recent = [enrich(c) for c in get_db().complaints
              .find({"student_id": sid}, {"status_history": 0})
              .sort("created_at", -1).limit(5)]
    awaiting_feedback = get_db().complaints.count_documents(
        {"student_id": sid, "status": "Resolved", "feedback_given": {"$ne": True}})
    open_count = sum(counts[s] for s in OPEN_STATUSES)
    return render_template("student/dashboard.html", stats=stats, recent=recent,
                           awaiting_feedback=awaiting_feedback, open_count=open_count)
