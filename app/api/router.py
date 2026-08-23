from fastapi import APIRouter

from app.api.routes import authentication, health, encryption

api_router = APIRouter()
api_router.include_router(authentication.router, prefix="/auth", tags=["authentication"])
api_router.include_router(encryption.router, prefix="/card-vault", tags=["card_vault"])
api_router.include_router(health.router, prefix="/health", tags=["health"])
