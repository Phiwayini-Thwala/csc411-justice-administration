import json
from datetime import datetime, timedelta, timezone

import httpx
import jwt
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.judiciary_client import JudiciaryClient
from app.main import create_app

SECRET = "test-secret-not-for-production-use-0123456789"
PASSWORD = "demo-password-123"


class FakeJudiciary:
    """Stands in for the Judiciary service (httpx.MockTransport)."""

    def __init__(self):
        self.calls = []            # every request the Police service made
        self.mode = "ok"           # ok | down | timeout | duplicate | error500 | bad_body
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
        if self.mode == "duplicate":
            return httpx.Response(409, json={"error": "CONFLICT", "message": "exists"})
        if self.mode == "error500":
            return httpx.Response(500, json={"error": "INTERNAL_ERROR", "message": "boom"})
        if self.mode == "bad_body":
            return httpx.Response(201, json={"unexpected": True})
        self.counter += 1
        return httpx.Response(201, json={"court_case_id": f"CRT-2026-{self.counter:04d}"})


@pytest.fixture
def judiciary():
    return FakeJudiciary()


@pytest.fixture
def client(judiciary):
    settings = Settings(
        jwt_secret=SECRET,
        database_url="sqlite://",              # in-memory, fresh per test
        seed_demo_users=True,
        demo_password=PASSWORD,
        bcrypt_rounds=4,                       # fast hashing for tests only
    )
    jc = JudiciaryClient(
        "http://judiciary.test", client=httpx.Client(transport=httpx.MockTransport(judiciary.handler))
    )
    with TestClient(create_app(settings, jc)) as c:
        yield c


def login(client, username):
    r = client.post("/auth/login", json={"username": username, "password": PASSWORD})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture
def officer(client):
    return {"Authorization": f"Bearer {login(client, 'officer1')}"}


@pytest.fixture
def court(client):
    return {"Authorization": f"Bearer {login(client, 'court1')}"}


@pytest.fixture
def correctional(client):
    return {"Authorization": f"Bearer {login(client, 'correctional1')}"}


@pytest.fixture
def admin(client):
    return {"Authorization": f"Bearer {login(client, 'admin')}"}


def make_token(role="police_officer", sub="officer1", expires_in=3600, secret=SECRET, alg="HS256"):
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {"sub": sub, "role": role, "iat": now, "exp": now + timedelta(seconds=expires_in)},
        secret, algorithm=alg,
    )


SUSPECT = {
    "full_name": "Sipho Dlamini",
    "national_id": "8001015800083",
    "date_of_birth": "1980-01-01",
    "gender": "male",
    "address": "Ngwane Park, Manzini",
}


@pytest.fixture
def open_case(client, officer):
    """A suspect, arrest and OPEN case with one charge."""
    sus = client.post("/suspects", json=SUSPECT, headers=officer).json()
    arr = client.post(
        "/arrests",
        json={"suspect_id": sus["suspect_id"], "arrest_date": "2026-10-20T09:00:00", "location": "Manzini"},
        headers=officer,
    ).json()
    case = client.post("/cases", json={"arrest_id": arr["arrest_id"]}, headers=officer).json()
    client.post(
        f"/cases/{case['case_id']}/charges",
        json={"offence": "Theft", "statute": "Theft Act s.5"},
        headers=officer,
    )
    return case["case_id"]
