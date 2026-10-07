# CampusFix — Smart Campus Complaint & Resolution System

A Flask + MongoDB web application where students report campus problems (classrooms, hostels, labs, Wi‑Fi, water, transport, canteen…) and staff/admin review, route, resolve and analyse them. It goes beyond CRUD with a **status workflow state machine**, **embedded status history**, **smart routing**, **SLA monitoring**, **duplicate detection**, **QR reporting**, **in‑app notifications** and **live analytics built with MongoDB aggregation pipelines**.

> > **College-only access:** students may sign in only with `@nec.edu.in` emails (password login and Google). Staff/Admin login is unchanged.

> Version 2 adds: Continue with Google (students), QR code reporting, smart duplicate detection, notification centre, SLA monitoring, reopen resolved complaints, department performance score, and a cleaned‑up login page. See `CHANGES.md` for the file‑by‑file list.

---

## 1. Features

| Area | Highlights |
|---|---|
| Authentication (basic setup) | Student and Staff/Admin portals, **Continue with Google for students** (OAuth 2.0 / OpenID Connect, college‑domain check, auto account creation), Werkzeug password hashing, sessions, role decorators, CSRF on every form, generic login errors |
| Module 1 — Complaint Management | Student dashboard, submit with image/PDF, auto IDs (`CF-2026-0001`), **QR‑prefilled location**, **duplicate detection with "view existing / submit anyway"**, "I'm facing this too", My Complaints, Track by ID, details with stepper, timeline and **SLA panel**, **Reopen Complaint** |
| Module 2 — Resolution & Departments | Admin dashboard with **SLA monitor**, search + filters + quick views (High/Critical, SLA breached, **Approaching SLA**, Assigned to me), smart department suggestion, assign/reassign, state‑machine status changes, remarks, urgent/overdue flags, department management, **QR location management** (generate, download, print, counts) |
| Module 3 — Analytics & Feedback | Chart.js charts from aggregation pipelines, resolution time, overdue count, **SLA compliance by department**, **Department Performance Score & ranking**, 1–5 star feedback (one per complaint), rating per department via `$lookup` |
| Notification centre | 🔔 bell with unread count + dropdown, notifications page, mark one / all read; triggered by submit, assign, reassign, status change, resolve, feedback request, reopen, new/critical complaint and SLA breach |

## 2. Technologies

Python 3.10+, Flask 3, Jinja2, PyMongo 4, MongoDB 6/7, python‑dotenv, Werkzeug, **Authlib** (Google OAuth), **qrcode** (local QR generation), HTML5, CSS3, JavaScript, Bootstrap 5, Bootstrap Icons, Chart.js 4. **MongoDB is the only database.**

## 3. Project structure

```
CampusFix/
├── app.py                    # App factory, blueprints, CSRF, overdue watcher, bell context, error handlers
├── config.py                 # Config class — reads .env (Mongo, Google OAuth, SLA targets, QR base URL)
├── seed.py                   # Demo users + departments + QR locations ONLY (no fake complaints)
├── requirements.txt  .env  .env.example  .gitignore  README.md  CHANGES.md
├── routes/
│   ├── auth_routes.py        # password login, Google OAuth (/auth/google, /auth/google/callback), logout, profile
│   ├── student_routes.py     # student dashboard                                  (Module 1)
│   ├── complaint_routes.py   # submit (+QR, +duplicates), list, track, details, reopen, me-too (Module 1)
│   ├── admin_routes.py       # dashboard, complaints, assign, status, remarks, departments (Module 2)
│   ├── location_routes.py    # QR locations: list, add, enable/disable, download SVG, print (Module 2)
│   ├── analytics_routes.py   # analytics page + JSON API                           (Module 3)
│   ├── feedback_routes.py    # submit feedback, feedback overview                  (Module 3)
│   └── notification_routes.py# /notifications, /notifications/read/<id>, /notifications/read-all
├── utils/
│   ├── auth.py               # session helpers, @student_required / @staff_required / @admin_required
│   ├── database.py           # MongoClient + indexes
│   ├── helpers.py            # constants, TRANSITIONS state machine, IDs, SLA logic, uploads, safe redirects
│   ├── analytics.py          # all aggregation pipelines (stats, SLA, department performance, locations)
│   ├── duplicates.py         # keyword-similarity duplicate detection
│   └── notifications.py      # notify(), unread count, overdue notifications
├── templates/
│   ├── base.html  _flash.html  _macros.html  login.html  profile.html  notifications.html
│   ├── errors/error.html  errors/_error_box.html
│   ├── student/ dashboard  submit_complaint  complaints  track  complaint_details
│   └── admin/   dashboard  complaints  complaint_details  departments  analytics  feedback  locations  qr_print
└── static/  css/style.css   js/script.js   js/analytics.js   uploads/
```

## 4. MongoDB database design (`campusfix`)

| Collection | Purpose / key fields |
|---|---|
| `users` | `login_id`, `name`, `email`, `password_hash` (null for Google‑only students), `role` (student/staff/admin), `department`, `auth_provider` (password/google), `google_sub`, `created_at` |
| `complaints` | `complaint_id`, `student_id`, `student_name`, `title`, `description`, `category`, `location`, `priority`, `status`, `department`, `assigned_staff {login_id, name, department}`, `attachment`, `reported_via` (web/qr), `supporters [login_id]`, `possible_duplicates [complaint_id]`, `reopen_count`, `overdue_notified`, `created_at`, `updated_at`, `resolved_at`, `resolution_remarks`, `feedback_given`, **`status_history [ {from_status, status, changed_by, changed_by_name, remarks, timestamp} ]`** |
| `feedback` | `complaint_id` (unique), `student_id`, `rating`, `comment`, `created_at` |
| `departments` | `name`, `description`, `categories []` (used for smart routing), `active` |
| `locations` *(new)* | `name`, `slug`, `description`, `active` — the QR campus locations |
| `notifications` *(new)* | `user_id` (login ID), `title`, `message`, `type`, `complaint_id`, `is_read`, `created_at` |
| `counters` | `{_id: "complaint_2026", seq}` — atomic complaint ID sequence |

**Indexes** (created automatically at startup and by `seed.py`): `users.email` (unique), `users.login_id` (unique), `users.google_sub` (unique, sparse), `complaints.complaint_id` (unique), `student_id`, `status`, `category`, `department`, `created_at`, compound `(status, priority)`, compound `(category, location, status)` for duplicate detection, `notifications (user_id, is_read, created_at)`, `feedback.complaint_id` (unique), `departments.name` (unique), `locations.slug` / `locations.name` (unique).

Existing v1 data keeps working — new fields are optional and read with safe defaults.

## 5. Installation & running

### 5.1 MongoDB
* **Windows:** install *MongoDB Community Server* ("Install as a Service") → `mongodb://localhost:27017/`. Optional: MongoDB Compass to browse data.
* **Linux/macOS:** `sudo systemctl start mongod` / `brew services start mongodb-community`.
* **Atlas:** put the `mongodb+srv://…` string in `MONGO_URI`.

### 5.2 Commands (Windows)
```bash
cd CampusFix
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python seed.py          # demo accounts + departments + 10 QR locations (safe to re-run)
python app.py           # http://127.0.0.1:5000
```
Linux/macOS: `source venv/bin/activate`. `python seed.py --reset` wipes complaints, feedback and notifications for a fresh demo (users, departments and locations are kept).

### 5.3 `.env`
```
MONGO_URI=mongodb://localhost:27017/
DB_NAME=campusfix
SECRET_KEY=replace-with-a-long-random-string
FLASK_DEBUG=1
HOST=127.0.0.1
PORT=5000
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GOOGLE_REDIRECT_URI=http://127.0.0.1:5000/auth/google/callback
GOOGLE_ALLOWED_DOMAIN=
PUBLIC_BASE_URL=
```
`.env` is listed in `.gitignore`; secrets never appear in templates or source code.

### Required packages
`Flask`, `pymongo`, `python-dotenv`, `Werkzeug`, `Authlib`, `requests` (used by Authlib's Flask client), `qrcode`.

## 6. Google Cloud Console — OAuth setup (Continue with Google)

1. Open **console.cloud.google.com** → create/select a project (e.g. *CampusFix*).
2. **APIs & Services → OAuth consent screen**: User type *External* (or *Internal* if your college uses Google Workspace and you want only college accounts). App name *CampusFix*, support email, developer email. Scopes: `openid`, `email`, `profile`. While in *Testing* mode, add the Google accounts you will demo with under **Test users**.
3. **APIs & Services → Credentials → Create credentials → OAuth client ID** → Application type **Web application**.
4. **Authorized redirect URIs** — add exactly:
   ```
   http://127.0.0.1:5000/auth/google/callback
   ```
   (If you open the app as `http://localhost:5000`, also add `http://localhost:5000/auth/google/callback` and set `GOOGLE_REDIRECT_URI` to match. The URL in the browser and the redirect URI must use the same host.)
5. Copy the **Client ID** and **Client secret** into `.env` as `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET`.
6. Set `GOOGLE_ALLOWED_DOMAIN=nec.edu.in` — the email domain only (no `@`, no `http://`, **not** `127.0.0.1:5000`). If it is empty or invalid, CampusFix falls back to `nec.edu.in`.
7. Restart `python app.py`.

If the Google variables are empty, the button shows a friendly "not available" message and students can still use ID/password.

**Flow:** Continue with Google → Google's normal account chooser (`prompt=select_account`, **no `hd` restriction**, so college, personal and other signed-in accounts are all listed) → callback verifies `state` + ID token (Authlib) → backend checks the email exists, `email_verified` is true and the domain after the last `@` is **exactly** `nec.edu.in` (otherwise *"Please use your official college Google account ending with @nec.edu.in."* — no account, no session, no linking) → existing user (matched by Google ID or email) logs in / new student is created (Student ID = email prefix, e.g. `21cs045@…` → `21CS045`) → Student Dashboard. Staff/admin emails are refused on Google login and must use the Staff/Admin portal. Google students can optionally set a password on the Profile page to also log in with their Student ID.

## 7. QR codes on a phone
QR codes encode `<base>/complaints/new?location=Computer%20Lab%203`. On the same laptop, `<base>` is the current address. To scan with a phone on the same Wi‑Fi, set `HOST=0.0.0.0` and `PUBLIC_BASE_URL=http://<your-laptop-IP>:5000` in `.env`, restart, and reprint. QR codes are generated locally (SVG) by the `qrcode` library — no external service. (Google login on a phone needs that IP redirect URI too; for the viva, scan → log in with Student ID, or demo QR on the laptop by opening the link.)

## 8. Demo login credentials
Not shown anywhere in the app — for the examiner/README only.

| Role | Login ID | Password |
|---|---|---|
| Students | STU001 … STU005 (or arun@nec.edu.in …) | student123 |
| Staff (Maintenance / IT Support / Electrical) | STAFF01 / STAFF02 / STAFF03 | staff123 |
| Admin | ADMIN01 | admin123 |

## 9. Demo workflow (27 steps)

1. Open `http://127.0.0.1:5000`.
2. Clean login page: CampusFix, title, ID/email, password 👁, Login, OR, Continue with Google.
3. No usernames or passwords are shown or pre‑filled.
4. Click **Continue with Google**.
5. Choose your college Google account on Google's consent screen.
6. Student Dashboard opens (account auto‑created on first login; welcome notification in 🔔).
7. Admin → **QR Locations** → print/open the *Computer Lab 3* code; scan it (or open its link).
8. The complaint form opens (if logged out, login first — you return to the form automatically).
9. **"QR detected location — Computer Lab 3"** is shown and the location is pre‑filled.
10. Enter title/description/category/priority (e.g. *Projector not working*, Laboratory, Critical).
11. Submit → duplicate detection runs. (Log in as another student and submit a similar complaint to see the warning.)
12. **Possible existing complaint found** → *View Existing Complaint* (limited view + "I'm facing this too") or *Submit New Complaint Anyway*.
13. Complaint stored in MongoDB with `reported_via: "qr"` and its first `status_history` entry.
14. Log in as **ADMIN01** → 🔔 shows *Critical complaint submitted*.
15. Open it → *Under Review*.
16. Smart routing pre‑selects **Academic/Laboratory ★ suggested**.
17. Assign department + staff (e.g. Suresh Babu) → status becomes *Assigned*.
18. Student gets *Complaint assigned*; the staff member gets *Complaint assigned to you*.
19. Log in as that staff member → *In Progress*.
20. SLA panel: target, deadline, status (green / yellow / red) and time left or overdue.
21. *Resolved* with remarks.
22. Student gets *Complaint resolved* + *Feedback requested*.
23. Student rates the resolution (⭐ 1–5, once only).
24. Student clicks **Reopen Complaint** → "Why are you reopening this complaint?" → status *Reopened*; staff/admin are notified. Staff: Reopened → In Progress → Resolved.
25. Admin → **Analytics**: all charts reflect the new data (Refresh button re‑queries MongoDB).
26. **Department Performance Score** ranking updates.
27. **SLA compliance** chart, SLA summary and the dashboard SLA monitor update.

## 10. Testing checklist
- [ ] Login page (both tabs) shows no demo IDs/passwords; fields are empty; Google button only on Student tab; no "Forgot password".
- [ ] Wrong password, unknown ID, or student ID on Staff tab → always *"Invalid ID/email or password."*
- [ ] Google chooser lists all accounts; `@gmail.com` / `@yahoo.com` / other domains → *"Please use your official college Google account ending with @nec.edu.in."*; `@nec.edu.in` (any letter case) → dashboard; staff email refused.
- [ ] Student password login with a non‑college email → *"Please use your official college email ID ending with @nec.edu.in."*; Student ID login still works; Staff/Admin unchanged.
- [ ] Logged‑out QR link → login → returns to the form with the location filled and the QR banner.
- [ ] Similar complaint → warning with match %, View Existing / Submit Anyway; attachment kept; unrelated complaint → no warning.
- [ ] Other student viewing an open complaint sees no names/attachment; "I'm facing this too" counts once.
- [ ] Bell count increases for the right users only; clicking opens the complaint and marks it read; Mark all read works; users cannot open others' notifications (404).
- [ ] Status transitions outside `TRANSITIONS` are rejected (e.g. Reopened → Resolved).
- [ ] Reopen requires a reason (≥10 chars), only for the owner, only from Resolved.
- [ ] A Critical complaint older than 1 day shows red **BREACHED**; a Medium one in its last 25 % shows yellow; overdue notification is sent once.
- [ ] Analytics: SLA cards, SLA by department chart, performance ranking change after resolving/rating.
- [ ] QR page: download SVG, print one / all, admin adds and disables a location; staff cannot add (403).
- [ ] Stop MongoDB → friendly "temporarily unavailable" page, no technical details.

## 11. Viva explanation — unique features

**Continue with Google.** Uses OAuth 2.0 Authorization Code flow with OpenID Connect via Authlib. Authlib stores a random `state` (CSRF protection for the OAuth round‑trip) and `nonce` in the Flask session and verifies them plus the signed ID token on the callback. We then enforce `email_verified` and the college domain (`hd` hint + server‑side check, because the hint alone can be bypassed). Accounts are matched by Google's stable `sub` ID or email; new students are inserted into `users` with `auth_provider: "google"` and no password. Staff cannot use Google — keeps privileged logins on the controlled ID/password path.

**QR complaint reporting.** Each `locations` document gets a QR code generated server‑side as SVG (vector → prints sharply, no image library). The code is just a URL with a `location` query parameter; Flask reads `request.args`, validates it against active locations (so random text can't be injected as a "QR location"), pre‑fills the form and marks `reported_via: "qr"`. `login_required` saves `?next=` so a logged‑out scan returns to the form; `safe_next()` only allows local paths for the user's role (no open redirect). Counts per location come from a `$group` pipeline.

**Smart duplicate detection.** Candidates = open complaints from the last 30 days with the same category or location (indexed query). Each is scored: 0.30 × same category + 0.30 × location word overlap + 0.40 × text similarity (Jaccard similarity of keyword sets after removing stop‑words and a tiny stemmer). Score ≥ 0.45 with some shared keywords → shown with a match %. It never blocks: the student can submit anyway (the IDs shown are stored in `possible_duplicates` for staff) or join the existing complaint with `$addToSet` on `supporters`.

**Notification centre.** One small document per recipient in `notifications`, written by a single `notify()` helper with `insert_many`. The bell count is `count_documents({user_id, is_read: false})`, served by the compound index `(user_id, is_read, created_at)`. The person performing an action is not notified about their own action. There is no background scheduler, so overdue notifications are generated lazily (at most once a minute) when staff browse; `overdue_notified` makes each one fire only once.

**SLA monitoring.** Deadline = `created_at` + target days (Critical 1, High 3, Medium 5, Low 7). Green = more than 25 % of the window left, yellow = approaching, red = breached; resolved complaints show *SLA met* or *resolved after deadline*. In MongoDB the pipeline computes `elapsed = (resolved_at or now) − created_at` and compares it with `sla_days × 86 400 000 ms` using `$switch`, `$subtract`, `$multiply`, `$gt`, then `$group` counts breaches → compliance %.

**Reopen resolved complaint.** Added a `Reopened` state to the existing `TRANSITIONS` dictionary (`Resolved → Reopened → In Progress → Resolved`). The student route checks the same state machine, requires a reason, clears `resolved_at`, increments `reopen_count` (`$inc`) and `$push`es the reason into `status_history` — one atomic update.

**Department performance score.** One aggregation groups complaints by department (total, resolved, open, overdue, SLA breaches, `$avg` resolution hours) and is merged with average ratings from a `$lookup` pipeline. Score (0–100) = 30 % resolution rate + 35 % SLA compliance + 25 % rating (neutral 3/5 until rated) + 10 % (1 − overdue/open). Formula is shown on the page; departments without complaints are listed but not ranked.

**Login cleanup & security.** No credentials or technical details on the page, empty fields, one generic error message (no user enumeration), CSRF tokens on all POST forms, Werkzeug hashes, role‑checked routes, `re.escape` on user regexes, only whitelisted values in queries, and database errors show a generic message (details only in the server log).

## 12. Where WFP (Flask) concepts are demonstrated

| Concept | Where |
|---|---|
| App factory, configuration from environment | `app.py → create_app()`, `config.py` + `.env` |
| Blueprints & routes (8), dynamic URLs | `routes/*.py` — `/complaints/<cid>`, `/notifications/read/<nid>`, `/admin/locations/<slug>/qr.svg` |
| Request handling | `request.form`, `request.args` (QR location), `request.files` (attachments), `request.referrer` |
| Forms & validation | submit (+duplicate step), reopen modal, assign, status, feedback, locations, departments, profile |
| Templates, Jinja2, inheritance, macros, filters | `base.html`, `_macros.html` (`sla_panel`, `timeline`, `stepper`…), `dt` filter, `include`, `Markup` for SVG |
| Sessions | login state, CSRF token, OAuth state/nonce, `oauth_next` |
| Decorators / access control | `@student_required`, `@staff_required`, `@admin_required` |
| Redirects & `url_for` | PRG after every POST, `?next=` after login, OAuth redirect |
| Flash messages | all actions and errors |
| Hooks | `before_request` (CSRF check, overdue watcher), `context_processor` (bell, constants) |
| Static files & custom responses | CSS/JS/uploads; SVG download via `Response` with `Content-Disposition` |
| JSON API | `/admin/analytics/data` with `jsonify` |
| Error handlers | 400, 403, 404, 413, 500, MongoDB errors |
| Third‑party integration | Authlib Flask OAuth client (Google OpenID Connect) |

## 13. Where NoSQL / MongoDB concepts are demonstrated

| Concept | Where |
|---|---|
| Collections & documents | `users`, `complaints`, `feedback`, `departments`, `locations`, `notifications`, `counters` |
| Embedded documents & arrays | `status_history[]`, `assigned_staff{}`, `supporters[]`, `possible_duplicates[]`, `departments.categories[]` |
| Flexible schema | Google users without `password_hash`, optional `reported_via`/`reopen_count` on old documents |
| Queries & filtering | `$in`, `$nin`, `$ne`, `$or`, `$and`, date ranges, anchored case‑insensitive `$regex`, array membership |
| Updates | `$set`, `$push`, `$inc`, `$addToSet`, `update_many`, `find_one_and_update`, upserts in seed |
| Atomic counter | complaint IDs |
| Aggregation pipelines | `$match`, `$group`, `$sort`, `$project`, `$addFields`, `$limit`, `$unwind`, `$lookup`, `$cond`, `$switch`, `$subtract`, `$multiply`, `$divide`, `$avg`, `$dateToString`, `$arrayElemAt` |
| Indexes | unique, sparse unique (`google_sub`), compound `(category, location, status)` and `(user_id, is_read, created_at)` |
| ObjectId handling | `ObjectId(nid)` with `InvalidId` guard in notifications; profile lookup |
| Error handling | `DuplicateKeyError` (IDs, feedback, departments, locations), connection errors |

## 14. Future enhancements
Email/SMS/push notifications · background scheduler (e.g. APScheduler) for SLA alerts · staff view limited to their own department · multiple attachments/gallery · PDF/Excel reports · TF‑IDF or embeddings for duplicate detection · PWA/mobile app.
