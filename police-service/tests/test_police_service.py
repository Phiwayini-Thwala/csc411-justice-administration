import re

from .conftest import PASSWORD, SUSPECT, make_token


# ---------------- authentication / authorisation (FR-01, NFR-01) ----------------

def test_login_returns_jwt_with_role_and_60_minute_expiry(client):
    r = client.post("/auth/login", json={"username": "officer1", "password": PASSWORD})
    assert r.status_code == 200
    body = r.json()
    assert body["token_type"] == "bearer" and body["expires_in"] == 3600
    import jwt
    claims = jwt.decode(body["access_token"], options={"verify_signature": False})
    assert claims["sub"] == "officer1" and claims["role"] == "police_officer"
    assert claims["exp"] - claims["iat"] == 3600


def test_login_wrong_password_and_unknown_user_are_401(client):
    for creds in ({"username": "officer1", "password": "nope"}, {"username": "ghost", "password": "x"}):
        r = client.post("/auth/login", json=creds)
        assert r.status_code == 401
        assert r.json()["error"] == "UNAUTHORIZED"


def test_every_endpoint_requires_a_token(client):
    for method, path in [
        ("post", "/suspects"), ("get", "/suspects/SUS-0001"), ("post", "/arrests"),
        ("post", "/cases"), ("get", "/cases/CASE-2026-0001"),
        ("post", "/cases/CASE-2026-0001/charges"), ("post", "/cases/CASE-2026-0001/refer"),
        ("get", "/audit-logs"),
    ]:
        r = getattr(client, method)(path)
        assert r.status_code == 401, (method, path)
        assert r.json()["error"] == "UNAUTHORIZED"


def test_expired_tampered_and_wrong_alg_tokens_are_401(client):
    bad = [
        make_token(expires_in=-10),                          # expired
        make_token(secret="some-other-secret"),              # tampered / wrong key
        make_token(alg="HS512"),                             # algorithm not allowed
        "not-a-jwt",
    ]
    for tok in bad:
        r = client.get("/suspects/SUS-0001", headers={"Authorization": f"Bearer {tok}"})
        assert r.status_code == 401, tok


def test_roles_are_enforced(client, officer, court, correctional, admin):
    # correctional_officer: no access to Police endpoints at all
    assert client.post("/suspects", json=SUSPECT, headers=correctional).status_code == 403
    assert client.get("/suspects/SUS-0001", headers=correctional).status_code == 403
    # court_officer: read only
    assert client.post("/suspects", json=SUSPECT, headers=court).status_code == 403
    # police_officer cannot read the audit log, admin can
    assert client.get("/audit-logs", headers=officer).status_code == 403
    assert client.get("/audit-logs", headers=admin).status_code == 200
    # admin may write
    assert client.post("/suspects", json=SUSPECT, headers=admin).status_code == 201


def test_court_officer_can_read(client, officer, court):
    sus = client.post("/suspects", json=SUSPECT, headers=officer).json()
    assert client.get(f"/suspects/{sus['suspect_id']}", headers=court).status_code == 200


# ---------------- registering and reading (FR-02..FR-05) ----------------

def test_full_police_flow_and_identifier_formats(client, officer):
    sus = client.post("/suspects", json=SUSPECT, headers=officer)
    assert sus.status_code == 201
    sus = sus.json()
    assert sus["suspect_id"] == "SUS-0001"
    assert "password" not in sus

    arr = client.post(
        "/arrests",
        json={"suspect_id": "SUS-0001", "arrest_date": "2026-10-20T09:00:00", "location": "Matsapha"},
        headers=officer,
    )
    assert arr.status_code == 201
    assert arr.json()["arrest_id"] == "ARR-0001"
    assert arr.json()["arresting_officer"] == "officer1"      # defaults to the logged-in user

    case = client.post("/cases", json={"arrest_id": "ARR-0001"}, headers=officer)
    assert case.status_code == 201
    case = case.json()
    assert re.fullmatch(r"CASE-\d{4}-0001", case["case_id"])
    assert case["status"] == "OPEN" and case["court_case_id"] is None and case["charges"] == []

    ch = client.post(
        f"/cases/{case['case_id']}/charges",
        json={"offence": "Theft", "statute": "Theft Act s.5"},
        headers=officer,
    )
    assert ch.status_code == 201 and ch.json()["charge_id"] == "CHG-0001"

    got = client.get(f"/cases/{case['case_id']}", headers=officer).json()
    assert [c["offence"] for c in got["charges"]] == ["Theft"]


def test_duplicate_national_id_is_409(client, officer):
    assert client.post("/suspects", json=SUSPECT, headers=officer).status_code == 201
    r = client.post("/suspects", json=SUSPECT, headers=officer)
    assert r.status_code == 409 and r.json()["error"] == "CONFLICT"
    assert "SUS-0001" in r.json()["message"]


def test_second_case_for_same_arrest_is_409(client, officer, open_case):
    r = client.post("/cases", json={"arrest_id": "ARR-0001"}, headers=officer)
    assert r.status_code == 409


def test_not_found_uses_shared_error_body(client, officer):
    r = client.get("/suspects/SUS-0099", headers=officer)
    assert r.status_code == 404
    assert r.json() == {"error": "NOT_FOUND", "message": "Suspect SUS-0099 does not exist"}
    assert client.post("/cases", json={"arrest_id": "ARR-9"}, headers=officer).status_code == 404
    assert client.post(
        "/arrests",
        json={"suspect_id": "SUS-0099", "arrest_date": "2026-10-20T09:00:00", "location": "x1"},
        headers=officer,
    ).status_code == 404


def test_validation_errors_are_400_with_shared_body(client, officer):
    r = client.post("/suspects", json={"full_name": "A"}, headers=officer)
    assert r.status_code == 400
    body = r.json()
    assert set(body) == {"error", "message"} and body["error"] == "VALIDATION_ERROR"
    assert "national_id" in body["message"]

    r = client.post("/suspects", json={**SUSPECT, "date_of_birth": "not-a-date"}, headers=officer)
    assert r.status_code == 400

    r = client.get("/audit-logs?limit=0", headers={"Authorization": "Bearer " + make_token("admin")})
    assert r.status_code == 400


def test_unknown_route_uses_shared_error_body(client, officer):
    r = client.get("/nope", headers=officer)
    assert r.status_code == 404 and r.json()["error"] == "NOT_FOUND"


# ---------------- referral to the Judiciary (FR-06, design 5.2) ----------------

def test_refer_calls_judiciary_forwards_token_and_marks_referred(client, officer, judiciary, open_case):
    r = client.post(f"/cases/{open_case}/refer", headers=officer)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "REFERRED"
    assert body["court_case_id"] == "CRT-2026-0001"

    assert len(judiciary.calls) == 1
    call = judiciary.calls[0]
    assert call["method"] == "POST" and call["path"] == "/court-cases"
    assert call["auth"] == officer["Authorization"]                 # user's token forwarded
    sent = call["body"]
    assert sent["police_case_id"] == open_case
    assert sent["suspect"]["national_id"] == SUSPECT["national_id"]
    assert sent["suspect"]["full_name"] == "Sipho Dlamini"
    assert sent["arrest"]["location"] == "Manzini"
    assert [c["offence"] for c in sent["charges"]] == ["Theft"]

    assert client.get(f"/cases/{open_case}", headers=officer).json()["status"] == "REFERRED"


def test_case_cannot_be_referred_twice(client, officer, judiciary, open_case):
    assert client.post(f"/cases/{open_case}/refer", headers=officer).status_code == 200
    r = client.post(f"/cases/{open_case}/refer", headers=officer)
    assert r.status_code == 409 and r.json()["error"] == "CONFLICT"
    assert len(judiciary.calls) == 1                                # no second downstream call


def test_refer_needs_at_least_one_charge(client, officer, judiciary):
    client.post("/suspects", json=SUSPECT, headers=officer)
    client.post("/arrests", json={"suspect_id": "SUS-0001", "arrest_date": "2026-10-20T09:00:00",
                                  "location": "Manzini"}, headers=officer)
    case = client.post("/cases", json={"arrest_id": "ARR-0001"}, headers=officer).json()
    r = client.post(f"/cases/{case['case_id']}/refer", headers=officer)
    assert r.status_code == 409
    assert judiciary.calls == []


def test_charges_cannot_be_added_after_referral(client, officer, open_case):
    client.post(f"/cases/{open_case}/refer", headers=officer)
    r = client.post(f"/cases/{open_case}/charges", json={"offence": "Assault"}, headers=officer)
    assert r.status_code == 409


def test_refer_unknown_case_is_404(client, officer):
    assert client.post("/cases/CASE-2026-0099/refer", headers=officer).status_code == 404


def test_court_officer_cannot_refer(client, court, open_case):
    assert client.post(f"/cases/{open_case}/refer", headers=court).status_code == 403


def test_judiciary_down_gives_502_and_leaves_case_open(client, officer, judiciary, open_case):
    for mode in ("down", "timeout", "error500", "bad_body"):
        judiciary.mode = mode
        r = client.post(f"/cases/{open_case}/refer", headers=officer)
        assert r.status_code == 502, mode
        assert r.json()["error"] == "BAD_GATEWAY"
        case = client.get(f"/cases/{open_case}", headers=officer).json()
        assert case["status"] == "OPEN" and case["court_case_id"] is None, mode   # no partial update

    judiciary.mode = "ok"                                           # user can simply retry
    assert client.post(f"/cases/{open_case}/refer", headers=officer).status_code == 200


def test_judiciary_duplicate_is_409_and_case_stays_open(client, officer, judiciary, open_case):
    judiciary.mode = "duplicate"
    r = client.post(f"/cases/{open_case}/refer", headers=officer)
    assert r.status_code == 409
    assert client.get(f"/cases/{open_case}", headers=officer).json()["status"] == "OPEN"


# ---------------- audit log (FR-18, NFR-08) ----------------

def test_audit_log_records_every_create_update_and_referral(client, officer, admin, open_case):
    client.post(f"/cases/{open_case}/refer", headers=officer)
    # failed attempts must not leave audit rows
    client.post(f"/cases/{open_case}/refer", headers=officer)

    logs = client.get("/audit-logs", headers=admin).json()
    actions = [(l["action"], l["record_id"]) for l in reversed(logs)]
    assert actions == [
        ("SUSPECT_CREATED", "SUS-0001"),
        ("ARREST_RECORDED", "ARR-0001"),
        ("CASE_CREATED", open_case),
        ("CHARGE_ADDED", "CHG-0001"),
        ("CASE_REFERRED", open_case),
    ]
    assert all(l["username"] == "officer1" and l["role"] == "police_officer" and l["timestamp"] for l in logs)

    only = client.get(f"/audit-logs?record_id={open_case}", headers=admin).json()
    assert {l["action"] for l in only} == {"CASE_CREATED", "CASE_REFERRED"}


def test_records_store_who_and_when(client, officer, open_case):
    sus = client.get("/suspects/SUS-0001", headers=officer).json()
    assert sus["created_by"] == "officer1" and sus["created_at"]
