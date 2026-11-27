"""All database access for the Judiciary service lives here."""
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import AuditLog, CourtCase, Hearing, User


class JudiciaryRepository:
    def __init__(self, db: Session):
        self.db = db

    # ----- users -----
    def get_user(self, username: str) -> Optional[User]:
        return self.db.get(User, username)

    def add_user(self, username: str, password_hash: str, role: str) -> User:
        user = User(username=username, password_hash=password_hash, role=role)
        self.db.add(user)
        return user

    # ----- court cases -----
    def next_case_seq(self, year: int) -> int:
        top = self.db.execute(select(func.max(CourtCase.seq)).where(CourtCase.year == year)).scalar()
        return (top or 0) + 1

    def next_hearing_seq(self) -> int:
        top = self.db.execute(select(func.max(Hearing.seq))).scalar()
        return (top or 0) + 1

    def get_court_case(self, court_case_id: str) -> Optional[CourtCase]:
        return self.db.get(CourtCase, court_case_id)

    def get_by_police_case_id(self, police_case_id: str) -> Optional[CourtCase]:
        return self.db.execute(
            select(CourtCase).where(CourtCase.police_case_id == police_case_id)
        ).scalar_one_or_none()

    def list_court_cases(self, status: Optional[str] = None) -> list[CourtCase]:
        stmt = select(CourtCase).order_by(CourtCase.year, CourtCase.seq)
        if status:
            stmt = stmt.where(CourtCase.status == status)
        return list(self.db.execute(stmt).scalars().all())

    def add(self, obj):
        self.db.add(obj)
        return obj

    # ----- audit -----
    def add_audit(self, username: str, role: str, action: str, record_id: str) -> None:
        self.db.add(AuditLog(username=username, role=role, action=action, record_id=record_id))

    def list_audit(self, limit: int = 100, record_id: Optional[str] = None,
                   username: Optional[str] = None) -> list[AuditLog]:
        stmt = select(AuditLog).order_by(AuditLog.id.desc()).limit(limit)
        if record_id:
            stmt = stmt.where(AuditLog.record_id == record_id)
        if username:
            stmt = stmt.where(AuditLog.username == username)
        return list(self.db.execute(stmt).scalars().all())

    # ----- unit of work -----
    def commit(self) -> None:
        self.db.commit()

    def rollback(self) -> None:
        self.db.rollback()
