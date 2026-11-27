# Correctional Service Microservice

## 1. Project Overview

The Correctional Service Microservice is part of the CSC411 Justice Administration System. It manages correctional records and activities after individuals enter the correctional system through the justice process.

The microservice provides functionality for inmate admission, inmate status updates, transfers between correctional facilities, releases, and audit logging.

It is designed to integrate with the Police and Judiciary microservices through REST-based communication and shared authentication.

## 2. Technologies Used

- **Python** – Main programming language.
- **FastAPI** – Backend framework for developing REST APIs.
- **SQLite** – Database for storing correctional records.
- **JWT (JSON Web Tokens)** – Authentication and authorization.
- **bcrypt** – Password hashing.
- **Uvicorn** – ASGI server used to run the application.
- **Git and GitHub** – Version control and source-code collaboration.
- **Swagger UI** – API documentation and testing.

## 3. Project Structure

```text
correctional-service/
│
├── auth.py              JWT validation and role checks
├── database.py          SQLite schema, demo users and sample inmates
├── judiciary_client.py  calls to the Judiciary service (custody events, court case reads)
├── main.py              API endpoints and the /ui route
├── static/index.html    Custody Console (same design as the Police and Court consoles)
├── test_flow.py         self-test with the Judiciary mocked
├── requirements.txt
├── .env.example
└── README.md
```

## 4. Requirements

Before running the application, ensure that you have installed:

- Python 3.10 or later
- Visual Studio Code
- Git

## 5. Installation and Setup

### Step 1: Clone the Repository

```powershell
git clone https://github.com/Phiwayini-Thwala/csc411-justice-administration.git
```

### Step 2: Navigate to the Correctional Service Folder

```powershell
cd csc411-justice-administration/correctional-service
```

### Step 3: Create a Virtual Environment

```powershell
python -m venv .venv
```

### Step 4: Activate the Virtual Environment

```powershell
.\.venv\Scripts\activate
```

### Step 5: Install Dependencies

```powershell
pip install -r requirements.txt
```

## 6. Environment Configuration

The application reads the JWT secret from the `JWT_SECRET` environment variable.

For Windows PowerShell, set the variable before starting the application:

```powershell
$env:JWT_SECRET="your-secure-shared-secret-of-at-least-32-characters"
```

The JWT secret must be the same across the Police, Judiciary, and Correctional Service applications when shared JWT authentication is used.

**Important:** Do not upload actual secret values to GitHub. The application currently has a development fallback secret intended only for local development and testing.

The `.env.example` file is provided as a reference. The application does not automatically load `.env` files in its current configuration.

## 7. Running the Application

```powershell
uvicorn main:app --port 8003 --reload
```

- Custody Console (web UI): http://127.0.0.1:8003/ui
- Swagger UI: http://127.0.0.1:8003/docs

Demo users (password `DEMO_PASSWORD`, default `Passw0rd!`): `correctional1`, `court1`, `police1`, `admin1`.
Two sample inmates match the Police and Judiciary sample cases: `INM-0001` (remand, `CRT-2026-0001`) and `INM-0002` (convicted, `CRT-2026-0002`).

| Variable | Purpose | Default |
|---|---|---|
| `JWT_SECRET` | shared HS256 secret | shared dev secret (warning logged) |
| `JUDICIARY_URL` | where transfers and releases are reported | `http://localhost:8002` |
| `CORRECTIONAL_DB` | database file | `correctional.db` next to `main.py` |
| `DEMO_PASSWORD` | password for the demo users | `Passw0rd!` |

## 8. Main Functionalities

| Method and path | Roles | What it does |
|---|---|---|
| `POST /auth/login` | anyone | JWT with role |
| `GET /inmates` | all four roles | List and search (`status`, `search`) |
| `POST /inmates` | court_officer (via Judiciary), correctional_officer, admin | Admit (REMAND or CONVICTED) |
| `GET /inmates/{id}` | all four roles | Inmate with transfers and releases |
| `GET /inmates/{id}/linked` | all four roles | The court case, read live from the Judiciary |
| `PUT /inmates/{id}` | correctional_officer, admin | Correct name or sentence |
| `PUT /inmates/{id}/status` | court_officer (via Judiciary), correctional_officer, admin | REMAND → CONVICTED |
| `PUT /inmates/{id}/transfer` | correctional_officer, admin | Move to another facility (reported to the court) |
| `POST /inmates/{id}/release` | court_officer (via Judiciary), correctional_officer, admin | Release (reported to the court unless the court ordered it) |
| `POST /inmates/{id}/notify-court` | correctional_officer, admin | Resend the last transfer/release to the court |
| `GET /audit-logs` | admin | Audit trail (array of `time, username, role, action, record_id`) |

All errors use `{"error": "...", "message": "..."}`; validation errors are 400.
`status` follows the contract (`REMAND`, `CONVICTED`, `TRANSFERRED`, `RELEASED`);
`legal_status` keeps REMAND/CONVICTED after a transfer.

## 9. Testing

```powershell
python test_flow.py
```

Uses a temporary database and a mocked Judiciary. Covers authentication, roles,
admission rules, conviction, transfer and release (including the report to the
court and that court-ordered releases are not echoed back), the linked view and
the audit log.

## 10. Integration with Other Microservices

- The **Judiciary** admits, convicts and releases inmates here; those calls carry
  `X-Origin-Service: judiciary`.
- Transfers and releases done here are sent to the Judiciary
  (`POST /court-cases/{id}/custody-events`), which records them on the court file
  and passes them on to the **Police** case. A completed sentence closes the court case.
- If the Judiciary is down, the change is still saved here and marked
  `court_sync: FAILED`; **Resend to Court** in the console retries it.

## 11. Academic Information

**Course:** CSC411 – Integrative Programming Technologies  
**Project:** Justice Administration System  
**Component:** Correctional Service Microservice  
**Institution:** University of Eswatini (UNESWA)

## 12. Repository

GitHub Repository:

https://github.com/Phiwayini-Thwala/csc411-justice-administration
