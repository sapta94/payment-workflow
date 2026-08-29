from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user_id
from app.database.base import get_db
from app.database.models import Merchant, Payment, PaymentMethod, PaymentStatus
from app.orchestrator.orchestrator import PaymentOrchestrator
from app.orchestrator.processors.base import ProcessorPaymentRequest

router = APIRouter()
payment_orchestrator = PaymentOrchestrator()


class CreatePaymentRequest(BaseModel):
    """Client-supplied values required to start a payment."""

    model_config = ConfigDict(extra="forbid")

    merchant_id: Annotated[int, Field(gt=0)]
    payment_method_id: Annotated[int, Field(gt=0)]
    amount: Annotated[Decimal, Field(gt=0, max_digits=12, decimal_places=2)]
    currency: Annotated[str, Field(min_length=3, max_length=3)]

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, value: str) -> str:
        """Normalize and validate an ISO 4217-style alphabetic currency code."""
        currency = value.upper()
        if not currency.isalpha():
            raise ValueError("Currency must contain only letters")
        return currency


class CreatePaymentResponse(BaseModel):
    """Final, normalized result of a payment attempt."""

    payment_id: int
    merchant_id: int
    payment_method_id: int
    amount: Decimal
    currency: str
    payment_status: PaymentStatus
    provider: str | None
    transaction_id: str | None
    failure_code: str | None
    failure_message: str | None
    message: str


class FetchPaymentResponse(CreatePaymentResponse):
    """Payment details visible only to the user who created the payment."""

    user_id: int


def build_payment_response(payment: Payment, message: str) -> CreatePaymentResponse:
    """Build a public response without exposing the saved card token."""
    return CreatePaymentResponse(
        payment_id=payment.payment_id,
        merchant_id=payment.merchant_id,
        payment_method_id=payment.payment_method_id,
        amount=payment.amount,
        currency=payment.currency,
        payment_status=payment.payment_status,
        provider=payment.provider,
        transaction_id=payment.transaction_id,
        failure_code=payment.failure_code,
        failure_message=payment.failure_message,
        message=message,
    )


@router.post(
    "/make-payment",
    response_model=CreatePaymentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_payment(
    payment_request: CreatePaymentRequest,
    current_user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[AsyncSession, Depends(get_db)],
    idempotency_key: Annotated[str, Header(min_length=1, max_length=100)],
) -> CreatePaymentResponse:
    """Create, route, process, normalize, and persist one payment attempt."""
    user_id = int(current_user_id)

    existing_payment = await db.scalar(
        select(Payment).where(
            Payment.user_id == user_id,
            Payment.idempotency_key == idempotency_key,
        ),
    )
    if existing_payment is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Payment already exists for this idempotency key.",
        )

    merchant = await db.scalar(
        select(Merchant).where(Merchant.merchant_id == payment_request.merchant_id),
    )
    if merchant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Merchant not found.",
        )

    payment_method = await db.scalar(
        select(PaymentMethod).where(
            PaymentMethod.payment_method_id == payment_request.payment_method_id,
            PaymentMethod.user_id == user_id,
        ),
    )
    if payment_method is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment method not found.",
        )

    payment = Payment(
        user_id=user_id,
        merchant_id=payment_request.merchant_id,
        payment_method_id=payment_request.payment_method_id,
        amount=payment_request.amount,
        currency=payment_request.currency,
        payment_status=PaymentStatus.CREATED,
        idempotency_key=idempotency_key,
    )
    db.add(payment)

    try:
        await db.commit()
        await db.refresh(payment)
    except IntegrityError as error:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Payment already exists for this idempotency key.",
        ) from error

    payment.payment_status = PaymentStatus.PROCESSING
    await db.commit()

    processor_request = ProcessorPaymentRequest(
        payment_id=payment.payment_id,
        merchant_id=payment.merchant_id,
        amount=payment.amount,
        currency=payment.currency,
        payment_token=payment_method.token,
    )

    try:
        processor_result = await payment_orchestrator.process_payment(processor_request)
    except Exception:
        payment.payment_status = PaymentStatus.FAILED
        payment.failure_code = "PROCESSOR_ERROR"
        payment.failure_message = "The payment processor could not complete the payment."
        payment.provider = None
        payment.transaction_id = None
        message = "Payment failed."
    else:
        payment.payment_status = (
            PaymentStatus.SUCCESS if processor_result.success else PaymentStatus.FAILED
        )
        payment.provider = processor_result.processor
        payment.transaction_id = processor_result.processor_transaction_id
        payment.failure_code = processor_result.error_code
        payment.failure_message = processor_result.error_message
        message = (
            "Payment completed successfully."
            if processor_result.success
            else "Payment failed."
        )

    try:
        await db.commit()
        await db.refresh(payment)
    except Exception:
        await db.rollback()
        raise

    return build_payment_response(payment, message)


@router.get(
    "/fetch-payment/{payment_id}",
    response_model=FetchPaymentResponse,
    status_code=status.HTTP_200_OK,
)
async def fetch_payment(
    payment_id: int,
    current_user_id: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> FetchPaymentResponse:
    """Return a payment only when it belongs to the authenticated user."""
    user_id = int(current_user_id)
    payment = await db.scalar(
        select(Payment).where(
            Payment.payment_id == payment_id,
            Payment.user_id == user_id,
        ),
    )
    if payment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment not found.",
        )

    return FetchPaymentResponse(
        **build_payment_response(payment, "Payment found.").model_dump(),
        user_id=payment.user_id,
    )
