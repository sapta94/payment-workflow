from fastapi import APIRouter

from app.api.routes import authentication, encryption, health, merchant, payment

api_router = APIRouter()
api_router.include_router(authentication.router, prefix="/auth", tags=["authentication"])
api_router.include_router(encryption.router, prefix="/card-vault", tags=["card_vault"])
api_router.include_router(health.router, prefix="/health", tags=["health"])
api_router.include_router(merchant.router, prefix="/merchant" ,tags=["merchants"])
api_router.include_router(payment.router, prefix="/payment", tags=["payments"])
