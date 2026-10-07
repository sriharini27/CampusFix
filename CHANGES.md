# CampusFix v2 — change log

Built on top of the existing v1 code (nothing rebuilt; all v1 routes and features kept).

## Files created
| File | Purpose |
|---|---|
| `routes/location_routes.py` | QR locations: list with counts, add, enable/disable, SVG download, printable sheet |
| `routes/notification_routes.py` | `/notifications`, `/notifications/read/<id>`, `/notifications/read-all` |
| `utils/notifications.py` | `notify()`, unread count, latest items, once-only overdue notifications |
| `utils/duplicates.py` | Keyword (Jaccard) similarity duplicate detection |
| `templates/notifications.html` | Notification centre page |
| `templates/admin/locations.html` | QR location management |
| `templates/admin/qr_print.html` | Printable QR posters |
| `CHANGES.md` | This file |

## Files modified
| File | Change |
|---|---|
| `config.py` | Google OAuth vars, `HOST`, `PUBLIC_BASE_URL`, SLA warning ratio, overdue check interval, duplicate look-back |
| `app.py` | Registers 2 new blueprints + OAuth; overdue watcher (`before_request`); bell data in context processor; generic DB error text; `HOST` |
| `requirements.txt` | + `Authlib`, `requests`, `qrcode` |
| `.env.example` / `.env` | Google, `HOST`, `PUBLIC_BASE_URL` |
| `seed.py` | Seeds 10 QR locations; `--reset` also clears notifications |
| `utils/database.py` | New indexes (google_sub, category+location+status, notifications, locations) |
| `utils/helpers.py` | `Reopened` status in `TRANSITIONS`; SLA calculation (`sla_info`, `approaching_query`); `safe_next`; default locations; `pending_attachment` |
| `utils/auth.py` | `login_required` remembers `?next=` (QR scans) |
| `utils/analytics.py` | SLA pipeline + summary, department performance score, location counts |
| `routes/auth_routes.py` | Google OAuth routes; generic login error; Google users can set a password |
| `routes/complaint_routes.py` | QR prefill, duplicate step, notifications, limited view for other students, reopen, "I'm facing this too" |
| `routes/admin_routes.py` | SLA stats, "Approaching SLA" view, notifications on assign/reassign/status, supporters |
| `routes/student_routes.py` | Reopened counted as in progress |
| `templates/login.html` | Cleaned: no demo credentials/instructions, empty fields, OR + Continue with Google |
| `templates/base.html` | 🔔 bell dropdown, Notifications and QR Locations nav items |
| `templates/_macros.html` | `sla_badge`, `sla_panel`, Reopened in stepper, privacy option in timeline |
| `templates/student/submit_complaint.html` | QR banner, location suggestions, duplicate panel |
| `templates/student/complaint_details.html` | SLA panel, Reopen modal, limited view + me-too |
| `templates/admin/dashboard.html` | SLA monitor strip |
| `templates/admin/complaints.html` | SLA column, Approaching SLA tab, QR / supporters markers |
| `templates/admin/complaint_details.html` | SLA panel, supporters, similar complaints, QR/reopen info |
| `templates/admin/analytics.html` | Department Performance Score table, SLA compliance chart, SLA summary |
| `templates/profile.html` | Sign-in method; set password for Google users |
| `static/css/style.css` | Styles for the above (existing design unchanged); fixed invisible "Critical" priority button text |
| `static/js/analytics.js` | SLA-by-department chart, Reopened colour |
| `README.md` | Updated documentation |

## MongoDB changes
New collections `notifications` and `locations`; new optional fields on `users` (`auth_provider`, `google_sub`) and `complaints` (`reported_via`, `supporters`, `possible_duplicates`, `reopen_count`, `overdue_notified`); new status value `Reopened`; new indexes. No migration needed — run `python seed.py` once to create locations and indexes.

## v2.1 — college-only student authentication (@nec.edu.in)
| File | Change |
|---|---|
| `config.py` | `GOOGLE_ALLOWED_DOMAIN` defaults to `nec.edu.in`; leading `@` stripped; invalid values (e.g. `127.0.0.1:5000`) fall back to `nec.edu.in`. Used only for backend validation. |
| `utils/auth.py` | New `is_college_email()` (exact, case-insensitive domain after the last `@`) and `college_domain()` |
| `routes/auth_routes.py` | Removed the Google `hd` parameter (chooser shows all accounts; `prompt=select_account` kept). Callback: email exists + `email_verified` + exact domain checked before any lookup/linking/creation. Student password login rejects non-college emails before any database lookup. Staff/Admin login unchanged. |
| `seed.py` | Demo student emails moved to `@nec.edu.in` (re-run `python seed.py`) |
| `.env` / `.env.example` | `GOOGLE_ALLOWED_DOMAIN=nec.edu.in` |
