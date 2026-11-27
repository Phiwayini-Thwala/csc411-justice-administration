"""Model/schema layer: Pydantic DTOs for requests and responses (design 4.3, 7)."""
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int          # seconds
    username: str
    role: str


class SuspectCreate(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)
    national_id: str = Field(min_length=3, max_length=30)
    date_of_birth: date
    gender: Optional[str] = Field(default=None, max_length=20)
    address: str = Field(min_length=2, max_length=255)


class SuspectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    suspect_id: str
    national_id: str
    full_name: str
    date_of_birth: date
    gender: Optional[str]
    address: str
    created_at: datetime
    created_by: str


class ArrestCreate(BaseModel):
    suspect_id: str = Field(min_length=1, max_length=20)
    arrest_date: datetime
    location: str = Field(min_length=2, max_length=255)
    arresting_officer: Optional[str] = Field(default=None, min_length=2, max_length=120)


class ArrestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    arrest_id: str
    suspect_id: str
    arrest_date: datetime
    location: str
    arresting_officer: str
    created_at: datetime
    created_by: str


class CaseCreate(BaseModel):
    arrest_id: str = Field(min_length=1, max_length=20)
    summary: Optional[str] = Field(default=None, max_length=500)


class ChargeCreate(BaseModel):
    offence: str = Field(min_length=2, max_length=200)
    statute: Optional[str] = Field(default=None, max_length=200)


class ChargeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    charge_id: str
    case_id: str
    offence: str
    statute: Optional[str]
    created_at: datetime


class CaseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    case_id: str
    arrest_id: str
    suspect_id: str
    status: str
    summary: Optional[str] = None
    court_case_id: Optional[str]
    court_status: Optional[str] = None
    court_outcome: Optional[str] = None
    inmate_id: Optional[str] = None
    court_updated_at: Optional[datetime] = None
    created_at: datetime
    created_by: str
    updated_at: datetime
    charges: list[ChargeOut] = []
    # filled in for list views so the UI does not need a second call per row
    suspect_name: Optional[str] = None
    national_id: Optional[str] = None


class CourtUpdate(BaseModel):
    """Pushed by the Judiciary service whenever the court case changes."""
    court_case_id: str = Field(min_length=1, max_length=30)
    court_status: str = Field(min_length=1, max_length=30)
    outcome: Optional[str] = Field(default=None, max_length=500)
    inmate_id: Optional[str] = Field(default=None, max_length=20)


class CaseTracking(BaseModel):
    """Police case plus the live records the other two services hold for it."""
    case: CaseOut
    court_case: Optional[dict] = None
    court_error: Optional[str] = None
    inmate: Optional[dict] = None
    inmate_error: Optional[str] = None


class AuditLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    timestamp: datetime
    time: Optional[datetime] = None      # same value; the shared contract calls it "time"
    username: str
    role: str
    action: str
    record_id: str


def audit_out(row) -> AuditLogOut:
    out = AuditLogOut.model_validate(row)
    out.time = out.timestamp
    return out
