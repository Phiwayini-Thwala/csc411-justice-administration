
"""Correctional Service API - CSC411 Justice Administration System."""

from contextlib import asynccontextmanager
from typing import Literal, Optional

import bcrypt
from fastapi import Depends, FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

from auth import ApiError, create_token, require_roles
from database import get_conn, init_db, now


# ---------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------

COURT_WRITE = ("court_officer", "correctional_officer", "admin")
READ_ROLES = (
    "correctional_officer",
    "admin",
    "police_officer",
    "court_officer",
)

TRANSFER_ROLES = ("correctional_officer", "admin")
ADMIN_ROLES = ("admin",)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="Correctional Service",
    description="Correctional records and custody management microservice.",
    version="1.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------
# ERROR HANDLING
# ---------------------------------------------------------

@app.exception_handler(ApiError)
async def api_error_handler(request: Request, exc: ApiError):
    return JSONResponse(
        status_code=exc.status,
        content={
            "error": exc.code,
            "message": exc.message,
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(
    request: Request,
    exc: RequestValidationError,
):
    return JSONResponse(
        status_code=422,
        content={
            "error": "VALIDATION_ERROR",
            "message": "The submitted information is invalid.",
            "details": exc.errors(),
        },
    )


@app.exception_handler(StarletteHTTPException)
async def http_error_handler(
    request: Request,
    exc: StarletteHTTPException,
):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": "HTTP_ERROR",
            "message": str(exc.detail),
        },
    )


# ---------------------------------------------------------
# REQUEST MODELS
# ---------------------------------------------------------

class LoginRequest(BaseModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


class AdmitRequest(BaseModel):
    national_id: str = Field(min_length=1)
    court_case_id: str = Field(min_length=1)
    admission_type: Literal["REMAND", "CONVICTED"]
    facility: str = Field(min_length=1)
    full_name: Optional[str] = None
    sentence_months: Optional[int] = Field(default=None, ge=1)


class StatusUpdate(BaseModel):
    status: Literal["REMAND", "CONVICTED"]
    sentence_months: Optional[int] = Field(default=None, ge=1)


class TransferRequest(BaseModel):
    new_facility: str = Field(min_length=1)
    reason: Optional[str] = None


class ReleaseRequest(BaseModel):
    reason: Literal[
        "SENTENCE_COMPLETED",
        "ACQUITTED",
        "COURT_ORDER",
        "BAIL_GRANTED",
    ]
    notes: Optional[str] = None


# ---------------------------------------------------------
# DATABASE HELPERS
# ---------------------------------------------------------

def audit(username: str, role: str, action: str, record_id: Optional[str] = None):
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO audit_log
            (time, username, role, action, record_id)
            VALUES (?, ?, ?, ?, ?)
            """,
            (now(), username, role, action, record_id),
        )


def get_inmate(inmate_id: str):
    with get_conn() as conn:
        inmate = conn.execute(
            "SELECT * FROM inmates WHERE inmate_id = ?",
            (inmate_id,),
        ).fetchone()

    if inmate is None:
        raise ApiError(404, "NOT_FOUND", "Inmate record was not found.")

    return dict(inmate)


def full_inmate(inmate_id: str):
    inmate = get_inmate(inmate_id)

    with get_conn() as conn:
        transfers = conn.execute(
            """
            SELECT transfer_id, from_facility, new_facility,
                   reason, transferred_at, by_user
            FROM transfers
            WHERE inmate_id = ?
            ORDER BY transferred_at DESC
            """,
            (inmate_id,),
        ).fetchall()

        releases = conn.execute(
            """
            SELECT release_id, reason, notes, released_at, by_user
            FROM releases
            WHERE inmate_id = ?
            ORDER BY released_at DESC
            """,
            (inmate_id,),
        ).fetchall()

    inmate["transfers"] = [dict(row) for row in transfers]
    inmate["releases"] = [dict(row) for row in releases]

    return inmate


# ---------------------------------------------------------
# SERVICE HEALTH
# ---------------------------------------------------------

@app.get("/")
def health_check():
    return {
        "service": "Correctional Service",
        "status": "online",
        "version": "1.1.0",
    }


# ---------------------------------------------------------
# AUTHENTICATION
# ---------------------------------------------------------

@app.post("/auth/login")
def login(data: LoginRequest):
    with get_conn() as conn:
        user = conn.execute(
            "SELECT * FROM users WHERE username = ?",
            (data.username,),
        ).fetchone()

    if user is None:
        raise ApiError(401, "UNAUTHORIZED", "Invalid username or password.")

    if not bcrypt.checkpw(
        data.password.encode(),
        user["password_hash"].encode(),
    ):
        raise ApiError(401, "UNAUTHORIZED", "Invalid username or password.")

    token = create_token(user["username"], user["role"])

    audit(user["username"], user["role"], "LOGIN")

    return {
        "access_token": token,
        "token_type": "bearer",
        "username": user["username"],
        "role": user["role"],
    }


# ---------------------------------------------------------
# INMATE LIST
# ---------------------------------------------------------

@app.get("/inmates")
def list_inmates(
    status: Optional[
        Literal["REMAND", "CONVICTED", "TRANSFERRED", "RELEASED"]
    ] = None,
    search: Optional[str] = Query(default=None, max_length=100),
    user: dict = Depends(require_roles(*READ_ROLES)),
):
    sql = "SELECT * FROM inmates WHERE 1=1"
    params = []

    if status:
        sql += " AND status = ?"
        params.append(status)

    if search and search.strip():
        term = f"%{search.strip()}%"
        sql += """
            AND (
                inmate_id LIKE ?
                OR full_name LIKE ?
                OR court_case_id LIKE ?
                OR facility LIKE ?
            )
        """
        params.extend([term, term, term, term])

    sql += " ORDER BY admitted_at DESC"

    with get_conn() as conn:
        rows = conn.execute(sql, params).fetchall()

    inmates = [dict(row) for row in rows]

    # Do not expose national ID in the general listing.
    for inmate in inmates:
        inmate.pop("national_id", None)

    return {
        "total": len(inmates),
        "inmates": inmates,
    }


# ---------------------------------------------------------
# ADMIT AN INMATE
# ---------------------------------------------------------

@app.post("/inmates", status_code=201)
def admit_inmate(
    data: AdmitRequest,
    user: dict = Depends(require_roles(*COURT_WRITE)),
):
    if data.admission_type == "CONVICTED" and data.sentence_months is None:
        raise ApiError(
            422,
            "VALIDATION_ERROR",
            "Sentence duration is required for a convicted inmate.",
        )

    if data.admission_type == "REMAND" and data.sentence_months is not None:
        raise ApiError(
            422,
            "VALIDATION_ERROR",
            "A remand admission should not have a sentence duration.",
        )

    with get_conn() as conn:
        existing = conn.execute(
            """
            SELECT inmate_id FROM inmates
            WHERE national_id = ? OR court_case_id = ?
            """,
            (data.national_id, data.court_case_id),
        ).fetchone()

        if existing:
            raise ApiError(
                409,
                "CONFLICT",
                "An inmate record with this national ID or court case already exists.",
            )

        count = conn.execute(
            "SELECT COUNT(*) FROM inmates"
        ).fetchone()[0]

        inmate_id = f"INM-{count + 1:04d}"

        admitted_at = now()

        conn.execute(
            """
            INSERT INTO inmates (
                inmate_id, national_id, full_name, court_case_id,
                admission_type, status, facility, sentence_months,
                admitted_at, released_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
            """,
            (
                inmate_id,
                data.national_id,
                data.full_name,
                data.court_case_id,
                data.admission_type,
                data.admission_type,
                data.facility,
                data.sentence_months,
                admitted_at,
            ),
        )

    audit(
        user["username"],
        user["role"],
        "INMATE_ADMITTED",
        inmate_id,
    )

    return {
        "message": "Inmate admitted successfully.",
        "inmate_id": inmate_id,
        "status": data.admission_type,
    }


# ---------------------------------------------------------
# VIEW ONE INMATE
# ---------------------------------------------------------

@app.get("/inmates/{inmate_id}")
def get_inmate_details(
    inmate_id: str,
    user: dict = Depends(require_roles(*READ_ROLES)),
):
    return full_inmate(inmate_id)


# ---------------------------------------------------------
# UPDATE INMATE STATUS / RECORD CONVICTION
# ---------------------------------------------------------

@app.put("/inmates/{inmate_id}/status")
def update_inmate_status(
    inmate_id: str,
    data: StatusUpdate,
    user: dict = Depends(require_roles(*COURT_WRITE)),
):
    inmate = get_inmate(inmate_id)

    if inmate["status"] in ("TRANSFERRED", "RELEASED"):
        raise ApiError(
            409,
            "CONFLICT",
            "The status of a transferred or released inmate cannot be updated.",
        )

    if data.status == "CONVICTED" and data.sentence_months is None:
        raise ApiError(
            422,
            "VALIDATION_ERROR",
            "Sentence duration is required for a convicted inmate.",
        )

    with get_conn() as conn:
        conn.execute(
            """
            UPDATE inmates
            SET status = ?, sentence_months = ?
            WHERE inmate_id = ?
            """,
            (
                data.status,
                data.sentence_months,
                inmate_id,
            ),
        )

    audit(
        user["username"],
        user["role"],
        "STATUS_UPDATED",
        inmate_id,
    )

    return {
        "message": "Inmate status updated successfully.",
        "inmate_id": inmate_id,
        "status": data.status,
        "sentence_months": data.sentence_months,
    }


# ---------------------------------------------------------
# TRANSFER AN INMATE
# ---------------------------------------------------------

@app.put("/inmates/{inmate_id}/transfer")
def transfer_inmate(
    inmate_id: str,
    data: TransferRequest,
    user: dict = Depends(require_roles(*TRANSFER_ROLES)),
):
    inmate = get_inmate(inmate_id)

    if inmate["status"] == "RELEASED":
        raise ApiError(
            409,
            "CONFLICT",
            "A released inmate cannot be transferred.",
        )

    if inmate["status"] == "TRANSFERRED":
        raise ApiError(
            409,
            "CONFLICT",
            "This inmate is already marked as transferred.",
        )

    if inmate["facility"].strip().lower() == data.new_facility.strip().lower():
        raise ApiError(
            409,
            "CONFLICT",
            "The new facility must be different from the current facility.",
        )

    transferred_at = now()

    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO transfers (
                inmate_id, from_facility, new_facility,
                reason, transferred_at, by_user
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                inmate_id,
                inmate["facility"],
                data.new_facility,
                data.reason,
                transferred_at,
                user["username"],
            ),
        )

        conn.execute(
            """
            UPDATE inmates
            SET facility = ?, status = 'TRANSFERRED'
            WHERE inmate_id = ?
            """,
            (data.new_facility, inmate_id),
        )

    audit(
        user["username"],
        user["role"],
        "INMATE_TRANSFERRED",
        inmate_id,
    )

    return {
        "message": "Inmate transferred successfully.",
        "inmate_id": inmate_id,
        "facility": data.new_facility,
        "status": "TRANSFERRED",
    }


# ---------------------------------------------------------
# RELEASE AN INMATE
# ---------------------------------------------------------

@app.post("/inmates/{inmate_id}/release")
def release_inmate(
    inmate_id: str,
    data: ReleaseRequest,
    user: dict = Depends(require_roles(*COURT_WRITE)),
):
    inmate = get_inmate(inmate_id)

    if inmate["status"] == "RELEASED":
        raise ApiError(
            409,
            "CONFLICT",
            "This inmate has already been released.",
        )

    released_at = now()

    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO releases (
                inmate_id, reason, notes, released_at, by_user
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                inmate_id,
                data.reason,
                data.notes,
                released_at,
                user["username"],
            ),
        )

        conn.execute(
            """
            UPDATE inmates
            SET status = 'RELEASED', released_at = ?
            WHERE inmate_id = ?
            """,
            (released_at, inmate_id),
        )

    audit(
        user["username"],
        user["role"],
        "INMATE_RELEASED",
        inmate_id,
    )

    return {
        "message": "Inmate released successfully.",
        "inmate_id": inmate_id,
        "status": "RELEASED",
        "reason": data.reason,
        "released_at": released_at,
    }


# ---------------------------------------------------------
# AUDIT LOGS - ADMIN ONLY
# ---------------------------------------------------------

@app.get("/audit-logs")
def get_audit_logs(
    limit: int = Query(default=200, ge=1, le=1000),
    user: dict = Depends(require_roles(*ADMIN_ROLES)),
):
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT id, time, username, role, action, record_id
            FROM audit_log
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    logs = [dict(row) for row in rows]

    return {
        "total": len(logs),
        "logs": logs,
    }
