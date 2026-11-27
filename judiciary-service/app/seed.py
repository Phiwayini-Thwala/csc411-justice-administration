"""Demo data: users and two sample court cases.

The sample cases use the same court_case_ids and national IDs as the two
inmates the Correctional service seeds (INM-0001 on remand for CRT-2026-0001,
INM-0002 convicted for CRT-2026-0002), and the same police_case_ids as the
Police seed (CASE-2026-0001 and CASE-2026-0002). That keeps the three databases
consistent, and means the first case Police refers gets CRT-2026-0003 so it
never collides with a seeded inmate."""
import logging
from datetime import date, datetime

from .models import Charge, CourtCase, CourtCaseStatus as S, Decision, DecisionKind, Hearing
from .repository import JudiciaryRepository
from .security import hash_password

log = logging.getLogger("judiciary.seed")

DEMO_USERS = {                      # same accounts as the Correctional service and the Postman collection
    "court1": "court_officer",
    "police1": "police_officer",
    "correctional1": "correctional_officer",
    "admin1": "admin",
}


def seed_demo_users(repo: JudiciaryRepository, password: str, rounds: int = 12) -> None:
    password_hash = hash_password(password, rounds)
    created = []
    for username, role in DEMO_USERS.items():
        if repo.get_user(username) is None:
            repo.add_user(username, password_hash, role)
            created.append(username)
    repo.commit()
    if created:
        log.info("seeded demo users: %s", ", ".join(created))


def seed_sample_cases(repo: JudiciaryRepository) -> None:
    if repo.list_court_cases():
        return
    now = datetime(2026, 10, 20, 9, 0)

    c1 = CourtCase(
        court_case_id="CRT-2026-0001", year=2026, seq=1, police_case_id="CASE-2026-0001",
        status=S.ON_REMAND, suspect_id="SUS-0001", national_id="8001015800083",
        full_name="Sipho Dlamini", date_of_birth=date(1980, 1, 1), gender="male",
        address="Ngwane Park, Manzini", summary="Theft of goods", inmate_id="INM-0001",
        police_sync="OK", created_by="seed", updated_by="seed",
        charges=[Charge(charge_id="CHG-0001", offence="Theft", statute="Theft Act section 4")])
    c1.hearings.append(Hearing(hearing_id="HRG-0001", seq=1, hearing_date=now,
                               court_name="Manzini Magistrate Court",
                               presiding_officer="Magistrate Simelane", created_by="seed"))
    c1.decisions.append(Decision(kind=DecisionKind.REMAND, reason="Risk of absconding",
                                 facility="Matsapha Correctional Centre",
                                 next_hearing_date=datetime(2026, 11, 20, 9, 0),
                                 inmate_id="INM-0001", decided_by="seed"))

    c2 = CourtCase(
        court_case_id="CRT-2026-0002", year=2026, seq=2, police_case_id="CASE-2026-0002",
        status=S.SENTENCED, suspect_id="SUS-0002", national_id="7505055800081",
        full_name="Thandi Nkambule", date_of_birth=date(1975, 5, 5), gender="female",
        address="Mbabane", summary="Fraud", inmate_id="INM-0002", police_sync="OK",
        created_by="seed", updated_by="seed",
        charges=[Charge(charge_id="CHG-0002", offence="Fraud", statute="Fraud Act section 2")])
    c2.hearings.append(Hearing(hearing_id="HRG-0002", seq=2, hearing_date=now,
                               court_name="Mbabane Magistrate Court",
                               presiding_officer="Magistrate Dlamini", created_by="seed"))
    c2.decisions.append(Decision(kind=DecisionKind.VERDICT, verdict="GUILTY",
                                 sentence_type="IMPRISONMENT", sentence_months=24,
                                 facility="Matsapha Correctional Centre",
                                 inmate_id="INM-0002", decided_by="seed"))

    repo.add(c1)
    repo.add(c2)
    repo.commit()
    log.info("seeded 2 sample court cases")
