"""POST /auth/login (FR-01)."""
from fastapi import APIRouter, Depends

from ..deps import get_auth_service
from ..schemas import LoginRequest, TokenResponse
from ..services import AuthService

router = APIRouter(tags=["auth"])


@router.post("/auth/login", response_model=TokenResponse)
def login(body: LoginRequest, service: AuthService = Depends(get_auth_service)):
    token, expires_in = service.login(body.username, body.password)
    return TokenResponse(access_token=token, expires_in=expires_in)
