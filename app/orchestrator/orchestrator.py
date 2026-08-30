"""Payment orchestration with ranked processor failover."""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.orchestrator.processors.base import (
    ProcessorPaymentRequest,
    ProcessorPaymentResult,
)
from app.orchestrator.processors.registry import ProcessorRegistry
from app.orchestrator.router import PaymentRouter

logger = logging.getLogger(__name__)


class PaymentOrchestrator:
    """Rank eligible processor servers and execute them in failover order."""

    def __init__(self) -> None:
        self.router = PaymentRouter()
        self.registry = ProcessorRegistry()

    async def process_payment(
        self,
        request: ProcessorPaymentRequest,
        db: AsyncSession,
    ) -> ProcessorPaymentResult:
        """Try each ranked processor until one successfully captures payment."""
        candidates = await self.router.rank_processors(db, request)
        if not candidates:
            return ProcessorPaymentResult(
                success=False,
                processor=None,
                processor_transaction_id=None,
                status="FAILED",
                error_code="NO_ELIGIBLE_PROCESSOR",
                error_message="No active processor supports this payment context.",
            )

        # This is the scored [A, B, C] execution list used for failover.
        logger.info(
            "Payment %s failover order: %s",
            request.payment_id,
            [candidate.processor_code for candidate in candidates],
        )

        last_failure: ProcessorPaymentResult | None = None
        for candidate in candidates:
            logger.info(
                "Trying processor %s for payment %s (score=%s, reason=%s)",
                candidate.processor_code,
                request.payment_id,
                candidate.score,
                candidate.reason,
            )
            processor = self.registry.get(candidate.processor_code, candidate.base_url)
            result = await processor.process_payment(request)
            if result.success:
                return result
            last_failure = result

        # Every eligible processor failed, so the Payment record receives the
        # final normalized failure response.
        return last_failure or ProcessorPaymentResult(
            success=False,
            processor=None,
            processor_transaction_id=None,
            status="FAILED",
            error_code="PROCESSOR_ERROR",
            error_message="No processor completed the payment.",
        )
