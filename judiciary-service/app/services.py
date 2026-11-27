"""Business rules, state changes, audit logging and calls to the Correctional
service (design 4.3, 5.3, 5.4).

Rule used everywhere a decision needs the Correctional service: call it FIRST;
only when it succeeds change our own record. If it fails nothing is saved and
the caller gets 502 (design 11)."""
import logging
from typing import Optional

from .config import Settings
from .correctional_client import CorrectionalClient, PoliceClient, RemoteReadError
from .errors import ConflictError, NotFoundError, UnauthorizedError, ValidationFailed
from .models import (CourtCase, CourtCaseStatus as S, Charge, CustodyEvent, Decision, DecisionKind, Hearing,
                     utcnow)
from .repository import JudiciaryRepository
from .schemas import (BailDecision, CourtCaseCreate, CustodyEventIn, HearingCreate, LinkedRecords,
                      RemandDecision, VerdictDecision, naive_utc)
from .security import DUMMY_HASH, Principal, create_token, verify_password

log = logging.getLogger("judiciary.service")

OPEN_STATES = (S.RECEIVED, S.HEARING_SCHEDULED, S.ON_BAIL, S.ON_REMAND)


class AuthService:
    def __init__(self, repo: JudiciaryRepository, settings: Settings):
        self.repo = repo
        self.settings = settings

    def login(self, username: str, password: str) -> tuple[str, int, str]:
        user = self.repo.get_user(username)
        ok = verify_password(password, user.password_hash if user else DUMMY_HASH)
        if not user or not ok:
            log.info("login failed user=%s", username)
            raise UnauthorizedError("Invalid username or password")
        log.info("login ok user=%s role=%s", user.username, user.role)
        token, ttl = create_token(user.username, user.role, self.settings)
        return token, ttl, user.role


def _money(x: Optional[float]) -> str:
    return "E {:,.2f}".format(x or 0)


def _day(d) -> str:
    return d.strftime("%d %b %Y %H:%M") if d else "a date to be confirmed"


def outcome_text(case: CourtCase) -> str:
    """One line describing where the case stands; sent to the Police service."""
    last = case.decisions[-1] if case.decisions else None
    hearing = case.hearings[-1] if case.hearings else None
    ev = case.custody_events[-1] if case.custody_events else None
    if case.status == S.RECEIVED:
        return "Received by the court; awaiting a hearing date"
    if case.status == S.HEARING_SCHEDULED:
        return f"Hearing on {_day(hearing.hearing_date if hearing else None)}" + (
            f" at {hearing.court_name}" if hearing else "")
    if case.status == S.ON_BAIL and last:
        return f"Released on bail of {_money(last.amount)}"
    if case.status == S.ON_REMAND and last:
        where = ev.facility if ev and ev.event == "TRANSFERRED" and ev.facility else last.facility
        return f"Remanded in custody at {where}; next hearing {_day(last.next_hearing_date)}"
    if case.status == S.SENTENCED and last:
        where = ev.facility if ev and ev.event == "TRANSFERRED" and ev.facility else last.facility
        return f"Guilty: imprisonment for {last.sentence_months} months" + (f" at {where}" if where else "")
    if case.status == S.CLOSED:
        if ev and ev.event == "RELEASED" and ev.reason == "SENTENCE_COMPLETED":
            return "Sentence completed; released by Correctional Services"
        if last and last.kind == DecisionKind.VERDICT:
            if last.verdict == "NOT_GUILTY":
                return "Not guilty: acquitted"
            if last.sentence_type == "FINE":
                return f"Guilty: fine of {_money(last.fine_amount)}"
            if last.sentence_type == "SUSPENDED":
                return "Guilty: suspended sentence"
        return "Case closed"
    return case.status


class JudiciaryService:
    def __init__(self, repo: JudiciaryRepository, correctional: CorrectionalClient,
                 police: Optional[PoliceClient] = None):
        self.repo = repo
        self.correctional = correctional
        self.police = police

    # ----- feedback to the Police service (best effort, design 11) -----
    def _tell_police(self, case: CourtCase, who: Principal) -> None:
        """Push the new court state to the Police database. Our own change is
        already committed, so a failure is only recorded (police_sync=FAILED)
        and can be resent from the console."""
        if self.police is None:
            return
        payload = {"court_case_id": case.court_case_id, "court_status": case.status,
                   "outcome": outcome_text(case), "inmate_id": case.inmate_id}
        ok, message = self.police.send_court_update(case.police_case_id, payload, who.token, who.username)
        case.police_sync = "OK" if ok else "FAILED"
        case.police_sync_message = message[:255]
        if ok:
            self.repo.add_audit(who.username, who.role, "POLICE_NOTIFIED", case.court_case_id)
        self.repo.commit()

    def resend_to_police(self, court_case_id: str, who: Principal) -> CourtCase:
        case = self.get_case(court_case_id)
        if self.police is None:
            raise ConflictError("No Police service is configured")
        self._tell_police(case, who)
        return case

    # ----- linked records (read from the other two databases) -----
    def linked(self, court_case_id: str, who: Principal) -> LinkedRecords:
        case = self.get_case(court_case_id)
        out = LinkedRecords(court_case_id=case.court_case_id)
        if self.police is not None:
            try:
                out.police_case = self.police.get_case(case.police_case_id, who.token, who.username)
            except RemoteReadError as exc:
                out.police_error = str(exc)
        if case.inmate_id:
            try:
                out.inmate = self.correctional.get_inmate(case.inmate_id, who.token, who.username)
            except RemoteReadError as exc:
                out.inmate_error = str(exc)
        return out

    # ----- news from the Correctional service -----
    def record_custody_event(self, court_case_id: str, data: CustodyEventIn, who: Principal) -> CourtCase:
        """POST /court-cases/{id}/custody-events (called by the Correctional service)."""
        case = self.get_case(court_case_id)
        if not case.inmate_id or case.inmate_id != data.inmate_id:
            raise ConflictError(
                f"Court case {court_case_id} is not linked to inmate {data.inmate_id}")
        case.custody_events.append(CustodyEvent(
            inmate_id=data.inmate_id, event=data.event, facility=data.facility, reason=data.reason,
            notes=data.notes, recorded_by=who.username))
        # the sentence has been served: the court file can be closed
        if data.event == "RELEASED" and data.reason == "SENTENCE_COMPLETED" and case.status == S.SENTENCED:
            self._touch(case, who, S.CLOSED)
        else:
            self._touch(case, who)
        self.repo.add_audit(who.username, who.role, f"CUSTODY_{data.event}", case.court_case_id)
        self.repo.commit()
        self._tell_police(case, who)
        return case

    # ----- helpers -----
    def get_case(self, court_case_id: str) -> CourtCase:
        case = self.repo.get_court_case(court_case_id)
        if case is None:
            raise NotFoundError(f"Court case {court_case_id} does not exist")
        return case

    @staticmethod
    def _require_state(case: CourtCase, allowed: tuple, action: str, hint: str = "") -> None:
        if case.status not in allowed:
            msg = f"Court case {case.court_case_id} is {case.status}; cannot {action}"
            raise ConflictError(f"{msg}. {hint}".strip() if hint else msg)

    def _touch(self, case: CourtCase, who: Principal, status: Optional[str] = None) -> None:
        if status:
            case.status = status
        case.updated_at = utcnow()
        case.updated_by = who.username

    # ----- FR-07: receive a referred case -----
    def receive_case(self, data: CourtCaseCreate, who: Principal) -> CourtCase:
        existing = self.repo.get_by_police_case_id(data.police_case_id)
        if existing:
            raise ConflictError(
                f"Police case {data.police_case_id} already has court case {existing.court_case_id}")
        year = utcnow().year
        seq = self.repo.next_case_seq(year)
        s = data.suspect
        case = CourtCase(
            court_case_id=f"CRT-{year}-{seq:04d}", year=year, seq=seq,
            police_case_id=data.police_case_id, status=S.RECEIVED,
            suspect_id=s.suspect_id, national_id=s.national_id, full_name=s.full_name,
            date_of_birth=s.date_of_birth, gender=s.gender, address=s.address,
            summary=data.summary, created_by=who.username, updated_by=who.username,
            charges=[Charge(charge_id=c.charge_id, offence=c.offence, statute=c.statute,
                            description=c.description) for c in data.charges],
        )
        self.repo.add(case)
        self.repo.add_audit(who.username, who.role, "COURT_CASE_RECEIVED", case.court_case_id)
        self.repo.commit()
        log.info("user=%s received %s from %s", who.username, case.court_case_id, data.police_case_id)
        return case

    def list_cases(self, status: Optional[str] = None) -> list[CourtCase]:
        return self.repo.list_court_cases(status)

    # ----- FR-08: schedule a hearing -----
    def schedule_hearing(self, court_case_id: str, data: HearingCreate, who: Principal) -> Hearing:
        case = self.get_case(court_case_id)
        self._require_state(case, OPEN_STATES, "schedule a hearing")
        seq = self.repo.next_hearing_seq()
        hearing = Hearing(
            hearing_id=f"HRG-{seq:04d}", seq=seq, hearing_date=naive_utc(data.hearing_date),
            court_name=data.court_name, presiding_officer=data.presiding_officer,
            created_by=who.username)
        case.hearings.append(hearing)
        if case.status == S.RECEIVED:
            self._touch(case, who, S.HEARING_SCHEDULED)
        else:
            self._touch(case, who)
        self.repo.add_audit(who.username, who.role, "HEARING_SCHEDULED", case.court_case_id)
        self.repo.commit()
        self._tell_police(case, who)
        return hearing

    # ----- FR-09, FR-20: bail -----
    def grant_bail(self, court_case_id: str, data: BailDecision, who: Principal) -> CourtCase:
        case = self.get_case(court_case_id)
        self._require_state(
            case, (S.HEARING_SCHEDULED, S.ON_REMAND), "grant bail",
            "Schedule a hearing first." if case.status == S.RECEIVED else "")

        released_inmate = None
        if case.status == S.ON_REMAND and case.inmate_id:
            # suspect is in custody: the Correctional service must release them first
            self.correctional.release(case.inmate_id, "BAIL_GRANTED", data.conditions,
                                      who.token, who.username)
            released_inmate = case.inmate_id

        case.decisions.append(Decision(
            kind=DecisionKind.BAIL, amount=data.amount, conditions=data.conditions,
            inmate_id=released_inmate, decided_by=who.username))
        self._touch(case, who, S.ON_BAIL)
        self.repo.add_audit(who.username, who.role, "BAIL_GRANTED", case.court_case_id)
        self.repo.commit()
        self._tell_police(case, who)
        return case

    # ----- FR-10: remand in custody -----
    def remand(self, court_case_id: str, data: RemandDecision, who: Principal) -> CourtCase:
        case = self.get_case(court_case_id)
        self._require_state(
            case, (S.HEARING_SCHEDULED, S.ON_BAIL), "remand the suspect",
            "Schedule a hearing first." if case.status == S.RECEIVED else "")

        inmate_id = self.correctional.admit({
            "national_id": case.national_id,
            "full_name": case.full_name,
            "court_case_id": case.court_case_id,
            "admission_type": "REMAND",
            "facility": data.facility,
        }, who.token, who.username)

        case.inmate_id = inmate_id
        case.decisions.append(Decision(
            kind=DecisionKind.REMAND, reason=data.reason, facility=data.facility,
            next_hearing_date=naive_utc(data.next_hearing_date),
            inmate_id=inmate_id, decided_by=who.username))
        # the remand sets the next appearance date, so it also appears as a hearing
        last = case.hearings[-1] if case.hearings else None
        seq = self.repo.next_hearing_seq()
        case.hearings.append(Hearing(
            hearing_id=f"HRG-{seq:04d}", seq=seq, hearing_date=naive_utc(data.next_hearing_date),
            court_name=last.court_name if last else "To be confirmed",
            presiding_officer=last.presiding_officer if last else None,
            created_by=who.username))
        self._touch(case, who, S.ON_REMAND)
        self.repo.add_audit(who.username, who.role, "REMAND_ORDERED", case.court_case_id)
        self.repo.commit()
        self._tell_police(case, who)
        return case

    # ----- FR-11, FR-12, FR-20: verdict and sentence (table in design 5.4) -----
    def verdict(self, court_case_id: str, data: VerdictDecision, who: Principal) -> CourtCase:
        case = self.get_case(court_case_id)
        self._require_state(
            case, (S.HEARING_SCHEDULED, S.ON_BAIL, S.ON_REMAND), "record a verdict",
            "Schedule a hearing first." if case.status == S.RECEIVED else "")

        on_remand = case.status == S.ON_REMAND and bool(case.inmate_id)
        decision = Decision(kind=DecisionKind.VERDICT, verdict=data.verdict, decided_by=who.username)
        user, token = who.username, who.token

        if data.verdict == "NOT_GUILTY":
            if on_remand:
                self.correctional.release(case.inmate_id, "ACQUITTED", None, token, user)
                decision.inmate_id = case.inmate_id
            new_status = S.CLOSED

        else:  # GUILTY
            if data.sentence_type is None:
                raise ValidationFailed("sentence_type is required when the verdict is GUILTY")
            decision.sentence_type = data.sentence_type

            if data.sentence_type == "IMPRISONMENT":
                if data.sentence_months is None:
                    raise ValidationFailed("sentence_months is required when sentence_type is IMPRISONMENT")
                decision.sentence_months = data.sentence_months
                if on_remand:
                    self.correctional.set_convicted(case.inmate_id, data.sentence_months, token, user)
                    decision.facility = data.facility
                else:
                    if not data.facility:
                        raise ValidationFailed(
                            "facility is required for an imprisonment sentence when the suspect is not on remand")
                    case.inmate_id = self.correctional.admit({
                        "national_id": case.national_id,
                        "full_name": case.full_name,
                        "court_case_id": case.court_case_id,
                        "admission_type": "CONVICTED",
                        "facility": data.facility,
                        "sentence_months": data.sentence_months,
                    }, token, user)
                    decision.facility = data.facility
                decision.inmate_id = case.inmate_id
                new_status = S.SENTENCED

            else:  # FINE or SUSPENDED: no custody, release first if on remand
                if data.sentence_type == "FINE":
                    if data.fine_amount is None:
                        raise ValidationFailed("fine_amount is required when sentence_type is FINE")
                    decision.fine_amount = data.fine_amount
                if on_remand:
                    self.correctional.release(case.inmate_id, "COURT_ORDER", None, token, user)
                    decision.inmate_id = case.inmate_id
                new_status = S.CLOSED

        case.decisions.append(decision)
        self._touch(case, who, new_status)
        self.repo.add_audit(who.username, who.role, "VERDICT_RECORDED", case.court_case_id)
        self.repo.commit()
        self._tell_police(case, who)
        return case
