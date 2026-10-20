# CSC411 Mini Project: Justice Administration

**University of Eswatini, Department of Computer Science**
Course: Integrative Programming Technologies (CSC411), Instructor: Dr MA Nxumalo

## Overview

This project automates one inter-organizational process: a suspect moving from **Police** to **Judiciary** to **Correctional Services**. Three independent REST services, each with its own database, work together to complete the process.

1. **Police** registers the suspect, records the arrest, creates the case, adds charges and refers the case to court.
2. **Judiciary** receives the case, schedules a hearing, decides bail or remand, and records the verdict and sentence. It then calls the Correctional service to admit the inmate.
3. **Correctional Services** admits the inmate and manages status, transfer and release.

## Architecture

| Service | Port | Database | Folder |
|---|---|---|---|
| Police | 8001 | SQLite (`police.db`) | `/police-service/` |
| Judiciary | 8002 | SQLite (`judiciary.db`) | `/judiciary-service/` |
| Correctional | 8003 | SQLite (`correctional.db`) | `/correctional-service/` |

- **Language and framework:** Python 3.10+ with FastAPI
- **Communication:** REST with JSON (services call each other using the `requests` library)
- **Security:** JWT with role-based access control, plus audit logging
- **API contract:** OpenAPI/Swagger (see `/docs/api-contract/openapi.yaml`)
- **Frontend:** HTML and JavaScript
- **Testing:** Postman

## Project structure

| Path | Contents |
|---|---|
| `/docs/part1-process/` | Part 1: process research, stakeholders, DFD |
| `/docs/part2-design/` | Part 2: requirements, architecture, class diagram |
| `/docs/api-contract/` | OpenAPI contract |
| `/police-service/` | Police service (port 8001) |
| `/judiciary-service/` | Judiciary service (port 8002) |
| `/correctional-service/` | Correctional service (port 8003) |
| `/frontend/` | HTML/JavaScript frontend |
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

2. Install dependencies for each service (repeat for all three folders):

```
   cd police-service
   pip install -r requirements.txt
```

3. Start each service in its own terminal:

```
   cd police-service
   uvicorn main:app --port 8001 --reload

   cd judiciary-service
   uvicorn main:app --port 8002 --reload

   cd correctional-service
   uvicorn main:app --port 8003 --reload
```

4. Open the interactive API docs in a browser:
   - Police: http://localhost:8001/docs
   - Judiciary: http://localhost:8002/docs
   - Correctional: http://localhost:8003/docs

5. Open `/frontend/index.html` in a browser to use the frontend.

> Database files are not stored in the repository. Each service creates and seeds its database with sample data on first start.

## Running the tests

1. Open Postman and import the files in `/tests/postman/` (the collection and the environment).
2. Select the imported environment.
3. Make sure all three services are running.
4. Run the collection with the **Collection Runner**. It tests the full flow: Police, then Judiciary, then Correctional.

## Team contributions

| Member | Name | Student number | GitHub profile | Role |
|---|---|---|---|---|
| 1 |Kwanele Motsa |155307 |https://github.com/kwanelemotsa62-netizen | Process research, diagrams, frontend, report editing |
| 2 |Melody Sylvester | | https://github.com/Melody386 | System design, requirements, OpenAPI contract |
| 3 |Thandinkosi Magagula | | https://github.com| Police service |
| 4 |Sibusiso Maseko |202301241 |https://github.com | Judiciary service |
| 5 | Phiwayini Thwala |202403175 | https://github.com/Phiwayini-Thwala | Correctional service, Postman tests, repository admin, submission |

## Documentation

- [Part 1: Process](docs/part1-process/)
- [Part 2: Design](docs/part2-design/)
- [API contract](docs/api-contract/)
