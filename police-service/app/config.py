"""Runtime configuration, read from environment variables (design section 6.2:
secrets live in the environment and are never committed).

The JWT secret MUST be the same in the Police, Judiciary and Correctional
services. If JWT_SECRET is not set we fall back to the same development secret
the other two services use, so the three services work together out of the box
on a developer laptop. Set JWT_SECRET for anything beyond the demo.
"""
import os
from dataclasses import dataclass
from typing import Optional

DEV_SECRET = "dev-only-shared-secret-change-me-32chars"   # same default as judiciary and correctional


def _flag(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    return default if value is None else value.lower() in ("1", "true", "yes")


@dataclass(frozen=True)
class Settings:
    jwt_secret: str = DEV_SECRET
    database_url: str = "sqlite:///./police.db"
    jwt_algorithm: str = "HS256"
    token_ttl_minutes: int = 60          # design 6.2: tokens expire after 60 minutes
    judiciary_url: str = "http://localhost:8002"
    correctional_url: str = "http://localhost:8003"
    request_timeout: float = 5.0         # design section 11: 5-second service-to-service timeout
    seed_demo_users: bool = False
    demo_password: Optional[str] = None
    seed_sample_cases: bool = False      # on by default when started from the environment
    bcrypt_rounds: int = 12

    def __post_init__(self):
        if len(self.jwt_secret) < 32:
            raise RuntimeError("JWT_SECRET must be at least 32 characters long (HS256 key strength)")

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            jwt_secret=os.environ.get("JWT_SECRET", DEV_SECRET),
            database_url=os.environ.get("POLICE_DB_URL", "sqlite:///./police.db"),
            judiciary_url=os.environ.get("JUDICIARY_URL", "http://localhost:8002"),
            correctional_url=os.environ.get("CORRECTIONAL_URL", "http://localhost:8003"),
            seed_demo_users=_flag("SEED_DEMO_USERS", True),
            demo_password=os.environ.get("DEMO_PASSWORD", "Passw0rd!"),
            seed_sample_cases=_flag("SEED_SAMPLE_CASES", True),
        )
