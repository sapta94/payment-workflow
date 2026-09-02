from fastapi import FastAPI
from pydantic import BaseModel
from decimal import Decimal
import asyncio
import uuid


app = FastAPI(
    title="Processor B"
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
        "processor": "PROCESSOR_B",
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
        f"[PROCESSOR B] "
        f"Received payment {request.payment_id}"
    )

    await asyncio.sleep(0.8)

    transaction_id = (
        f"PB-{uuid.uuid4()}"
    )

    return PaymentResponse(
        success=True,
        processor="PROCESSOR_B",
        processor_transaction_id=transaction_id,
        status="CAPTURED",
    )