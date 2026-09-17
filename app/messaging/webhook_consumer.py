import json

from aiokafka import AIOKafkaConsumer
from sqlalchemy import select

from app.core.config import get_settings
from app.database.base import AsyncSessionLocal
from app.database.models import Merchant
from app.messaging.webhook_client import call_merchant_webhook


class WebhookConsumer:

    def __init__(self):

        settings = get_settings()

        self.consumer = AIOKafkaConsumer(
            "payment-events",

            bootstrap_servers=settings.kafka_bootstrap_servers,

            group_id="merchant-webhook-consumer",

            enable_auto_commit=False,

            auto_offset_reset="earliest",
        )

    async def start(self) -> None:
        await self.consumer.start()

    async def stop(self) -> None:
        await self.consumer.stop()

    async def run(self) -> None:
        async for message in self.consumer:
            event = json.loads(
                message.value.decode("utf-8")
            )

            await self.process_event(event)

            await self.consumer.commit()

    async def process_event(
        self,
        event: dict,
    ) -> None:

        payload = event["payload"]

        merchant_id = payload["merchant_id"]

        async with AsyncSessionLocal() as db:

            merchant = await db.scalar(
                select(Merchant).where(
                    Merchant.merchant_id == merchant_id
                )
            )

        if merchant is None:
            raise ValueError(
                f"Merchant {merchant_id} not found"
            )

        if not merchant.webhook_url:
            raise ValueError(
                f"Merchant {merchant_id} has no webhook URL"
            )

        webhook_payload = {
            "event_id": event["event_id"],
            "payment_id": payload["payment_id"],
            "merchant_id": payload["merchant_id"],
            "payment_status": payload["status"],
        }

        await call_merchant_webhook(
            webhook_url=merchant.webhook_url,
            payload=webhook_payload,
        )