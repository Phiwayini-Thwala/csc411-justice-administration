"""FastAPI dependencies: database session, services and role checks."""
from typing import Iterator, Optional

from fastapi import Depends, Header, Request
from sqlalchemy.orm import Session

from .config import Settings
from .errors import ForbiddenError, UnauthorizedError
from .judiciary_client import JudiciaryClient
from .repository import PoliceRepository
from .security import Principal, decode_token
from .services import AuthService, PoliceService

# Role matrix for the Police endpoint group (design 6.2 table)
WRITE_ROLES = ("police_officer", "admin")
READ_ROLES = ("police_officer", "court_officer", "admin")


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_db(request: Request) -> Iterator[Session]:
    db = request.app.state.session_factory()
    try:
        yield db
    finally:
        db.close()


def get_repo(db: Session = Depends(get_db)) -> PoliceRepository:
    return PoliceRepository(db)


def get_police_service(request: Request, repo: PoliceRepository = Depends(get_repo)) -> PoliceService:
    return PoliceService(repo, request.app.state.judiciary)


def get_auth_service(
    settings: Settings = Depends(get_settings), repo: PoliceRepository = Depends(get_repo)
) -> AuthService:
    return AuthService(repo, settings)


def get_principal(
    authorization: Optional[str] = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> Principal:
    if not authorization:
        raise UnauthorizedError("Missing Authorization header")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise UnauthorizedError("Authorization header must be 'Bearer <token>'")
    return decode_token(token.strip(), settings)


def require_roles(*roles: str):
    """Dependency factory: 401 for no/bad token, 403 for the wrong role (NFR-01)."""

    def dependency(principal: Principal = Depends(get_principal)) -> Principal:
        if principal.role not in roles:
            raise ForbiddenError(f"Role '{principal.role}' is not allowed to do this")
        return principal

    return dependency
