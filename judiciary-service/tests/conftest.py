import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.correctional_client import CorrectionalClient, PoliceClient
from app.main import create_app

SECRET = "test-secret-not-for-production-use-0123456789"
PASSWORD = "demo-password-123"


class FakeCorrectional:
    """Stands in for the Correctional service (httpx.MockTransport)."""

    def __init__(self):
        self.calls = []          # every request the Judiciary made
        self.mode = "ok"         # ok | down | timeout | conflict | error500
        self.counter = 0

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.calls.append({
            "method": request.method,
            "path": request.url.path,
            "auth": request.headers.get("authorization"),
            "body": json.loads(request.content) if request.content else None,
        })
        if self.mode == "down":
            raise httpx.ConnectError("connection refused")
        if self.mode == "timeout":
            raise httpx.ReadTimeout("too slow")
        if self.mode == "conflict":
            return httpx.Response(409, json={"error": "CONFLICT", "message": "already in custody"})
        if self.mode == "error500":
            return httpx.Response(500, json={"error": "INTERNAL_ERROR", "message": "boom"})
        if request.method == "POST" and request.url.path == "/inmates":
            self.counter += 1
            return httpx.Response(201, json={"inmate_id": f"INM-9{self.counter:03d}"})
        return httpx.Response(200, json={"status": "OK"})


class FakePolice:
    """Stands in for the Police service (receives court updates, serves case reads)."""

    def __init__(self):
        self.calls = []
        self.mode = "ok"         # ok | down

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.calls.append({
            "method": request.method,
            "path": request.url.path,
            "auth": request.headers.get("authorization"),
            "body": json.loads(request.content) if request.content else None,
        })
        if self.mode == "down":
            raise httpx.ConnectError("connection refused")
        if request.method == "GET":
            return httpx.Response(200, json={"case_id": request.url.path.rsplit("/", 1)[-1], "status": "REFERRED"})
        return httpx.Response(200, json={"status": "REFERRED"})


@pytest.fixture
def correctional():
    return FakeCorrectional()


@pytest.fixture
def police_service():
    return FakePolice()


@pytest.fixture
def client(correctional, police_service):
    settings = Settings(
        jwt_secret=SECRET, database_url="sqlite://", seed_demo_users=True, demo_password=PASSWORD,
        seed_sample_cases=True, bcrypt_rounds=4)
    http = httpx.Client(transport=httpx.MockTransport(correctional.handler))
    phttp = httpx.Client(transport=httpx.MockTransport(police_service.handler))
    app = create_app(settings, CorrectionalClient("http://correctional.test", client=http),
                     PoliceClient("http://police.test", client=phttp))
    with TestClient(app) as c:
        yield c


def login(client, username):
    r = client.post("/auth/login", json={"username": username, "password": PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
def court(client):
    return login(client, "court1")


@pytest.fixture
def police(client):
    return login(client, "police1")


@pytest.fixture
def correctional_user(client):
    return login(client, "correctional1")


@pytest.fixture
def admin(client):
    return login(client, "admin1")


REFERRAL = {
    "police_case_id": "CASE-2026-0101",
    "suspect": {"suspect_id": "SUS-0001", "national_id": "8888800000001", "full_name": "Test Suspect",
                "date_of_birth": "1990-02-03", "gender": "male", "address": "Manzini"},
    "arrest": {"arrest_id": "ARR-0001", "location": "Manzini"},
    "charges": [{"charge_id": "CHG-0001", "offence": "Theft", "statute": "Theft Act section 4"}],
}


@pytest.fixture
def new_case(client, police):
    """A freshly received court case (status RECEIVED)."""
    r = client.post("/court-cases", json=REFERRAL, headers=police)
    assert r.status_code == 201, r.text
    return r.json()["court_case_id"]


HEARING = {"hearing_date": "2026-11-20T09:00:00", "court_name": "Manzini Magistrate Court",
           "presiding_officer": "Magistrate Simelane"}
REMAND = {"reason": "Risk of absconding", "facility": "Matsapha Correctional Centre",
          "next_hearing_date": "2026-11-27T09:00:00"}


@pytest.fixture
def scheduled_case(client, court, new_case):
    r = client.post(f"/court-cases/{new_case}/hearings", json=HEARING, headers=court)
    assert r.status_code == 201, r.text
    return new_case


@pytest.fixture
def remanded_case(client, court, scheduled_case, correctional):
    r = client.post(f"/court-cases/{scheduled_case}/remand", json=REMAND, headers=court)
    assert r.status_code == 200, r.text
    correctional.calls.clear()
    return scheduled_case
