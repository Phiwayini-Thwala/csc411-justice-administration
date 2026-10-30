# Police Service (port 8001)

Police part of the Eswatini Justice Administration system (CSC411 mini project).
Built to the Part 2 System Design: FastAPI, SQLite + SQLAlchemy, JWT (HS256), bcrypt.

## Run (one command per service)

```bash
pip install -r requirements.txt

export JWT_SECRET="<same 32+ character secret as the other two services>"
export JUDICIARY_URL="http://localhost:8002"      # optional, this is the default
export SEED_DEMO_USERS=1                           # optional: create demo users on start
export DEMO_PASSWORD="<choose a demo password>"    # required when SEED_DEMO_USERS=1

uvicorn app.main:create_app --factory --port 8001
```

Swagger UI: http://localhost:8001/docs

Demo users (when seeded, all with `DEMO_PASSWORD`): `officer1` (police_officer),
`court1` (court_officer), `correctional1` (correctional_officer), `admin` (admin).

| Variable | Purpose | Default |
|---|---|---|
| `JWT_SECRET` | HS256 secret shared by the three services (required, 32+ chars) | none |
| `POLICE_DB_URL` | database | `sqlite:///./police.db` |
| `JUDICIARY_URL` | Judiciary base URL | `http://localhost:8002` |
| `SEED_DEMO_USERS` / `DEMO_PASSWORD` | create demo users | off |

Never commit these values. `police.db` and `.env` are in `.gitignore`.

## Tests

```bash
python -m pytest
```

The tests replace the Judiciary service with a mock, so no other service needs to run.

## Endpoints

| Method and path | Roles | Success |
|---|---|---|
| `POST /auth/login` | anyone | 200 |
| `POST /suspects` | police_officer, admin | 201 |
| `GET /suspects/{id}` | police_officer, court_officer, admin | 200 |
| `POST /arrests` | police_officer, admin | 201 |
| `POST /cases` (body `{"arrest_id": ...}`) | police_officer, admin | 201 |
| `GET /cases/{id}` | police_officer, court_officer, admin | 200 |
| `POST /cases/{id}/charges` | police_officer, admin | 201 |
| `POST /cases/{id}/refer` | police_officer, admin | 200 |
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
- The `REFERRED -> CLOSED` transition exists in the state machine, but the Police contract
  has no endpoint that closes a case, so nothing calls it yet.
- bcrypt is used directly (`bcrypt` package) instead of through `passlib`, because passlib
  1.7.x fails with bcrypt 4.1 and later. The hashing algorithm is the same.
