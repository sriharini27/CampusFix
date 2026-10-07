"""QR code complaint reporting — campus locations with printable QR codes (staff/admin)."""
from urllib.parse import quote

import qrcode
import qrcode.image.svg
from flask import (Blueprint, render_template, request, redirect, url_for, flash, abort,
                   current_app, Response)
from markupsafe import Markup
from pymongo.errors import DuplicateKeyError

from utils.auth import staff_required, admin_required
from utils.database import get_db
from utils.analytics import location_counts
from utils.helpers import clean, slugify, now

location_bp = Blueprint("location", __name__, url_prefix="/admin/locations")


def report_url(name):
    """The URL a QR code opens: <base>/complaints/new?location=Computer%20Lab%203"""
    base = current_app.config["PUBLIC_BASE_URL"] or request.host_url.rstrip("/")
    return f"{base}{url_for('complaint.submit')}?location={quote(name)}"


def qr_svg(data):
    """Generate the QR code locally with the `qrcode` library (SVG — no Pillow, no external service)."""
    img = qrcode.make(data, image_factory=qrcode.image.svg.SvgPathImage, box_size=10, border=2)
    return img.to_string(encoding="unicode")


def location_list(only_active=False):
    counts = location_counts()
    query = {"active": True} if only_active else {}
    rows = list(get_db().locations.find(query).sort("name", 1))
    for loc in rows:
        c = counts.get(loc["name"], {})
        loc.update(total=c.get("total", 0), open=c.get("open", 0), via_qr=c.get("via_qr", 0),
                   url=report_url(loc["name"]), svg=Markup(qr_svg(report_url(loc["name"]))))
    return rows


@location_bp.route("/")
@staff_required
def locations():
    return render_template("admin/locations.html", locations=location_list())


@location_bp.route("/print")
@staff_required
def print_sheet():
    """Printable A4 sheet: all active locations, or one with ?slug=computer-lab-3"""
    rows = location_list(only_active=True)
    slug = request.args.get("slug")
    if slug:
        rows = [r for r in rows if r["slug"] == slug] or abort(404)
    return render_template("admin/qr_print.html", locations=rows)


@location_bp.route("/<slug>/qr.svg")
@staff_required
def download(slug):
    loc = get_db().locations.find_one({"slug": slug}) or abort(404)
    return Response(qr_svg(report_url(loc["name"])), mimetype="image/svg+xml",
                    headers={"Content-Disposition": f'attachment; filename="campusfix-qr-{slug}.svg"'})


@location_bp.route("/save", methods=["POST"])
@admin_required
def save():
    name = clean(request.form.get("name"), 60)
    desc = clean(request.form.get("description"), 120)
    if len(name) < 2:
        flash("Location name is required.", "danger")
        return redirect(url_for("location.locations"))
    try:
        get_db().locations.insert_one({"name": name, "slug": slugify(name), "description": desc,
                                       "active": True, "created_at": now()})
        flash(f"Location '{name}' added. Its QR code is ready to print.", "success")
    except DuplicateKeyError:
        flash(f"A location named '{name}' already exists.", "danger")
    return redirect(url_for("location.locations"))


@location_bp.route("/toggle", methods=["POST"])
@admin_required
def toggle():
    loc = get_db().locations.find_one({"slug": request.form.get("slug", "")}) or abort(404)
    get_db().locations.update_one({"_id": loc["_id"]}, {"$set": {"active": not loc.get("active", True)}})
    flash(f"Location '{loc['name']}' {'disabled' if loc.get('active', True) else 'enabled'}.", "info")
    return redirect(url_for("location.locations"))
