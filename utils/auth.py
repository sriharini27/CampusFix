"""Session helpers and role-based route protection decorators."""
from functools import wraps
from flask import session, redirect, url_for, flash, abort, request, current_app


def login_user(user):
    session.clear()
    session.permanent = True
    session["user_id"] = str(user["_id"])
    session["login_id"] = user["login_id"]
    session["name"] = user["name"]
    session["role"] = user["role"]
    session["department"] = user.get("department")


def college_domain():
    return current_app.config["GOOGLE_ALLOWED_DOMAIN"]


def is_college_email(email):
    """True only if the part after the LAST '@' is exactly the college domain (case-insensitive).
    'x@nec.edu.in' -> True ; 'x@nec.edu.in.evil.com', 'x@sub.nec.edu.in', 'nec.edu.in@gmail.com' -> False"""
    email = (email or "").strip().lower()
    local, at, domain = email.rpartition("@")
    return bool(at and local) and domain == college_domain()


def current_role():
    return session.get("role")


def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in to continue.", "warning")
            # remember the page (e.g. a scanned QR link) so we can return after login
            nxt = request.full_path if request.method == "GET" else None
            return redirect(url_for("auth.login", next=nxt.rstrip("?") if nxt else None))
        return view(*args, **kwargs)
    return wrapper


def role_required(*roles):
    """Allow only the listed roles; everyone else gets a 403 page."""
    def decorator(view):
        @wraps(view)
        @login_required
        def wrapper(*args, **kwargs):
            if session.get("role") not in roles:
                abort(403)
            return view(*args, **kwargs)
        return wrapper
    return decorator


student_required = role_required("student")
staff_required = role_required("staff", "admin")
admin_required = role_required("admin")
