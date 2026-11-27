"""Runtime configuration, read from environment variables (design 6.2).

The JWT secret MUST be the same in the Police, Judiciary and Correctional
services. If JWT_SECRET is not set we fall back to the same development
secret the Correctional service uses, so the three services work together
out of the box on a developer laptop. Set JWT_SECRET for anything else.
"""
import os
from dataclasses import dataclass

DEV_SECRET = "dev-only-shared-secret-change-me-32chars"   # same default as correctional-service/auth.py


def _flag(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    return default if value is None else value.lower() in ("1", "true", "yes")


@dataclass(frozen=True)
class Settings:
    jwt_secret: str = DEV_SECRET
    database_url: str = "sqlite:///./judiciary.db"
    jwt_algorithm: str = "HS256"
    token_ttl_minutes: int = 60            # design 6.2: tokens expire after 60 minutes
    correctional_url: str = "http://localhost:8003"
    police_url: str = "http://localhost:8001"
    request_timeout: float = 5.0           # design 11: 5-second service-to-service timeout
    seed_demo_users: bool = True
    demo_password: str = "Passw0rd!"       # same demo password as the Postman environment
    seed_sample_cases: bool = True         # two sample cases matching the Correctional seed inmates
    bcrypt_rounds: int = 12

    def __post_init__(self):
        if len(self.jwt_secret) < 32:
            raise RuntimeError("JWT_SECRET must be at least 32 characters long (HS256 key strength)")

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            jwt_secret=os.environ.get("JWT_SECRET", DEV_SECRET),
            database_url=os.environ.get("JUDICIARY_DB_URL", "sqlite:///./judiciary.db"),
            correctional_url=os.environ.get("CORRECTIONAL_URL", "http://localhost:8003"),
            police_url=os.environ.get("POLICE_URL", "http://localhost:8001"),
            seed_demo_users=_flag("SEED_DEMO_USERS", True),
            demo_password=os.environ.get("DEMO_PASSWORD", "Passw0rd!"),
            seed_sample_cases=_flag("SEED_SAMPLE_CASES", True),
        )
