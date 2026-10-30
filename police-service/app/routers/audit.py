"""GET /audit-logs (admin only, FR-18)."""
from typing import Optional

from fastapi import APIRouter, Depends, Query

from ..deps import get_repo, require_roles
from ..repository import PoliceRepository
from ..schemas import AuditLogOut

router = APIRouter(tags=["audit"])


@router.get("/audit-logs", response_model=list[AuditLogOut])
def read_audit_logs(
    limit: int = Query(100, ge=1, le=500),
    record_id: Optional[str] = None,
    username: Optional[str] = None,
    _admin=Depends(require_roles("admin")),
    repo: PoliceRepository = Depends(get_repo),
):
    return repo.list_audit(limit=limit, record_id=record_id, username=username)
