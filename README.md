# e-RESBAHUB: Resident & Health Services System for the Barangay

Web-based system for residents, barangay personnel, health center personnel and administrators.
Bulacan Agricultural State College - Institute of Computer Studies.

**Tech stack:** Python 3 + Flask (back end) - SQLite (database) - HTML/CSS/JavaScript with Jinja templates (front end).
No Node.js, no XAMPP, no database server to install. Only Python.

---------------------------------------------------------------------

## 1. What the system does (matches the approved scope)

| Scope item | Where in the system |
|---|---|
| Resident registration & profile | `/register`, `/profile` (identity fields lock after verification) |
| Online barangay requests + document upload | `/requests/new` (PDF/PNG/JPG, max 3 files, 5 MB) |
| Request tracking & notifications | `/requests`, `/requests/<id>`, `/notifications` |
| Administrative dashboard | `/staff/` (pending / ongoing / completed counts) |
| Request approval & processing | Open a request > "Process request" (approve / reject / remarks) |
| Barangay announcements | `/staff/announcements` (post), `/announcements` (everyone reads) |
| Patient registration & records | `/health/patients` |
| Appointment & queue management | `/health/appointments` (queue number auto-assigned per day) |
| Health service management | Visit form: consultation, immunization, maternal & child health, health monitoring, other |
| Patient visit monitoring | `/health/visits`, patient detail page (date, purpose, services, vitals) |
| Search & record retrieval | `/search` + search boxes on every list |
| Reports & monitoring | `/reports` (+ CSV download, print) |
| User access control | 4 roles: Resident, Barangay Personnel, Health Center Personnel, Administrator |

---------------------------------------------------------------------

## 2. One-time setup (Windows, step by step)

### Step 1 - Install Python
1. Go to https://www.python.org/downloads/ and install Python 3.10 or newer.
2. **Tick "Add python.exe to PATH"** on the first installer screen, then click Install.
3. Open **Command Prompt** (press Windows key, type `cmd`, Enter) and check:
   ```
   python --version
   ```
   It must print `Python 3.x.x`. (On Mac/Linux use `python3` instead of `python` everywhere below.)

### Step 2 - Get the project
- If your team uses GitHub (see Section 5): `git clone <repo-url>` then `cd e-resbahub`
- Or unzip the project folder and open Command Prompt inside it:
  `cd C:\path\to\e-resbahub`

### Step 3 - Create a virtual environment (keeps packages tidy)
```
python -m venv venv
venv\Scripts\activate
```
Your prompt should now start with `(venv)`. (Mac/Linux: `source venv/bin/activate`)

### Step 4 - Install the packages
```
pip install -r requirements.txt
```

### Step 5 - Create the database and the first admin
```
python seed.py --demo
```
This creates `instance/resbahub.db` (the database) and these accounts:

| Username | Password | Role |
|---|---|---|
| admin | Admin@12345 | Administrator |
| barangay1 | Demo@12345 | Barangay Personnel |
| health1 | Demo@12345 | Health Center Personnel |
| resident1 | Demo@12345 | Resident (verified) |
| resident2 | Demo@12345 | Resident (NOT verified) |

Use `python seed.py` (without `--demo`) for a clean system with only the admin.
**Change the admin password right after your first login** (top bar > Password).

### Step 6 - Run the system
```
python run.py
```
Open your browser at **http://127.0.0.1:5000** . Stop the server with `Ctrl + C`.

### Next time you work on it
```
cd e-resbahub
venv\Scripts\activate
python run.py
```

---------------------------------------------------------------------

## 3. Try it (suggested demo flow)

1. Log in as `resident1` > **New Request** > choose *Barangay Clearance*, write a purpose, upload a PNG/JPG/PDF > Submit. Note the reference number.
2. Log out, log in as `barangay1` > **Requests** > open it > change status to *Processing / Approved* (a *Rejected* status needs a remark) > later *Completed*.
3. Log in again as `resident1` > **Notifications** and **My Requests** show the new status and history.
4. As `barangay1` > **Residents** > open `resident2` > tick *Verified resident* > Save. `resident2` can now submit requests.
5. As `health1` > **Patients** > *New patient* > **Book appointment** (queue number is automatic) > on the day, change status Waiting > In Consultation and **Record visit**.
6. As `health1` or `barangay1` > **Reports** to see the summaries and download CSV files.
7. As `admin` > **Admin** to create staff accounts, manage services (and fees), and read the audit log.

---------------------------------------------------------------------

## 4. Project structure (who edits what)

```
e-resbahub/
  run.py                  start the server
  seed.py                 creates admin / demo data
  requirements.txt        Python packages
  tests/test_app.py       automated tests (27)
  resbahub/
    __init__.py           app setup, security (CSRF, headers), error pages
    schema.sql            DATABASE: all tables           <- Database Programmer
    db.py                 database connection helpers    <- Database Programmer
    utils.py              validation, notifications, audit log, upload checks
    auth.py               login, register, roles         <- Back-End Programmer
    resident.py           resident pages & requests      <- Back-End Programmer
    staff.py              barangay personnel pages       <- Back-End Programmer
    health.py             health center pages            <- Back-End Programmer
    admin.py              users, services, audit log     <- Back-End Programmer
    reports.py            reports, CSV export, search    <- Back-End Programmer
    templates/            HTML pages (Jinja)             <- Front-End Programmer / Designer
    static/css/style.css  design (colors, layout)        <- Digital Designer
    static/js/app.js      small browser scripts          <- Front-End Programmer
  instance/               created automatically: database, uploaded files, secret key (NOT in Git)
```

### Database tables
`users`, `residents`, `services`, `requests`, `request_documents`, `request_history`, `notifications`,
`announcements`, `patients`, `appointments`, `visits`, `audit_log`.
Open the database with the free **DB Browser for SQLite** (https://sqlitebrowser.org) > File > Open > `instance/resbahub.db`.

### Security built in
Password hashing - CSRF protection on every form - login throttling (5 wrong tries = 5-minute wait) - role checks on every page -
residents can only see their own requests - upload type/size/content checks with random stored names - SQL injection safe (parameterized queries) -
XSS safe (auto-escaped templates) - CSV formula-injection guard - secure HTTP headers - audit log - Data Privacy consent at registration.

---------------------------------------------------------------------

## 5. Team repository (GitHub) - everyone can access and edit

1. **One person (e.g. Project Manager)** creates a free account at https://github.com > **New repository** > name `e-resbahub` > *Private* > create (do not add a README).
2. Repository **Settings > Collaborators > Add people** > add every teammate's GitHub username (they accept the email invite).
3. Everyone installs **Git** (https://git-scm.com/download/win) and sets their identity once:
   ```
   git config --global user.name "Your Name"
   git config --global user.email "you@example.com"
   ```
4. The person who has this project folder uploads it (first time only), inside the project folder:
   ```
   git init
   git add .
   git commit -m "Initial e-RESBAHUB system"
   git branch -M main
   git remote add origin https://github.com/<owner>/e-resbahub.git
   git push -u origin main
   ```
   `.gitignore` already keeps the database, uploads and secret key **out** of GitHub.
5. Everyone else downloads it: `git clone https://github.com/<owner>/e-resbahub.git` and follows Section 2 (Steps 3-6).

### Daily teamwork routine (avoid overwriting each other)
```
git pull                                  # 1. get the latest code BEFORE you start
git checkout -b feature/short-name        # 2. work on your own branch (e.g. feature/patient-form)
   ... edit files, test with python run.py ...
python -m unittest                        # 3. run the tests; they should say OK
git add .
git commit -m "Describe what you changed"
git push -u origin feature/short-name     # 4. upload your branch
```
Then on GitHub click **Compare & pull request** > a teammate reviews > **Merge**. Everyone runs `git checkout main` and `git pull` afterwards.
Tip: let each member mainly edit their own area (see "who edits what") so merge conflicts are rare. Never commit the `instance/` or `venv/` folders.

---------------------------------------------------------------------

## 6. Troubleshooting

| Problem | Fix |
|---|---|
| `'python' is not recognized` | Reinstall Python and tick "Add python.exe to PATH"; reopen Command Prompt. |
| `No module named flask` | You forgot `venv\Scripts\activate` or `pip install -r requirements.txt`. |
| `Address already in use` | Another program uses port 5000. Edit `port=5000` in `run.py` to `5001` and open that port. |
| PowerShell says scripts are disabled | Use **Command Prompt** (cmd), or run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once. |
| Forgot admin password | Delete the `instance` folder, run `python seed.py` again (this erases all data!). |
| Want a fresh demo | Stop the server, delete the `instance` folder, run `python seed.py --demo`. |
| "Form token missing or expired" | Refresh the page and submit again (the session expired). |
| Upload rejected | Only real PDF/PNG/JPG files, max 3 files and 5 MB total. |

## 7. Settings you may change
- Barangay name shown in the footer: set an environment variable `BARANGAY_NAME` (Windows: `set BARANGAY_NAME=Barangay Pinaod`) before `python run.py`, or edit `resbahub/__init__.py`.
- Require verification before requests: `REQUIRE_VERIFIED_FOR_REQUESTS` in `resbahub/__init__.py` (True/False).
- Service fees are SAMPLE values: edit them in **Admin > Barangay services** (add new services there too).

## 8. Before real-world (production) use
This is a complete academic system. Before using it with real residents: run it with a production server (e.g. `pip install waitress` then `waitress-serve --port=8000 --call resbahub:create_app`),
use HTTPS, set a strong `SECRET_KEY`, back up `instance/` regularly, and get the barangay's approval on data-privacy handling (RA 10173).
Moving to MySQL/PostgreSQL later means rewriting `db.py` and small SQL differences in `schema.sql`.
