from fastapi import FastAPI
from pydantic import BaseModel
from decimal import Decimal
import asyncio
import uuid


app = FastAPI(
    title="Processor C"
)


class PaymentRequest(BaseModel):
    payment_id: int
    merchant_id: int
    amount: Decimal
    currency: str
    payment_token: str


class PaymentResponse(BaseModel):
    success: bool
    processor: str
    processor_transaction_id: str | None
    status: str
    error_code: str | None = None
    error_message: str | None = None


@app.get("/health")
async def health():

    return {
        "processor": "PROCESSOR_C",
        "status": "HEALTHY"
    }


@app.post(
    "/process-payment",
    response_model=PaymentResponse,
)
async def process_payment(
    request: PaymentRequest,
):

    print(
        f"[PROCESSOR C] "
        f"Received payment {request.payment_id}"
    )

    await asyncio.sleep(1.0)

    transaction_id = (
        f"PC-{uuid.uuid4()}"
    )

    return PaymentResponse(
        success=True,
        processor="PROCESSOR_C",
        processor_transaction_id=transaction_id,
        status="CAPTURED",
    )