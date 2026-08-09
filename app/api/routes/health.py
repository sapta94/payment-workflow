from datetime import datetime, timezone

from fastapi import APIRouter, status

from app.core.config import get_settings

router = APIRouter()


@router.get("", status_code=status.HTTP_200_OK)
async def health_check() -> dict[str, str]:
    """Return a liveness response for load balancers and monitors."""
    settings = get_settings()
    return {
        "status": "ok",
        "service": settings.app_name,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/ready", status_code=status.HTTP_200_OK)
async def readiness_check() -> dict[str, str]:
    """Return readiness status; add dependency checks here as the service grows."""
    return {"status": "ready"}
