"""JWT validation and role checks (HS256, secret shared by the three services)."""
import os
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

SECRET = os.getenv("JWT_SECRET", "dev-only-shared-secret-change-me-32chars")
ALGORITHM = "HS256"
TOKEN_MINUTES = 60
bearer = HTTPBearer(auto_error=False)


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str):
        self.status, self.code, self.message = status, code, message


def create_token(username: str, role: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": username, "role": role, "iat": now,
               "exp": now + timedelta(minutes=TOKEN_MINUTES)}
    return jwt.encode(payload, SECRET, algorithm=ALGORITHM)


def current_user(creds: HTTPAuthorizationCredentials = Depends(bearer)) -> dict:
    if creds is None:
        raise ApiError(401, "UNAUTHORIZED", "Missing bearer token")
    try:
        data = jwt.decode(creds.credentials, SECRET, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise ApiError(401, "UNAUTHORIZED", "Token expired")
    except jwt.PyJWTError:
        raise ApiError(401, "UNAUTHORIZED", "Invalid token")
    return {"username": data.get("sub"), "role": data.get("role")}


def require_roles(*roles: str):
    def checker(user: dict = Depends(current_user)) -> dict:
        if user["role"] not in roles:
            raise ApiError(403, "FORBIDDEN", f"Role '{user['role']}' is not allowed here")
        return user
    return checker
