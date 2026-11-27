"""Quick self-test: python test_flow.py  (temporary database, Judiciary mocked)"""
import json
import os
import tempfile

os.environ["CORRECTIONAL_DB"] = os.path.join(tempfile.mkdtemp(), "t.db")

import httpx  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import judiciary_client  # noqa: E402
from main import app  # noqa: E402

court_calls = []


def fake_judiciary(request: httpx.Request) -> httpx.Response:
    court_calls.append((request.method, request.url.path, json.loads(request.content) if request.content else None))
    if request.method == "GET":
        return httpx.Response(200, json={"court_case_id": request.url.path.rsplit("/", 1)[-1], "status": "SENTENCED"})
    return httpx.Response(200, json={"status": "OK"})


judiciary_client.set_http_client(httpx.Client(transport=httpx.MockTransport(fake_judiciary)))

with TestClient(app) as c:
    def tok(u):
        r = c.post("/auth/login", json={"username": u, "password": "Passw0rd!"})
        assert r.status_code == 200, r.text
        return {"Authorization": "Bearer " + r.json()["access_token"]}
    court, corr, admin, police = tok("court1"), tok("correctional1"), tok("admin1"), tok("police1")
    as_judiciary = {**court, "X-Origin-Service": "judiciary"}

    def check(label, r, code):
        print(("PASS" if r.status_code == code else "FAIL"), label, r.status_code, r.json() if r.status_code >= 400 else "")
        assert r.status_code == code, r.text
        if code >= 400:
            assert set(r.json()) == {"error", "message"}, r.json()
        return r.json()

    check("no token", c.get("/inmates/INM-0001"), 401)
    check("bad login", c.post("/auth/login", json={"username": "x", "password": "y"}), 401)
    body = {"full_name": "Test Person", "national_id": "9001015800085", "court_case_id": "CRT-2026-0100",
            "admission_type": "REMAND", "facility": "Mbabane Remand Centre"}
    check("police cannot admit", c.post("/inmates", json=body, headers=police), 403)
    i = check("admit remand", c.post("/inmates", json=body, headers=as_judiciary), 201)
    assert i["inmate_id"] == "INM-0003" and i["status"] == "REMAND"
    check("duplicate court case", c.post("/inmates", json=body, headers=court), 409)
    check("convicted needs sentence", c.post("/inmates", json={**body, "court_case_id": "CRT-9", "admission_type": "CONVICTED"}, headers=court), 400)
    check("bad enum", c.post("/inmates", json={**body, "court_case_id": "CRT-8", "admission_type": "X"}, headers=court), 400)
    iid = i["inmate_id"]
    check("court read", c.get(f"/inmates/{iid}", headers=court), 200)
    r = check("convict", c.put(f"/inmates/{iid}/status", json={"status": "CONVICTED", "sentence_months": 18}, headers=as_judiciary), 200)
    assert r["status"] == "CONVICTED" and r["sentence_months"] == 18
    check("convict twice", c.put(f"/inmates/{iid}/status", json={"status": "CONVICTED", "sentence_months": 18}, headers=court), 409)
    check("court cannot transfer", c.put(f"/inmates/{iid}/transfer", json={"new_facility": "Sidwashini", "reason": "overcrowding"}, headers=court), 403)
    court_calls.clear()
    t = check("transfer", c.put(f"/inmates/{iid}/transfer", json={"new_facility": "Sidwashini Correctional Centre", "reason": "overcrowding"}, headers=corr), 200)
    assert t["status"] == "TRANSFERRED" and len(t["transfers"]) == 1 and t["legal_status"] == "CONVICTED"
    assert court_calls[-1][1] == "/court-cases/CRT-2026-0100/custody-events" and court_calls[-1][2]["event"] == "TRANSFERRED"
    assert t["court_sync"] == "OK"
    r = check("release", c.post(f"/inmates/{iid}/release", json={"reason": "SENTENCE_COMPLETED"}, headers=corr), 200)
    assert r["status"] == "RELEASED" and r["released_at"]
    assert court_calls[-1][2]["event"] == "RELEASED" and court_calls[-1][2]["reason"] == "SENTENCE_COMPLETED"
    check("release twice", c.post(f"/inmates/{iid}/release", json={"reason": "COURT_ORDER"}, headers=corr), 409)
    court_calls.clear()
    j = check("court release order is not echoed back", c.post("/inmates/INM-0001/release", json={"reason": "BAIL_GRANTED"}, headers=as_judiciary), 200)
    assert not court_calls and j["status"] == "RELEASED"
    check("transfer needs reason", c.put("/inmates/INM-0002/transfer", json={"new_facility": "X"}, headers=corr), 400)
    check("admit needs full_name", c.post("/inmates", json={k: v for k, v in body.items() if k != "full_name"} | {"court_case_id": "CRT-7"}, headers=court), 400)
    check("correctional can admit", c.post("/inmates", json={**body, "court_case_id": "CRT-2026-0200"}, headers=corr), 201)
    check("re-admit after release (same court case)", c.post("/inmates", json={**body, "admission_type": "CONVICTED", "sentence_months": 12}, headers=court), 201)
    check("unknown inmate", c.get("/inmates/INM-9999", headers=corr), 404)
    lst = check("list", c.get("/inmates?search=Test", headers=corr), 200)
    assert isinstance(lst, list) and len(lst) >= 3
    link = check("linked court case", c.get("/inmates/INM-0002/linked", headers=corr), 200)
    assert link["court_case"]["court_case_id"] == "CRT-2026-0002"
    check("audit non-admin", c.get("/audit-logs", headers=corr), 403)
    logs = check("audit admin", c.get("/audit-logs", headers=admin), 200)
    assert isinstance(logs, list) and {"time", "username", "role", "action", "record_id"} <= set(logs[0])
    print("audit rows:", len(logs))
print("ALL TESTS PASSED")
