"""Correctional Service (port 8003). Run: uvicorn main:app --port 8003 --reload"""
from contextlib import asynccontextmanager
from typing import Literal, Optional

import bcrypt
from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

from auth import ApiError, create_token, require_roles
from database import get_conn, init_db, now


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Correctional Service", version="1.0.0", lifespan=lifespan)

# Court officers act only through Judiciary service calls (intended use, see design 6.2)
COURT_WRITE = ("court_officer", "correctional_officer", "admin")
READ_ROLES = ("correctional_officer", "admin", "police_officer", "court_officer")


# ---------- error format: {"error": "...", "message": "..."} ----------
@app.exception_handler(ApiError)
async def api_error(_: Request, e: ApiError):
    return JSONResponse(status_code=e.status, content={"error": e.code, "message": e.message})


@app.exception_handler(RequestValidationError)
async def validation_error(_: Request, e: RequestValidationError):
    msg = "; ".join(f"{'.'.join(str(p) for p in x['loc'][1:])}: {x['msg']}" for x in e.errors())
    return JSONResponse(status_code=400, content={"error": "VALIDATION_ERROR", "message": msg})


@app.exception_handler(StarletteHTTPException)
async def http_error(_: Request, e: StarletteHTTPException):
    code = {404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED"}.get(e.status_code, "ERROR")
    return JSONResponse(status_code=e.status_code, content={"error": code, "message": str(e.detail)})


# ---------- schemas ----------
class LoginRequest(BaseModel):
    username: str
    password: str


class AdmitRequest(BaseModel):
    national_id: str = Field(min_length=1)
    court_case_id: str = Field(min_length=1)
    admission_type: Literal["REMAND", "CONVICTED"]
    facility: str = Field(min_length=1)
    full_name: str = Field(min_length=1)
    sentence_months: Optional[int] = Field(default=None, gt=0)


class StatusUpdate(BaseModel):
    status: Literal["REMAND", "CONVICTED"]
    sentence_months: Optional[int] = Field(default=None, gt=0)


class TransferRequest(BaseModel):
    new_facility: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class ReleaseRequest(BaseModel):
    reason: Literal["SENTENCE_COMPLETED", "ACQUITTED", "COURT_ORDER", "BAIL_GRANTED"]
    notes: Optional[str] = None


# ---------- helpers ----------
def audit(c, user: dict, action: str, record_id: str) -> None:
    c.execute("INSERT INTO audit_log (time, username, role, action, record_id) VALUES (?,?,?,?,?)",
              (now(), user["username"], user["role"], action, record_id))


def get_inmate(c, inmate_id: str):
    row = c.execute("SELECT * FROM inmates WHERE inmate_id=?", (inmate_id,)).fetchone()
    if row is None:
        raise ApiError(404, "NOT_FOUND", f"Inmate {inmate_id} does not exist")
    return row


def full_inmate(c, inmate_id: str) -> dict:
    data = dict(get_inmate(c, inmate_id))
    data["transfers"] = [dict(r) for r in c.execute(
        "SELECT * FROM transfers WHERE inmate_id=? ORDER BY transfer_id", (inmate_id,))]
    return data


# ---------- endpoints ----------
@app.post("/auth/login")
def login(body: LoginRequest):
    with get_conn() as c:
        row = c.execute("SELECT * FROM users WHERE username=?", (body.username,)).fetchone()
    if row is None or not bcrypt.checkpw(body.password.encode(), row["password_hash"].encode()):
        raise ApiError(401, "UNAUTHORIZED", "Invalid username or password")
    return {"access_token": create_token(row["username"], row["role"]),
            "token_type": "bearer", "expires_in": 3600, "role": row["role"]}


@app.post("/inmates", status_code=201)
def admit_inmate(body: AdmitRequest, user=Depends(require_roles(*COURT_WRITE))):
    if body.admission_type == "CONVICTED" and body.sentence_months is None:
        raise ApiError(400, "VALIDATION_ERROR", "sentence_months is required when CONVICTED")
    with get_conn() as c:
        if c.execute("SELECT 1 FROM inmates WHERE court_case_id=? AND status!='RELEASED'", (body.court_case_id,)).fetchone():
            raise ApiError(409, "CONFLICT", f"Court case {body.court_case_id} already has an inmate in custody")
        n = c.execute("SELECT COUNT(*) FROM inmates").fetchone()[0] + 1
        inmate_id = f"INM-{n:04d}"
        c.execute("INSERT INTO inmates VALUES (?,?,?,?,?,?,?,?,?,NULL)",
                  (inmate_id, body.national_id, body.full_name, body.court_case_id,
                   body.admission_type, body.admission_type, body.facility,
                   body.sentence_months, now()))
        audit(c, user, f"ADMIT_{body.admission_type}", inmate_id)
        return full_inmate(c, inmate_id)


@app.get("/inmates/{inmate_id}")
def inmate_status(inmate_id: str, user=Depends(require_roles(*READ_ROLES))):
    with get_conn() as c:
        return full_inmate(c, inmate_id)


@app.put("/inmates/{inmate_id}/status")
def update_status(inmate_id: str, body: StatusUpdate, user=Depends(require_roles(*COURT_WRITE))):
    with get_conn() as c:
        inm = get_inmate(c, inmate_id)
        if inm["status"] == "RELEASED":
            raise ApiError(409, "CONFLICT", "Inmate is already released")
        if body.status != "CONVICTED" or inm["admission_type"] != "REMAND":
            raise ApiError(409, "CONFLICT", "Only a remand inmate can be updated to CONVICTED")
        if body.sentence_months is None:
            raise ApiError(400, "VALIDATION_ERROR", "sentence_months is required when CONVICTED")
        new_status = "TRANSFERRED" if inm["status"] == "TRANSFERRED" else "CONVICTED"
        c.execute("UPDATE inmates SET admission_type='CONVICTED', status=?, sentence_months=? "
                  "WHERE inmate_id=?", (new_status, body.sentence_months, inmate_id))
        audit(c, user, "SET_CONVICTED", inmate_id)
        return full_inmate(c, inmate_id)


@app.put("/inmates/{inmate_id}/transfer")
def transfer_inmate(inmate_id: str, body: TransferRequest,
                    user=Depends(require_roles("correctional_officer", "admin"))):
    with get_conn() as c:
        inm = get_inmate(c, inmate_id)
        if inm["status"] == "RELEASED":
            raise ApiError(409, "CONFLICT", "Cannot transfer a released inmate")
        if inm["facility"] == body.new_facility:
            raise ApiError(409, "CONFLICT", "Inmate is already at that facility")
        c.execute("INSERT INTO transfers (inmate_id, from_facility, new_facility, reason, "
                  "transferred_at, by_user) VALUES (?,?,?,?,?,?)",
                  (inmate_id, inm["facility"], body.new_facility, body.reason, now(), user["username"]))
        c.execute("UPDATE inmates SET facility=?, status='TRANSFERRED' WHERE inmate_id=?",
                  (body.new_facility, inmate_id))
        audit(c, user, "TRANSFER", inmate_id)
        return full_inmate(c, inmate_id)


@app.post("/inmates/{inmate_id}/release")
def release_inmate(inmate_id: str, body: ReleaseRequest, user=Depends(require_roles(*COURT_WRITE))):
    with get_conn() as c:
        inm = get_inmate(c, inmate_id)
        if inm["status"] == "RELEASED":
            raise ApiError(409, "CONFLICT", "Inmate is already released")
        ts = now()
        c.execute("INSERT INTO releases (inmate_id, reason, notes, released_at, by_user) "
                  "VALUES (?,?,?,?,?)", (inmate_id, body.reason, body.notes, ts, user["username"]))
        c.execute("UPDATE inmates SET status='RELEASED', released_at=? WHERE inmate_id=?", (ts, inmate_id))
        audit(c, user, f"RELEASE_{body.reason}", inmate_id)
        return full_inmate(c, inmate_id)


@app.get("/audit-logs")
def audit_logs(user=Depends(require_roles("admin"))):
    with get_conn() as c:
        return [dict(r) for r in c.execute("SELECT * FROM audit_log ORDER BY id DESC")]
