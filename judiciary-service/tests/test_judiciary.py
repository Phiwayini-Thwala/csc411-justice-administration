"""Judiciary service tests. The Correctional service is replaced by a mock,
so no other service needs to be running."""
from .conftest import HEARING, REFERRAL, REMAND, SECRET

import jwt as pyjwt


# ------------------------------------------------------------ auth and roles
def test_login_ok_and_wrong_password(client):
    r = client.post("/auth/login", json={"username": "court1", "password": "demo-password-123"})
    assert r.status_code == 200
    assert r.json()["role"] == "court_officer" and r.json()["token_type"] == "bearer"
    bad = client.post("/auth/login", json={"username": "court1", "password": "nope"})
    assert bad.status_code == 401
    assert set(bad.json()) == {"error", "message"}


def test_no_token_is_401_and_wrong_role_is_403(client, police, correctional_user, new_case):
    assert client.get(f"/court-cases/{new_case}").status_code == 401
    assert client.get(f"/court-cases/{new_case}", headers=police).status_code == 200      # police: follow one case
    assert client.get("/court-cases", headers=police).status_code == 403                 # ...but not the docket
    r = client.post(f"/court-cases/{new_case}/hearings", json=HEARING, headers=correctional_user)
    assert r.status_code == 403                                                              # correctional: read only
    assert client.get(f"/court-cases/{new_case}", headers=correctional_user).status_code == 200


def test_tampered_and_expired_tokens_are_401(client, new_case):
    forged = pyjwt.encode({"sub": "x", "role": "admin", "exp": 9999999999}, "wrong-secret-wrong-secret-wrong-secret", "HS256")
    assert client.get("/court-cases", headers={"Authorization": f"Bearer {forged}"}).status_code == 401
    expired = pyjwt.encode({"sub": "x", "role": "admin", "exp": 1}, SECRET, "HS256")
    assert client.get("/court-cases", headers={"Authorization": f"Bearer {expired}"}).status_code == 401


# ------------------------------------------------------------ receive a case
def test_seed_cases_match_correctional_seed(client, court):
    r = client.get("/court-cases/CRT-2026-0001", headers=court)
    assert r.status_code == 200
    assert r.json()["status"] == "ON_REMAND" and r.json()["inmate_id"] == "INM-0001"


def test_receive_case_then_duplicate_is_409(client, police, court):
    r = client.post("/court-cases", json=REFERRAL, headers=police)
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "RECEIVED"
    assert body["court_case_id"].startswith("CRT-")
    assert body["court_case_id"] not in ("CRT-2026-0001", "CRT-2026-0002")      # those belong to the seeded cases
    assert body["suspect"]["full_name"] == "Test Suspect" and len(body["charges"]) == 1
    assert client.post("/court-cases", json=REFERRAL, headers=police).status_code == 409


def test_receive_case_validation(client, police):
    r = client.post("/court-cases", json={**REFERRAL, "charges": []}, headers=police)
    assert r.status_code == 400 and set(r.json()) == {"error", "message"}


def test_unknown_case_is_404(client, court):
    assert client.get("/court-cases/CRT-9999-0001", headers=court).status_code == 404


# ------------------------------------------------------------ hearings
def test_schedule_hearing_changes_status(client, court, new_case):
    r = client.post(f"/court-cases/{new_case}/hearings", json=HEARING, headers=court)
    assert r.status_code == 201 and r.json()["hearing_id"].startswith("HRG-")
    assert client.get(f"/court-cases/{new_case}", headers=court).json()["status"] == "HEARING_SCHEDULED"


# ------------------------------------------------------------ bail
def test_bail_needs_a_hearing_first(client, court, new_case, correctional):
    r = client.post(f"/court-cases/{new_case}/bail", json={"amount": 2000, "conditions": "Report weekly"}, headers=court)
    assert r.status_code == 409
    assert correctional.calls == []


def test_bail_when_not_on_remand_makes_no_correctional_call(client, court, scheduled_case, correctional):
    r = client.post(f"/court-cases/{scheduled_case}/bail", json={"amount": 2000, "conditions": "Report weekly"}, headers=court)
    assert r.status_code == 200 and r.json()["status"] == "ON_BAIL"
    assert correctional.calls == []
    again = client.post(f"/court-cases/{scheduled_case}/bail", json={"amount": 1, "conditions": "x"}, headers=court)
    assert again.status_code == 409


def test_bail_after_remand_releases_the_inmate(client, court, remanded_case, correctional):
    inmate = client.get(f"/court-cases/{remanded_case}", headers=court).json()["inmate_id"]
    r = client.post(f"/court-cases/{remanded_case}/bail", json={"amount": 2000, "conditions": "Report weekly"}, headers=court)
    assert r.status_code == 200 and r.json()["status"] == "ON_BAIL"
    call = correctional.calls[-1]
    assert (call["method"], call["path"]) == ("POST", f"/inmates/{inmate}/release")
    assert call["body"]["reason"] == "BAIL_GRANTED"


# ------------------------------------------------------------ remand
def test_remand_admits_inmate_and_forwards_token(client, court, scheduled_case, correctional):
    r = client.post(f"/court-cases/{scheduled_case}/remand", json=REMAND, headers=court)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ON_REMAND" and body["inmate_id"].startswith("INM-")
    call = correctional.calls[-1]
    assert (call["method"], call["path"]) == ("POST", "/inmates")
    assert call["auth"] == court["Authorization"]                                  # JWT forwarded
    assert call["body"]["admission_type"] == "REMAND"
    assert call["body"]["court_case_id"] == scheduled_case
    assert call["body"]["national_id"] == REFERRAL["suspect"]["national_id"]


def test_remand_failure_saves_nothing(client, court, scheduled_case, correctional):
    for mode in ("down", "timeout", "error500"):
        correctional.mode = mode
        r = client.post(f"/court-cases/{scheduled_case}/remand", json=REMAND, headers=court)
        assert r.status_code == 502, mode
        assert set(r.json()) == {"error", "message"}
    case = client.get(f"/court-cases/{scheduled_case}", headers=court).json()
    assert case["status"] == "HEARING_SCHEDULED" and case["inmate_id"] is None and case["decisions"] == []


def test_remand_conflict_from_correctional_is_409(client, court, scheduled_case, correctional):
    correctional.mode = "conflict"
    assert client.post(f"/court-cases/{scheduled_case}/remand", json=REMAND, headers=court).status_code == 409


# ------------------------------------------------------------ verdict
IMPRISON = {"verdict": "GUILTY", "sentence_type": "IMPRISONMENT", "sentence_months": 12,
            "facility": "Matsapha Correctional Centre"}


def test_guilty_imprisonment_on_remand_updates_inmate(client, court, remanded_case, correctional):
    inmate = client.get(f"/court-cases/{remanded_case}", headers=court).json()["inmate_id"]
    r = client.post(f"/court-cases/{remanded_case}/verdict", json=IMPRISON, headers=court)
    assert r.status_code == 200 and r.json()["status"] == "SENTENCED"
    call = correctional.calls[-1]
    assert (call["method"], call["path"]) == ("PUT", f"/inmates/{inmate}/status")
    assert call["body"] == {"status": "CONVICTED", "sentence_months": 12}


def test_guilty_imprisonment_not_on_remand_admits_convicted(client, court, scheduled_case, correctional):
    r = client.post(f"/court-cases/{scheduled_case}/verdict", json=IMPRISON, headers=court)
    assert r.status_code == 200 and r.json()["status"] == "SENTENCED" and r.json()["inmate_id"]
    call = correctional.calls[-1]
    assert (call["method"], call["path"]) == ("POST", "/inmates")
    assert call["body"]["admission_type"] == "CONVICTED" and call["body"]["sentence_months"] == 12


def test_not_guilty_on_remand_releases_and_closes(client, court, remanded_case, correctional):
    r = client.post(f"/court-cases/{remanded_case}/verdict", json={"verdict": "NOT_GUILTY"}, headers=court)
    assert r.status_code == 200 and r.json()["status"] == "CLOSED"
    assert correctional.calls[-1]["body"]["reason"] == "ACQUITTED"


def test_not_guilty_not_on_remand_makes_no_call(client, court, scheduled_case, correctional):
    r = client.post(f"/court-cases/{scheduled_case}/verdict", json={"verdict": "NOT_GUILTY"}, headers=court)
    assert r.status_code == 200 and r.json()["status"] == "CLOSED" and correctional.calls == []


def test_fine_on_remand_releases_with_court_order(client, court, remanded_case, correctional):
    r = client.post(f"/court-cases/{remanded_case}/verdict",
                    json={"verdict": "GUILTY", "sentence_type": "FINE", "fine_amount": 500}, headers=court)
    assert r.status_code == 200 and r.json()["status"] == "CLOSED"
    assert correctional.calls[-1]["body"]["reason"] == "COURT_ORDER"


def test_verdict_validation_and_state_rules(client, court, new_case):
    url = f"/court-cases/{new_case}/verdict"
    # no hearing scheduled yet
    assert client.post(url, json={"verdict": "NOT_GUILTY"}, headers=court).status_code == 409
    client.post(f"/court-cases/{new_case}/hearings", json=HEARING, headers=court)
    # GUILTY needs a sentence type; IMPRISONMENT needs months; and a facility when not on remand
    assert client.post(url, json={"verdict": "GUILTY"}, headers=court).status_code == 400
    assert client.post(url, json={"verdict": "GUILTY", "sentence_type": "IMPRISONMENT"},
                       headers=court).status_code == 400
    assert client.post(url, json={"verdict": "GUILTY", "sentence_type": "IMPRISONMENT", "sentence_months": 6},
                       headers=court).status_code == 400
    assert client.post(url, json={"verdict": "GUILTY", "sentence_type": "FINE"},
                       headers=court).status_code == 400


def test_verdict_failure_saves_nothing(client, court, remanded_case, correctional):
    correctional.mode = "down"
    r = client.post(f"/court-cases/{remanded_case}/verdict", json=IMPRISON, headers=court)
    assert r.status_code == 502
    assert client.get(f"/court-cases/{remanded_case}", headers=court).json()["status"] == "ON_REMAND"


def test_closed_case_rejects_everything(client, court, scheduled_case):
    client.post(f"/court-cases/{scheduled_case}/verdict", json={"verdict": "NOT_GUILTY"}, headers=court)
    assert client.post(f"/court-cases/{scheduled_case}/hearings", json=HEARING, headers=court).status_code == 409
    assert client.post(f"/court-cases/{scheduled_case}/remand", json=REMAND, headers=court).status_code == 409


# ------------------------------------------------------------ audit
def test_audit_log_admin_only(client, court, admin, scheduled_case):
    assert client.get("/audit-logs", headers=court).status_code == 403
    r = client.get("/audit-logs", headers=admin)
    assert r.status_code == 200
    actions = {e["action"] for e in r.json()}
    assert {"COURT_CASE_RECEIVED", "HEARING_SCHEDULED"} <= actions
    assert set(r.json()[0]) == {"time", "username", "role", "action", "record_id"}


# ------------------------------------------------------------ feedback between the databases
def test_every_court_decision_is_reported_to_police(client, court, scheduled_case, police_service):
    # scheduling the hearing already sent one update
    first = police_service.calls[-1]
    assert first["method"] == "POST" and first["path"] == "/cases/CASE-2026-0101/court-updates"
    assert first["body"]["court_status"] == "HEARING_SCHEDULED"
    assert first["auth"] == court["Authorization"]
    r = client.post(f"/court-cases/{scheduled_case}/verdict",
                    json={"verdict": "GUILTY", "sentence_type": "FINE", "fine_amount": 500}, headers=court)
    assert r.status_code == 200 and r.json()["police_sync"] == "OK"
    last = police_service.calls[-1]["body"]
    assert last["court_status"] == "CLOSED" and "fine" in last["outcome"].lower()


def test_police_down_does_not_undo_the_court_decision(client, court, new_case, police_service):
    police_service.mode = "down"
    r = client.post(f"/court-cases/{new_case}/hearings", json=HEARING, headers=court)
    assert r.status_code == 201
    case = client.get(f"/court-cases/{new_case}", headers=court).json()
    assert case["status"] == "HEARING_SCHEDULED" and case["police_sync"] == "FAILED"
    police_service.mode = "ok"
    r = client.post(f"/court-cases/{new_case}/notify-police", headers=court)
    assert r.status_code == 200 and r.json()["police_sync"] == "OK"


def test_custody_events_from_correctional(client, court, correctional_user, remanded_case, police_service):
    case = client.get(f"/court-cases/{remanded_case}", headers=court).json()
    inmate = case["inmate_id"]
    # wrong inmate is refused
    bad = client.post(f"/court-cases/{remanded_case}/custody-events",
                      json={"inmate_id": "INM-0000", "event": "TRANSFERRED"}, headers=correctional_user)
    assert bad.status_code == 409
    # court officers may not post custody events
    assert client.post(f"/court-cases/{remanded_case}/custody-events",
                       json={"inmate_id": inmate, "event": "TRANSFERRED"}, headers=court).status_code == 403
    r = client.post(f"/court-cases/{remanded_case}/custody-events",
                    json={"inmate_id": inmate, "event": "TRANSFERRED", "facility": "Sidwashini Correctional Centre",
                          "reason": "Overcrowding"}, headers=correctional_user)
    assert r.status_code == 200
    assert r.json()["custody_events"][0]["facility"] == "Sidwashini Correctional Centre"
    assert "Sidwashini" in police_service.calls[-1]["body"]["outcome"]


def test_sentence_completed_closes_the_court_case(client, court, correctional_user):
    # seeded CRT-2026-0002 is SENTENCED with inmate INM-0002
    r = client.post("/court-cases/CRT-2026-0002/custody-events",
                    json={"inmate_id": "INM-0002", "event": "RELEASED", "reason": "SENTENCE_COMPLETED"},
                    headers=correctional_user)
    assert r.status_code == 200 and r.json()["status"] == "CLOSED"


def test_linked_records_reads_police_and_correctional(client, court, correctional):
    r = client.get("/court-cases/CRT-2026-0001/linked", headers=court)
    assert r.status_code == 200
    body = r.json()
    assert body["police_case"]["case_id"] == "CASE-2026-0001"
    assert body["inmate"] is not None and body["inmate_error"] is None
    assert any(c["method"] == "GET" and c["path"] == "/inmates/INM-0001" for c in correctional.calls)
