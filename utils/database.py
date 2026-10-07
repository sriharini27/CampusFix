"""MongoDB connection (PyMongo) and index creation."""
from pymongo import MongoClient, ASCENDING, DESCENDING
from pymongo.errors import PyMongoError

client = None
db = None


def init_db(app):
    """Connect to MongoDB once at startup and create indexes."""
    global client, db
    client = MongoClient(app.config["MONGO_URI"], serverSelectionTimeoutMS=3000)
    db = client[app.config["DB_NAME"]]
    try:
        client.admin.command("ping")
        create_indexes(db)
        app.logger.info("Connected to MongoDB database '%s'", app.config["DB_NAME"])
    except PyMongoError as exc:
        app.logger.error("MongoDB connection failed: %s", exc)
    return db


def get_db():
    return db


def create_indexes(database):
    # users
    database.users.create_index("email", unique=True)
    database.users.create_index("login_id", unique=True)
    database.users.create_index("role")
    database.users.create_index("google_sub", unique=True, sparse=True)
    # complaints
    database.complaints.create_index("complaint_id", unique=True)
    database.complaints.create_index("student_id")
    database.complaints.create_index("status")
    database.complaints.create_index("category")
    database.complaints.create_index("department")
    database.complaints.create_index([("created_at", DESCENDING)])
    database.complaints.create_index([("status", ASCENDING), ("priority", ASCENDING)])
    # duplicate detection looks up open complaints by category + location
    database.complaints.create_index([("category", ASCENDING), ("location", ASCENDING), ("status", ASCENDING)])
    # notifications — the bell query is "my unread, newest first"
    database.notifications.create_index([("user_id", ASCENDING), ("is_read", ASCENDING),
                                         ("created_at", DESCENDING)])
    # QR campus locations
    database.locations.create_index("slug", unique=True)
    database.locations.create_index("name", unique=True)
    # feedback — unique index guarantees ONE feedback per complaint
    database.feedback.create_index("complaint_id", unique=True)
    database.feedback.create_index([("created_at", DESCENDING)])
    # departments
    database.departments.create_index("name", unique=True)
