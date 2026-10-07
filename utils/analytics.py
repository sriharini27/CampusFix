"""All MongoDB aggregation pipelines used by dashboards, analytics and feedback."""
from datetime import timedelta

from flask import current_app

from utils.database import get_db
from utils.helpers import (CATEGORIES, PRIORITIES, STATUSES, OPEN_STATUSES,
                           now, overdue_query, approaching_query)

DAY_MS = 86400000


def count_by(field, match=None):
    """$match -> $group -> $sort : returns {value: count}."""
    pipeline = [
        {"$match": match or {}},
        {"$group": {"_id": f"${field}", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]
    return {(r["_id"] or "Unassigned"): r["count"]
            for r in get_db().complaints.aggregate(pipeline)}


def status_counts(match=None):
    counts = count_by("status", match)
    return {s: counts.get(s, 0) for s in STATUSES}


def complaints_over_time(days=14):
    """Daily submissions for the last N days using $dateToString."""
    start = (now() - timedelta(days=days - 1)).replace(hour=0, minute=0, second=0)
    pipeline = [
        {"$match": {"created_at": {"$gte": start}}},
        {"$group": {"_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$created_at"}},
                    "count": {"$sum": 1}}},
        {"$sort": {"_id": 1}},
    ]
    found = {r["_id"]: r["count"] for r in get_db().complaints.aggregate(pipeline)}
    labels = [(start + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(days)]
    return labels, [found.get(d, 0) for d in labels]


def resolution_stats():
    """$project the resolution time in hours, then $group for avg/min/max."""
    pipeline = [
        {"$match": {"resolved_at": {"$ne": None}, "status": {"$in": ["Resolved", "Closed"]}}},
        {"$project": {"hours": {"$divide": [{"$subtract": ["$resolved_at", "$created_at"]}, 3600000]}}},
        {"$group": {"_id": None, "avg": {"$avg": "$hours"}, "min": {"$min": "$hours"},
                    "max": {"$max": "$hours"}, "count": {"$sum": 1}}},
    ]
    res = list(get_db().complaints.aggregate(pipeline))
    if not res:
        return {"avg": 0, "min": 0, "max": 0, "count": 0}
    r = res[0]
    return {k: round(r[k] or 0, 1) for k in ("avg", "min", "max")} | {"count": r["count"]}


def avg_resolution_by_department():
    pipeline = [
        {"$match": {"resolved_at": {"$ne": None}, "department": {"$ne": None}}},
        {"$project": {"department": 1,
                      "hours": {"$divide": [{"$subtract": ["$resolved_at", "$created_at"]}, 3600000]}}},
        {"$group": {"_id": "$department", "avg": {"$avg": "$hours"}, "count": {"$sum": 1}}},
        {"$sort": {"avg": 1}},
    ]
    return [{"department": r["_id"], "avg": round(r["avg"], 1), "count": r["count"]}
            for r in get_db().complaints.aggregate(pipeline)]


def overdue_count():
    return get_db().complaints.count_documents(overdue_query())


# ---------------- Feedback ----------------
def feedback_summary():
    db = get_db()
    res = list(db.feedback.aggregate([
        {"$group": {"_id": None, "avg": {"$avg": "$rating"}, "count": {"$sum": 1}}}
    ]))
    dist = {r["_id"]: r["count"] for r in db.feedback.aggregate([
        {"$group": {"_id": "$rating", "count": {"$sum": 1}}}, {"$sort": {"_id": 1}}])}
    return {
        "avg": round(res[0]["avg"] or 0, 2) if res else 0,
        "count": res[0]["count"] if res else 0,
        "distribution": [dist.get(i, 0) for i in range(1, 6)],
    }


def rating_by_department():
    """$lookup joins feedback with its complaint to rate each department."""
    pipeline = [
        {"$lookup": {"from": "complaints", "localField": "complaint_id",
                     "foreignField": "complaint_id", "as": "complaint"}},
        {"$unwind": "$complaint"},
        {"$group": {"_id": "$complaint.department", "avg": {"$avg": "$rating"},
                    "count": {"$sum": 1}}},
        {"$sort": {"avg": -1}},
    ]
    return [{"department": r["_id"] or "Unassigned", "avg": round(r["avg"], 2), "count": r["count"]}
            for r in get_db().feedback.aggregate(pipeline)]


def recent_feedback(limit=10):
    """$lookup complaint title + student name for each feedback entry."""
    pipeline = [
        {"$sort": {"created_at": -1}},
        {"$limit": limit},
        {"$lookup": {"from": "complaints", "localField": "complaint_id",
                     "foreignField": "complaint_id", "as": "complaint"}},
        {"$lookup": {"from": "users", "localField": "student_id",
                     "foreignField": "login_id", "as": "student"}},
        {"$project": {"complaint_id": 1, "rating": 1, "comment": 1, "created_at": 1,
                      "complaint": {"$arrayElemAt": ["$complaint", 0]},
                      "student": {"$arrayElemAt": ["$student", 0]}}},
    ]
    return list(get_db().feedback.aggregate(pipeline))


def department_overview():
    """Per-department totals using $cond inside $group."""
    pipeline = [
        {"$match": {"department": {"$ne": None}}},
        {"$group": {
            "_id": "$department",
            "total": {"$sum": 1},
            "open": {"$sum": {"$cond": [{"$in": ["$status", OPEN_STATUSES]}, 1, 0]}},
            "resolved": {"$sum": {"$cond": [{"$in": ["$status", ["Resolved", "Closed"]]}, 1, 0]}},
        }},
    ]
    return {r["_id"]: r for r in get_db().complaints.aggregate(pipeline)}


# ---------------- SLA monitoring ----------------
def sla_stages():
    """Pipeline stages that add `breached` to every non-rejected complaint.
    elapsed = (resolved_at or now) - created_at ;  breached = elapsed > SLA days in ms."""
    days = current_app.config["OVERDUE_DAYS"]
    sla_days = {"$switch": {"branches": [{"case": {"$eq": ["$priority", p]}, "then": d}
                                         for p, d in days.items()], "default": 7}}
    return [
        {"$match": {"status": {"$ne": "Rejected"}}},
        {"$addFields": {
            "sla_ms": {"$multiply": [sla_days, DAY_MS]},
            "elapsed_ms": {"$subtract": [{"$ifNull": ["$resolved_at", now()]}, "$created_at"]},
            "is_open": {"$in": ["$status", OPEN_STATUSES]},
            "is_resolved": {"$in": ["$status", ["Resolved", "Closed"]]},
        }},
        {"$addFields": {"breached": {"$gt": ["$elapsed_ms", "$sla_ms"]}}},
    ]


def sla_summary():
    pipeline = sla_stages() + [{"$group": {
        "_id": None,
        "total": {"$sum": 1},
        "breached": {"$sum": {"$cond": ["$breached", 1, 0]}},
        "critical": {"$sum": {"$cond": [{"$and": ["$breached", {"$eq": ["$priority", "Critical"]}]}, 1, 0]}},
    }}]
    r = (list(get_db().complaints.aggregate(pipeline)) or [{"total": 0, "breached": 0, "critical": 0}])[0]
    total = r["total"]
    return {
        "breached": r["breached"],
        "critical_breached": r["critical"],
        "approaching": get_db().complaints.count_documents(approaching_query()),
        "compliance": round((total - r["breached"]) / total * 100, 1) if total else 100.0,
    }


# ---------------- Department performance ----------------
def department_performance():
    """One $group per department, then a transparent score (0-100) computed in Python:
    30% resolution rate + 35% SLA compliance + 25% student rating + 10% overdue backlog."""
    pipeline = [{"$match": {"department": {"$ne": None}}}] + sla_stages() + [
        {"$addFields": {"hours": {"$cond": [
            {"$and": ["$is_resolved", {"$ne": ["$resolved_at", None]}]},
            {"$divide": [{"$subtract": ["$resolved_at", "$created_at"]}, 3600000]}, None]}}},
        {"$group": {
            "_id": "$department",
            "total": {"$sum": 1},
            "resolved": {"$sum": {"$cond": ["$is_resolved", 1, 0]}},
            "open": {"$sum": {"$cond": ["$is_open", 1, 0]}},
            "overdue": {"$sum": {"$cond": [{"$and": ["$is_open", "$breached"]}, 1, 0]}},
            "breached": {"$sum": {"$cond": ["$breached", 1, 0]}},
            "avg_hours": {"$avg": "$hours"},
        }},
    ]
    stats = {r["_id"]: r for r in get_db().complaints.aggregate(pipeline)}
    ratings = {r["department"]: r for r in rating_by_department()}
    rows = []
    for d in get_db().departments.find({}, {"name": 1}).sort("name", 1):
        s = stats.get(d["name"], {})
        total = s.get("total", 0)
        rating = ratings.get(d["name"])
        row = {"department": d["name"], "total": total, "resolved": s.get("resolved", 0),
               "open": s.get("open", 0), "overdue": s.get("overdue", 0),
               "avg_hours": round(s["avg_hours"], 1) if s.get("avg_hours") is not None else None,
               "avg_rating": rating["avg"] if rating else None, "score": None,
               "sla": round((total - s.get("breached", 0)) / total * 100, 1) if total else None}
        if total:
            rating_part = (rating["avg"] / 5) if rating else 0.6      # neutral 3/5 until rated
            backlog = 1 - row["overdue"] / row["open"] if row["open"] else 1
            row["score"] = round(100 * (0.30 * row["resolved"] / total + 0.35 * row["sla"] / 100
                                        + 0.25 * rating_part + 0.10 * backlog), 1)
        rows.append(row)
    rows.sort(key=lambda r: (r["score"] is None, -(r["score"] or 0)))
    for i, r in enumerate(rows, 1):
        r["rank"] = i if r["score"] is not None else None
    return rows


def location_counts():
    """Complaints per campus location (used by the QR locations page)."""
    pipeline = [
        {"$group": {"_id": "$location", "total": {"$sum": 1},
                    "open": {"$sum": {"$cond": [{"$in": ["$status", OPEN_STATUSES]}, 1, 0]}},
                    "via_qr": {"$sum": {"$cond": [{"$eq": ["$reported_via", "qr"]}, 1, 0]}}}},
    ]
    return {r["_id"]: r for r in get_db().complaints.aggregate(pipeline)}


def full_analytics():
    """Everything the analytics page + Chart.js needs, in one JSON-able dict."""
    db = get_db()
    total = db.complaints.count_documents({})
    statuses = status_counts()
    resolved = statuses["Resolved"] + statuses["Closed"]
    unresolved = sum(statuses[s] for s in OPEN_STATUSES)
    cat = count_by("category")
    pri = count_by("priority")
    labels, series = complaints_over_time()
    return {
        "total": total,
        "resolved": resolved,
        "unresolved": unresolved,
        "rejected": statuses["Rejected"],
        "overdue": overdue_count(),
        "resolution": resolution_stats(),
        "resolution_rate": round(resolved / total * 100, 1) if total else 0,
        "by_status": statuses,
        "by_category": {c: cat.get(c, 0) for c in CATEGORIES},
        "by_priority": {p: pri.get(p, 0) for p in PRIORITIES},
        "by_department": count_by("department"),
        "dept_resolution": avg_resolution_by_department(),
        "timeline": {"labels": labels, "values": series},
        "feedback": feedback_summary(),
        "rating_by_department": rating_by_department(),
        "sla": sla_summary(),
        "performance": department_performance(),
    }
