"""Smart duplicate detection — lightweight keyword similarity (no external AI).

score = 0.30 x same category
      + 0.30 x location similarity      (Jaccard of location words)
      + 0.40 x text similarity          (Jaccard of title words / title+description keywords)
A complaint is a "possible duplicate" when score >= 0.45 and the texts share some keywords.
"""
import re
from datetime import timedelta

from flask import current_app

from utils.database import get_db
from utils.helpers import OPEN_STATUSES, now

STOPWORDS = set("""a an the and or but is are was were be been being am of in on at to for from with by
this that these those it its there here not no very too also has have had do does did can could will would
should please since from near into out up down our my your their we i you he she they me us them all any
some more most other than then so such only just about after before again still every each issue problem
complaint working work""".split())

THRESHOLD = 0.45


def keywords(text):
    words = re.findall(r"[a-z0-9]+", (text or "").lower())
    out = set()
    for w in words:
        if w in STOPWORDS or (len(w) < 3 and not w.isdigit()):
            continue
        if len(w) > 4 and w.endswith("s"):          # tiny stemmer: "lights" -> "light"
            w = w[:-1]
        out.add(w)
    return out


def jaccard(a, b):
    return len(a & b) / len(a | b) if a and b else 0.0


def similarity(new, old):
    cat = 1.0 if new["category"] == old.get("category") else 0.0
    loc = jaccard(set(re.findall(r"[a-z0-9]+", new["location"].lower())),
                  set(re.findall(r"[a-z0-9]+", (old.get("location") or "").lower())))
    title = jaccard(keywords(new["title"]), keywords(old.get("title")))
    full = jaccard(keywords(new["title"] + " " + new["description"]),
                   keywords(old.get("title", "") + " " + old.get("description", "")))
    text = 0.6 * title + 0.4 * full
    return round(0.30 * cat + 0.30 * loc + 0.40 * text, 2), text


def find_duplicates(form, limit=3):
    """Return recent OPEN complaints that look like the new one (best match first)."""
    since = now() - timedelta(days=current_app.config["DUPLICATE_LOOKBACK_DAYS"])
    loc_rx = {"$regex": "^" + re.escape(form["location"]) + "$", "$options": "i"}
    candidates = get_db().complaints.find(
        {"status": {"$in": OPEN_STATUSES}, "created_at": {"$gte": since},
         "$or": [{"category": form["category"]}, {"location": loc_rx}]},
        {"status_history": 0}).limit(200)
    matches = []
    for c in candidates:
        score, text = similarity(form, c)
        if score >= THRESHOLD and text >= 0.15:
            c["match"] = int(score * 100)
            matches.append(c)
    matches.sort(key=lambda c: c["match"], reverse=True)
    return matches[:limit]
