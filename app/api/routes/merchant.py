from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user_id
from app.database.base import get_db
from app.database.models import Merchant, User, UserType

router = APIRouter()


class CreateMerchantRequest(BaseModel):
    """Business details for the authenticated merchant's profile."""

    model_config = ConfigDict(extra="forbid")

    business_name: Annotated[str, Field(min_length=1, max_length=255)]
    business_address: Annotated[str, Field(min_length=1, max_length=500)]
    city: Annotated[str | None, Field(default=None, max_length=100)]
    state: Annotated[str | None, Field(default=None, max_length=100)]
    country: Annotated[str | None, Field(default=None, max_length=100)]
    postal_code: Annotated[str | None, Field(default=None, max_length=20)]


class CreateMerchantResponse(BaseModel):
    """Response returned after a merchant profile is created."""

    merchant_id: int
    message: str


@router.post(
    "/business-details",
    response_model=CreateMerchantResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_merchant(
    merchant_data: CreateMerchantRequest,
    current_user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CreateMerchantResponse:
    """Create a merchant profile for the authenticated merchant account."""
    merchant_id = int(current_user_id)

    user = await db.get(User, merchant_id)
    if user is None or user.user_type != UserType.MERCHANT:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only merchant accounts can create merchant profiles.",
        )

    existing_merchant = await db.scalar(
        select(Merchant).where(Merchant.merchant_id == merchant_id),
    )
    if existing_merchant is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A merchant profile already exists for this account.",
        )

    merchant = Merchant(
        merchant_id=merchant_id,
        business_name=merchant_data.business_name,
        business_address=merchant_data.business_address,
        city=merchant_data.city,
        state=merchant_data.state,
        country=merchant_data.country,
        postal_code=merchant_data.postal_code,
    )
    db.add(merchant)

    try:
        await db.commit()
    except Exception:
        await db.rollback()
        raise

    return CreateMerchantResponse(
        merchant_id=merchant.merchant_id,
        message="Merchant profile created successfully.",
    )
