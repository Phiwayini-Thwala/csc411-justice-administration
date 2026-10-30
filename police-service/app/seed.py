"""Demo users for the presentation. Passwords come from the DEMO_PASSWORD
environment variable; nothing is hard-coded (design 6.2)."""
import logging

from .repository import PoliceRepository
from .security import hash_password

log = logging.getLogger("police.seed")

DEMO_USERS = {
    "officer1": "police_officer",
    "court1": "court_officer",
    "correctional1": "correctional_officer",
    "admin": "admin",
}


def seed_demo_users(repo: PoliceRepository, password: str, rounds: int = 12) -> None:
    created = []
    password_hash = hash_password(password, rounds)
    for username, role in DEMO_USERS.items():
        if repo.get_user(username) is None:
            repo.add_user(username, password_hash, role)
            created.append(username)
    repo.commit()
    if created:
        log.info("seeded demo users: %s", ", ".join(created))
