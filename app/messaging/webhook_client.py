import httpx


async def call_merchant_webhook(
    webhook_url: str,
    payload: dict,
) -> None:

    async with httpx.AsyncClient(
        timeout=10.0
    ) as client:

        response = await client.post(
            webhook_url,
            json=payload,
        )

        response.raise_for_status()