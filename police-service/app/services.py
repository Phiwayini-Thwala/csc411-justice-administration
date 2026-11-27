"""Service layer: business rules, state changes, audit logging and calls to
other services (design 4.3)."""
import logging
from typing import Optional

from .config import Settings
from .errors import ConflictError, NotFoundError, UnauthorizedError
from .judiciary_client import CorrectionalClient, JudiciaryClient, RemoteReadError
from .models import Arrest, Case, CaseStatus, Charge, Suspect, utcnow
from .repository import PoliceRepository
from .schemas import ArrestCreate, CaseOut, CaseTracking, ChargeCreate, CourtUpdate, SuspectCreate
from .security import DUMMY_HASH, Principal, create_token, verify_password

log = logging.getLogger("police.service")

# State machine for the Police case (design 5.3).
ALLOWED_TRANSITIONS = {
    CaseStatus.OPEN: {CaseStatus.REFERRED},
    CaseStatus.REFERRED: {CaseStatus.CLOSED},
    CaseStatus.CLOSED: set(),
}

# Court statuses after which the Police part of the process is finished.
COURT_FINAL = {"SENTENCED", "CLOSED"}


def check_transition(case: Case, new_status: str) -> None:
    if new_status not in ALLOWED_TRANSITIONS[case.status]:
        raise ConflictError(f"Case {case.case_id} is {case.status} and cannot move to {new_status}")


class AuthService:
    def __init__(self, repo: PoliceRepository, settings: Settings):
        self.repo = repo
        self.settings = settings

    def login(self, username: str, password: str) -> tuple[str, int, str]:
        user = self.repo.get_user(username)
        # always run bcrypt so response time does not reveal which usernames exist
        ok = verify_password(password, user.password_hash if user else DUMMY_HASH)
        if not user or not ok:
            log.info("login failed user=%s", username)
            raise UnauthorizedError("Invalid username or password")
        log.info("login ok user=%s role=%s", user.username, user.role)
        token, ttl = create_token(user.username, user.role, self.settings)
        return token, ttl, user.role


class PoliceService:
    def __init__(self, repo: PoliceRepository, judiciary: JudiciaryClient,
                 correctional: Optional[CorrectionalClient] = None):
        self.repo = repo
        self.judiciary = judiciary
        self.correctional = correctional

    # ----- read models for the console -----
    def case_out(self, case: Case) -> CaseOut:
        out = CaseOut.model_validate(case)
        suspect = self.repo.get_suspect(case.suspect_id)
        if suspect:
            out.suspect_name = suspect.full_name
            out.national_id = suspect.national_id
        return out

    def list_suspects(self) -> list[Suspect]:
        return self.repo.list_suspects()

    def list_arrests(self) -> list[Arrest]:
        return self.repo.list_arrests()

    def list_cases(self, status: Optional[str] = None) -> list[CaseOut]:
        return [self.case_out(c) for c in self.repo.list_cases(status)]

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
    def create_case(self, arrest_id: str, who: Principal, summary: Optional[str] = None) -> Case:
        arrest = self.repo.get_arrest(arrest_id)
        if not arrest:
            raise NotFoundError(f"Arrest {arrest_id} does not exist")
        existing = self.repo.get_case_by_arrest(arrest_id)
        if existing:
            raise ConflictError(f"Arrest {arrest_id} already has case {existing.case_id}")
        case = self.repo.add_case(
            year=utcnow().year, created_by=who.username,
            arrest_id=arrest.arrest_id, suspect_id=arrest.suspect_id, summary=summary,
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
            "summary": case.summary,
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

    # ----- feedback from the Judiciary (closes the loop of design 5.3) -----
    def _apply_court_news(self, case: Case, court_status: str, outcome: Optional[str],
                          inmate_id: Optional[str], who: Principal) -> bool:
        """Copy the court's latest state into our record. Returns True if the
        police case was closed by this update (REFERRED -> CLOSED)."""
        case.court_status = court_status
        if outcome:
            case.court_outcome = outcome
        if inmate_id:
            case.inmate_id = inmate_id
        case.court_updated_at = utcnow()
        closed = False
        if court_status in COURT_FINAL and case.status == CaseStatus.REFERRED:
            check_transition(case, CaseStatus.CLOSED)
            case.status = CaseStatus.CLOSED
            case.updated_at = utcnow()
            case.updated_by = who.username
            closed = True
        return closed

    def receive_court_update(self, case_id: str, data: CourtUpdate, who: Principal) -> Case:
        """POST /cases/{id}/court-updates, called by the Judiciary service."""
        case = self.get_case(case_id)
        if case.status == CaseStatus.OPEN or not case.court_case_id:
            raise ConflictError(f"Case {case_id} has not been referred to court")
        if case.court_case_id != data.court_case_id:
            raise ConflictError(
                f"Case {case_id} was referred as {case.court_case_id}, not {data.court_case_id}")
        closed = self._apply_court_news(case, data.court_status, data.outcome, data.inmate_id, who)
        self.repo.add_audit(who.username, who.role, "COURT_UPDATE_RECEIVED", case.case_id)
        if closed:
            self.repo.add_audit(who.username, who.role, "CASE_CLOSED", case.case_id)
        self.repo.commit()
        log.info("user=%s court update %s -> %s", who.username, case_id, data.court_status)
        return case

    def track_case(self, case_id: str, who: Principal) -> CaseTracking:
        """GET /cases/{id}/tracking: our record plus the live court and custody
        records. A service that is down only blanks its own part."""
        case = self.get_case(case_id)
        result = CaseTracking(case=self.case_out(case))
        if not case.court_case_id:
            return result
        try:
            court = self.judiciary.get_court_case(case.court_case_id, who.token, who.username)
            result.court_case = court
            inmate_id = court.get("inmate_id") or case.inmate_id
            status = court.get("status")
            if isinstance(status, str) and (status != case.court_status or inmate_id != case.inmate_id):
                closed = self._apply_court_news(case, status, None, inmate_id, who)
                if closed:
                    self.repo.add_audit(who.username, who.role, "CASE_CLOSED", case.case_id)
                self.repo.commit()
                result.case = self.case_out(case)
        except RemoteReadError as exc:
            result.court_error = str(exc)
            inmate_id = case.inmate_id
        if inmate_id and self.correctional is not None:
            try:
                result.inmate = self.correctional.get_inmate(inmate_id, who.token, who.username)
            except RemoteReadError as exc:
                result.inmate_error = str(exc)
        return result
