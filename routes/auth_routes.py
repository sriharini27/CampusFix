"""Authentication (basic setup): password login, Google login (students), logout, profile."""
import re

from authlib.integrations.flask_client import OAuth
from bson import ObjectId
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, current_app
from pymongo.errors import DuplicateKeyError
from werkzeug.security import check_password_hash, generate_password_hash

from utils.database import get_db
from utils.auth import login_user, login_required, is_college_email, college_domain
from utils.helpers import safe_next, now
from utils.notifications import notify

auth_bp = Blueprint("auth", __name__)
oauth = OAuth()

INVALID_LOGIN = "Invalid ID/email or password."


def init_oauth(app):
    """Register Google's OpenID Connect client. Credentials come only from .env."""
    oauth.init_app(app)
    if app.config["GOOGLE_CLIENT_ID"] and app.config["GOOGLE_CLIENT_SECRET"]:
        oauth.register(
            name="google",
            client_id=app.config["GOOGLE_CLIENT_ID"],
            client_secret=app.config["GOOGLE_CLIENT_SECRET"],
            server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
            client_kwargs={"scope": "openid email profile", "prompt": "select_account"},
        )


def home_for(role):
    return url_for("student.dashboard") if role == "student" else url_for("admin.dashboard")


def finish_login(user, next_url=None):
    login_user(user)
    flash(f"Welcome, {user['name']}!", "success")
    return redirect(safe_next(next_url, user["role"]) or home_for(user["role"]))


@auth_bp.route("/")
def index():
    if "user_id" in session:
        return redirect(home_for(session["role"]))
    return redirect(url_for("auth.login"))


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if "user_id" in session:
        return redirect(home_for(session["role"]))

    portal = "staff" if request.values.get("portal") == "staff" else "student"
    next_url = request.values.get("next", "")
    if request.method == "POST":
        identifier = request.form.get("identifier", "").strip()[:100]
        password = request.form.get("password", "")
        if not identifier or not password:
            flash("Please enter your ID/email and password.", "danger")
            return render_template("login.html", portal=portal, next_url=next_url)

        # Student portal: an email must be an official college email. Checked BEFORE any database
        # lookup, so the message only depends on what was typed (never on whether an account exists).
        # Student IDs (no '@') and the Staff/Admin portal are unchanged.
        if portal == "student" and "@" in identifier and not is_college_email(identifier):
            flash(f"Please use your official college email ID ending with @{college_domain()}.", "danger")
            return render_template("login.html", portal=portal, next_url=next_url)

        allowed = ["student"] if portal == "student" else ["staff", "admin"]
        # Safe query: plain string values only, never operators taken from the user
        user = get_db().users.find_one({
            "$or": [{"login_id": identifier.upper()}, {"login_id": identifier},
                    {"email": identifier.lower()}],
            "role": {"$in": allowed},
        })
        # Same message whatever went wrong — never reveal if the ID exists or which role it has
        if not user or not user.get("password_hash") or \
                not check_password_hash(user["password_hash"], password):
            flash(INVALID_LOGIN, "danger")
            return render_template("login.html", portal=portal, next_url=next_url)
        return finish_login(user, next_url)

    return render_template("login.html", portal=portal, next_url=next_url)


# ---------------- Google OAuth 2.0 (students only) ----------------
@auth_bp.route("/auth/google")
def google_login():
    if "user_id" in session:
        return redirect(home_for(session["role"]))
    if oauth.create_client("google") is None:
        flash("Google sign-in is not available right now. Please use your Student ID and password.", "warning")
        return redirect(url_for("auth.login"))
    session["oauth_next"] = request.args.get("next", "")
    # No "hd" parameter: Google's normal account chooser lists ALL signed-in accounts
    # (prompt=select_account is set in init_oauth). The college domain is enforced in the callback.
    # Authlib stores a random `state` (CSRF) and `nonce` in the session and checks them on callback.
    return oauth.google.authorize_redirect(current_app.config["GOOGLE_REDIRECT_URI"])


@auth_bp.route("/auth/google/callback")
def google_callback():
    if oauth.create_client("google") is None:
        return redirect(url_for("auth.login"))
    next_url = session.pop("oauth_next", "")      # always consumed, even if this attempt fails
    try:
        token = oauth.google.authorize_access_token()     # verifies state + ID token signature/nonce
    except Exception as exc:                                # user cancelled, state mismatch, network…
        current_app.logger.warning("Google OAuth failed: %s", exc)
        flash("Google sign-in was cancelled or failed. Please try again.", "danger")
        return redirect(url_for("auth.login"))

    # Backend checks — ALL must pass before any lookup, linking, account creation or login:
    # 1. Google authentication succeeded (above)  2. email exists  3. verified by Google  4. exact college domain
    info = token.get("userinfo") or {}
    email = (info.get("email") or "").strip().lower()
    if not email or not info.get("sub") or info.get("email_verified") is not True:
        flash("Your Google account email could not be verified.", "danger")
        return redirect(url_for("auth.login"))
    if not is_college_email(email):
        current_app.logger.info("Rejected non-college Google account (domain %s)", email.rpartition("@")[2])
        flash(f"Please use your official college Google account ending with @{college_domain()}.", "danger")
        return redirect(url_for("auth.login"))

    db = get_db()
    user = db.users.find_one({"$or": [{"google_sub": info["sub"]}, {"email": email}]})
    if user and user["role"] != "student":
        flash("Google sign-in is available for students only. Please use the Staff / Admin login.", "warning")
        return redirect(url_for("auth.login", portal="staff"))

    if user:                                   # existing student -> link Google account and log in
        if not user.get("google_sub"):
            db.users.update_one({"_id": user["_id"]}, {"$set": {"google_sub": info["sub"]}})
        return finish_login(user, next_url)

    # New student -> create the account. Student ID = email prefix (e.g. 21cs045 -> 21CS045)
    base = re.sub(r"[^A-Za-z0-9]", "", email.split("@")[0]).upper()[:12] or "STUDENT"
    login_id, n = base, 1
    while db.users.find_one({"login_id": login_id}):
        n += 1
        login_id = f"{base}{n}"
    user = {
        "login_id": login_id, "student_id": login_id, "name": info.get("name") or login_id,
        "email": email, "password_hash": None, "role": "student", "department": None,
        "auth_provider": "google", "google_sub": info["sub"], "created_at": now(),
    }
    try:
        user["_id"] = db.users.insert_one(user).inserted_id
    except DuplicateKeyError:
        flash("Could not create your account. Please try again.", "danger")
        return redirect(url_for("auth.login"))
    login_user(user)
    notify([login_id], "Welcome to CampusFix",
           "Your student account was created with Google. You can now report campus issues.",
           "submitted", skip_self=False)
    flash(f"Welcome to CampusFix, {user['name']}! Your student account is ready.", "success")
    return redirect(safe_next(next_url, "student") or url_for("student.dashboard"))


@auth_bp.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("auth.login"))


@auth_bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    db = get_db()
    full = db.users.find_one({"_id": ObjectId(session["user_id"])})
    has_password = bool(full.get("password_hash"))

    if request.method == "POST":
        current = request.form.get("current_password", "")
        new = request.form.get("new_password", "")
        confirm = request.form.get("confirm_password", "")
        if has_password and not check_password_hash(full["password_hash"], current):
            flash("Current password is incorrect.", "danger")
        elif len(new) < 6:
            flash("New password must be at least 6 characters.", "danger")
        elif new != confirm:
            flash("New passwords do not match.", "danger")
        else:
            db.users.update_one({"_id": full["_id"]},
                                {"$set": {"password_hash": generate_password_hash(new)}})
            flash("Password updated successfully.", "success")
        return redirect(url_for("auth.profile"))

    full.pop("password_hash", None)
    if full["role"] == "student":
        stats = {"total": db.complaints.count_documents({"student_id": full["login_id"]})}
    else:
        stats = {"total": db.complaints.count_documents({"assigned_staff.login_id": full["login_id"]})}
    return render_template("profile.html", user=full, stats=stats, has_password=has_password)
