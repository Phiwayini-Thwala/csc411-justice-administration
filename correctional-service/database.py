"""SQLite setup for the Correctional service (database per service)."""
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterator

import bcrypt

DB_PATH = os.getenv("CORRECTIONAL_DB", os.path.join(os.path.dirname(os.path.abspath(__file__)), "correctional.db"))
DEMO_PASSWORD = os.getenv("DEMO_PASSWORD", "Passw0rd!")


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0, tzinfo=None).isoformat()


@contextmanager
def db() -> Iterator[sqlite3.Connection]:
    """One connection per unit of work: commit on success, roll back on error, always close."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    username TEXT PRIMARY KEY, password_hash TEXT NOT NULL, role TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS inmates (
    inmate_id TEXT PRIMARY KEY, national_id TEXT NOT NULL, full_name TEXT,
    court_case_id TEXT NOT NULL,
    admission_type TEXT NOT NULL,          -- REMAND or CONVICTED (how the person arrived)
    status TEXT NOT NULL,                  -- REMAND, CONVICTED, TRANSFERRED, RELEASED (contract field)
    facility TEXT NOT NULL, sentence_months INTEGER,
    admitted_at TEXT NOT NULL, released_at TEXT,
    legal_status TEXT,                     -- REMAND or CONVICTED, kept when the status is TRANSFERRED
    court_sync TEXT, court_sync_message TEXT);
CREATE TABLE IF NOT EXISTS transfers (
    transfer_id INTEGER PRIMARY KEY AUTOINCREMENT, inmate_id TEXT NOT NULL,
    from_facility TEXT NOT NULL, new_facility TEXT NOT NULL, reason TEXT,
    transferred_at TEXT NOT NULL, by_user TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS releases (
    release_id INTEGER PRIMARY KEY AUTOINCREMENT, inmate_id TEXT NOT NULL,
    reason TEXT NOT NULL, notes TEXT, released_at TEXT NOT NULL, by_user TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT, time TEXT NOT NULL, username TEXT NOT NULL,
    role TEXT NOT NULL, action TEXT NOT NULL, record_id TEXT);
"""

# Columns added after the first version; added to an existing correctional.db on start.
NEW_COLUMNS = {"legal_status": "TEXT", "court_sync": "TEXT", "court_sync_message": "TEXT"}

# Demo accounts, the same four in all three services (change/remove for anything beyond the demo)
SEED_USERS = [
    ("correctional1", "correctional_officer"),
    ("court1", "court_officer"),
    ("police1", "police_officer"),
    ("admin1", "admin"),
]

# The same two people the Police and Judiciary services seed (CASE-2026-000x -> CRT-2026-000x).
SEED_INMATES = [
    ("INM-0001", "8001015800083", "Sipho Dlamini", "CRT-2026-0001", "REMAND", "REMAND",
     "Matsapha Correctional Centre", None, "2026-10-20T09:30:00", "REMAND"),
    ("INM-0002", "7505055800081", "Thandi Nkambule", "CRT-2026-0002", "CONVICTED", "CONVICTED",
     "Matsapha Correctional Centre", 24, "2026-10-20T11:00:00", "CONVICTED"),
]


def init_db() -> None:
    with db() as c:
        c.executescript(SCHEMA)
        existing = {r["name"] for r in c.execute("PRAGMA table_info(inmates)")}
        for name, ddl in NEW_COLUMNS.items():
            if name not in existing:
                c.execute(f"ALTER TABLE inmates ADD COLUMN {name} {ddl}")
        c.execute("UPDATE inmates SET legal_status = CASE WHEN sentence_months IS NULL THEN 'REMAND' "
                  "ELSE 'CONVICTED' END WHERE legal_status IS NULL")
        for username, role in SEED_USERS:
            if c.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone() is None:
                h = bcrypt.hashpw(DEMO_PASSWORD.encode(), bcrypt.gensalt()).decode()
                c.execute("INSERT INTO users VALUES (?,?,?)", (username, h, role))
        if c.execute("SELECT COUNT(*) FROM inmates").fetchone()[0] == 0:
            for row in SEED_INMATES:
                c.execute(
                    "INSERT INTO inmates (inmate_id, national_id, full_name, court_case_id, admission_type, "
                    "status, facility, sentence_months, admitted_at, legal_status, court_sync) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,'OK')", row)
