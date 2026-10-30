"""Repository layer: the only code that reads or writes police.db (design 4.3).
It never commits; the service layer owns the transaction so that a business
operation and its audit row succeed or fail together."""
from datetime import datetime
from typing import Callable, Optional, TypeVar

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .models import Arrest, AuditLog, Case, CaseStatus, Charge, Suspect, User, utcnow

T = TypeVar("T")


class PoliceRepository:
    def __init__(self, db: Session):
        self.db = db

    # ----- transaction control (called by the service layer) -----
    def commit(self) -> None:
        self.db.commit()

    def rollback(self) -> None:
        self.db.rollback()

    # ----- identifiers -----
    def _insert_with_seq(self, model, build: Callable[[int], T], year: Optional[int] = None) -> T:
        """Allocate the next sequence number and insert. The unique constraint
        is the safety net: if two requests race, the loser retries."""
        for _ in range(5):
            q = select(func.coalesce(func.max(model.seq), 0) + 1)
            if year is not None:
                q = q.where(model.year == year)
            seq = self.db.execute(q).scalar_one()
            obj = build(seq)
            try:
                with self.db.begin_nested():
                    self.db.add(obj)
                    self.db.flush()
                return obj
            except IntegrityError:
                continue
        raise IntegrityError("could not allocate a unique identifier", None, Exception())

    # ----- users -----
    def get_user(self, username: str) -> Optional[User]:
        return self.db.get(User, username)

    def add_user(self, username: str, password_hash: str, role: str) -> User:
        user = User(username=username, password_hash=password_hash, role=role)
        self.db.add(user)
        self.db.flush()
        return user

    # ----- suspects -----
    def get_suspect(self, suspect_id: str) -> Optional[Suspect]:
        return self.db.get(Suspect, suspect_id)

    def get_suspect_by_national_id(self, national_id: str) -> Optional[Suspect]:
        return self.db.execute(
            select(Suspect).where(Suspect.national_id == national_id)
        ).scalar_one_or_none()

    def add_suspect(self, created_by: str, **fields) -> Suspect:
        return self._insert_with_seq(
            Suspect,
            lambda seq: Suspect(suspect_id=f"SUS-{seq:04d}", seq=seq, created_by=created_by, **fields),
        )

    # ----- arrests -----
    def get_arrest(self, arrest_id: str) -> Optional[Arrest]:
        return self.db.get(Arrest, arrest_id)

    def add_arrest(self, created_by: str, **fields) -> Arrest:
        return self._insert_with_seq(
            Arrest,
            lambda seq: Arrest(arrest_id=f"ARR-{seq:04d}", seq=seq, created_by=created_by, **fields),
        )

    # ----- cases -----
    def get_case(self, case_id: str) -> Optional[Case]:
        return self.db.get(Case, case_id)

    def get_case_by_arrest(self, arrest_id: str) -> Optional[Case]:
        return self.db.execute(
            select(Case).where(Case.arrest_id == arrest_id)
        ).scalar_one_or_none()

    def add_case(self, year: int, created_by: str, **fields) -> Case:
        return self._insert_with_seq(
            Case,
            lambda seq: Case(
                case_id=f"CASE-{year}-{seq:04d}", year=year, seq=seq,
                status=CaseStatus.OPEN, created_by=created_by, updated_by=created_by, **fields,
            ),
            year=year,
        )

    def add_charge(self, case: Case, created_by: str, **fields) -> Charge:
        charge = self._insert_with_seq(
            Charge,
            lambda seq: Charge(
                charge_id=f"CHG-{seq:04d}", seq=seq, case_id=case.case_id,
                created_by=created_by, **fields,
            ),
        )
        case.updated_at = utcnow()
        case.updated_by = created_by
        self.db.flush()
        self.db.refresh(case)          # reload so case.charges includes the new row
        return charge

    def mark_referred(self, case_id: str, court_case_id: str, updated_by: str) -> bool:
        """Compare-and-set OPEN -> REFERRED. False means another request got
        there first (a case cannot be referred twice)."""
        result = self.db.execute(
            update(Case)
            .where(Case.case_id == case_id, Case.status == CaseStatus.OPEN)
            .values(
                status=CaseStatus.REFERRED,
                court_case_id=court_case_id,
                updated_at=utcnow(),
                updated_by=updated_by,
            )
        )
        return result.rowcount == 1

    def refresh(self, obj) -> None:
        self.db.refresh(obj)

    # ----- audit log -----
    def add_audit(self, username: str, role: str, action: str, record_id: str) -> None:
        self.db.add(AuditLog(username=username, role=role, action=action, record_id=record_id))

    def list_audit(
        self, limit: int = 100, record_id: Optional[str] = None, username: Optional[str] = None
    ) -> list[AuditLog]:
        q = select(AuditLog).order_by(AuditLog.id.desc()).limit(limit)
        if record_id:
            q = q.where(AuditLog.record_id == record_id)
        if username:
            q = q.where(AuditLog.username == username)
        return list(self.db.execute(q).scalars())
