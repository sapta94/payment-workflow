from fastapi import FastAPI, status
from pydantic import BaseModel
from decimal import Decimal


app = FastAPI(
    title="Processor A"
)


class MerchantWebhookRequest(BaseModel):
    event_id: str
    payment_id: int
    merchant_id: int
    payment_status: str


class MerchantWebhookResponse(BaseModel):
    order_status: str
    message: str


@app.get("/health")
async def health():
    return {
        "api": "Webhook",
        "status": "HEALTHY"
    }

@app.post("/webhook",
          response_model=MerchantWebhookResponse,
          status_code=status.HTTP_200_OK)
async def merhcant_webhook(
    data : MerchantWebhookRequest
) -> MerchantWebhookResponse:

    if data.payment_status == 'SUCCESS':
        return MerchantWebhookResponse(
            order_status="CREATED",
            message=f"Order Placed Successfully"
        )
    else:
        return MerchantWebhookResponse(
                    order_status="FAILED",
                    message=f"Order not placed due to payment failure"
                )
