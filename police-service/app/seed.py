"""Demo data for the presentation.

Users: the same four accounts exist in all three services (police1, court1,
correctional1, admin1), plus officer1/admin kept for the existing tests.

Sample records: the two sample police cases are the ones the Judiciary and
Correctional services also seed (CASE-2026-0001 -> CRT-2026-0001 -> INM-0001
on remand, CASE-2026-0002 -> CRT-2026-0002 -> INM-0002 convicted), so the
three databases agree from the first start. A third case is left OPEN so a
referral can be shown live.
"""
import logging
from datetime import date, datetime

from .models import Arrest, Case, CaseStatus, Charge, Suspect
from .repository import PoliceRepository
from .security import hash_password

log = logging.getLogger("police.seed")

DEMO_USERS = {
    "police1": "police_officer",
    "officer1": "police_officer",
    "court1": "court_officer",
    "correctional1": "correctional_officer",
    "admin1": "admin",
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


SAMPLES = [
    # suspect, arrest, case, charge
    dict(n=1, national_id="8001015800083", full_name="Sipho Dlamini", dob=date(1980, 1, 1), gender="male",
         address="Ngwane Park, Manzini", when=datetime(2026, 10, 18, 14, 30), location="Manzini Central",
         officer="Insp. Mamba", summary="Theft of goods", offence="Theft", statute="Theft Act section 4",
         status=CaseStatus.REFERRED, court="CRT-2026-0001", court_status="ON_REMAND", inmate="INM-0001",
         outcome="Remanded in custody at Matsapha Correctional Centre"),
    dict(n=2, national_id="7505055800081", full_name="Thandi Nkambule", dob=date(1975, 5, 5), gender="female",
         address="Mbabane", when=datetime(2026, 9, 2, 10, 0), location="Mbabane CBD",
         officer="Sgt. Dube", summary="Fraud", offence="Fraud", statute="Fraud Act section 2",
         status=CaseStatus.CLOSED, court="CRT-2026-0002", court_status="SENTENCED", inmate="INM-0002",
         outcome="Guilty: imprisonment for 24 months at Matsapha Correctional Centre"),
    dict(n=3, national_id="9203120700085", full_name="Nomvula Shongwe", dob=date(1992, 3, 12), gender="female",
         address="Lobamba", when=datetime(2026, 11, 20, 21, 15), location="Ezulwini Valley",
         officer="Const. Hlophe", summary="Assault at a public venue", offence="Assault",
         statute="Crimes Act section 12", status=CaseStatus.OPEN, court=None, court_status=None, inmate=None,
         outcome=None),
]


def seed_sample_cases(repo: PoliceRepository) -> None:
    if repo.list_suspects():
        return
    db = repo.db
    for s in SAMPLES:
        n = s["n"]
        db.add(Suspect(suspect_id=f"SUS-{n:04d}", seq=n, national_id=s["national_id"], full_name=s["full_name"],
                       date_of_birth=s["dob"], gender=s["gender"], address=s["address"],
                       created_at=s["when"], created_by="seed"))
        db.add(Arrest(arrest_id=f"ARR-{n:04d}", seq=n, suspect_id=f"SUS-{n:04d}", arrest_date=s["when"],
                      location=s["location"], arresting_officer=s["officer"], created_at=s["when"],
                      created_by="seed"))
        db.flush()
        db.add(Case(case_id=f"CASE-2026-{n:04d}", year=2026, seq=n, arrest_id=f"ARR-{n:04d}",
                    suspect_id=f"SUS-{n:04d}", status=s["status"], summary=s["summary"],
                    court_case_id=s["court"], court_status=s["court_status"], court_outcome=s["outcome"],
                    inmate_id=s["inmate"], court_updated_at=s["when"] if s["court"] else None,
                    created_at=s["when"], created_by="seed", updated_at=s["when"], updated_by="seed"))
        db.flush()
        db.add(Charge(charge_id=f"CHG-{n:04d}", seq=n, case_id=f"CASE-2026-{n:04d}", offence=s["offence"],
                      statute=s["statute"], created_at=s["when"], created_by="seed"))
    repo.commit()
    log.info("seeded %d sample police cases", len(SAMPLES))
