"""Request and response bodies, matching docs/api-contract/openapi.yaml."""
from datetime import date, datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


def naive_utc(value: datetime) -> datetime:
    """SQLite stores naive datetimes; convert aware ones to UTC first."""
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


# ---------------------------------------------------------------- auth
class LoginRequest(BaseModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    role: str


# ---------------------------------------------------------------- requests
class SuspectIn(BaseModel):
    suspect_id: Optional[str] = None
    national_id: str = Field(min_length=1, max_length=30)
    full_name: str = Field(min_length=1, max_length=120)
    date_of_birth: date
    gender: Optional[str] = None
    address: Optional[str] = None


class ChargeIn(BaseModel):
    charge_id: Optional[str] = None
    offence: str = Field(min_length=1, max_length=255)
    statute: Optional[str] = None
    description: Optional[str] = None


class CourtCaseCreate(BaseModel):
    police_case_id: str = Field(min_length=1, max_length=30)
    suspect: SuspectIn
    charges: list[ChargeIn] = Field(min_length=1)
    summary: Optional[str] = None
    # Police also sends an "arrest" object; unknown fields are ignored.


class HearingCreate(BaseModel):
    hearing_date: datetime
    court_name: str = Field(min_length=1, max_length=120)
    presiding_officer: Optional[str] = None


class BailDecision(BaseModel):
    amount: float = Field(ge=0)
    conditions: str = Field(min_length=1)


class RemandDecision(BaseModel):
    reason: str = Field(min_length=1)
    facility: str = Field(min_length=1, max_length=120)
    next_hearing_date: datetime


class VerdictDecision(BaseModel):
    verdict: Literal["GUILTY", "NOT_GUILTY"]
    sentence_type: Optional[Literal["IMPRISONMENT", "FINE", "SUSPENDED"]] = None
    sentence_months: Optional[int] = Field(default=None, ge=1)
    fine_amount: Optional[float] = Field(default=None, ge=0)
    facility: Optional[str] = None


class CustodyEventIn(BaseModel):
    """Sent by the Correctional service when its inmate is transferred or released."""
    inmate_id: str = Field(min_length=1, max_length=20)
    event: Literal["TRANSFERRED", "RELEASED"]
    facility: Optional[str] = Field(default=None, max_length=120)
    reason: Optional[str] = Field(default=None, max_length=60)
    notes: Optional[str] = None


# ---------------------------------------------------------------- responses
class SuspectOut(BaseModel):
    suspect_id: Optional[str]
    national_id: str
    full_name: str
    date_of_birth: date
    gender: Optional[str]
    address: Optional[str]


class ChargeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    charge_id: Optional[str]
    offence: str
    statute: Optional[str]
    description: Optional[str]


class HearingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    hearing_id: str
    hearing_date: datetime
    court_name: str
    presiding_officer: Optional[str]


class DecisionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    kind: str
    decided_at: datetime
    decided_by: str
    amount: Optional[float]
    conditions: Optional[str]
    reason: Optional[str]
    next_hearing_date: Optional[datetime]
    verdict: Optional[str]
    sentence_type: Optional[str]
    sentence_months: Optional[int]
    fine_amount: Optional[float]
    facility: Optional[str]
    inmate_id: Optional[str]


class CustodyEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    inmate_id: str
    event: str
    facility: Optional[str]
    reason: Optional[str]
    notes: Optional[str]
    recorded_at: datetime
    recorded_by: str


class CourtCaseOut(BaseModel):
    court_case_id: str
    police_case_id: str
    status: str
    summary: Optional[str]
    inmate_id: Optional[str]
    suspect: SuspectOut
    charges: list[ChargeOut]
    hearings: list[HearingOut]
    decisions: list[DecisionOut]
    custody_events: list[CustodyEventOut] = []
    police_sync: Optional[str] = None
    police_sync_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_case(cls, c) -> "CourtCaseOut":
        return cls(
            court_case_id=c.court_case_id,
            police_case_id=c.police_case_id,
            status=c.status,
            summary=c.summary,
            inmate_id=c.inmate_id,
            suspect=SuspectOut(
                suspect_id=c.suspect_id, national_id=c.national_id, full_name=c.full_name,
                date_of_birth=c.date_of_birth, gender=c.gender, address=c.address),
            charges=[ChargeOut.model_validate(x) for x in c.charges],
            hearings=[HearingOut.model_validate(x) for x in c.hearings],
            decisions=[DecisionOut.model_validate(x) for x in c.decisions],
            custody_events=[CustodyEventOut.model_validate(x) for x in c.custody_events],
            police_sync=c.police_sync,
            police_sync_message=c.police_sync_message,
            created_at=c.created_at,
            updated_at=c.updated_at,
        )


class LinkedRecords(BaseModel):
    """The records the other two services hold for one court case."""
    court_case_id: str
    police_case: Optional[dict] = None
    police_error: Optional[str] = None
    inmate: Optional[dict] = None
    inmate_error: Optional[str] = None


class AuditLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    time: datetime
    username: str
    role: str
    action: str
    record_id: str
