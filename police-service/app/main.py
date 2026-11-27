"""Police Service (port 8001), part of the Eswatini Justice Administration system.

Run (from the police-service folder):
    uvicorn main:app --port 8001 --reload
(The factory form also works: uvicorn app.main:create_app --factory --port 8001)
"""
import logging
import os
import time
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import IntegrityError
from starlette.exceptions import HTTPException as StarletteHTTPException

from .config import DEV_SECRET, Settings
from .database import Base, add_missing_columns, make_engine, make_session_factory
from .errors import AppError
from .judiciary_client import CorrectionalClient, JudiciaryClient
from .repository import PoliceRepository
from .routers import audit, auth, police
from .seed import seed_demo_users, seed_sample_cases

log = logging.getLogger("police.http")

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")

HTTP_ERROR_CODES = {
    404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED", 401: "UNAUTHORIZED", 403: "FORBIDDEN",
}


def error_body(code: str, message: str) -> dict:
    return {"error": code, "message": message}


def create_app(
    settings: Optional[Settings] = None,
    judiciary: Optional[JudiciaryClient] = None,
    correctional: Optional[CorrectionalClient] = None,
) -> FastAPI:
    settings = settings or Settings.from_env()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    if settings.jwt_secret == DEV_SECRET:
        logging.getLogger("police").warning(
            "Using the development JWT secret. Set JWT_SECRET (same value in all three services).")

    engine = make_engine(settings.database_url)
    import app.models  # noqa: F401  (registers the tables on Base)
    Base.metadata.create_all(engine)
    add_missing_columns(engine)
    session_factory = make_session_factory(engine)

    with session_factory() as db:
        repo = PoliceRepository(db)
        if settings.seed_demo_users:
            if not settings.demo_password:
                raise RuntimeError("SEED_DEMO_USERS is on but DEMO_PASSWORD is not set")
            seed_demo_users(repo, settings.demo_password, settings.bcrypt_rounds)
        if settings.seed_sample_cases:
            seed_sample_cases(repo)

    app = FastAPI(
        title="Police Service",
        version="1.0.0",
        description="Suspects, arrests, cases, charges and referral to the Judiciary.",
    )
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.judiciary = judiciary or JudiciaryClient(settings.judiciary_url, settings.request_timeout)
    app.state.correctional = correctional or CorrectionalClient(
        settings.correctional_url, settings.request_timeout)

    # the browser consoles of the other services call us from another origin/port
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

    app.include_router(auth.router)
    app.include_router(police.router)
    app.include_router(audit.router)

    # ----- one error format for every failure (design 9.2) -----
    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError):
        headers = {"WWW-Authenticate": "Bearer"} if exc.status_code == 401 else None
        return JSONResponse(error_body(exc.code, exc.message), status_code=exc.status_code, headers=headers)

    @app.exception_handler(RequestValidationError)
    async def handle_validation(request: Request, exc: RequestValidationError):
        parts = []
        for err in exc.errors():
            loc = ".".join(str(p) for p in err["loc"][1:]) or str(err["loc"][0])
            parts.append(f"{loc}: {err['msg']}")
        return JSONResponse(error_body("VALIDATION_ERROR", "; ".join(parts)), status_code=400)

    @app.exception_handler(StarletteHTTPException)
    async def handle_http(request: Request, exc: StarletteHTTPException):
        code = HTTP_ERROR_CODES.get(exc.status_code, "HTTP_ERROR")
        return JSONResponse(error_body(code, str(exc.detail)), status_code=exc.status_code)

    @app.exception_handler(IntegrityError)
    async def handle_integrity(request: Request, exc: IntegrityError):
        return JSONResponse(
            error_body("CONFLICT", "The record conflicts with an existing record; please retry"),
            status_code=409,
        )

    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        ms = (time.perf_counter() - start) * 1000
        log.info("%s %s -> %s (%.0f ms)", request.method, request.url.path, response.status_code, ms)
        return response

    # ----- police officer web console (served by this service) -----
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/ui", include_in_schema=False)
    def ui():
        return FileResponse(os.path.join(STATIC_DIR, "index.html"))

    @app.get("/", include_in_schema=False)
    def root():
        return {"service": "Police Service", "port": 8001, "status": "running", "ui": "/ui", "docs": "/docs"}

    return app
