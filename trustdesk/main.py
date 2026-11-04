from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException

from trustdesk.api.v1.actions import router as actions_router
from trustdesk.api.v1.drafts import router as drafts_router
from trustdesk.api.v1.health import router as health_router
from trustdesk.api.v1.tickets import router as tickets_router
from trustdesk.api.v1.triage import router as triage_router
from trustdesk.core.config import settings
from trustdesk.core.exceptions import TrustDeskException
from trustdesk.core.logging import configure_logging, get_logger

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager for initialization and cleanup."""
    configure_logging()
    logger.info("TrustDesk application initialized in %s mode.", settings.environment)
    yield
    logger.info("TrustDesk application shutting down.")


app = FastAPI(
    title="TrustDesk API",
    description="AI-Assisted Customer Support Operations Platform",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# Standard Security & CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    """Attach standard security headers to all API responses (docs/architecture.md §5.2)."""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Content-Security-Policy"] = "default-src 'self'"
    return response


@app.exception_handler(TrustDeskException)
async def trustdesk_exception_handler(request: Request, exc: TrustDeskException) -> JSONResponse:
    """Standardized JSON error formatting for domain exceptions."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.error_code,
                "message": exc.message,
                "details": exc.details,
            }
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Standardized JSON error formatting for Pydantic request validation errors."""
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Request validation failed.",
                "details": {"errors": exc.errors()},
            }
        },
    )


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Standardized JSON error formatting for Starlette HTTP exceptions."""
    error_code = "UNAUTHORIZED" if exc.status_code == 401 else (
        "NOT_FOUND" if exc.status_code == 404 else (
            "FORBIDDEN" if exc.status_code == 403 else "HTTP_ERROR"
        )
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": error_code,
                "message": str(exc.detail),
                "details": {},
            }
        },
    )


@app.exception_handler(OperationalError)
async def database_operational_exception_handler(request: Request, exc: OperationalError) -> JSONResponse:
    """Standardized JSON error formatting when database is unreachable or connection drops."""
    logger.error("Database connection failure encountered: %s", exc)
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={
            "error": {
                "code": "DATABASE_UNAVAILABLE",
                "message": "Primary database service is unreachable.",
                "details": {},
            }
        },
    )


# Register API Routers
app.include_router(health_router, prefix="/api/v1")
app.include_router(tickets_router, prefix="/api/v1")
app.include_router(triage_router, prefix="/api/v1")
app.include_router(drafts_router, prefix="/api/v1")
app.include_router(actions_router, prefix="/api/v1")


@app.get("/", include_in_schema=False)
def root_redirect() -> dict[str, str]:
    """Root endpoint providing service status."""
    return {
        "service": "TrustDesk API",
        "version": "0.1.0",
        "status": "online",
        "docs": "/docs",
    }
