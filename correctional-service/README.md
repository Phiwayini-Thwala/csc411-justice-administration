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
├── auth.py
├── database.py
├── main.py
├── requirements.txt
├── test_flow.py
├── .env.example
├── .gitignore
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

Start the Correctional Service API using:

```powershell
uvicorn main:app --port 8003 --reload
```

The application will run locally at:

```text
http://127.0.0.1:8003
```

### API Documentation

FastAPI provides interactive API documentation through Swagger UI.

Open the following address in your browser:

```text
http://127.0.0.1:8003/docs
```

Swagger UI can be used to view, test, and interact with the available API endpoints.

## 8. Main Functionalities

The Correctional Service Microservice supports the following operations:

1. **Authentication:** Allows authorized users to access protected API endpoints.
2. **Inmate Admission:** Records individuals admitted into the correctional system.
3. **Inmate Status Management:** Supports updates to inmate statuses, including REMAND and CONVICTED.
4. **Facility Transfers:** Records transfers between correctional facilities.
5. **Inmate Release:** Supports the release of inmates using authorized release reasons, including court orders.
6. **Audit Logging:** Records important activities performed within the system for accountability and tracking.

## 9. Testing

The project includes a test file named `test_flow.py`.

The main workflow tested includes:

- User authentication.
- Inmate admission.
- Updating an inmate's status.
- Transferring an inmate to another correctional facility.
- Releasing an inmate using a court order.
- Retrieving audit logs.

## 10. Integration with Other Microservices

The Correctional Service Microservice forms part of the larger Justice Administration System, which includes:

- Police Service
- Judiciary Service
- Correctional Service

It is intended to work with the other services through REST API communication and shared authentication.

Integration testing with the Police and Judiciary microservices will be performed as part of the overall group project.

## 11. Academic Information

**Course:** CSC411 – Integrative Programming Technologies  
**Project:** Justice Administration System  
**Component:** Correctional Service Microservice  
**Institution:** University of Eswatini (UNESWA)

## 12. Repository

GitHub Repository:

https://github.com/Phiwayini-Thwala/csc411-justice-administration
