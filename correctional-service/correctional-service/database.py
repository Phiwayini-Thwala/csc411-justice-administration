"""SQLite setup for the Correctional service (database per service)."""
import os
import sqlite3
from datetime import datetime, timezone

import bcrypt

DB_PATH = os.getenv("CORRECTIONAL_DB", os.path.join(os.path.dirname(__file__), "correctional.db"))


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    username TEXT PRIMARY KEY, password_hash TEXT NOT NULL, role TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS inmates (
    inmate_id TEXT PRIMARY KEY, national_id TEXT NOT NULL, full_name TEXT,
    court_case_id TEXT NOT NULL,
    admission_type TEXT NOT NULL,          -- REMAND or CONVICTED
    status TEXT NOT NULL,                  -- REMAND, CONVICTED, TRANSFERRED, RELEASED
    facility TEXT NOT NULL, sentence_months INTEGER,
    admitted_at TEXT NOT NULL, released_at TEXT);
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

# Demo accounts (change/remove for anything beyond the demo)
SEED_USERS = [
    ("correctional1", "Passw0rd!", "correctional_officer"),
    ("court1", "Passw0rd!", "court_officer"),
    ("police1", "Passw0rd!", "police_officer"),
    ("admin1", "Passw0rd!", "admin"),
]


def init_db() -> None:
    with get_conn() as c:
        c.executescript(SCHEMA)
        if c.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
            for u, p, r in SEED_USERS:
                h = bcrypt.hashpw(p.encode(), bcrypt.gensalt()).decode()
                c.execute("INSERT INTO users VALUES (?,?,?)", (u, h, r))
        if c.execute("SELECT COUNT(*) FROM inmates").fetchone()[0] == 0:
            c.execute(
                "INSERT INTO inmates VALUES (?,?,?,?,?,?,?,?,?,NULL)",
                ("INM-0001", "8001015800083", "Sipho Dlamini", "CRT-2026-0001",
                 "REMAND", "REMAND", "Matsapha Correctional Centre", None, now()))
            c.execute(
                "INSERT INTO inmates VALUES (?,?,?,?,?,?,?,?,?,NULL)",
                ("INM-0002", "7505055800081", "Thandi Nkambule", "CRT-2026-0002",
                 "CONVICTED", "CONVICTED", "Matsapha Correctional Centre", 24, now()))
