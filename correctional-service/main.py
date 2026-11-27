"""Correctional Service API (port 8003) - CSC411 Justice Administration System.

Run (from the correctional-service folder):
    uvicorn main:app --port 8003 --reload

Inmates are admitted by the Judiciary service (remand or sentence) or by a
correctional officer. Transfers and releases done here are reported back to
the Judiciary service, which in turn reports to the Police service.
"""
import logging
import os
import time
from contextlib import asynccontextmanager
from typing import Literal, Optional

import bcrypt
from fastapi import Depends, FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

import judiciary_client
from auth import SECRET, TOKEN_MINUTES, ApiError, create_token, require_roles
from database import db, init_db, now

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("correctional.http")

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

# ---------------------------------------------------------
# ROLE MATRIX (design 6.2)
# ---------------------------------------------------------
COURT_WRITE = ("court_officer", "correctional_officer", "admin")   # admit, status, release
READ_ROLES = ("correctional_officer", "admin", "police_officer", "court_officer")
CUSTODY_ROLES = ("correctional_officer", "admin")                  # transfer, edit, resend
ADMIN_ROLES = ("admin",)

HTTP_ERROR_CODES = {404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED", 401: "UNAUTHORIZED", 403: "FORBIDDEN"}


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    if SECRET == "dev-only-shared-secret-change-me-32chars":
        logging.getLogger("correctional").warning(
            "Using the development JWT secret. Set JWT_SECRET (same value in all three services).")
    yield


app = FastAPI(
    title="Correctional Service",
    description="Inmate admission, status, transfer and release. Reports transfers and releases "
                "back to the Judiciary service.",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# ---------------------------------------------------------
# ONE ERROR FORMAT FOR EVERY FAILURE (design 9.2)
# ---------------------------------------------------------
def error_body(code: str, message: str) -> dict:
    return {"error": code, "message": message}


@app.exception_handler(ApiError)
async def api_error_handler(request: Request, exc: ApiError):
    headers = {"WWW-Authenticate": "Bearer"} if exc.status == 401 else None
    return JSONResponse(error_body(exc.code, exc.message), status_code=exc.status, headers=headers)


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    parts = []
    for err in exc.errors():
        loc = ".".join(str(p) for p in err["loc"][1:]) or str(err["loc"][0])
        parts.append(f"{loc}: {err['msg']}")
    return JSONResponse(error_body("VALIDATION_ERROR", "; ".join(parts)), status_code=400)


@app.exception_handler(StarletteHTTPException)
async def http_error_handler(request: Request, exc: StarletteHTTPException):
    code = HTTP_ERROR_CODES.get(exc.status_code, "HTTP_ERROR")
    return JSONResponse(error_body(code, str(exc.detail)), status_code=exc.status_code)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    ms = (time.perf_counter() - start) * 1000
    log.info("%s %s -> %s (%.0f ms)", request.method, request.url.path, response.status_code, ms)
    return response


def bad_request(message: str) -> ApiError:
    return ApiError(400, "VALIDATION_ERROR", message)


# ---------------------------------------------------------
# REQUEST MODELS
# ---------------------------------------------------------
class LoginRequest(BaseModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


class AdmitRequest(BaseModel):
    national_id: str = Field(min_length=1, max_length=30)
    full_name: str = Field(min_length=1, max_length=120)
    court_case_id: str = Field(min_length=1, max_length=30)
    admission_type: Literal["REMAND", "CONVICTED"]
    facility: str = Field(min_length=1, max_length=120)
    sentence_months: Optional[int] = Field(default=None, ge=1)


class EditInmateRequest(BaseModel):
    full_name: Optional[str] = None
    facility: Optional[str] = None
    sentence_months: Optional[int] = Field(default=None, ge=1)


class StatusUpdate(BaseModel):
    status: Literal["REMAND", "CONVICTED"]
    sentence_months: Optional[int] = Field(default=None, ge=1)


class TransferRequest(BaseModel):
    new_facility: str = Field(min_length=1, max_length=120)
    reason: str = Field(min_length=1, max_length=255)


class ReleaseRequest(BaseModel):
    reason: Literal["SENTENCE_COMPLETED", "ACQUITTED", "COURT_ORDER", "BAIL_GRANTED"]
    notes: Optional[str] = None


# ---------------------------------------------------------
# DATABASE HELPERS
# ---------------------------------------------------------
def audit(username: str, role: str, action: str, record_id: Optional[str] = None) -> None:
    with db() as conn:
        conn.execute("INSERT INTO audit_log (time, username, role, action, record_id) VALUES (?,?,?,?,?)",
                     (now(), username, role, action, record_id))


def get_inmate(inmate_id: str) -> dict:
    with db() as conn:
        row = conn.execute("SELECT * FROM inmates WHERE inmate_id = ?", (inmate_id,)).fetchone()
    if row is None:
        raise ApiError(404, "NOT_FOUND", f"Inmate {inmate_id} does not exist")
    return dict(row)


def full_inmate(inmate_id: str) -> dict:
    inmate = get_inmate(inmate_id)
    with db() as conn:
        transfers = conn.execute(
            "SELECT transfer_id, from_facility, new_facility, reason, transferred_at, by_user "
            "FROM transfers WHERE inmate_id = ? ORDER BY transfer_id", (inmate_id,)).fetchall()
        releases = conn.execute(
            "SELECT release_id, reason, notes, released_at, by_user "
            "FROM releases WHERE inmate_id = ? ORDER BY release_id", (inmate_id,)).fetchall()
    inmate["transfers"] = [dict(r) for r in transfers]
    inmate["releases"] = [dict(r) for r in releases]
    return inmate


def next_inmate_id(conn) -> str:
    top = conn.execute("SELECT MAX(CAST(SUBSTR(inmate_id, 5) AS INTEGER)) FROM inmates").fetchone()[0]
    return f"INM-{(top or 0) + 1:04d}"


def from_judiciary(request: Request) -> bool:
    """True when the Judiciary itself made this call (remand, verdict, release
    order). Then we must not report the change back to it."""
    return request.headers.get("X-Origin-Service", "").lower() == "judiciary"


def tell_court(inmate: dict, payload: dict, user: dict) -> None:
    """Report a transfer or release to the Judiciary service (best effort)."""
    ok, message = judiciary_client.notify_custody_event(
        inmate["court_case_id"], {"inmate_id": inmate["inmate_id"], **payload}, user["token"], user["username"])
    with db() as conn:
        conn.execute("UPDATE inmates SET court_sync = ?, court_sync_message = ? WHERE inmate_id = ?",
                     ("OK" if ok else "FAILED", message[:255], inmate["inmate_id"]))
    if ok:
        audit(user["username"], user["role"], "COURT_NOTIFIED", inmate["inmate_id"])


# ---------------------------------------------------------
# SERVICE HEALTH AND WEB CONSOLE
# ---------------------------------------------------------
@app.get("/", include_in_schema=False)
def health_check():
    return {"service": "Correctional Service", "port": 8003, "status": "running", "ui": "/ui", "docs": "/docs"}


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/ui", include_in_schema=False)
def ui():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


# ---------------------------------------------------------
# AUTHENTICATION
# ---------------------------------------------------------
@app.post("/auth/login", tags=["Auth"])
def login(data: LoginRequest):
    with db() as conn:
        user = conn.execute("SELECT * FROM users WHERE username = ?", (data.username,)).fetchone()
    ok = bool(user) and bcrypt.checkpw(data.password.encode(), user["password_hash"].encode())
    if not ok:
        raise ApiError(401, "UNAUTHORIZED", "Invalid username or password")
    token = create_token(user["username"], user["role"])
    audit(user["username"], user["role"], "LOGIN", user["username"])
    return {"access_token": token, "token_type": "bearer", "expires_in": TOKEN_MINUTES * 60,
            "username": user["username"], "role": user["role"]}


# ---------------------------------------------------------
# INMATES
# ---------------------------------------------------------
@app.get("/inmates", tags=["Correctional"], summary="List inmates (newest first)")
def list_inmates(
    status: Optional[Literal["REMAND", "CONVICTED", "TRANSFERRED", "RELEASED"]] = None,
    search: Optional[str] = Query(default=None, max_length=100),
    user: dict = Depends(require_roles(*READ_ROLES)),
):
    sql, params = "SELECT * FROM inmates WHERE 1=1", []
    if status:
        sql += " AND status = ?"
        params.append(status)
    if search and search.strip():
        term = f"%{search.strip()}%"
        sql += (" AND (inmate_id LIKE ? OR full_name LIKE ? OR national_id LIKE ? "
                "OR court_case_id LIKE ? OR facility LIKE ?)")
        params.extend([term] * 5)
    sql += " ORDER BY admitted_at DESC, inmate_id DESC"
    with db() as conn:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]


@app.post("/inmates", status_code=201, tags=["Correctional"], summary="Admit an inmate")
def admit_inmate(data: AdmitRequest, user: dict = Depends(require_roles(*COURT_WRITE))):
    if data.admission_type == "CONVICTED" and data.sentence_months is None:
        raise bad_request("sentence_months is required for a convicted inmate")
    if data.admission_type == "REMAND" and data.sentence_months is not None:
        raise bad_request("A remand admission cannot have a sentence")
    with db() as conn:
        active = conn.execute(
            "SELECT inmate_id FROM inmates WHERE court_case_id = ? AND status != 'RELEASED'",
            (data.court_case_id,)).fetchone()
        if active:
            raise ApiError(409, "CONFLICT",
                           f"Court case {data.court_case_id} already has inmate {active['inmate_id']} in custody")
        inmate_id = next_inmate_id(conn)
        conn.execute(
            "INSERT INTO inmates (inmate_id, national_id, full_name, court_case_id, admission_type, status, "
            "facility, sentence_months, admitted_at, released_at, legal_status) "
            "VALUES (?,?,?,?,?,?,?,?,?,NULL,?)",
            (inmate_id, data.national_id.strip(), data.full_name.strip(), data.court_case_id.strip(),
             data.admission_type, data.admission_type, data.facility.strip(), data.sentence_months, now(),
             data.admission_type))
    audit(user["username"], user["role"], "INMATE_ADMITTED", inmate_id)
    return {"message": "Inmate admitted", **full_inmate(inmate_id)}


@app.get("/inmates/{inmate_id}", tags=["Correctional"], summary="Get an inmate with transfers and releases")
def get_inmate_details(inmate_id: str, user: dict = Depends(require_roles(*READ_ROLES))):
    return full_inmate(inmate_id)


@app.get("/inmates/{inmate_id}/linked", tags=["Correctional"],
         summary="The court case behind this inmate, read live from the Judiciary service")
def linked_records(inmate_id: str, user: dict = Depends(require_roles(*READ_ROLES))):
    inmate = get_inmate(inmate_id)
    court, error = judiciary_client.get_court_case(inmate["court_case_id"], user["token"], user["username"])
    return {"inmate_id": inmate_id, "court_case": court, "court_error": error}


@app.put("/inmates/{inmate_id}", tags=["Correctional"], summary="Correct an inmate's details")
def edit_inmate(inmate_id: str, data: EditInmateRequest, user: dict = Depends(require_roles(*CUSTODY_ROLES))):
    inmate = get_inmate(inmate_id)
    if inmate["status"] == "RELEASED":
        raise ApiError(409, "CONFLICT", "A released inmate record cannot be edited")
    changes = data.model_dump(exclude_unset=True)
    if not changes:
        raise bad_request("Provide at least one field to update")
    for field in ("full_name", "facility"):
        if field in changes:
            value = changes[field]
            if value is None or not value.strip():
                raise bad_request(f"{field} cannot be empty")
            changes[field] = value.strip()
    if "sentence_months" in changes:
        if inmate["legal_status"] == "REMAND" and changes["sentence_months"] is not None:
            raise bad_request("A remand inmate cannot have a sentence")
        if inmate["legal_status"] == "CONVICTED" and changes["sentence_months"] is None:
            raise bad_request("A convicted inmate must have a sentence")
    columns = ", ".join(f"{f} = ?" for f in changes)       # field names come from the model, not the user
    with db() as conn:
        conn.execute(f"UPDATE inmates SET {columns} WHERE inmate_id = ?", [*changes.values(), inmate_id])
    audit(user["username"], user["role"], "INMATE_DETAILS_UPDATED", inmate_id)
    return full_inmate(inmate_id)


@app.put("/inmates/{inmate_id}/status", tags=["Correctional"],
         summary="Update the legal status (REMAND to CONVICTED after a guilty verdict)")
def update_inmate_status(inmate_id: str, data: StatusUpdate, user: dict = Depends(require_roles(*COURT_WRITE))):
    inmate = get_inmate(inmate_id)
    if inmate["status"] == "RELEASED":
        raise ApiError(409, "CONFLICT", "The status of a released inmate cannot be updated")
    if inmate["legal_status"] == data.status:
        raise ApiError(409, "CONFLICT", f"Inmate {inmate_id} is already {data.status}")
    if data.status == "CONVICTED" and data.sentence_months is None:
        raise bad_request("sentence_months is required for a convicted inmate")
    if data.status == "REMAND" and data.sentence_months is not None:
        raise bad_request("A remand inmate cannot have a sentence")
    with db() as conn:
        conn.execute("UPDATE inmates SET status = ?, legal_status = ?, sentence_months = ? WHERE inmate_id = ?",
                     (data.status, data.status, data.sentence_months, inmate_id))
    audit(user["username"], user["role"], "STATUS_UPDATED", inmate_id)
    return full_inmate(inmate_id)


@app.put("/inmates/{inmate_id}/transfer", tags=["Correctional"], summary="Transfer to another facility")
def transfer_inmate(inmate_id: str, data: TransferRequest, request: Request,
                    user: dict = Depends(require_roles(*CUSTODY_ROLES))):
    inmate = get_inmate(inmate_id)
    if inmate["status"] == "RELEASED":
        raise ApiError(409, "CONFLICT", "A released inmate cannot be transferred")
    new_facility = data.new_facility.strip()
    if not new_facility:
        raise bad_request("new_facility cannot be empty")
    if inmate["facility"].strip().lower() == new_facility.lower():
        raise ApiError(409, "CONFLICT", "The new facility must be different from the current facility")
    with db() as conn:
        conn.execute(
            "INSERT INTO transfers (inmate_id, from_facility, new_facility, reason, transferred_at, by_user) "
            "VALUES (?,?,?,?,?,?)",
            (inmate_id, inmate["facility"], new_facility, data.reason.strip(), now(), user["username"]))
        conn.execute("UPDATE inmates SET facility = ?, status = 'TRANSFERRED' WHERE inmate_id = ?",
                     (new_facility, inmate_id))
    audit(user["username"], user["role"], "INMATE_TRANSFERRED", inmate_id)
    if not from_judiciary(request):
        tell_court(inmate, {"event": "TRANSFERRED", "facility": new_facility, "reason": data.reason.strip()}, user)
    return full_inmate(inmate_id)


@app.post("/inmates/{inmate_id}/release", tags=["Correctional"], summary="Release an inmate")
def release_inmate(inmate_id: str, data: ReleaseRequest, request: Request,
                   user: dict = Depends(require_roles(*COURT_WRITE))):
    inmate = get_inmate(inmate_id)
    if inmate["status"] == "RELEASED":
        raise ApiError(409, "CONFLICT", f"Inmate {inmate_id} has already been released")
    released_at = now()
    with db() as conn:
        conn.execute("INSERT INTO releases (inmate_id, reason, notes, released_at, by_user) VALUES (?,?,?,?,?)",
                     (inmate_id, data.reason, data.notes, released_at, user["username"]))
        conn.execute("UPDATE inmates SET status = 'RELEASED', released_at = ? WHERE inmate_id = ?",
                     (released_at, inmate_id))
    audit(user["username"], user["role"], "INMATE_RELEASED", inmate_id)
    if not from_judiciary(request):
        tell_court(inmate, {"event": "RELEASED", "facility": inmate["facility"], "reason": data.reason,
                            "notes": data.notes}, user)
    return full_inmate(inmate_id)


@app.post("/inmates/{inmate_id}/notify-court", tags=["Correctional"],
          summary="Send the latest transfer or release to the Judiciary again")
def resend_to_court(inmate_id: str, user: dict = Depends(require_roles(*CUSTODY_ROLES))):
    inmate = full_inmate(inmate_id)
    if inmate["status"] == "RELEASED" and inmate["releases"]:
        last = inmate["releases"][-1]
        payload = {"event": "RELEASED", "facility": inmate["facility"], "reason": last["reason"],
                   "notes": last["notes"]}
    elif inmate["transfers"]:
        last = inmate["transfers"][-1]
        payload = {"event": "TRANSFERRED", "facility": last["new_facility"], "reason": last["reason"]}
    else:
        raise ApiError(409, "CONFLICT", "There is no transfer or release to report for this inmate")
    tell_court(inmate, payload, user)
    return full_inmate(inmate_id)


# ---------------------------------------------------------
# AUDIT LOGS - ADMIN ONLY (FR-18)
# ---------------------------------------------------------
@app.get("/audit-logs", tags=["Auth"])
def get_audit_logs(limit: int = Query(default=200, ge=1, le=1000), user: dict = Depends(require_roles(*ADMIN_ROLES))):
    with db() as conn:
        rows = conn.execute("SELECT id, time, username, role, action, record_id FROM audit_log "
                            "ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    return [dict(r) for r in rows]
