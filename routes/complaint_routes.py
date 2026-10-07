"""Module 1 — Complaint Management (students submit, list, track, view, reopen)."""
import re

from flask import Blueprint, render_template, request, redirect, url_for, flash, session, abort
from pymongo.errors import DuplicateKeyError

from utils.auth import student_required
from utils.database import get_db
from utils.duplicates import find_duplicates
from utils.helpers import (CATEGORIES, PRIORITIES, STATUSES, OPEN_STATUSES, TRANSITIONS, enrich,
                           next_complaint_id, save_attachment, pending_attachment, clean, now,
                           suggest_department)
from utils.notifications import notify, admin_ids, staff_ids_in

complaint_bp = Blueprint("complaint", __name__, url_prefix="/complaints")


def active_locations():
    return [l["name"] for l in get_db().locations.find({"active": True}, {"name": 1}).sort("name", 1)]


def render_form(form, **extra):
    return render_template("student/submit_complaint.html", form=form, categories=CATEGORIES,
                           priorities=PRIORITIES, locations=active_locations(), **extra)


@complaint_bp.route("/new", methods=["GET", "POST"])
@student_required
def submit():
    if request.method == "GET":
        form = {}
        # QR code links look like /complaints/new?location=Computer%20Lab%203
        qr_loc = clean(request.args.get("location"), 120)
        if qr_loc:
            loc = get_db().locations.find_one(
                {"name": {"$regex": "^" + re.escape(qr_loc) + "$", "$options": "i"}, "active": True})
            if loc:
                form = {"location": loc["name"], "reported_via": "qr"}
            else:
                flash("The scanned location was not recognised. Please type the location.", "warning")
        return render_form(form)

    form = {
        "title": clean(request.form.get("title"), 120),
        "description": clean(request.form.get("description"), 2000),
        "category": request.form.get("category", ""),
        "location": clean(request.form.get("location"), 120),
        "priority": request.form.get("priority", ""),
        "reported_via": "qr" if request.form.get("reported_via") == "qr" else "web",
    }
    errors = []
    if len(form["title"]) < 5:
        errors.append("Title must be at least 5 characters.")
    if len(form["description"]) < 10:
        errors.append("Description must be at least 10 characters.")
    if form["category"] not in CATEGORIES:
        errors.append("Please choose a valid category.")
    if form["priority"] not in PRIORITIES:
        errors.append("Please choose a valid priority.")
    if not form["location"]:
        errors.append("Location is required.")

    # A file chosen before the duplicate warning is kept, so the student need not re-upload it
    attachment = pending_attachment(request.form.get("pending_attachment"))
    if not errors and not attachment:
        attachment, err = save_attachment(request.files.get("attachment"))
        if err:
            errors.append(err)
    if errors:
        for e in errors:
            flash(e, "danger")
        return render_form(form)

    # ---- Smart duplicate detection (assistance only — never blocks the student) ----
    duplicates = find_duplicates(form)
    if duplicates and request.form.get("confirm_duplicate") != "1":
        return render_form(form, duplicates=[enrich(d) for d in duplicates], pending=attachment)

    ts = now()
    doc = {
        **form,
        "student_id": session["login_id"],
        "student_name": session["name"],
        "status": "Submitted",
        "department": None,
        "assigned_staff": None,
        "attachment": attachment,
        "created_at": ts,
        "updated_at": ts,
        "resolved_at": None,
        "resolution_remarks": "",
        "feedback_given": False,
        "reopen_count": 0,
        "supporters": [],
        "possible_duplicates": [d["complaint_id"] for d in duplicates],
        # Embedded documents: the full workflow history lives inside the complaint
        "status_history": [{
            "from_status": None,
            "status": "Submitted",
            "changed_by": session["login_id"],
            "changed_by_name": session["name"],
            "remarks": "Complaint submitted by student" + (" (via QR code)" if form["reported_via"] == "qr" else ""),
            "timestamp": ts,
        }],
    }
    for _ in range(3):  # unique index on complaint_id -> retry on the rare duplicate
        doc["complaint_id"] = next_complaint_id()
        try:
            get_db().complaints.insert_one(doc)
            break
        except DuplicateKeyError:
            doc.pop("_id", None)
    else:
        flash("Could not generate a unique complaint ID. Please try again.", "danger")
        return render_form(form)

    cid = doc["complaint_id"]
    notify([session["login_id"]], "Complaint submitted",
           f"{cid} \"{doc['title']}\" was received and is waiting for review.", "submitted", cid, skip_self=False)
    staff = admin_ids() + staff_ids_in(suggest_department(doc["category"]))
    if doc["priority"] == "Critical":
        notify(staff, "Critical complaint submitted",
               f"{cid} at {doc['location']}: \"{doc['title']}\" needs urgent attention.", "critical", cid)
    else:
        notify(staff, "New complaint",
               f"{cid} ({doc['priority']}, {doc['category']}) at {doc['location']}: \"{doc['title']}\".", "new", cid)

    flash(f"Complaint {cid} submitted successfully!", "success")
    return redirect(url_for("complaint.details", cid=cid))


@complaint_bp.route("/mine")
@student_required
def my_complaints():
    query = {"student_id": session["login_id"]}
    status = request.args.get("status", "")
    category = request.args.get("category", "")
    q = clean(request.args.get("q"), 60)
    if status in STATUSES:
        query["status"] = status
    if category in CATEGORIES:
        query["category"] = category
    if q:
        rx = {"$regex": re.escape(q), "$options": "i"}
        query["$or"] = [{"title": rx}, {"complaint_id": rx}, {"location": rx}]
    complaints = [enrich(c) for c in get_db().complaints
                  .find(query, {"status_history": 0}).sort("created_at", -1)]
    return render_template("student/complaints.html", complaints=complaints,
                           statuses=STATUSES, categories=CATEGORIES,
                           f={"status": status, "category": category, "q": q})


@complaint_bp.route("/track", methods=["GET", "POST"])
@student_required
def track():
    """Track a complaint by its ID (students can only see their own)."""
    cid = clean(request.values.get("cid"), 20).upper()
    complaint = None
    if cid:
        complaint = get_db().complaints.find_one({"complaint_id": cid, "student_id": session["login_id"]})
        if complaint:
            complaint = enrich(complaint)
        else:
            flash(f"No complaint with ID {cid} was found in your account.", "warning")
    active = [enrich(c) for c in get_db().complaints.find(
        {"student_id": session["login_id"], "status": {"$nin": ["Closed", "Rejected"]}},
        {"status_history": 0}).sort("updated_at", -1).limit(6)]
    return render_template("student/track.html", cid=cid, complaint=complaint, active=active)


@complaint_bp.route("/<cid>")
@student_required
def details(cid):
    db = get_db()
    complaint = db.complaints.find_one({"complaint_id": cid})
    if not complaint:
        abort(404)
    is_owner = complaint["student_id"] == session["login_id"]
    # Other students may open an OPEN complaint (e.g. from the duplicate warning) in a limited view
    if not is_owner and complaint["status"] not in OPEN_STATUSES:
        abort(404)
    feedback = db.feedback.find_one({"complaint_id": cid}) if is_owner else None
    return render_template("student/complaint_details.html", c=enrich(complaint), feedback=feedback,
                           is_owner=is_owner,
                           can_reopen=is_owner and "Reopened" in TRANSITIONS.get(complaint["status"], []))


@complaint_bp.route("/<cid>/reopen", methods=["POST"])
@student_required
def reopen(cid):
    """Resolved -> Reopened, validated with the same TRANSITIONS state machine staff use."""
    db = get_db()
    c = db.complaints.find_one({"complaint_id": cid, "student_id": session["login_id"]})
    if not c:
        abort(404)
    reason = clean(request.form.get("reason"), 1000)
    if "Reopened" not in TRANSITIONS.get(c["status"], []):
        flash(f"A complaint that is {c['status']} cannot be reopened.", "warning")
    elif len(reason) < 10:
        flash("Please explain why you are reopening the complaint (at least 10 characters).", "danger")
    else:
        ts = now()
        db.complaints.update_one({"_id": c["_id"]}, {
            "$set": {"status": "Reopened", "resolved_at": None, "updated_at": ts, "overdue_notified": False},
            "$inc": {"reopen_count": 1},
            "$push": {"status_history": {
                "from_status": c["status"], "status": "Reopened",
                "changed_by": session["login_id"], "changed_by_name": session["name"],
                "remarks": f"Reopened by student: {reason}", "timestamp": ts}},
        })
        notify([session["login_id"]], "Complaint reopened",
               f"{cid} was reopened. The team has been informed.", "reopened", cid, skip_self=False)
        staff = admin_ids() + ([c["assigned_staff"]["login_id"]] if c.get("assigned_staff") else [])
        notify(staff, "Complaint reopened by student",
               f"{cid} \"{c['title']}\" was reopened: {reason[:120]}", "reopened", cid)
        flash("Complaint reopened. The resolution team has been notified.", "success")
    return redirect(url_for("complaint.details", cid=cid))


@complaint_bp.route("/<cid>/support", methods=["POST"])
@student_required
def support(cid):
    """'I'm facing this too' — $addToSet keeps one vote per student."""
    c = get_db().complaints.find_one({"complaint_id": cid, "status": {"$in": OPEN_STATUSES}})
    if not c:
        abort(404)
    if c["student_id"] == session["login_id"]:
        flash("This is your own complaint.", "info")
    else:
        get_db().complaints.update_one({"_id": c["_id"]}, {"$addToSet": {"supporters": session["login_id"]}})
        flash("Thanks! We've recorded that you are facing this issue too — no need for a new complaint.", "success")
    return redirect(url_for("complaint.details", cid=cid))
