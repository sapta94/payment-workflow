"""HTTP adapter for the approved local processor server contract."""

from urllib.parse import urlsplit

import httpx

from app.orchestrator.processors.base import (
    PaymentProcessor,
    ProcessorPaymentRequest,
    ProcessorPaymentResult,
)


class HttpPaymentProcessor(PaymentProcessor):
    """Call a processor's standard ``POST /process-payment`` endpoint."""

    def __init__(self, processor_code: str, base_url: str) -> None:
        self.processor_code = processor_code
        self.base_url = base_url.strip()

    async def process_payment(
        self,
        request: ProcessorPaymentRequest,
    ) -> ProcessorPaymentResult:
        """Send the processor's documented tokenized-payment request body."""
        endpoint = self._endpoint()
        if endpoint is None:
            return self._failure(
                code="PROCESSOR_CONFIGURATION_ERROR",
                message="Processor endpoint is not configured.",
            )

        # This exact body matches processor_servers/*/main.py. Card network
        # and geography are routing-only inputs, not processor API fields.
        payload = {
            "payment_id": request.payment_id,
            "merchant_id": request.merchant_id,
            "amount": str(request.amount),
            "currency": request.currency,
            # This is a vault token, never a PAN or CVV.
            "payment_token": request.payment_token,
        }

        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
                response = await client.post(endpoint, json=payload)
        except httpx.TimeoutException:
            return self._failure(
                code="PROCESSOR_TIMEOUT",
                message="Processor did not respond before the timeout.",
            )
        except httpx.RequestError:
            return self._failure(
                code="PROCESSOR_UNAVAILABLE",
                message="Processor could not be reached.",
            )

        if response.is_error:
            return self._failure(
                code=f"PROCESSOR_HTTP_{response.status_code}",
                message="Processor did not approve the payment.",
            )

        try:
            result = response.json()
        except ValueError:
            return self._failure(
                code="PROCESSOR_INVALID_RESPONSE",
                message="Processor returned an invalid response.",
            )

        if not isinstance(result, dict) or not isinstance(result.get("success"), bool):
            return self._failure(
                code="PROCESSOR_INVALID_RESPONSE",
                message="Processor returned an incomplete response.",
            )

        success = result["success"]
        return ProcessorPaymentResult(
            success=success,
            processor=self.processor_code,
            processor_transaction_id=result.get("processor_transaction_id"),
            status=str(result.get("status") or ("CAPTURED" if success else "FAILED")),
            error_code=None if success else result.get("error_code"),
            error_message=None if success else result.get("error_message"),
        )

    def _endpoint(self) -> str | None:
        """Validate the configured HTTP(S) base URL before calling it."""
        parsed = urlsplit(self.base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return None
        return f"{self.base_url.rstrip('/')}/process-payment"

    def _failure(self, code: str, message: str) -> ProcessorPaymentResult:
        return ProcessorPaymentResult(
            success=False,
            processor=self.processor_code,
            processor_transaction_id=None,
            status="FAILED",
            error_code=code,
            error_message=message,
        )
