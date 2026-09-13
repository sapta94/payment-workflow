import json

from aiokafka import AIOKafkaProducer


class KafkaProducer:

    def __init__(self, bootstrap_servers: str):
        self.producer = AIOKafkaProducer(
            bootstrap_servers=bootstrap_servers
        )

    async def start(self) -> None:
        await self.producer.start()

    async def stop(self) -> None:
        await self.producer.stop()

    async def publish(
        self,
        topic: str,
        key: str,
        value: dict,
    ) -> None:

        await self.producer.send_and_wait(
            topic=topic,
            key=key.encode("utf-8"),
            value=json.dumps(value).encode("utf-8"),
        )