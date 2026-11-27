"""ORM tables for judiciary.db (design section 10): users, court_cases,
charges, hearings, decisions (bail / remand / verdict) and audit_log.
No foreign key points at another service's data: police_case_id and
inmate_id are plain reference IDs (design 10)."""
from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class CourtCaseStatus:
    """Court case life cycle (design 5.3):
    RECEIVED -> HEARING_SCHEDULED -> ON_BAIL or ON_REMAND -> SENTENCED or CLOSED"""
    RECEIVED = "RECEIVED"
    HEARING_SCHEDULED = "HEARING_SCHEDULED"
    ON_BAIL = "ON_BAIL"
    ON_REMAND = "ON_REMAND"
    SENTENCED = "SENTENCED"
    CLOSED = "CLOSED"


class DecisionKind:
    BAIL = "BAIL"
    REMAND = "REMAND"
    VERDICT = "VERDICT"


class User(Base):
    __tablename__ = "users"

    username: Mapped[str] = mapped_column(String(50), primary_key=True)
    password_hash: Mapped[str] = mapped_column(String(100))
    role: Mapped[str] = mapped_column(String(30))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class CourtCase(Base):
    __tablename__ = "court_cases"
    __table_args__ = (UniqueConstraint("year", "seq"),)

    court_case_id: Mapped[str] = mapped_column(String(20), primary_key=True)      # CRT-2026-0001
    year: Mapped[int] = mapped_column(Integer)
    seq: Mapped[int] = mapped_column(Integer)
    police_case_id: Mapped[str] = mapped_column(String(30), unique=True)          # reference only
    status: Mapped[str] = mapped_column(String(20), default=CourtCaseStatus.RECEIVED)

    # our own copy of the suspect (database per service, design 4.2)
    suspect_id: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    national_id: Mapped[str] = mapped_column(String(30))
    full_name: Mapped[str] = mapped_column(String(120))
    date_of_birth: Mapped[date] = mapped_column(Date)
    gender: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    address: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    inmate_id: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)   # set when admitted
    # result of the last update sent to the Police service: OK, FAILED or NULL (nothing sent yet)
    police_sync: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    police_sync_message: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    created_by: Mapped[str] = mapped_column(String(50))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_by: Mapped[str] = mapped_column(String(50))

    charges: Mapped[list["Charge"]] = relationship(
        back_populates="court_case", order_by="Charge.id", lazy="selectin", cascade="all, delete-orphan")
    hearings: Mapped[list["Hearing"]] = relationship(
        back_populates="court_case", order_by="Hearing.seq", lazy="selectin", cascade="all, delete-orphan")
    decisions: Mapped[list["Decision"]] = relationship(
        back_populates="court_case", order_by="Decision.id", lazy="selectin", cascade="all, delete-orphan")
    custody_events: Mapped[list["CustodyEvent"]] = relationship(
        back_populates="court_case", order_by="CustodyEvent.id", lazy="selectin", cascade="all, delete-orphan")


class Charge(Base):
    __tablename__ = "charges"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    court_case_id: Mapped[str] = mapped_column(ForeignKey("court_cases.court_case_id"))
    charge_id: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)   # Police's CHG-xxxx
    offence: Mapped[str] = mapped_column(String(255))
    statute: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    court_case: Mapped["CourtCase"] = relationship(back_populates="charges")


class Hearing(Base):
    __tablename__ = "hearings"

    hearing_id: Mapped[str] = mapped_column(String(20), primary_key=True)         # HRG-0001
    seq: Mapped[int] = mapped_column(Integer, unique=True)
    court_case_id: Mapped[str] = mapped_column(ForeignKey("court_cases.court_case_id"))
    hearing_date: Mapped[datetime] = mapped_column(DateTime)
    court_name: Mapped[str] = mapped_column(String(120))
    presiding_officer: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    created_by: Mapped[str] = mapped_column(String(50))

    court_case: Mapped["CourtCase"] = relationship(back_populates="hearings")


class Decision(Base):
    """One row per court decision (bail, remand or verdict). Columns that do
    not apply to a kind stay NULL."""
    __tablename__ = "decisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    court_case_id: Mapped[str] = mapped_column(ForeignKey("court_cases.court_case_id"))
    kind: Mapped[str] = mapped_column(String(10))
    # bail
    amount: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    conditions: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # remand
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    next_hearing_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    # verdict
    verdict: Mapped[Optional[str]] = mapped_column(String(15), nullable=True)
    sentence_type: Mapped[Optional[str]] = mapped_column(String(15), nullable=True)
    sentence_months: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    fine_amount: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # remand and imprisonment
    facility: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    inmate_id: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    decided_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    decided_by: Mapped[str] = mapped_column(String(50))

    court_case: Mapped["CourtCase"] = relationship(back_populates="decisions")


class CustodyEvent(Base):
    """News from the Correctional service about the inmate of this case
    (transfer to another facility, or release)."""
    __tablename__ = "custody_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    court_case_id: Mapped[str] = mapped_column(ForeignKey("court_cases.court_case_id"))
    inmate_id: Mapped[str] = mapped_column(String(20))
    event: Mapped[str] = mapped_column(String(15))                 # TRANSFERRED or RELEASED
    facility: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    reason: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    recorded_by: Mapped[str] = mapped_column(String(50))

    court_case: Mapped["CourtCase"] = relationship(back_populates="custody_events")


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    time: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    username: Mapped[str] = mapped_column(String(50))
    role: Mapped[str] = mapped_column(String(30))
    action: Mapped[str] = mapped_column(String(40))
    record_id: Mapped[str] = mapped_column(String(40))
