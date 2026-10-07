"""Module 3 — Feedback: students rate resolved complaints, staff review quality."""
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, abort
from pymongo.errors import DuplicateKeyError

from utils.auth import student_required, staff_required
from utils.database import get_db
from utils.analytics import feedback_summary, rating_by_department, recent_feedback
from utils.helpers import clean, now

feedback_bp = Blueprint("feedback", __name__)


@feedback_bp.route("/complaints/<cid>/feedback", methods=["POST"])
@student_required
def submit(cid):
    db = get_db()
    c = db.complaints.find_one({"complaint_id": cid, "student_id": session["login_id"]})
    if not c:
        abort(404)
    if c["status"] not in ("Resolved", "Closed"):
        flash("Feedback can only be given after the complaint is resolved.", "warning")
        return redirect(url_for("complaint.details", cid=cid))

    try:
        rating = int(request.form.get("rating", 0))
    except ValueError:
        rating = 0
    if rating not in range(1, 6):
        flash("Please select a rating between 1 and 5 stars.", "danger")
        return redirect(url_for("complaint.details", cid=cid))

    try:
        # Unique index on feedback.complaint_id blocks a second submission
        db.feedback.insert_one({
            "complaint_id": cid,
            "student_id": session["login_id"],
            "rating": rating,
            "comment": clean(request.form.get("comment"), 1000),
            "created_at": now(),
        })
    except DuplicateKeyError:
        flash("You have already submitted feedback for this complaint.", "warning")
        return redirect(url_for("complaint.details", cid=cid))

    db.complaints.update_one({"complaint_id": cid},
                             {"$set": {"feedback_given": True, "feedback_rating": rating}})
    flash("Thank you! Your feedback has been recorded.", "success")
    return redirect(url_for("complaint.details", cid=cid))


@feedback_bp.route("/admin/feedback")
@staff_required
def overview():
    return render_template("admin/feedback.html", summary=feedback_summary(),
                           by_department=rating_by_department(),
                           recent=recent_feedback(25))
