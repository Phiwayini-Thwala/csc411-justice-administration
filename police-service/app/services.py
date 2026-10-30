"""Service layer: business rules, state changes, audit logging and calls to
other services (design 4.3)."""
import logging

from .config import Settings
from .errors import ConflictError, NotFoundError, UnauthorizedError
from .judiciary_client import JudiciaryClient
from .models import Arrest, Case, CaseStatus, Charge, Suspect, utcnow
from .repository import PoliceRepository
from .schemas import ArrestCreate, ChargeCreate, SuspectCreate
from .security import DUMMY_HASH, Principal, create_token, verify_password

log = logging.getLogger("police.service")

# State machine for the Police case (design 5.3).
ALLOWED_TRANSITIONS = {
    CaseStatus.OPEN: {CaseStatus.REFERRED},
    CaseStatus.REFERRED: {CaseStatus.CLOSED},
    CaseStatus.CLOSED: set(),
}


def check_transition(case: Case, new_status: str) -> None:
    if new_status not in ALLOWED_TRANSITIONS[case.status]:
        raise ConflictError(f"Case {case.case_id} is {case.status} and cannot move to {new_status}")


class AuthService:
    def __init__(self, repo: PoliceRepository, settings: Settings):
        self.repo = repo
        self.settings = settings

    def login(self, username: str, password: str) -> tuple[str, int]:
        user = self.repo.get_user(username)
        # always run bcrypt so response time does not reveal which usernames exist
        ok = verify_password(password, user.password_hash if user else DUMMY_HASH)
        if not user or not ok:
            log.info("login failed user=%s", username)
            raise UnauthorizedError("Invalid username or password")
        log.info("login ok user=%s role=%s", user.username, user.role)
        return create_token(user.username, user.role, self.settings)


class PoliceService:
    def __init__(self, repo: PoliceRepository, judiciary: JudiciaryClient):
        self.repo = repo
        self.judiciary = judiciary

    # ----- suspects (FR-02) -----
    def register_suspect(self, data: SuspectCreate, who: Principal) -> Suspect:
        existing = self.repo.get_suspect_by_national_id(data.national_id)
        if existing:
            raise ConflictError(
                f"National ID {data.national_id} is already registered as {existing.suspect_id}"
            )
        suspect = self.repo.add_suspect(created_by=who.username, **data.model_dump())
        self.repo.add_audit(who.username, who.role, "SUSPECT_CREATED", suspect.suspect_id)
        self.repo.commit()
        log.info("user=%s created %s", who.username, suspect.suspect_id)
        return suspect

    def get_suspect(self, suspect_id: str) -> Suspect:
        suspect = self.repo.get_suspect(suspect_id)
        if not suspect:
            raise NotFoundError(f"Suspect {suspect_id} does not exist")
        return suspect

    # ----- arrests (FR-03) -----
    def record_arrest(self, data: ArrestCreate, who: Principal) -> Arrest:
        self.get_suspect(data.suspect_id)
        fields = data.model_dump()
        fields["arresting_officer"] = fields["arresting_officer"] or who.username
        arrest = self.repo.add_arrest(created_by=who.username, **fields)
        self.repo.add_audit(who.username, who.role, "ARREST_RECORDED", arrest.arrest_id)
        self.repo.commit()
        log.info("user=%s created %s", who.username, arrest.arrest_id)
        return arrest

    # ----- cases (FR-04, FR-05) -----
    def create_case(self, arrest_id: str, who: Principal) -> Case:
        arrest = self.repo.get_arrest(arrest_id)
        if not arrest:
            raise NotFoundError(f"Arrest {arrest_id} does not exist")
        existing = self.repo.get_case_by_arrest(arrest_id)
        if existing:
            raise ConflictError(f"Arrest {arrest_id} already has case {existing.case_id}")
        case = self.repo.add_case(
            year=utcnow().year, created_by=who.username,
            arrest_id=arrest.arrest_id, suspect_id=arrest.suspect_id,
        )
        self.repo.add_audit(who.username, who.role, "CASE_CREATED", case.case_id)
        self.repo.commit()
        log.info("user=%s created %s", who.username, case.case_id)
        return case

    def get_case(self, case_id: str) -> Case:
        case = self.repo.get_case(case_id)
        if not case:
            raise NotFoundError(f"Case {case_id} does not exist")
        return case

    def add_charge(self, case_id: str, data: ChargeCreate, who: Principal) -> Charge:
        case = self.get_case(case_id)
        if case.status != CaseStatus.OPEN:
            raise ConflictError(f"Case {case_id} is {case.status}; charges can only be added to an OPEN case")
        charge = self.repo.add_charge(case, created_by=who.username, **data.model_dump())
        self.repo.add_audit(who.username, who.role, "CHARGE_ADDED", charge.charge_id)
        self.repo.commit()
        log.info("user=%s added %s to %s", who.username, charge.charge_id, case_id)
        return charge

    # ----- referral (FR-06, sequence in design 5.2) -----
    def refer_case(self, case_id: str, who: Principal) -> Case:
        case = self.get_case(case_id)
        check_transition(case, CaseStatus.REFERRED)          # a case cannot be referred twice
        if not case.charges:
            raise ConflictError(f"Case {case_id} needs at least one charge before it can be referred")

        suspect = self.get_suspect(case.suspect_id)
        arrest = self.repo.get_arrest(case.arrest_id)
        payload = {
            "police_case_id": case.case_id,
            "suspect": {
                "suspect_id": suspect.suspect_id,
                "national_id": suspect.national_id,
                "full_name": suspect.full_name,
                "date_of_birth": suspect.date_of_birth.isoformat(),
                "gender": suspect.gender,
                "address": suspect.address,
            },
            "arrest": {
                "arrest_id": arrest.arrest_id,
                "arrest_date": arrest.arrest_date.isoformat(),
                "location": arrest.location,
                "arresting_officer": arrest.arresting_officer,
            },
            "charges": [
                {"charge_id": c.charge_id, "offence": c.offence, "statute": c.statute}
                for c in case.charges
            ],
        }

        # 1. Call the Judiciary first. If this raises, nothing was changed (NFR-03).
        court_case_id = self.judiciary.create_court_case(payload, who.token, who.username)

        # 2. Only now change our own record, together with its audit row.
        if not self.repo.mark_referred(case.case_id, court_case_id, who.username):
            self.repo.rollback()
            raise ConflictError(f"Case {case_id} was referred by another request")
        self.repo.add_audit(who.username, who.role, "CASE_REFERRED", case.case_id)
        self.repo.commit()
        self.repo.refresh(case)
        log.info("user=%s referred %s -> %s", who.username, case_id, court_case_id)
        return case
