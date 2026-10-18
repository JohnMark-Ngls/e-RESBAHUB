
# e-RESBAHUB: Resident & Health Services System for the Barangay

Web-based system for residents, barangay personnel, health center personnel, and administrators.

Bulacan Agricultural State College - Institute of Computer Studies.

**Tech Stack:** Python 3 + Flask (back end), SQLite (database), HTML/CSS/JavaScript with Jinja templates (front end).

No Node.js, no XAMPP, and no database server to install. Only Python is required.

---

## 1. What the System Does

| Scope Item | Where in the System |
|---|---|
| Resident registration and profile | `/register`, `/profile` |
| Online barangay requests and document upload | `/requests/new` |
| Request tracking and notifications | `/requests`, `/requests/<id>`, `/notifications` |
| Administrative dashboard | `/staff/` |
| Request approval and processing | Open a request and select Process Request |
| Barangay announcements | `/staff/announcements`, `/announcements` |
| Patient registration and records | `/health/patients` |
| Appointment and queue management | `/health/appointments` |
| Health service management | Consultation, immunization, maternal and child health, health monitoring, and other services |
| Patient visit monitoring | `/health/visits` and patient detail pages |
| Search and record retrieval | `/search` and search boxes on lists |
| Reports and monitoring | `/reports`, including CSV download and printing |
| User access control | Resident, Barangay Personnel, Health Center Personnel, Administrator |

---

## 2. One-Time Setup (Windows)

### Step 1 - Install Python

1. Visit https://www.python.org/downloads/.
2. Install a Python version supported by the project's dependencies.
3. Enable **Add Python to PATH** during installation.
4. Open Command Prompt or the VS Code terminal and run:

```bash
python --version
```

### Step 2 - Get the Project

If you downloaded the project as a ZIP file, extract it and open the extracted `e-resbahub` folder in VS Code.

If your team uses GitHub, clone the repository instead:

```bash
git clone <repo-url>
cd e-resbahub
```

Make sure the folder contains `run.py` and `requirements.txt`.

### Step 3 - Create a Virtual Environment

```bash
python -m venv venv
```

Activate it in Windows PowerShell:

```powershell
.\venv\Scripts\Activate.ps1
```

If PowerShell blocks activation, you can use Command Prompt:

```bat
venv\Scripts\activate.bat
```

Your terminal should show `(venv)` when activation succeeds.

### Step 4 - Install the Packages

```bash
python -m pip install -r requirements.txt
```

### Step 5 - Create the Database and Demo Accounts

```bash
python seed.py --demo
```

This initializes the local database and creates demo accounts.

| Username | Password | Role |
|---|---|---|
| `admin` | `Admin@12345` | Administrator |
| `barangay1` | `Demo@12345` | Barangay Personnel |
| `health1` | `Demo@12345` | Health Center Personnel |
| `resident1` | `Demo@12345` | Resident (verified) |
| `resident2` | `Demo@12345` | Resident (not verified) |

Use `python seed.py` without `--demo` for a clean system with only the administrator, according to the project's setup instructions.

**Change the administrator password after your first login.**

### Step 6 - Run the System

```bash
python run.py
```

Open your browser at:

http://127.0.0.1:5000

Keep the terminal running while using the application. Press `Ctrl + C` to stop the server.

### Next Time You Work on the Project

```powershell
.\venv\Scripts\Activate.ps1
python run.py
```

---

## 3. Suggested Demo Flow

1. Log in as `resident1`. Submit a new Barangay Clearance request with a purpose and an allowed document.
2. Log in as `barangay1`. Open the request, process it, and update its status.
3. Log in again as `resident1`. Check My Requests and Notifications.
4. As `barangay1`, verify `resident2` if required by the system.
5. Log in as `health1`. Register a patient, book an appointment, and record a visit.
6. As `health1` or `barangay1`, open Reports to view summaries and download CSV files.
7. As `admin`, manage staff accounts, services, fees, and audit logs.

---

## 4. Project Structure

```text
e-resbahub/
├── run.py
├── seed.py
├── requirements.txt
├── tests/
│   └── test_app.py
├── resbahub/
│   ├── __init__.py
│   ├── schema.sql
│   ├── db.py
│   ├── utils.py
│   ├── auth.py
│   ├── resident.py
│   ├── staff.py
│   ├── health.py
│   ├── admin.py
│   ├── reports.py
│   ├── templates/
│   └── static/
│       ├── css/
│       │   └── style.css
│       └── js/
│           └── app.js
└── instance/
```

### Main File Responsibilities

- `run.py` - Starts the Flask development server.
- `seed.py` - Initializes the database and creates administrator or demo data.
- `requirements.txt` - Lists required Python packages.
- `resbahub/__init__.py` - Application setup, security configuration, and error pages.
- `resbahub/schema.sql` - Database table definitions.
- `resbahub/db.py` - Database connection helpers.
- `resbahub/utils.py` - Validation, notifications, audit logging, and upload checks.
- `resbahub/auth.py` - Login, registration, and role management.
- `resbahub/resident.py` - Resident pages and requests.
- `resbahub/staff.py` - Barangay personnel pages.
- `resbahub/health.py` - Health center pages.
- `resbahub/admin.py` - User management, services, and audit logs.
- `resbahub/reports.py` - Reports, CSV exports, and search.
- `resbahub/templates/` - HTML templates rendered by Jinja.
- `resbahub/static/css/style.css` - Website styling.
- `resbahub/static/js/app.js` - Browser-side JavaScript.

The `instance/` folder is used for local application data. Do not upload private databases, uploaded documents, or secret keys to GitHub.

### Database Tables

The project documentation identifies these tables:

- `users`
- `residents`
- `services`
- `requests`
- `request_documents`
- `request_history`
- `notifications`
- `announcements`
- `patients`
- `appointments`
- `visits`
- `audit_log`

You can inspect the local SQLite database using DB Browser for SQLite:

https://sqlitebrowser.org/

### Security Features Described in the Project

- Password hashing
- CSRF protection
- Login throttling
- Role-based access checks
- Resident request access restrictions
- Upload validation
- Parameterized SQL queries
- Template output escaping
- CSV formula-injection protection
- Security headers
- Audit logging
- Data privacy consent during registration

Verify these features against the actual application code before claiming they are all fully implemented.

---

## 5. Team Repository (GitHub)

### Initial Repository Setup

1. Create a GitHub repository or use your existing team repository.
2. Add teammates through the repository's Settings and Collaborators section.
3. Configure your Git identity once:

```bash
git config --global user.name "Your Name"
git config --global user.email "you@example.com"
```

Replace the example name and email with your own details.

### Uploading the Project for the First Time

Run these commands only when initializing a new local Git repository:

```bash
git init
git add .
git commit -m "Initial e-RESBAHUB system"
git branch -M main
git remote add origin https://github.com/<owner>/e-resbahub.git
git push -u origin main
```

Replace `<owner>` with the actual GitHub username or organization.

**If your repository already exists and has commits, do not blindly repeat these commands.** Check your existing remote and repository history first to avoid conflicts or overwriting work.

### Daily Teamwork Routine

```bash
git pull
git checkout -b feature/short-name

# Edit files and test the application.
python run.py

# Run the tests.
python -m unittest

git add .
git commit -m "Describe what you changed"
git push -u origin feature/short-name
```

After pushing, create a pull request on GitHub. Have a teammate review and merge it. Then update your local main branch:

```bash
git checkout main
git pull origin main
```

Avoid committing `venv/`, private environment files, local databases, uploaded documents, or secret keys.

---

## 6. Troubleshooting

| Problem | Solution |
|---|---|
| `python` is not recognized | Install Python and enable Add Python to PATH. Restart VS Code. |
| `No module named flask` | Activate the virtual environment and run `python -m pip install -r requirements.txt`. |
| Address already in use | Stop the other process using port 5000 or configure another port in the application. |
| PowerShell says scripts are disabled | Use Command Prompt or temporarily adjust the PowerShell execution policy for the current terminal session. |
| Forgot administrator password | Follow the project's verified password-reset procedure. Do not delete the database unless you intend to erase its data. |
| Want a fresh demo | Back up any needed data before resetting the local database and running the seed script again. |
| Form token missing or expired | Refresh the page and submit the form again. |
| Upload rejected | Check that the file type and size meet the application's configured limits. |

---

## 7. Settings You May Change

- **Barangay name:** The project documentation identifies `BARANGAY_NAME` as an environment setting or a value configurable in `resbahub/__init__.py`.
- **Resident verification:** The documentation identifies `REQUIRE_VERIFIED_FOR_REQUESTS` as a setting in `resbahub/__init__.py`.
- **Service fees:** Sample service fees may be configurable through the Admin section.

Check the actual source code before changing settings, since the implementation may differ from the documentation.

---

## 8. Before Real-World Production Use

This project is intended as an academic system. Before using it with real residents:

1. Use a production-ready application server instead of Flask's development server.
2. Configure HTTPS.
3. Set a strong, private `SECRET_KEY`.
4. Arrange secure database backups and access controls.
5. Protect uploaded files and private resident or patient information.
6. Obtain the necessary barangay approvals and review compliance with the Philippine Data Privacy Act of 2012 (RA 10173).
7. Test authentication, authorization, input validation, backups, and recovery procedures.

The project documentation indicates that moving from SQLite to MySQL or PostgreSQL would require changes to the database connection code and potentially SQL statements in `schema.sql`.

---

**End of README**
