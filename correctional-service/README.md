# Correctional Service Microservice

## 1. Project Overview

The Correctional Service Microservice is part of the CSC411 Justice Administration Mini Project developed for the University of Eswatini, Department of Computer Science.

The microservice is designed to support correctional administration by managing inmates after court processing. It provides functionality for inmate admission, status management, transfers between correctional facilities, releases and audit logging.

The service is developed using FastAPI and exposes REST API endpoints that can be accessed by other services within the integrated Justice Administration system.

## 2. Technologies Used

The following technologies are used in the development of this microservice:

- **Python:** Main programming language.
- **FastAPI:** Framework for developing REST APIs.
- **SQLite:** Database used for storing application records.
- **JWT:** Used for authentication and access control.
- **Uvicorn:** ASGI server used to run the application.
- **Git and GitHub:** Version control and collaborative development.
- **Swagger UI:** Used for viewing and testing API endpoints.

## 3. Project Structure

```text
correctional-service/
│
├── main.py
├── auth.py
├── database.py
├── requirements.txt
├── test_flow.py
├── .env.example
├── .gitignore
└── README.md
```

### Main Files

- `main.py`: Contains the FastAPI application and API endpoints.
- `auth.py`: Handles authentication and JWT-related functionality.
- `database.py`: Handles database configuration and operations.
- `requirements.txt`: Lists the Python dependencies required by the application.
- `test_flow.py`: Contains the application flow testing code.
- `.env.example`: Provides an example of the required environment configuration.
- `.gitignore`: Specifies files and directories that should not be uploaded to GitHub.

## 4. Requirements

Before running the application, ensure that you have installed:

- Python 3.10 or later.
- Git.
- Visual Studio Code or another suitable code editor.

## 5. Installation and Setup

### Step 1: Clone the Repository

Clone the shared group repository:

```bash
git clone https://github.com/Phiwayini-Thwala/csc411-justice-administration.git
```

Navigate to the Correctional Service folder:

```bash
cd csc411-justice-administration/correctional-service
```

### Step 2: Create a Virtual Environment

```bash
python -m venv .venv
```

### Step 3: Activate the Virtual Environment

For Windows PowerShell:

```powershell
.venv\Scripts\activate
```

### Step 4: Install Dependencies

```bash
pip install -r requirements.txt
```

## 6. Environment Configuration

The application uses an environment variable for JWT configuration.

Create a `.env` file in the `correctional-service` folder using `.env.example` as a guide.

Example:

```env
JWT_SECRET=your-secure-shared-secret-of-at-least-32-characters
```

**Important:** The JWT secret must match the secret configured in the other participating services. Use the group's agreed secret and keep actual secret values out of GitHub.

## 7. Running the Application

After installing the dependencies and configuring the environment, start the FastAPI server:

```bash
uvicorn main:app --port 8003 --reload
```

The application will be available at:

```text
http://127.0.0.1:8003
```

## 8. API Documentation and Testing

FastAPI automatically provides interactive API documentation through Swagger UI.

Open the following address in your browser:

```text
http://127.0.0.1:8003/docs
```

Swagger UI allows users to view available endpoints, submit requests and inspect responses.

The implemented functionality includes:

- User authentication and login.
- Inmate registration and admission.
- Inmate status updates.
- Transfer of inmates between correctional facilities.
- Inmate release processing.
- Viewing audit logs by authorised administrators.

For protected endpoints, authenticate using the login endpoint and the returned JWT access token.

## 9. Testing

The service has been tested using Swagger UI.

The tested application flow includes:

1. User authentication.
2. Inmate admission.
3. Updating an inmate's status from REMAND to CONVICTED.
4. Transferring an inmate to another correctional facility.
5. Processing an inmate release using a court order.
6. Retrieving audit logs.

## 10. Integration

The Correctional Service is intended to form part of the integrated Justice Administration system involving the Police, Judiciary and Correctional Services.

The service is designed to support the correctional stage of the process after court proceedings. Integration testing with the other participating services is part of the overall group project.

## 11. Project Information

**Institution:** University of Eswatini  
**Department:** Computer Science  
**Programme:** BSc Information Technology  
**Course:** Integrative Programming Technologies  
**Course Code:** CSC411  
**Project:** Justice Administration Mini Project  
**Component:** Correctional Service Microservice

**GitHub Repository:**  
https://github.com/Phiwayini-Thwala/csc411-justice-administration