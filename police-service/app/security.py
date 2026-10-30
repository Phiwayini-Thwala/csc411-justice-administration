"""JWT (HS256) and bcrypt helpers (design section 6)."""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from .config import Settings
from .errors import UnauthorizedError

ROLES = ("police_officer", "court_officer", "correctional_officer", "admin")


@dataclass(frozen=True)
class Principal:
    """The authenticated caller. `token` is kept so it can be forwarded on
    service-to-service calls (design 6.2)."""
    username: str
    role: str
    token: str


def hash_password(password: str, rounds: int = 12) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=rounds)).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("ascii"))
    except ValueError:
        return False


# A real hash to compare against when the username is unknown, so a wrong
# username and a wrong password take about the same time.
DUMMY_HASH = hash_password("not-a-real-password")


def create_token(username: str, role: str, settings: Settings) -> tuple[str, int]:
    now = datetime.now(timezone.utc)
    ttl = timedelta(minutes=settings.token_ttl_minutes)
    claims = {"sub": username, "role": role, "iat": now, "exp": now + ttl}
    token = jwt.encode(claims, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return token, int(ttl.total_seconds())


def decode_token(token: str, settings: Settings) -> Principal:
    try:
        claims = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],      # pinned: never trust the token's own alg
            options={"require": ["exp", "sub", "role"]},
        )
    except jwt.ExpiredSignatureError:
        raise UnauthorizedError("Token has expired; log in again")
    except jwt.PyJWTError:
        raise UnauthorizedError("Invalid token")
    role = claims["role"]
    if role not in ROLES:
        raise UnauthorizedError("Token carries an unknown role")
    return Principal(username=str(claims["sub"]), role=role, token=token)
