"""ORM tables for police.db (design section 10): users, suspects, arrests,
cases, charges, audit_log. No foreign key points at another service's data;
court_case_id is a plain reference ID (design 4.2)."""
from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class CaseStatus:
    """Police case life cycle: OPEN -> REFERRED -> CLOSED (design 5.3)."""
    OPEN = "OPEN"
    REFERRED = "REFERRED"
    CLOSED = "CLOSED"


class User(Base):
    __tablename__ = "users"

    username: Mapped[str] = mapped_column(String(50), primary_key=True)
    password_hash: Mapped[str] = mapped_column(String(100))
    role: Mapped[str] = mapped_column(String(30))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Suspect(Base):
    __tablename__ = "suspects"

    suspect_id: Mapped[str] = mapped_column(String(20), primary_key=True)     # SUS-0001
    seq: Mapped[int] = mapped_column(Integer, unique=True)
    national_id: Mapped[str] = mapped_column(String(30), unique=True)
    full_name: Mapped[str] = mapped_column(String(120))
    date_of_birth: Mapped[date] = mapped_column(Date)
    gender: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    address: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    created_by: Mapped[str] = mapped_column(String(50))


class Arrest(Base):
    __tablename__ = "arrests"

    arrest_id: Mapped[str] = mapped_column(String(20), primary_key=True)      # ARR-0001
    seq: Mapped[int] = mapped_column(Integer, unique=True)
    suspect_id: Mapped[str] = mapped_column(ForeignKey("suspects.suspect_id"))
    arrest_date: Mapped[datetime] = mapped_column(DateTime)
    location: Mapped[str] = mapped_column(String(255))
    arresting_officer: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    created_by: Mapped[str] = mapped_column(String(50))


class Case(Base):
    __tablename__ = "cases"
    __table_args__ = (UniqueConstraint("year", "seq"),)

    case_id: Mapped[str] = mapped_column(String(20), primary_key=True)        # CASE-2026-0001
    year: Mapped[int] = mapped_column(Integer)
    seq: Mapped[int] = mapped_column(Integer)
    arrest_id: Mapped[str] = mapped_column(ForeignKey("arrests.arrest_id"), unique=True)
    suspect_id: Mapped[str] = mapped_column(ForeignKey("suspects.suspect_id"))
    status: Mapped[str] = mapped_column(String(20), default=CaseStatus.OPEN)
    court_case_id: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)  # set on referral
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    created_by: Mapped[str] = mapped_column(String(50))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_by: Mapped[str] = mapped_column(String(50))

    charges: Mapped[list["Charge"]] = relationship(
        back_populates="case", order_by="Charge.seq", lazy="selectin"
    )


class Charge(Base):
    __tablename__ = "charges"

    charge_id: Mapped[str] = mapped_column(String(20), primary_key=True)      # CHG-0001
    seq: Mapped[int] = mapped_column(Integer, unique=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.case_id"))
    offence: Mapped[str] = mapped_column(String(200))
    statute: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    created_by: Mapped[str] = mapped_column(String(50))

    case: Mapped["Case"] = relationship(back_populates="charges")


class AuditLog(Base):
    """FR-18 / NFR-08: time, user, role, action, record ID."""
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    username: Mapped[str] = mapped_column(String(50))
    role: Mapped[str] = mapped_column(String(30))
    action: Mapped[str] = mapped_column(String(50))
    record_id: Mapped[str] = mapped_column(String(30), index=True)
