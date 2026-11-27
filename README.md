# CSC411 Mini Project: Justice Administration

**University of Eswatini, Department of Computer Science**
Course: Integrative Programming Technologies (CSC411), Instructor: Dr MA Nxumalo

## Overview

This project automates one inter-organizational process: a suspect moving from **Police** to **Judiciary** to **Correctional Services**. Three independent REST services, each with its own database, work together to complete the process.

1. **Police** registers the suspect, records the arrest, creates the case, adds charges and refers the case to court.
2. **Judiciary** receives the case, schedules a hearing, decides bail or remand, and records the verdict and sentence. It then calls the Correctional service to admit the inmate.
3. **Correctional Services** admits the inmate and manages status, transfer and release, and reports transfers and releases back to the court.
4. Every court decision is reported back to the **Police**, so the police case shows where the suspect is and closes itself after the verdict.

## Architecture

| Service | Port | Database | Folder | Web console |
|---|---|---|---|---|
| Police | 8001 | SQLite (`police.db`) | `/police-service/` | http://localhost:8001/ui |
| Judiciary | 8002 | SQLite (`judiciary.db`) | `/judiciary-service/` | http://localhost:8002/ui |
| Correctional | 8003 | SQLite (`correctional.db`) | `/correctional-service/` | http://localhost:8003/ui |

- **Language and framework:** Python 3.10+ with FastAPI
- **Communication:** REST with JSON; services call each other with `httpx` (5-second timeout) and forward the caller's JWT
- **Security:** JWT (HS256, one secret shared by the three services) with role-based access control, bcrypt passwords, audit logging
- **API contract:** OpenAPI/Swagger (see `/docs/api-contract/openapi.yaml`)
- **Frontend:** one web console per service (same design, served at `/ui`) and a system portal (`/frontend/index.html`)
- **Testing:** pytest per service and a Postman collection for the full flow

## How the three databases communicate

Each service owns its database; no service reads another's database directly. They stay in step through REST calls:

| From → To | Call | When | If the other service is down |
|---|---|---|---|
| Police → Judiciary | `POST /court-cases` | Officer refers a case | Nothing is saved; officer retries (502) |
| Judiciary → Correctional | `POST /inmates`, `PUT /inmates/{id}/status`, `POST /inmates/{id}/release` | Remand, guilty verdict, bail, acquittal, fine | Nothing is saved; court officer retries (502) |
| Judiciary → Police | `POST /cases/{id}/court-updates` | After **every** court decision | Decision is kept; marked “not delivered” and can be resent |
| Correctional → Judiciary | `POST /court-cases/{id}/custody-events` | Inmate transferred or released | Change is kept; marked “not delivered” and can be resent |
| Police → Judiciary + Correctional | `GET /cases/{id}/tracking` | Officer tracks a case | Only the unreachable part is blank |
| Judiciary → Police + Correctional | `GET /court-cases/{id}/linked` | Court officer opens a case file | Only the unreachable part is blank |
| Correctional → Judiciary | `GET /inmates/{id}/linked` | Officer opens an inmate record | Only the unreachable part is blank |

Result: when the court remands someone the police case shows *Held in Custody*; after the verdict the police case is closed automatically; when Correctional Services transfers or releases the inmate, the court file and the police case record it; a completed sentence closes the court case. Calls made by the Judiciary carry `X-Origin-Service: judiciary`, so Correctional does not echo the court's own orders back.

The three databases are seeded with the **same sample people** so they agree from the first start: `CASE-2026-0001 → CRT-2026-0001 → INM-0001` (Sipho Dlamini, on remand) and `CASE-2026-0002 → CRT-2026-0002 → INM-0002` (Thandi Nkambule, sentenced). Police also has an open case (`CASE-2026-0003`) ready to be referred live.

## Project structure

| Path | Contents |
|---|---|
| `/docs/part1-process/` | Part 1: process research, stakeholders, DFD |
| `/docs/part2-design/` | Part 2: requirements, architecture, class diagram |
| `/docs/api-contract/` | OpenAPI contract |
| `/police-service/` | Police service (port 8001), console in `app/static/` |
| `/judiciary-service/` | Judiciary service (port 8002), console in `app/static/` |
| `/correctional-service/` | Correctional service (port 8003), console in `static/` |
| `/frontend/` | System portal: service status, data-flow diagram, cross-system tracker |
| `/tests/postman/` | Postman collection and environment |

## Prerequisites

- Python 3.10 or newer
- Git
- Postman (for running the tests)

## How to run

1. Clone the repository:

```
   git clone https://github.com/Phiwayini-Thwala/csc411-justice-administration.git
   cd csc411-justice-administration
```

2. Install dependencies (once):

```
   pip install -r police-service/requirements.txt -r judiciary-service/requirements.txt -r correctional-service/requirements.txt
```

3. Start all three services.

   **Windows:** `powershell -ExecutionPolicy Bypass -File .\start_all.ps1` (opens one window per service and the portal)

   **macOS/Linux:** `./start_all.sh`

   Or start each one in its own terminal; the command is the same in every folder:

```
   cd police-service
   uvicorn main:app --port 8001 --reload

   cd judiciary-service
   uvicorn main:app --port 8002 --reload

   cd correctional-service
   uvicorn main:app --port 8003 --reload
```

4. Open `/frontend/index.html` (the portal) or go straight to a console:
   - Police console: http://localhost:8001/ui
   - Court console: http://localhost:8002/ui
   - Custody console: http://localhost:8003/ui
   - API docs: http://localhost:8001/docs, http://localhost:8002/docs, http://localhost:8003/docs

5. Sign in with a demo account. The same accounts exist in all three services and one sign-in carries across consoles through **Switch console** in the sidebar.

| Username | Role | Password |
|---|---|---|
| `police1` | Police officer | `DEMO_PASSWORD` (default `Passw0rd!`) |
| `court1` | Court officer | same |
| `correctional1` | Correctional officer | same |
| `admin1` | Administrator (all consoles + activity history) | same |

> Database files are not stored in the repository. Each service creates and seeds its database on first start. To start the demo again from the sample data, stop the services and run `reset_demo_data.ps1` (or `.sh`); always reset all three together.
>
> `JWT_SECRET` must be the same in all three services. If it is not set, all three use the same development secret and log a warning; set your own value for anything beyond the classroom demo.

## Running the tests

**Unit tests (no other service needs to run; the others are mocked):**

```
cd police-service        && python -m pytest
cd judiciary-service     && python -m pytest
cd correctional-service  && python test_flow.py
```

**End-to-end (Postman):**

1. Open Postman and import the files in `/tests/postman/` (the collection and the environment).
2. Select the imported environment.
3. Make sure all three services are running.
4. Run the collection with the **Collection Runner**. It tests the full flow: Police, then Judiciary, then Correctional, and then checks that the court news reached the Police database (step 7b), that the transfer and release reached the Judiciary (12b), that the police case closed with the final outcome (13), and the live tracking view (14).

## Team contributions

| Member | Name | Student number | GitHub profile | Role |
|---|---|---|---|---|
| 1 |Kwanele Motsa |155307 |https://github.com/kwanelemotsa62-netizen | Process research, diagrams, frontend, report editing |
| 2 |Melody Sylvester |202303641 | https://github.com/Melody386 | System design, requirements, OpenAPI contract |
| 3 |Thandinkosi Magagula |202302756 | https://github.com/Thandinkosi-20230275| Police service |
| 4 |Sibusiso Maseko |202301241 |https://github.com/SDMaseko | Judiciary service |
| 5 |Phiwayini Thwala |202403175 | https://github.com/Phiwayini-Thwala | Correctional service, Postman tests, repository admin, submission |

## Documentation

- [Part 1: Process](docs/part1-process/)
- [Part 2: Design](docs/part2-design/)
- [API contract](docs/api-contract/)

## Editing the web consoles

The three consoles and the portal are generated from shared files in `/frontend/console-src/` so they always look and behave the same. Edit those files, then run `python frontend/console-src/build.py`.

## Testing on GitHub

- **Automatic tests (GitHub Actions):** `.github/workflows/tests.yml` runs on every push. It runs the unit tests of the three services, then starts all three and runs the Postman collection end to end. Results are on the repository's **Actions** tab.
- **Run the app in the browser (GitHub Codespaces):** on the repository page choose **Code → Codespaces → Create codespace on main**. When it has opened, run `./start_all.sh` in the terminal, open the **Ports** tab and open port 8001 (add `/ui` to the address). To see the green status dots and use **Switch console**, right-click each port (8001, 8002, 8003) → **Port Visibility → Public**.
