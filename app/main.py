from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import get_settings
from app.database.base import check_database_connection, close_database_connection

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Manage resources that should start and stop with the application."""
    await check_database_connection()
    try:
        yield
    finally:
        await close_database_connection()


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    debug=settings.debug,
    lifespan=lifespan,
)

if settings.cors_origin_list:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(api_router, prefix=settings.api_v1_prefix)


@app.get("/", include_in_schema=False)
async def root() -> dict[str, str]:
    return {"message": f"Welcome to {settings.app_name}"}
