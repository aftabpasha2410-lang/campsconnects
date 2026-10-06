"""Campus Connect - placement & internship portal.
Roles: office (admin), company, student.  Backend: Flask + SQLite.
"""
import os
import sqlite3
from datetime import date
from functools import wraps

from flask import (Flask, flash, g, jsonify, redirect, render_template,
                   request, session, url_for, abort)
from werkzeug.security import check_password_hash, generate_password_hash

BASE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE, "campus_connect.db")

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "change-this-in-production")

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  email TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  role TEXT NOT NULL CHECK(role IN ('office','company','student'))
);
CREATE TABLE IF NOT EXISTS companies(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name TEXT NOT NULL, industry TEXT, location TEXT, website TEXT, about TEXT
);
CREATE TABLE IF NOT EXISTS students(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  roll_no TEXT, department TEXT, year TEXT, cgpa REAL, skills TEXT, resume_link TEXT
);
CREATE TABLE IF NOT EXISTS jobs(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
  title TEXT NOT NULL,
  kind TEXT NOT NULL CHECK(kind IN ('Job','Internship')),
  location TEXT, pay TEXT, skills TEXT, description TEXT,
  min_cgpa REAL DEFAULT 0,
  deadline TEXT,
  active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL DEFAULT CURRENT_DATE
);
CREATE TABLE IF NOT EXISTS applications(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  job_id INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
  student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
  status TEXT NOT NULL DEFAULT 'Applied',
  created_at TEXT NOT NULL DEFAULT CURRENT_DATE,
  UNIQUE(job_id, student_id)
);
"""
STATUSES = ["Applied", "Shortlisted", "Interview", "Selected", "Rejected"]


# ---------- database helpers ----------
def db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(_):
    conn = g.pop("db", None)
    if conn:
        conn.close()


def q(sql, args=(), one=False):
    cur = db().execute(sql, args)
    rows = cur.fetchall()
    return (rows[0] if rows else None) if one else rows


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
    exists = conn.execute("SELECT 1 FROM users WHERE role='office' LIMIT 1").fetchone()
    if not exists:
        conn.execute(
            "INSERT INTO users(name,email,password_hash,role) VALUES(?,?,?,?)",
            ("Placement Office", "office@campus.com",
             generate_password_hash("admin123"), "office"))
    conn.commit()
    conn.close()


# ---------- auth ----------
@app.before_request
def load_user():
    g.user = None
    if "uid" in session:
        g.user = q("SELECT * FROM users WHERE id=?", (session["uid"],), one=True)


def login_required(*roles):
    def deco(fn):
        @wraps(fn)
        def wrapper(*a, **kw):
            if not g.user:
                return redirect(url_for("login"))
            if roles and g.user["role"] not in roles:
                abort(403)
            return fn(*a, **kw)
        return wrapper
    return deco


def home_for(role):
    return {"office": "office_home", "company": "company_home",
            "student": "browse_jobs"}[role]


def current_company():
    return q("SELECT * FROM companies WHERE user_id=?", (g.user["id"],), one=True)


def current_student():
    return q("SELECT * FROM students WHERE user_id=?", (g.user["id"],), one=True)


@app.route("/")
def index():
    if g.user:
        return redirect(url_for(home_for(g.user["role"])))
    return render_template("landing.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        user = q("SELECT * FROM users WHERE email=?", (email,), one=True)
        if user and check_password_hash(user["password_hash"], request.form["password"]):
            session.clear()
            session["uid"] = user["id"]
            return redirect(url_for(home_for(user["role"])))
        flash("Email or password is incorrect.", "error")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


@app.errorhandler(403)
def forbidden(_):
    return render_template("message.html", title="Not allowed",
                           text="Your account can't open this page."), 403


# ---------- office (admin) ----------
@app.route("/office")
@login_required("office")
def office_home():
    stats = {
        "companies": q("SELECT COUNT(*) c FROM companies", one=True)["c"],
        "students": q("SELECT COUNT(*) c FROM students", one=True)["c"],
        "jobs": q("SELECT COUNT(*) c FROM jobs WHERE kind='Job'", one=True)["c"],
        "internships": q("SELECT COUNT(*) c FROM jobs WHERE kind='Internship'", one=True)["c"],
        "selected": q("SELECT COUNT(*) c FROM applications WHERE status='Selected'", one=True)["c"],
    }
    recent = q("""SELECT a.*, j.title, c.name company, u.name student
                  FROM applications a JOIN jobs j ON j.id=a.job_id
                  JOIN companies c ON c.id=j.company_id
                  JOIN students s ON s.id=a.student_id
                  JOIN users u ON u.id=s.user_id
                  ORDER BY a.id DESC LIMIT 8""")
    return render_template("office_home.html", stats=stats, recent=recent)


@app.route("/office/companies", methods=["GET", "POST"])
@login_required("office")
def office_companies():
    if request.method == "POST":
        f = request.form
        try:
            cur = db().execute(
                "INSERT INTO users(name,email,password_hash,role) VALUES(?,?,?,'company')",
                (f["name"].strip(), f["email"].strip().lower(),
                 generate_password_hash(f["password"])))
            db().execute(
                "INSERT INTO companies(user_id,name,industry,location,website,about) VALUES(?,?,?,?,?,?)",
                (cur.lastrowid, f["name"].strip(), f.get("industry"), f.get("location"),
                 f.get("website"), f.get("about")))
            db().commit()
            flash(f"{f['name']} added. They can now log in and post jobs.", "ok")
        except sqlite3.IntegrityError:
            db().rollback()
            flash("That email is already used by another account.", "error")
        return redirect(url_for("office_companies"))
    rows = q("""SELECT c.*, u.email,
                (SELECT COUNT(*) FROM jobs WHERE company_id=c.id) openings
                FROM companies c JOIN users u ON u.id=c.user_id ORDER BY c.name""")
    return render_template("office_companies.html", companies=rows)


@app.route("/office/students", methods=["GET", "POST"])
@login_required("office")
def office_students():
    if request.method == "POST":
        f = request.form
        try:
            cur = db().execute(
                "INSERT INTO users(name,email,password_hash,role) VALUES(?,?,?,'student')",
                (f["name"].strip(), f["email"].strip().lower(),
                 generate_password_hash(f["password"])))
            db().execute(
                "INSERT INTO students(user_id,roll_no,department,year,cgpa,skills) VALUES(?,?,?,?,?,?)",
                (cur.lastrowid, f.get("roll_no"), f.get("department"), f.get("year"),
                 float(f.get("cgpa") or 0), f.get("skills")))
            db().commit()
            flash(f"{f['name']} added. They can now log in and apply.", "ok")
        except sqlite3.IntegrityError:
            db().rollback()
            flash("That email is already used by another account.", "error")
        return redirect(url_for("office_students"))
    rows = q("""SELECT s.*, u.name, u.email,
                (SELECT COUNT(*) FROM applications WHERE student_id=s.id) applied
                FROM students s JOIN users u ON u.id=s.user_id ORDER BY u.name""")
    return render_template("office_students.html", students=rows)


@app.route("/office/jobs")
@login_required("office")
def office_jobs():
    rows = q("""SELECT j.*, c.name company,
                (SELECT COUNT(*) FROM applications WHERE job_id=j.id) applicants
                FROM jobs j JOIN companies c ON c.id=j.company_id ORDER BY j.id DESC""")
    return render_template("office_jobs.html", jobs=rows)


@app.post("/office/delete/<kind>/<int:rid>")
@login_required("office")
def office_delete(kind, rid):
    if kind == "company":
        row = q("SELECT user_id FROM companies WHERE id=?", (rid,), one=True)
    elif kind == "student":
        row = q("SELECT user_id FROM students WHERE id=?", (rid,), one=True)
    elif kind == "job":
        db().execute("DELETE FROM jobs WHERE id=?", (rid,))
        db().commit()
        flash("Posting removed.", "ok")
        return redirect(url_for("office_jobs"))
    else:
        abort(404)
    if row:
        db().execute("DELETE FROM users WHERE id=?", (row["user_id"],))  # cascades
        db().commit()
        flash(f"{kind.title()} removed.", "ok")
    return redirect(url_for("office_companies" if kind == "company" else "office_students"))


# ---------- company ----------
@app.route("/company")
@login_required("company")
def company_home():
    co = current_company()
    jobs = q("""SELECT j.*, (SELECT COUNT(*) FROM applications WHERE job_id=j.id) applicants
                FROM jobs j WHERE company_id=? ORDER BY j.id DESC""", (co["id"],))
    return render_template("company_home.html", co=co, jobs=jobs)


@app.route("/company/jobs/new", methods=["GET", "POST"])
@login_required("company")
def company_new_job():
    co = current_company()
    if request.method == "POST":
        f = request.form
        db().execute(
            """INSERT INTO jobs(company_id,title,kind,location,pay,skills,description,min_cgpa,deadline)
               VALUES(?,?,?,?,?,?,?,?,?)""",
            (co["id"], f["title"].strip(), f["kind"], f.get("location"), f.get("pay"),
             f.get("skills"), f.get("description"), float(f.get("min_cgpa") or 0),
             f.get("deadline") or None))
        db().commit()
        flash("Posted. Students can see it now.", "ok")
        return redirect(url_for("company_home"))
    return render_template("company_job_form.html")


@app.route("/company/jobs/<int:jid>")
@login_required("company")
def company_job(jid):
    co = current_company()
    job = q("SELECT * FROM jobs WHERE id=? AND company_id=?", (jid, co["id"]), one=True)
    if not job:
        abort(404)
    apps = q("""SELECT a.*, u.name, u.email, s.roll_no, s.department, s.year, s.cgpa,
                s.skills, s.resume_link
                FROM applications a JOIN students s ON s.id=a.student_id
                JOIN users u ON u.id=s.user_id WHERE a.job_id=? ORDER BY a.id DESC""", (jid,))
    return render_template("company_job.html", job=job, apps=apps, statuses=STATUSES)


@app.post("/company/applications/<int:aid>/status")
@login_required("company")
def company_set_status(aid):
    co = current_company()
    row = q("""SELECT a.id, a.job_id FROM applications a JOIN jobs j ON j.id=a.job_id
               WHERE a.id=? AND j.company_id=?""", (aid, co["id"]), one=True)
    status = request.form.get("status")
    if not row or status not in STATUSES:
        abort(400)
    db().execute("UPDATE applications SET status=? WHERE id=?", (status, aid))
    db().commit()
    return redirect(url_for("company_job", jid=row["job_id"]))


@app.post("/company/jobs/<int:jid>/toggle")
@login_required("company")
def company_toggle_job(jid):
    co = current_company()
    db().execute("UPDATE jobs SET active = 1-active WHERE id=? AND company_id=?", (jid, co["id"]))
    db().commit()
    return redirect(url_for("company_home"))


# ---------- student ----------
@app.route("/jobs")
@login_required("student")
def browse_jobs():
    kind = request.args.get("kind", "")
    text = request.args.get("q", "").strip()
    sql = """SELECT j.*, c.name company, c.industry FROM jobs j
             JOIN companies c ON c.id=j.company_id
             WHERE j.active=1 AND (j.deadline IS NULL OR j.deadline>=?)"""
    args = [date.today().isoformat()]
    if kind in ("Job", "Internship"):
        sql += " AND j.kind=?"
        args.append(kind)
    if text:
        sql += " AND (j.title LIKE ? OR c.name LIKE ? OR j.skills LIKE ? OR j.location LIKE ?)"
        args += [f"%{text}%"] * 4
    sql += " ORDER BY j.id DESC"
    st = current_student()
    applied = {r["job_id"] for r in q("SELECT job_id FROM applications WHERE student_id=?", (st["id"],))}
    return render_template("jobs.html", jobs=q(sql, args), kind=kind, text=text, applied=applied, st=st)


@app.route("/jobs/<int:jid>")
@login_required("student")
def job_detail(jid):
    job = q("""SELECT j.*, c.name company, c.about, c.website, c.industry FROM jobs j
               JOIN companies c ON c.id=j.company_id WHERE j.id=?""", (jid,), one=True)
    if not job:
        abort(404)
    st = current_student()
    app_row = q("SELECT * FROM applications WHERE job_id=? AND student_id=?", (jid, st["id"]), one=True)
    eligible = (st["cgpa"] or 0) >= (job["min_cgpa"] or 0)
    return render_template("job_detail.html", job=job, app_row=app_row, eligible=eligible, st=st)


@app.post("/jobs/<int:jid>/apply")
@login_required("student")
def apply(jid):
    st = current_student()
    job = q("SELECT * FROM jobs WHERE id=? AND active=1", (jid,), one=True)
    if not job:
        abort(404)
    if (st["cgpa"] or 0) < (job["min_cgpa"] or 0):
        flash(f"This role needs a CGPA of {job['min_cgpa']} or higher.", "error")
    else:
        try:
            db().execute("INSERT INTO applications(job_id,student_id) VALUES(?,?)", (jid, st["id"]))
            db().commit()
            flash("Application sent.", "ok")
        except sqlite3.IntegrityError:
            flash("You have already applied to this role.", "error")
    return redirect(url_for("job_detail", jid=jid))


@app.route("/my-applications")
@login_required("student")
def my_applications():
    st = current_student()
    rows = q("""SELECT a.*, j.title, j.kind, c.name company FROM applications a
                JOIN jobs j ON j.id=a.job_id JOIN companies c ON c.id=j.company_id
                WHERE a.student_id=? ORDER BY a.id DESC""", (st["id"],))
    return render_template("my_applications.html", apps=rows)


@app.route("/profile", methods=["GET", "POST"])
@login_required("student")
def profile():
    st = current_student()
    if request.method == "POST":
        f = request.form
        db().execute("UPDATE students SET department=?, year=?, cgpa=?, skills=?, resume_link=? WHERE id=?",
                     (f.get("department"), f.get("year"), float(f.get("cgpa") or 0),
                      f.get("skills"), f.get("resume_link"), st["id"]))
        db().commit()
        flash("Profile saved.", "ok")
        return redirect(url_for("profile"))
    return render_template("profile.html", st=st)


# ---------- JSON API ----------
@app.route("/api/jobs")
@login_required("student", "office")
def api_jobs():
    rows = q("""SELECT j.id, j.title, j.kind, j.location, j.pay, j.skills, j.deadline, c.name company
                FROM jobs j JOIN companies c ON c.id=j.company_id WHERE j.active=1""")
    return jsonify([dict(r) for r in rows])


if __name__ == "__main__":
    init_db()
    app.run(debug=True, port=5000)
