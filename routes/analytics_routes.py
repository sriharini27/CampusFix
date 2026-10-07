"""Module 3 — Smart Analytics (all numbers come from MongoDB aggregations)."""
from flask import Blueprint, render_template, jsonify

from utils.auth import staff_required
from utils.analytics import full_analytics

analytics_bp = Blueprint("analytics", __name__, url_prefix="/admin/analytics")


@analytics_bp.route("/")
@staff_required
def analytics():
    return render_template("admin/analytics.html", data=full_analytics())


@analytics_bp.route("/data")
@staff_required
def analytics_data():
    """JSON API consumed by Chart.js (fetch) — refreshes charts without reloading."""
    return jsonify(full_analytics())
