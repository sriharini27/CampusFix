"""Module 2 — Resolution & Department Management (staff/admin)."""
import re
from datetime import datetime, timedelta

from flask import Blueprint, render_template, request, redirect, url_for, flash, session, abort
from pymongo.errors import DuplicateKeyError

from utils.auth import staff_required, admin_required
from utils.database import get_db
from utils.analytics import (status_counts, overdue_count, department_overview, feedback_summary,
                             sla_summary)
from utils.helpers import (CATEGORIES, PRIORITIES, STATUSES, OPEN_STATUSES, TRANSITIONS,
                           enrich, overdue_query, approaching_query, suggest_department, clean, now)
from utils.notifications import notify, admin_ids

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


def get_complaint_or_404(cid):
    c = get_db().complaints.find_one({"complaint_id": cid})
    if not c:
        abort(404)
    return c


def history_entry(old, new, remarks):
    return {
        "from_status": old, "status": new,
        "changed_by": session["login_id"], "changed_by_name": session["name"],
        "remarks": remarks, "timestamp": now(),
    }


# ---------------- Dashboard ----------------
@admin_bp.route("/dashboard")
@staff_required
def dashboard():
    db = get_db()
    counts = status_counts()
    stats = {
        "total": sum(counts.values()),
        "new": counts["Submitted"],
        "review": counts["Under Review"],
        "assigned": counts["Assigned"],
        "progress": counts["In Progress"] + counts["Reopened"],
        "resolved": counts["Resolved"] + counts["Closed"],
        "rejected": counts["Rejected"],
        "high": db.complaints.count_documents(
            {"priority": {"$in": ["High", "Critical"]}, "status": {"$in": OPEN_STATUSES}}),
        "overdue": overdue_count(),
        "mine": db.complaints.count_documents(
            {"assigned_staff.login_id": session["login_id"], "status": {"$in": OPEN_STATUSES}}),
    }
    # Urgent queue: open Critical/High or overdue, oldest first
    urgent = [enrich(c) for c in db.complaints.find(
        {"$or": [{"priority": "Critical", "status": {"$in": OPEN_STATUSES}}, overdue_query()]},
        {"status_history": 0}).sort("created_at", 1).limit(6)]
    latest = [enrich(c) for c in db.complaints.find({}, {"status_history": 0})
              .sort("created_at", -1).limit(8)]
    return render_template("admin/dashboard.html", stats=stats, urgent=urgent, latest=latest,
                           feedback=feedback_summary(), sla=sla_summary())


# ---------------- Complaint list with search + filters ----------------
@admin_bp.route("/complaints")
@staff_required
def complaints():
    args = request.args
    query = {}
    f = {k: args.get(k, "") for k in ("q", "category", "priority", "status", "department",
                                     "date_from", "date_to", "view")}
    if f["category"] in CATEGORIES:
        query["category"] = f["category"]
    if f["priority"] in PRIORITIES:
        query["priority"] = f["priority"]
    if f["status"] in STATUSES:
        query["status"] = f["status"]
    if f["department"] == "Unassigned":
        query["department"] = None
    elif f["department"]:
        query["department"] = f["department"]
    date_q = {}
    try:
        if f["date_from"]:
            date_q["$gte"] = datetime.strptime(f["date_from"], "%Y-%m-%d")
        if f["date_to"]:
            date_q["$lt"] = datetime.strptime(f["date_to"], "%Y-%m-%d") + timedelta(days=1)
    except ValueError:
        flash("Invalid date filter ignored.", "warning")
        date_q = {}
    if date_q:
        query["created_at"] = date_q
    if f["q"]:
        rx = {"$regex": re.escape(clean(f["q"], 60)), "$options": "i"}
        query["$or"] = [{"complaint_id": rx}, {"title": rx}, {"description": rx},
                        {"location": rx}, {"student_id": rx}, {"student_name": rx}]
    if f["view"] == "overdue":
        query = {"$and": [query, overdue_query()]}
    elif f["view"] == "mine":
        query["assigned_staff.login_id"] = session["login_id"]
    elif f["view"] == "approaching":
        query = {"$and": [query, approaching_query()]}
    elif f["view"] == "urgent":
        query["priority"] = {"$in": ["High", "Critical"]}
        query["status"] = {"$in": OPEN_STATUSES}

    sort = args.get("sort", "newest")
    sort_spec = {"newest": [("created_at", -1)], "oldest": [("created_at", 1)],
                 "updated": [("updated_at", -1)]}.get(sort, [("created_at", -1)])
    rows = [enrich(c) for c in get_db().complaints.find(query, {"status_history": 0}).sort(sort_spec)]
    if sort == "priority":
        order = {p: i for i, p in enumerate(reversed(PRIORITIES))}
        rows.sort(key=lambda c: (order.get(c["priority"], 9), c["created_at"]))
    departments = [d["name"] for d in get_db().departments.find({}, {"name": 1}).sort("name", 1)]
    return render_template("admin/complaints.html", complaints=rows, f=f, sort=sort,
                           categories=CATEGORIES, priorities=PRIORITIES, statuses=STATUSES,
                           departments=departments)


# ---------------- Complaint details + workflow actions ----------------
@admin_bp.route("/complaints/<cid>")
@staff_required
def complaint_details(cid):
    db = get_db()
    c = enrich(get_complaint_or_404(cid))
    departments = list(db.departments.find({"active": True}).sort("name", 1))
    staff = list(db.users.find({"role": {"$in": ["staff", "admin"]}},
                               {"password_hash": 0}).sort("name", 1))
    student = db.users.find_one({"login_id": c["student_id"]}, {"password_hash": 0})
    feedback = db.feedback.find_one({"complaint_id": cid})
    supporters = list(db.users.find({"login_id": {"$in": c.get("supporters", [])}}, {"name": 1, "login_id": 1}))
    return render_template("admin/complaint_details.html", c=c, departments=departments, supporters=supporters,
                           staff=staff, student=student, feedback=feedback,
                           next_statuses=TRANSITIONS.get(c["status"], []),
                           suggested=suggest_department(c["category"]))


@admin_bp.route("/complaints/<cid>/assign", methods=["POST"])
@staff_required
def assign(cid):
    db = get_db()
    c = get_complaint_or_404(cid)
    if c["status"] in ("Resolved", "Closed", "Rejected"):
        flash("Finished complaints cannot be re-assigned. Re-open it first.", "warning")
        return redirect(url_for("admin.complaint_details", cid=cid))

    dept = request.form.get("department", "")
    staff_id = request.form.get("staff", "")
    remarks = clean(request.form.get("remarks"), 500)
    if not db.departments.find_one({"name": dept, "active": True}):
        flash("Please select a valid department.", "danger")
        return redirect(url_for("admin.complaint_details", cid=cid))

    staff = None
    if staff_id:
        u = db.users.find_one({"login_id": staff_id, "role": {"$in": ["staff", "admin"]}})
        if not u:
            flash("Selected staff member does not exist.", "danger")
            return redirect(url_for("admin.complaint_details", cid=cid))
        staff = {"login_id": u["login_id"], "name": u["name"], "department": u.get("department")}

    who = f" to {staff['name']}" if staff else ""
    note = remarks or f"Assigned to {dept} department{who}"
    update = {"$set": {"department": dept, "assigned_staff": staff, "updated_at": now()}}
    # Move the workflow forward automatically when a complaint is first assigned
    if c["status"] in ("Submitted", "Under Review"):
        update["$set"]["status"] = "Assigned"
        update["$push"] = {"status_history": history_entry(c["status"], "Assigned", note)}
    else:
        update["$push"] = {"status_history": history_entry(c["status"], c["status"], note)}
    db.complaints.update_one({"complaint_id": cid}, update)

    # ---- notifications ----
    old_staff = (c.get("assigned_staff") or {}).get("login_id")
    reassigned = bool(c.get("department")) and (c["department"] != dept or old_staff != (staff or {}).get("login_id"))
    notify([c["student_id"]], "Complaint reassigned" if reassigned else "Complaint assigned",
           f"{cid} is now handled by the {dept} department{who}.", "assigned", cid)
    if staff:
        notify([staff["login_id"]], "Complaint assigned to you",
               f"{cid} ({c['priority']}) \"{c['title']}\" at {c['location']}.", "assigned", cid)
    if reassigned:
        notify(admin_ids() + [old_staff], "Complaint reassigned",
               f"{cid} moved to {dept}{who} by {session['name']}.", "reassigned", cid)
    flash(f"Complaint assigned to {dept}{who}.", "success")
    return redirect(url_for("admin.complaint_details", cid=cid))


@admin_bp.route("/complaints/<cid>/status", methods=["POST"])
@staff_required
def update_status(cid):
    db = get_db()
    c = get_complaint_or_404(cid)
    new = request.form.get("status", "")
    remarks = clean(request.form.get("remarks"), 1000)

    if new not in TRANSITIONS.get(c["status"], []):
        flash(f"Invalid transition: {c['status']} → {new or '?'}.", "danger")
        return redirect(url_for("admin.complaint_details", cid=cid))
    if new in ("Assigned", "In Progress") and not c.get("department"):
        flash("Assign a department before moving to this status.", "warning")
        return redirect(url_for("admin.complaint_details", cid=cid))
    if new in ("Resolved", "Rejected") and not remarks:
        flash(f"Remarks are required when marking a complaint {new}.", "danger")
        return redirect(url_for("admin.complaint_details", cid=cid))

    ts = now()
    fields = {"status": new, "updated_at": ts}
    if new in ("Resolved", "Rejected"):
        fields["resolved_at"] = ts
        fields["resolution_remarks"] = remarks
    elif new in OPEN_STATUSES:            # re-opened -> clear the resolution time
        fields["resolved_at"] = None
    if new == "Reopened":
        fields["overdue_notified"] = False
    db.complaints.update_one({"complaint_id": cid}, {
        "$set": fields,
        "$push": {"status_history": history_entry(c["status"], new, remarks or f"Status changed to {new}")},
    })
    # ---- notifications for the student ----
    sid = c["student_id"]
    if new == "Resolved":
        notify([sid], "Complaint resolved", f"{cid} was resolved: {remarks[:150]}", "resolved", cid)
        notify([sid], "Feedback requested", f"How did we do on {cid}? Please rate the resolution.", "feedback", cid)
    elif new == "Reopened":
        notify([sid], "Complaint reopened", f"{cid} was reopened by {session['name']}.", "reopened", cid)
    else:
        notify([sid], "Status updated", f"{cid}: {c['status']} → {new}." + (f" {remarks[:120]}" if remarks else ""),
               "status", cid)
    flash(f"Status updated: {c['status']} → {new}.", "success")
    return redirect(url_for("admin.complaint_details", cid=cid))


@admin_bp.route("/complaints/<cid>/remark", methods=["POST"])
@staff_required
def add_remark(cid):
    """Add a progress note to the timeline without changing status."""
    c = get_complaint_or_404(cid)
    remarks = clean(request.form.get("remarks"), 1000)
    if not remarks:
        flash("Remark cannot be empty.", "danger")
    else:
        get_db().complaints.update_one({"complaint_id": cid}, {
            "$set": {"updated_at": now(), "resolution_remarks": remarks},
            "$push": {"status_history": history_entry(c["status"], c["status"], remarks)},
        })
        flash("Remark added to the timeline.", "success")
    return redirect(url_for("admin.complaint_details", cid=cid))


# ---------------- Departments ----------------
@admin_bp.route("/departments")
@staff_required
def departments():
    db = get_db()
    depts = list(db.departments.find().sort("name", 1))
    overview = department_overview()
    staff_counts = {r["_id"]: r["n"] for r in db.users.aggregate([
        {"$match": {"role": {"$in": ["staff", "admin"]}}},
        {"$group": {"_id": "$department", "n": {"$sum": 1}}}])}
    for d in depts:
        o = overview.get(d["name"], {})
        d.update(total=o.get("total", 0), open=o.get("open", 0), resolved=o.get("resolved", 0),
                 staff=staff_counts.get(d["name"], 0))
    return render_template("admin/departments.html", departments=depts, categories=CATEGORIES)


@admin_bp.route("/departments/save", methods=["POST"])
@admin_required
def save_department():
    db = get_db()
    original = request.form.get("original", "")
    name = clean(request.form.get("name"), 60)
    desc = clean(request.form.get("description"), 200)
    cats = [c for c in request.form.getlist("categories") if c in CATEGORIES]
    if len(name) < 2:
        flash("Department name is required.", "danger")
        return redirect(url_for("admin.departments"))
    try:
        if original:
            db.departments.update_one({"name": original},
                                      {"$set": {"name": name, "description": desc, "categories": cats}})
            if original != name:  # keep denormalised department names consistent
                db.complaints.update_many({"department": original}, {"$set": {"department": name}})
                db.users.update_many({"department": original}, {"$set": {"department": name}})
            flash(f"Department '{name}' updated.", "success")
        else:
            db.departments.insert_one({"name": name, "description": desc, "categories": cats,
                                       "active": True, "created_at": now()})
            flash(f"Department '{name}' created.", "success")
    except DuplicateKeyError:
        flash(f"A department named '{name}' already exists.", "danger")
    return redirect(url_for("admin.departments"))


@admin_bp.route("/departments/toggle", methods=["POST"])
@admin_required
def toggle_department():
    name = request.form.get("name", "")
    d = get_db().departments.find_one({"name": name})
    if d:
        get_db().departments.update_one({"_id": d["_id"]}, {"$set": {"active": not d.get("active", True)}})
        flash(f"Department '{name}' {'deactivated' if d.get('active', True) else 'activated'}.", "info")
    return redirect(url_for("admin.departments"))
