# Police Service (port 8001)

Police part of the Eswatini Justice Administration system (CSC411 mini project).
Built to the Part 2 System Design: FastAPI, SQLite + SQLAlchemy, JWT (HS256), bcrypt.

## Run

```bash
cd police-service
pip install -r requirements.txt
uvicorn main:app --port 8001 --reload
```

- Swagger UI: http://localhost:8001/docs
- Police Console (web UI for police officers): http://localhost:8001/ui

Nothing else is required: like the other two services it falls back to the shared
development secret, creates `police.db`, the demo users and three sample cases.

Demo users (all with `DEMO_PASSWORD`, default `Passw0rd!`): `police1` (police_officer),
`court1` (court_officer), `correctional1` (correctional_officer), `admin1` (admin).
`officer1` and `admin` are kept for the existing tests.

| Variable | Purpose | Default |
|---|---|---|
| `JWT_SECRET` | HS256 secret shared by the three services (32+ chars) | shared dev secret (warning logged) |
| `POLICE_DB_URL` | database | `sqlite:///./police.db` |
| `JUDICIARY_URL` | Judiciary base URL | `http://localhost:8002` |
| `CORRECTIONAL_URL` | Correctional base URL (read-only, for tracking) | `http://localhost:8003` |
| `SEED_DEMO_USERS` / `DEMO_PASSWORD` | create demo users | on / `Passw0rd!` |
| `SEED_SAMPLE_CASES` | create the three sample cases (match the other services' seeds) | on |

Never commit these values. `police.db` and `.env` are in `.gitignore`.

## Tests

```bash
python -m pytest
```

The tests replace the Judiciary and Correctional services with mocks, so no other service needs to run.

## Endpoints

| Method and path | Roles | Success |
|---|---|---|
| `POST /auth/login` | anyone | 200 |
| `GET /suspects`, `GET /arrests`, `GET /cases` | police_officer, court_officer, admin | 200 |
| `POST /suspects` | police_officer, admin | 201 |
| `GET /suspects/{id}` | police_officer, court_officer, admin | 200 |
| `POST /arrests` | police_officer, admin | 201 |
| `POST /cases` (body `{"arrest_id": ...}`) | police_officer, admin | 201 |
| `GET /cases/{id}` | police_officer, court_officer, admin | 200 |
| `POST /cases/{id}/charges` | police_officer, admin | 201 |
| `POST /cases/{id}/refer` | police_officer, admin | 200 |
| `POST /cases/{id}/court-updates` (called by Judiciary) | court_officer, correctional_officer, admin | 200 |
| `GET /cases/{id}/tracking` (reads Judiciary + Correctional live) | police_officer, court_officer, admin | 200 |
| `GET /audit-logs` (`limit`, `record_id`, `username`) | admin | 200 |

IDs: `SUS-0001`, `ARR-0001`, `CHG-0001`, `CASE-2026-0001`.
Errors: `{"error": "NOT_FOUND", "message": "..."}` with 400, 401, 403, 404, 409 or 502.

## Structure (design 4.3)

```
app/routers/      endpoints, input validation, role check
app/services.py   business rules, case state machine, audit, calls Judiciary
app/repository.py all database access (never commits; the service owns the transaction)
app/schemas.py    Pydantic request/response DTOs
app/models.py     SQLAlchemy tables: users, suspects, arrests, cases, charges, audit_log
app/judiciary_client.py   POST /court-cases, 5 s timeout, forwards the user's JWT
```

## What the Police service sends to the Judiciary

`POST {JUDICIARY_URL}/court-cases` with `Authorization: Bearer <user's token>`:

```json
{
  "police_case_id": "CASE-2026-0001",
  "suspect": {"suspect_id": "SUS-0001", "national_id": "...", "full_name": "...",
              "date_of_birth": "1980-01-01", "gender": "male", "address": "..."},
  "arrest": {"arrest_id": "ARR-0001", "arrest_date": "2026-10-20T09:00:00",
             "location": "Manzini", "arresting_officer": "officer1"},
  "charges": [{"charge_id": "CHG-0001", "offence": "Theft", "statute": "Theft Act s.5"}]
}
```

It expects `201` with `{"court_case_id": "CRT-2026-0001"}`. `409` from the Judiciary is
returned as `409`; anything else, a timeout or no connection returns `502`, and the case
stays `OPEN` so the officer can retry. **Check this payload with whoever builds the
Judiciary service**; the design only fixes the path and the response.

## Design decisions where the document was silent

- `POST /cases` takes an `arrest_id`; one arrest can have one case (second attempt: 409).
- Referring a case with no charges is 409 (wrong state), not 400.
- Charges can only be added while the case is `OPEN`.
- `address` is required when registering a suspect (FR-02); `gender` is optional.
- The same `national_id` cannot be registered twice (409), because it identifies the
  suspect across all three services.
- `arresting_officer` defaults to the logged-in user.
- `REFERRED -> CLOSED` happens when the Judiciary reports a court status of `SENTENCED` or
  `CLOSED` through `POST /cases/{id}/court-updates`. Later court news (transfer, sentence
  served) still updates `court_status` and `court_outcome` on the closed case.
- bcrypt is used directly (`bcrypt` package) instead of through `passlib`, because passlib
  1.7.x fails with bcrypt 4.1 and later. The hashing algorithm is the same.
