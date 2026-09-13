import asyncio

from app.core.config import get_settings
from app.messaging.kafka_producer import KafkaProducer
from app.messaging.outbox_publisher import OutboxPublisher


async def main() -> None:

    settings = get_settings()

    producer = KafkaProducer(
        settings.kafka_bootstrap_servers
    )

    await producer.start()

    try:

        publisher = OutboxPublisher(
            kafka_producer=producer,
            poll_interval=2.0,
            batch_size=100,
        )

        await publisher.run()

    finally:
        await producer.stop()


if __name__ == "__main__":
    asyncio.run(main())