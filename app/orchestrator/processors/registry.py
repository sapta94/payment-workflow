"""Factory for the processor servers configured in PaymentProcessor."""

from app.orchestrator.processors.base import PaymentProcessor
from app.orchestrator.processors.http_processor import HttpPaymentProcessor


class ProcessorRegistry:
    """Build an HTTP client for the selected processor server."""

    def get(self, processor_code: str, base_url: str) -> PaymentProcessor:
        """Return a client for ``POST {base_url}/process-payment``."""
        return HttpPaymentProcessor(
            processor_code=processor_code,
            base_url=base_url,
        )
