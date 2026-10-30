"""Runtime configuration, read from environment variables (design section 6.2:
secrets live in the environment and are never committed)."""
import os
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Settings:
    jwt_secret: str
    database_url: str = "sqlite:///./police.db"
    jwt_algorithm: str = "HS256"
    token_ttl_minutes: int = 60          # design 6.2: tokens expire after 60 minutes
    judiciary_url: str = "http://localhost:8002"
    request_timeout: float = 5.0         # design section 11: 5-second service-to-service timeout
    seed_demo_users: bool = False
    demo_password: Optional[str] = None
    bcrypt_rounds: int = 12

    def __post_init__(self):
        if len(self.jwt_secret) < 32:
            raise RuntimeError("JWT_SECRET must be at least 32 characters long (HS256 key strength)")

    @classmethod
    def from_env(cls) -> "Settings":
        secret = os.environ.get("JWT_SECRET")
        if not secret:
            raise RuntimeError(
                "JWT_SECRET is not set. All three services must share the same secret "
                "through this environment variable (see README)."
            )
        return cls(
            jwt_secret=secret,
            database_url=os.environ.get("POLICE_DB_URL", "sqlite:///./police.db"),
            judiciary_url=os.environ.get("JUDICIARY_URL", "http://localhost:8002"),
            seed_demo_users=os.environ.get("SEED_DEMO_USERS", "").lower() in ("1", "true", "yes"),
            demo_password=os.environ.get("DEMO_PASSWORD"),
        )
