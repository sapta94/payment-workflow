from datetime import datetime, timezone
from typing import Annotated
from pydantic import BaseModel, ConfigDict, Field, field_validator
from decimal import Decimal

from fastapi import (
    APIRouter,
    Depends,
    Header,
    HTTPException,
    status,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Payment, PaymentMethod
from app.database.models import Merchant

from app.database.base import get_db
from app.core.security import get_current_user_id



router = APIRouter()

class CreatePaymentRequest(BaseModel):
    """Client-supplied values required to start a payment."""

    model_config = ConfigDict(extra="forbid")

    merchant_id: Annotated[int, Field(gt=0)]
    payment_method_id: Annotated[int, Field(gt=0)]
    amount: Annotated[Decimal, Field(gt=0, max_digits=12, decimal_places=2)]
    currency: Annotated[str, Field(min_length=3, max_length=3)]
    idempotency_key: Annotated[str, Field(min_length=1, max_length=100)]

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, value: str) -> str:
        """Normalize and validate an ISO 4217-style alphabetic currency code."""
        currency = value.upper()
        if not currency.isalpha():
            raise ValueError("Currency must contain only letters")
        return currency

class CreatePaymentResponse(BaseModel):
    payment_id: int
    merchant_id: int
    payment_method_id: int
    amount: Decimal
    currency: str
    payment_status: str
    message: str

class FetchPaymentResponse(BaseModel):
    payment_id: int
    user_id: int
    merchant_id: int
    payment_method_id: int
    amount: Decimal
    currency: str
    status: str
    provider: str | None
    provider_payment_id: str | None
    failure_code: str | None
    failure_message: str | None

@router.post(
    "/make-payment",
    response_model=CreatePaymentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_payment(
    payment_request: CreatePaymentRequest,
    current_user: Annotated[int, Depends(get_current_user_id)],
    db: Annotated[AsyncSession,Depends(get_db)],

    idempotency_key: Annotated[
        str,
        Header(...),
    ],
) -> CreatePaymentResponse:
    """
    Create a new payment.

    Current responsibility of this endpoint:

        1. Authenticate customer.
        2. Validate merchant.
        3. Validate payment method.
        4. Ensure payment method belongs to customer.
        5. Check idempotency.
        6. Create Payment record.
        7. Return CREATED payment.
    """

    # =========================================================
    # 1. Validate idempotency key
    # =========================================================

    if not idempotency_key.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Idempotency-Key cannot be empty.",
        )

    # =========================================================
    # 2. Check whether this request was already processed
    #
    # This prevents accidental duplicate payments when a
    # client retries the same request.
    # =========================================================

    existing_payment = await db.scalar(
        select(Payment).where(
            Payment.user_id == current_user,
            Payment.idempotency_key == idempotency_key,
        )
    )

    if existing_payment is not None:

        # Return a 409 Conflict mwith message if idempotency key is already present

        raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Payment already exists for this idempotency key.",
                )

    # =========================================================
    # 3. Verify merchant exists
    # =========================================================

    merchant = await db.scalar(
        select(Merchant).where(
            Merchant.merchant_id
            == payment_request.merchant_id
        )
    )

    if merchant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Merchant not found.",
        )

    # =========================================================
    # 4. Verify payment method belongs to current user
    # =========================================================
   
    payment_method = await db.scalar(
        select(PaymentMethod).where(
            PaymentMethod.id
            == payment_request.payment_method_id,
            PaymentMethod.user_id
            == current_user,
        )
    )

    if payment_method is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment method not found.",
        )

    # =========================================================
    # 5. Create Payment record
    # =========================================================

    payment = Payment(
        user_id=current_user,

        merchant_id=payment_request.merchant_id,

        payment_method_id=payment_request.payment_method_id,

        amount=payment_request.amount,

        currency=payment_request.currency,

        payment_status="CREATED",

        provider=None,

        transaction_id=None,

        idempotency_key=idempotency_key,

        failure_code=None,

        failure_message=None,

        created_at=datetime.now(timezone.utc),

        updated_at=datetime.now(timezone.utc),
    )


    db.add(payment)

    await db.commit()

    await db.refresh(payment)


    return CreatePaymentResponse(
        payment_id=payment.payment_id,
        merchant_id=payment.merchant_id,
        payment_method_id=payment.payment_method_id,
        amount=payment.amount,
        currency=payment.currency,
        payment_status=payment.status,
        message="Payment created successfully.",
    )






