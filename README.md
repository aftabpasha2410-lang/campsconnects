# Campus Connect

Placement and internship portal. Python (Flask + SQLite) backend, HTML/CSS frontend.

## Run
```
pip install -r requirements.txt
python app.py
```
Open http://127.0.0.1:5000

First login: `office@campus.com` / `admin123` (change it after first use).

## Roles
- **Office**: add/remove companies and students, see all jobs, internships and applications.
- **Company**: post jobs/internships (with minimum CGPA and deadline), see applicants, set status
  (Applied, Shortlisted, Interview, Selected, Rejected), close or reopen postings.
- **Student**: search and filter jobs/internships, apply, track status, edit profile and resume link.

## Files
- `app.py` routes, database and login
- `templates/` pages, `static/style.css` styling
- `campus_connect.db` is created on first run

Set `SECRET_KEY` as an environment variable before deploying.
