"""CampusFix — Smart Campus Complaint & Resolution System (Flask + MongoDB)."""
import secrets

from flask import Flask, render_template, session, request, abort
from pymongo.errors import PyMongoError, ServerSelectionTimeoutError

from config import Config
from utils.database import init_db
from utils import helpers
from routes.auth_routes import auth_bp, init_oauth
from routes.student_routes import student_bp
from routes.complaint_routes import complaint_bp
from routes.admin_routes import admin_bp
from routes.analytics_routes import analytics_bp
from routes.feedback_routes import feedback_bp
from routes.location_routes import location_bp
from routes.notification_routes import notification_bp
from utils import notifications


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)
    init_db(app)
    init_oauth(app)

    for bp in (auth_bp, student_bp, complaint_bp, admin_bp, analytics_bp, feedback_bp,
               location_bp, notification_bp):
        app.register_blueprint(bp)

    # ---------- CSRF protection for every POST form ----------
    def csrf_token():
        if "_csrf" not in session:
            session["_csrf"] = secrets.token_hex(16)
        return session["_csrf"]

    @app.before_request
    def check_csrf():
        if request.method == "POST":
            token = request.form.get("_csrf")
            if not token or token != session.get("_csrf"):
                abort(400, description="Your form session expired. Please reload the page and try again.")

    @app.before_request
    def overdue_watch():
        # Generates "complaint overdue" notifications while staff/admin use the app
        if session.get("role") in ("staff", "admin") and request.endpoint != "static":
            notifications.check_overdue_notifications()

    # ---------- Values available in every template ----------
    @app.context_processor
    def inject_globals():
        bell = {"count": 0, "items": []}
        if session.get("login_id") and request.endpoint != "static":
            try:
                bell = {"count": notifications.unread_count(session["login_id"]),
                        "items": notifications.latest(session["login_id"])}
            except PyMongoError:
                pass
        return {
            "bell": bell,
            "NOTIF_ICONS": notifications.ICONS,
            "csrf_token": csrf_token,
            "STATUS_BADGE": helpers.STATUS_BADGE,
            "PRIORITY_BADGE": helpers.PRIORITY_BADGE,
            "RATING_LABELS": helpers.RATING_LABELS,
            "WORKFLOW": helpers.WORKFLOW,
        }

    @app.template_filter("dt")
    def format_datetime(value, fmt="%d %b %Y, %I:%M %p"):
        return value.strftime(fmt) if value else "—"

    # ---------- Friendly error pages ----------
    @app.errorhandler(400)
    def bad_request(e):
        return render_template("errors/error.html", code=400, title="Bad Request",
                               message=e.description), 400

    @app.errorhandler(403)
    def forbidden(e):
        return render_template("errors/error.html", code=403, title="Access Denied",
                               message="You are not authorised to view this page."), 403

    @app.errorhandler(404)
    def not_found(e):
        return render_template("errors/error.html", code=404, title="Not Found",
                               message="The page or complaint you requested does not exist."), 404

    @app.errorhandler(413)
    def too_large(e):
        return render_template("errors/error.html", code=413, title="File Too Large",
                               message="Attachments must be smaller than 5 MB."), 413

    @app.errorhandler(ServerSelectionTimeoutError)
    @app.errorhandler(PyMongoError)
    def db_error(e):
        app.logger.error("Database error: %s", e)
        return render_template("errors/error.html", code=503, title="Service Unavailable",
                               message="CampusFix is temporarily unavailable. Please try again in a moment."), 503

    @app.errorhandler(500)
    def server_error(e):
        return render_template("errors/error.html", code=500, title="Something went wrong",
                               message="An unexpected error occurred. Please try again."), 500

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host=app.config["HOST"], port=app.config["PORT"], debug=app.config["DEBUG"])
