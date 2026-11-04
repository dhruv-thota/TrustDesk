from __future__ import annotations

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from trustdesk.core.database import get_db
from trustdesk.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/health", tags=["Health"])


@router.get(
    "",
    summary="Application Health Check",
    description="Verifies database connectivity and server responsiveness.",
    responses={
        status.HTTP_200_OK: {
            "description": "System and database are healthy",
            "content": {"application/json": {"example": {"status": "healthy", "database": "connected"}}},
        },
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "description": "Database is unreachable",
            "content": {"application/json": {"example": {"status": "unhealthy", "database": "disconnected"}}},
        },
    },
)
def health_check(session: Session = Depends(get_db)) -> JSONResponse:
    """Performs a lightweight ping against the primary database."""
    try:
        session.execute(text("SELECT 1"))
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"status": "healthy", "database": "connected"},
        )
    except Exception as exc:
        logger.error("Health check database ping failed: %s", exc)
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "unhealthy", "database": "disconnected"},
        )

