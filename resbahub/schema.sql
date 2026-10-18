-- e-RESBAHUB database schema (SQLite). Safe to run many times (IF NOT EXISTS).

CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT NOT NULL UNIQUE COLLATE NOCASE,
    email         TEXT NOT NULL UNIQUE COLLATE NOCASE,
    full_name     TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL CHECK (role IN ('resident','barangay_staff','health_staff','admin')),
    is_active     INTEGER NOT NULL DEFAULT 1,
    created_at    TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    last_login    TEXT
);

CREATE TABLE IF NOT EXISTS residents (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    first_name  TEXT NOT NULL,
    middle_name TEXT,
    last_name   TEXT NOT NULL,
    suffix      TEXT,
    birthdate   TEXT NOT NULL,
    sex         TEXT NOT NULL CHECK (sex IN ('Male','Female')),
    civil_status TEXT NOT NULL,
    contact_no  TEXT NOT NULL,
    address     TEXT NOT NULL,
    purok       TEXT,
    occupation  TEXT,
    is_verified INTEGER NOT NULL DEFAULT 0,
    verified_by INTEGER REFERENCES users(id),
    verified_at TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS services (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    name              TEXT NOT NULL UNIQUE,
    description       TEXT,
    requires_document INTEGER NOT NULL DEFAULT 0,
    fee               REAL NOT NULL DEFAULT 0,
    is_active         INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS requests (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    reference_no TEXT UNIQUE,
    resident_id  INTEGER NOT NULL REFERENCES residents(id) ON DELETE CASCADE,
    service_id   INTEGER NOT NULL REFERENCES services(id),
    purpose      TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'Pending'
                 CHECK (status IN ('Pending','Processing','Approved','Rejected','Completed','Cancelled')),
    remarks      TEXT,
    processed_by INTEGER REFERENCES users(id),
    created_at   TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    updated_at   TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS request_documents (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id    INTEGER NOT NULL REFERENCES requests(id) ON DELETE CASCADE,
    original_name TEXT NOT NULL,
    stored_name   TEXT NOT NULL,
    uploaded_at   TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS request_history (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id INTEGER NOT NULL REFERENCES requests(id) ON DELETE CASCADE,
    status     TEXT NOT NULL,
    remarks    TEXT,
    changed_by INTEGER REFERENCES users(id),
    changed_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS notifications (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    message    TEXT NOT NULL,
    link       TEXT,
    is_read    INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS announcements (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    title      TEXT NOT NULL,
    body       TEXT NOT NULL,
    category   TEXT NOT NULL DEFAULT 'Announcement'
               CHECK (category IN ('Announcement','Schedule','Reminder','Health')),
    posted_by  INTEGER REFERENCES users(id),
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS patients (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_no    TEXT UNIQUE,
    resident_id   INTEGER REFERENCES residents(id) ON DELETE SET NULL,
    first_name    TEXT NOT NULL,
    middle_name   TEXT,
    last_name     TEXT NOT NULL,
    birthdate     TEXT NOT NULL,
    sex           TEXT NOT NULL CHECK (sex IN ('Male','Female')),
    contact_no    TEXT,
    address       TEXT,
    guardian_name TEXT,
    blood_type    TEXT,
    allergies     TEXT,
    notes         TEXT,
    created_by    INTEGER REFERENCES users(id),
    created_at    TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_patients_resident ON patients(resident_id) WHERE resident_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS appointments (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id       INTEGER NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
    service_type     TEXT NOT NULL,
    appointment_date TEXT NOT NULL,
    appointment_time TEXT,
    queue_no         INTEGER NOT NULL,
    status           TEXT NOT NULL DEFAULT 'Scheduled'
                     CHECK (status IN ('Scheduled','Waiting','In Consultation','Completed','Cancelled','No Show')),
    notes            TEXT,
    created_by       INTEGER REFERENCES users(id),
    created_at       TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    UNIQUE (appointment_date, queue_no)
);

CREATE TABLE IF NOT EXISTS visits (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id        INTEGER NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
    appointment_id    INTEGER REFERENCES appointments(id) ON DELETE SET NULL,
    visit_date        TEXT NOT NULL,
    service_type      TEXT NOT NULL,
    purpose           TEXT NOT NULL,
    services_provided TEXT,
    findings          TEXT,
    blood_pressure    TEXT,
    temperature       REAL,
    weight_kg         REAL,
    follow_up_date    TEXT,
    attended_by       INTEGER REFERENCES users(id),
    created_at        TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS audit_log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER REFERENCES users(id) ON DELETE SET NULL,
    action     TEXT NOT NULL,
    detail     TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE INDEX IF NOT EXISTS ix_requests_status    ON requests(status);
CREATE INDEX IF NOT EXISTS ix_requests_resident  ON requests(resident_id);
CREATE INDEX IF NOT EXISTS ix_patients_name      ON patients(last_name, first_name);
CREATE INDEX IF NOT EXISTS ix_appt_date          ON appointments(appointment_date);
CREATE INDEX IF NOT EXISTS ix_visits_date        ON visits(visit_date);
CREATE INDEX IF NOT EXISTS ix_notif_user         ON notifications(user_id, is_read);

-- Starting list of barangay services (fees are SAMPLE values; edit them under Admin > Services).
INSERT OR IGNORE INTO services (name, description, requires_document, fee) VALUES
 ('Barangay Clearance',        'Clearance for employment, business, travel and other legal purposes.', 1, 50),
 ('Certificate of Indigency',  'Proof that the resident belongs to an indigent family (for assistance, scholarships, medical aid).', 1, 0),
 ('Certificate of Residency',  'Proof that the resident lives in the barangay.', 1, 50),
 ('Barangay Certificate',      'General certification issued by the barangay.', 0, 50),
 ('Other Barangay Service',    'Other barangay-approved service. Describe it in the purpose field.', 0, 0);
