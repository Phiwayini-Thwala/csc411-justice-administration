# Judiciary Service (port 8002)

Court part of the Eswatini Justice Administration system (CSC411 mini project).
Receives cases from the Police service, schedules hearings, decides bail or remand,
records the verdict and sentence, and calls the Correctional service to admit,
convict or release the inmate. Built to `docs/api-contract/openapi.yaml` and the
Part 2 System Design: FastAPI, SQLite + SQLAlchemy, JWT (HS256), bcrypt.

## Run

```bash
cd judiciary-service
pip install -r requirements.txt
uvicorn main:app --port 8002 --reload
```

- Swagger UI: http://localhost:8002/docs
- Court Console (web UI for court officers): http://localhost:8002/ui

Nothing else is required. On first start the service creates `judiciary.db`, the demo
users and two sample cases. Start the Correctional service (8003) too if you want
remand, bail-from-custody and sentencing to work.

| Variable | Purpose | Default |
|---|---|---|
| `JWT_SECRET` | HS256 secret, **same in all three services** (32+ chars) | same dev secret as the Correctional service |
| `CORRECTIONAL_URL` | Correctional base URL | `http://localhost:8003` |
| `POLICE_URL` | Police base URL (court news is sent here) | `http://localhost:8001` |
| `JUDICIARY_DB_URL` | database | `sqlite:///./judiciary.db` |
| `SEED_DEMO_USERS` / `DEMO_PASSWORD` | create demo users | on / `Passw0rd!` |
| `SEED_SAMPLE_CASES` | create the two sample cases | on |

Demo users (same as the Correctional service and the Postman environment):
`court1` (court_officer), `police1` (police_officer), `correctional1` (correctional_officer), `admin1` (admin).

## Endpoints

| Method and path | Roles | What it does | Success |
|---|---|---|---|
| `POST /auth/login` | anyone | Get a JWT | 200 |
| `POST /court-cases` | police_officer, court_officer, admin | Receive a referred case (called by Police) | 201 |
| `GET /court-cases` | court_officer, correctional_officer, admin | List cases (extra, used by the UI) | 200 |
| `GET /court-cases/{id}` | court_officer, correctional_officer, police_officer, admin | Case with hearings, decisions and custody events | 200 |
| `GET /court-cases/{id}/linked` | court_officer, correctional_officer, admin | Live Police case and Correctional inmate for this case | 200 |
| `POST /court-cases/{id}/custody-events` | correctional_officer, admin | Transfer/release reported by Correctional | 200 |
| `POST /court-cases/{id}/notify-police` | court_officer, admin | Resend the court status to Police | 200 |
| `POST /court-cases/{id}/hearings` | court_officer, admin | Schedule a hearing | 201 |
| `POST /court-cases/{id}/bail` | court_officer, admin | Grant bail | 200 |
| `POST /court-cases/{id}/remand` | court_officer, admin | Remand in custody | 200 |
| `POST /court-cases/{id}/verdict` | court_officer, admin | Verdict and sentence | 200 |
| `GET /audit-logs` | admin | Audit trail | 200 |

Errors always look like `{"error": "NOT_FOUND", "message": "..."}` (400, 401, 403, 404, 409, 502).

## Court case life cycle

`RECEIVED -> HEARING_SCHEDULED -> ON_BAIL or ON_REMAND -> SENTENCED or CLOSED`

| Action | Allowed when the case is |
|---|---|
| Schedule hearing | RECEIVED, HEARING_SCHEDULED, ON_BAIL, ON_REMAND |
| Grant bail | HEARING_SCHEDULED, ON_REMAND |
| Remand | HEARING_SCHEDULED, ON_BAIL |
| Verdict | HEARING_SCHEDULED, ON_BAIL, ON_REMAND |

Anything else returns 409.

## Calls to the Correctional service (design 5.4)

| Decision | Suspect on remand? | Call made |
|---|---|---|
| Remand | no | `POST /inmates` (REMAND), inmate_id saved |
| Bail | yes | `POST /inmates/{id}/release` (BAIL_GRANTED) |
| Bail | no | none |
| Guilty, imprisonment | yes | `PUT /inmates/{id}/status` (CONVICTED + sentence_months) |
| Guilty, imprisonment | no | `POST /inmates` (CONVICTED, needs `facility`) |
| Guilty, fine or suspended | yes | `POST /inmates/{id}/release` (COURT_ORDER), case CLOSED |
| Guilty, fine or suspended | no | none, case CLOSED |
| Not guilty | yes | `POST /inmates/{id}/release` (ACQUITTED), case CLOSED |
| Not guilty | no | none, case CLOSED |

The caller's JWT is forwarded, with a 5-second timeout. The Correctional service is
called **first**; if it fails the decision is **not saved** and the answer is 502
(or 409 if Correctional reports a conflict).

## Feedback to the Police service

After every hearing, bail, remand, verdict or custody event the service calls
`POST {POLICE_URL}/cases/{police_case_id}/court-updates` with
`{court_case_id, court_status, outcome, inmate_id}`. The court decision is saved
first; if the Police service is down the case is marked `police_sync: FAILED`
and the court officer can press **Resend to Police** (or call `/notify-police`).
The Police case closes itself when the court status is `SENTENCED` or `CLOSED`.

Correctional reports transfers and releases to `POST /court-cases/{id}/custody-events`.
A release with reason `SENTENCE_COMPLETED` moves a `SENTENCED` case to `CLOSED`.
Our own calls to Correctional carry `X-Origin-Service: judiciary`, so Correctional
does not report the court's own release orders back.

## Sample data

`CRT-2026-0001` (Sipho Dlamini, on remand, `INM-0001`) and `CRT-2026-0002` (Thandi Nkambule,
sentenced, `INM-0002`) match the two inmates the Correctional service seeds. The first case
Police refers therefore becomes `CRT-2026-0003`, so it cannot clash with a seeded inmate.

## Tests

```bash
python -m pytest
```

The tests replace the Correctional service with a mock, so no other service needs to run.
