"""Seed ONLY login accounts, default departments and QR campus locations (no fake complaints).

Usage:
    python seed.py            # create/refresh demo accounts + departments
    python seed.py --reset    # ALSO wipe all complaints and feedback (fresh demo)
"""
import sys
from datetime import datetime

from pymongo import MongoClient
from pymongo.errors import PyMongoError
from werkzeug.security import generate_password_hash

from config import Config
from utils.database import create_indexes
from utils.helpers import DEFAULT_DEPARTMENTS, DEFAULT_LOCATIONS, slugify

USERS = [
    # login_id,   name,               email,                          role,      department,              password
    ("STU001", "Arun Kumar",        "arun@nec.edu.in",        "student", None,                    "student123"),
    ("STU002", "Priya Sharma",      "priya@nec.edu.in",       "student", None,                    "student123"),
    ("STU003", "Mohammed Irfan",    "irfan@nec.edu.in",       "student", None,                    "student123"),
    ("STU004", "Divya Lakshmi",     "divya@nec.edu.in",       "student", None,                    "student123"),
    ("STU005", "Karthik Raj",       "karthik@nec.edu.in",     "student", None,                    "student123"),
    ("STAFF01", "Ravi Shankar",     "ravi@campusfix.edu",     "staff",   "Maintenance",           "staff123"),
    ("STAFF02", "Meena Krishnan",   "meena@campusfix.edu",    "staff",   "IT Support",            "staff123"),
    ("STAFF03", "Suresh Babu",      "suresh@campusfix.edu",   "staff",   "Electrical",            "staff123"),
    ("ADMIN01", "Selva Murugan",    "admin@campusfix.edu",    "admin",   "Administration",        "admin123"),
]


def main():
    client = MongoClient(Config.MONGO_URI, serverSelectionTimeoutMS=3000)
    try:
        client.admin.command("ping")
    except PyMongoError as exc:
        sys.exit(f"[ERROR] Cannot connect to MongoDB at {Config.MONGO_URI}: {exc}")
    db = client[Config.DB_NAME]
    create_indexes(db)

    if "--reset" in sys.argv:
        db.complaints.delete_many({})
        db.feedback.delete_many({})
        db.counters.delete_many({})
        db.notifications.delete_many({})
        print("Cleared complaints, feedback, notifications and ID counters.")

    for login_id, name, email, role, dept, pwd in USERS:
        db.users.update_one(
            {"login_id": login_id},
            {"$set": {"name": name, "email": email, "role": role, "department": dept,
                      "student_id": login_id if role == "student" else None,
                      "auth_provider": "password",
                      "password_hash": generate_password_hash(pwd)},
             "$setOnInsert": {"created_at": datetime.now().replace(microsecond=0)}},
            upsert=True,
        )
    print(f"Users ready: {db.users.count_documents({})}")

    for d in DEFAULT_DEPARTMENTS:
        db.departments.update_one(
            {"name": d["name"]},
            {"$setOnInsert": {**d, "active": True, "created_at": datetime.now().replace(microsecond=0)}},
            upsert=True,
        )
    print(f"Departments ready: {db.departments.count_documents({})}")

    for name, desc in DEFAULT_LOCATIONS:
        db.locations.update_one(
            {"slug": slugify(name)},
            {"$setOnInsert": {"name": name, "slug": slugify(name), "description": desc, "active": True,
                              "created_at": datetime.now().replace(microsecond=0)}},
            upsert=True,
        )
    print(f"QR locations ready: {db.locations.count_documents({})}")
    print(f"Complaints in database: {db.complaints.count_documents({})} (none are seeded)")
    print("\nDemo logins -> Student: STU001 / student123 | Staff: STAFF01 / staff123 | Admin: ADMIN01 / admin123")


if __name__ == "__main__":
    main()
