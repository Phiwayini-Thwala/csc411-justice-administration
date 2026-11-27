"""FastAPI dependencies: database session, services and role checks."""
from typing import Iterator, Optional

from fastapi import Depends, Header, Request
from sqlalchemy.orm import Session

from .config import Settings
from .errors import ForbiddenError, UnauthorizedError
from .repository import JudiciaryRepository
from .security import Principal, decode_token
from .services import AuthService, JudiciaryService

# Role matrix for the Judiciary endpoint group (design 6.2 table)
RECEIVE_ROLES = ("police_officer", "court_officer", "admin")           # police: service call only
COURT_ROLES = ("court_officer", "admin")                               # hearings, bail, remand, verdict
READ_ROLES = ("court_officer", "correctional_officer", "admin")        # correctional: read only
CASE_READ_ROLES = READ_ROLES + ("police_officer",)                     # police may follow one referred case
CUSTODY_ROLES = ("correctional_officer", "admin")                      # correctional pushes custody news


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_db(request: Request) -> Iterator[Session]:
    db = request.app.state.session_factory()
    try:
        yield db
    finally:
        db.close()


def get_repo(db: Session = Depends(get_db)) -> JudiciaryRepository:
    return JudiciaryRepository(db)


def get_judiciary_service(request: Request, repo: JudiciaryRepository = Depends(get_repo)) -> JudiciaryService:
    return JudiciaryService(repo, request.app.state.correctional, request.app.state.police)


def get_auth_service(
    settings: Settings = Depends(get_settings), repo: JudiciaryRepository = Depends(get_repo)
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
    """401 for no/bad token, 403 for the wrong role."""

    def dependency(principal: Principal = Depends(get_principal)) -> Principal:
        if principal.role not in roles:
            raise ForbiddenError(f"Role '{principal.role}' is not allowed to do this")
        return principal

    return dependency
