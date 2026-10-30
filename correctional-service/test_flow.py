"""Quick self-test: python test_flow.py  (uses a temporary database)"""
import os, tempfile
os.environ["CORRECTIONAL_DB"] = os.path.join(tempfile.mkdtemp(), "t.db")
from fastapi.testclient import TestClient
from main import app

with TestClient(app) as c:
    def tok(u):
        return {"Authorization": "Bearer " + c.post("/auth/login", json={"username": u, "password": "Passw0rd!"}).json()["access_token"]}
    court, corr, admin, police = tok("court1"), tok("correctional1"), tok("admin1"), tok("police1")

    def check(label, r, code):
        print(("PASS" if r.status_code == code else "FAIL"), label, r.status_code, r.json() if r.status_code >= 400 else "")
        assert r.status_code == code
        return r.json()

    check("no token", c.get("/inmates/INM-0001"), 401)
    check("bad login", c.post("/auth/login", json={"username": "x", "password": "y"}), 401)
    body = {"full_name": "Test Person", "national_id": "9001015800085", "court_case_id": "CRT-2026-0100", "admission_type": "REMAND", "facility": "Mbabane Remand Centre"}
    check("police cannot admit", c.post("/inmates", json=body, headers=police), 403)
    i = check("admit remand", c.post("/inmates", json=body, headers=court), 201)
    check("duplicate court case", c.post("/inmates", json=body, headers=court), 409)
    check("convicted needs sentence", c.post("/inmates", json={**body, "court_case_id": "CRT-9", "admission_type": "CONVICTED"}, headers=court), 400)
    check("bad enum", c.post("/inmates", json={**body, "court_case_id": "CRT-8", "admission_type": "X"}, headers=court), 400)
    iid = i["inmate_id"]
    check("court read", c.get(f"/inmates/{iid}", headers=court), 200)
    check("convict", c.put(f"/inmates/{iid}/status", json={"status": "CONVICTED", "sentence_months": 18}, headers=court), 200)
    check("convict twice", c.put(f"/inmates/{iid}/status", json={"status": "CONVICTED", "sentence_months": 18}, headers=court), 409)
    check("court cannot transfer", c.put(f"/inmates/{iid}/transfer", json={"new_facility": "Sidwashini", "reason": "overcrowding"}, headers=court), 403)
    t = check("transfer", c.put(f"/inmates/{iid}/transfer", json={"new_facility": "Sidwashini Correctional Centre", "reason": "overcrowding"}, headers=corr), 200)
    assert len(t["transfers"]) == 1
    r = check("release", c.post(f"/inmates/{iid}/release", json={"reason": "SENTENCE_COMPLETED"}, headers=corr), 200)
    assert r["status"] == "RELEASED"
    check("release twice", c.post(f"/inmates/{iid}/release", json={"reason": "COURT_ORDER"}, headers=corr), 409)
    check("transfer needs reason", c.put("/inmates/INM-0001/transfer", json={"new_facility": "X"}, headers=corr), 400)
    check("admit needs full_name", c.post("/inmates", json={k: v for k, v in body.items() if k != "full_name"} | {"court_case_id": "CRT-7"}, headers=court), 400)
    check("correctional can admit", c.post("/inmates", json={**body, "court_case_id": "CRT-2026-0200"}, headers=corr), 201)
    check("re-admit after release (same court case)", c.post("/inmates", json={**body, "admission_type": "CONVICTED", "sentence_months": 12}, headers=court), 201)
    check("unknown inmate", c.get("/inmates/INM-9999", headers=corr), 404)
    check("audit non-admin", c.get("/audit-logs", headers=corr), 403)
    logs = check("audit admin", c.get("/audit-logs", headers=admin), 200)
    print("audit rows:", len(logs))
print("ALL TESTS PASSED")
