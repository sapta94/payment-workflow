import asyncio
from datetime import datetime

from sqlalchemy import select

from app.database.models import OutboxEvent


class OutboxPublisher:

    def __init__(
        self,
        db_session_factory,
        kafka_producer,
    ):
        self.db_session_factory = db_session_factory
        self.kafka_producer = kafka_producer
        self.running = False

    async def run(self):

        self.running = True

        while self.running:

            try:
                await self.publish_pending_events()

            except Exception as exc:
                print(
                    f"Outbox publisher error: {exc}"
                )

            await asyncio.sleep(2)

    async def publish_pending_events(self):

        async with self.db_session_factory() as db:

            result = await db.execute(
                select(OutboxEvent)
                .where(
                    OutboxEvent.published_at.is_(None)
                )
                .order_by(
                    OutboxEvent.id
                )
                .limit(100)
            )

            events = result.scalars().all()

            for event in events:

                await self.kafka_producer.publish(
                    topic="payment-events",
                    key=event.event_id,
                    value={
                        "event_id": event.event_id,
                        "event_type": event.event_type,
                        "event_version": event.event_version,
                        "aggregate_type": event.aggregate_type,
                        "aggregate_id": event.aggregate_id,
                        "source": event.source,
                        "occurred_at": event.occurred_at.isoformat(),
                        "payload": event.payload,
                    },
                )

                print(
                    f"Published event {event.event_id} "
                    f"({event.event_type}) "
                    f"for payment {event.aggregate_id}"
                )

                event.published_at = datetime.utcnow()

            await db.commit()

    def stop(self):
        self.running = False