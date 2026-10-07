"""Application configuration — every secret comes from the .env file."""
import os
import re
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "change-me-in-env")
    MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
    DB_NAME = os.getenv("DB_NAME", "campusfix")
    DEBUG = os.getenv("FLASK_DEBUG", "1") == "1"
    HOST = os.getenv("HOST", "127.0.0.1")        # use 0.0.0.0 to scan QR codes from a phone on the same Wi-Fi
    PORT = int(os.getenv("PORT", "5000"))

    # Google OAuth 2.0 (students only)
    GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
    GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
    GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI", "http://127.0.0.1:5000/auth/google/callback")
    # Official college email domain. Used ONLY for backend validation of student emails
    # (password login + Google login). It is never sent to Google, so the account picker shows all accounts.
    GOOGLE_ALLOWED_DOMAIN = os.getenv("GOOGLE_ALLOWED_DOMAIN", "nec.edu.in").strip().lower().lstrip("@")
    if not re.fullmatch(r"[a-z0-9-]+(\.[a-z0-9-]+)+", GOOGLE_ALLOWED_DOMAIN) or \
            re.fullmatch(r"[0-9.]+", GOOGLE_ALLOWED_DOMAIN):
        # e.g. "127.0.0.1:5000" is a server address, not an email domain -> fall back to the college domain
        GOOGLE_ALLOWED_DOMAIN = "nec.edu.in"

    # Base URL printed inside QR codes (e.g. http://192.168.1.20:5000). Empty = current host.
    PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")

    # File uploads
    UPLOAD_FOLDER = os.path.join(BASE_DIR, "static", "uploads")
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024          # 5 MB
    ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "pdf"}

    # SLA targets: a complaint must be resolved within N days of submission
    OVERDUE_DAYS = {"Critical": 1, "High": 3, "Medium": 5, "Low": 7}
    SLA_WARNING_RATIO = 0.25        # "approaching" when less than 25% of the SLA window is left
    OVERDUE_CHECK_SECONDS = 60      # how often overdue notifications are generated
    DUPLICATE_LOOKBACK_DAYS = 30    # duplicate detection compares with open complaints from the last N days

    PERMANENT_SESSION_LIFETIME = 60 * 60 * 4     # 4 hours
