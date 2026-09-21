import asyncio

from app.messaging.webhook_consumer import WebhookConsumer


async def main() -> None:

    consumer = WebhookConsumer()

    await consumer.start()

    try:
        await consumer.run()

    finally:
        await consumer.stop()


if __name__ == "__main__":
    asyncio.run(main())