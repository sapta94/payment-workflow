from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user_id
from app.core.encryption import encrypt_bank_numbers
from app.database.base import get_db, get_vault_db
from app.database.models import Merchant, User, UserType, MerchantBank
from app.core.encryption import encrypt_pan


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

class MerchantBankRequest(BaseModel):
    """
    Request body used when a merchant submits their
    bank and tax information.

    merchant_id is intentionally NOT part of the request.
    It is obtained from the authenticated user/JWT.
    """

    tin: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Merchant tax identification number",
    )

    bank_account: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Merchant bank account number",
    )

    routing_number: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Merchant bank routing number",
    )


class MerchantBankResponse(BaseModel):
    """
    Response returned after successfully saving
    merchant bank details.

    Sensitive values are intentionally NOT returned.
    """

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

@router.post(
    "/bank-details",
    response_model=MerchantBankResponse,
    status_code=status.HTTP_201_CREATED,
)
async def save_bank_details(
    bank_details: MerchantBankRequest,
    current_user: Annotated[int,Depends(get_current_user_id)],
    vault_db: Annotated[AsyncSession,Depends(get_vault_db)],
) -> MerchantBankResponse:
    """
    Save encrypted bank details for the authenticated merchant.

    Flow:

        1. Authenticate user using JWT.
        2. Get merchant_id from authenticated user.
        3. Check whether bank details already exist.
        4. Encrypt TIN.
        5. Encrypt bank account number.
        6. Encrypt routing number.
        7. Store encrypted values in MerchantBank.
        8. Never return sensitive values.

    The client does NOT provide merchant_id.
    """

    # ---------------------------------------------------------
    # 1. Get merchant ID from the authenticated user
    # ---------------------------------------------------------
    merchant_id = int(current_user)

    # ---------------------------------------------------------
    # 2. Check whether bank details already exist
    #
    # Since merchant_id is the PRIMARY KEY in MerchantBank,
    # a merchant can have only one bank-details record.
    # ---------------------------------------------------------

    existing_details = await vault_db.scalar(
        select(MerchantBank).where(
            MerchantBank.merchant_id == merchant_id
        )
    )

    if existing_details is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Bank details already exist for this merchant.",
        )

    # ---------------------------------------------------------
    # 3. Encrypt TIN
    # ---------------------------------------------------------

    encrypted_tin = encrypt_bank_numbers(
        bank_details.tin
    )

    # ---------------------------------------------------------
    # 4. Encrypt bank account number
    # ---------------------------------------------------------

    encrypted_bank_account = encrypt_bank_numbers(
        bank_details.bank_account
    )

    # ---------------------------------------------------------
    # 5. Encrypt routing number
    # ---------------------------------------------------------

    encrypted_routing_number = encrypt_bank_numbers(
        bank_details.routing_number
    )

    # ---------------------------------------------------------
    # 6. Create MerchantBank database object
    #
    # merchant_id is NOT encrypted.
    #
    # It is used as the primary key and is obtained from
    # the authenticated user.
    # ---------------------------------------------------------

    merchant_bank = MerchantBank(
        merchant_id=merchant_id,

        encrypted_tin=encrypted_tin,

        encrypted_bank_account=encrypted_bank_account,

        encrypted_routing_number=encrypted_routing_number,

        created_at=datetime.now(timezone.utc),

        updated_at=datetime.now(timezone.utc),
    )

    # ---------------------------------------------------------
    # 7. Add object to database session
    # ---------------------------------------------------------

    vault_db.add(merchant_bank)

    # ---------------------------------------------------------
    # 8. Commit transaction
    # ---------------------------------------------------------

    await vault_db.commit()

    # ---------------------------------------------------------
    # 9. Return safe response
    #
    # NEVER return:
    #
    #   encrypted_tin
    #   encrypted_bank_account
    #   encrypted_routing_number
    #
    # The API only confirms that the information was stored.
    # ---------------------------------------------------------

    return MerchantBankResponse(
        merchant_id=merchant_id,
        message="Merchant bank details saved successfully.",
    )