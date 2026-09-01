"""Payment orchestration with ranked processor failover."""

import logging
from time import perf_counter

from sqlalchemy import func
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import ProcessorMetrics
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
            started_at = perf_counter()
            result = await processor.process_payment(request)
            latency_ms = round((perf_counter() - started_at) * 1_000)
            await self._record_processor_metrics(
                db=db,
                processor_id=candidate.processor_id,
                request=request,
                success=result.success,
                latency_ms=latency_ms,
            )
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

    async def _record_processor_metrics(
        self,
        db: AsyncSession,
        processor_id: int,
        request: ProcessorPaymentRequest,
        success: bool,
        latency_ms: int,
    ) -> None:
        """Atomically add the outcome of one processor attempt to its metrics.

        The unique metric key is processor + card network + geography +
        currency.  MySQL's upsert keeps concurrent payment attempts from
        losing increments while recalculating success rate and average latency.
        Metrics are operational telemetry: a metrics write failure is logged
        but never changes the payment result already returned by a processor.
        """
        successful_increment = 1 if success else 0
        failed_increment = 0 if success else 1
        new_total = ProcessorMetrics.total_transactions + 1
        new_successful = ProcessorMetrics.successful_transactions + successful_increment

        statement = mysql_insert(ProcessorMetrics).values(
            processor_id=processor_id,
            card_network=request.card_network,
            geography=request.geography,
            currency=request.currency,
            total_transactions=1,
            successful_transactions=successful_increment,
            failed_transactions=failed_increment,
            success_rate=100 if success else 0,
            average_latency_ms=latency_ms,
        )
        statement = statement.on_duplicate_key_update(
            total_transactions=new_total,
            successful_transactions=new_successful,
            failed_transactions=ProcessorMetrics.failed_transactions + failed_increment,
            success_rate=func.round((new_successful * 100) / new_total, 2),
            average_latency_ms=func.round(
                (
                    ProcessorMetrics.average_latency_ms
                    * ProcessorMetrics.total_transactions
                    + latency_ms
                )
                / new_total,
            ),
        )

        try:
            await db.execute(statement)
            await db.commit()
        except Exception:
            await db.rollback()
            logger.exception(
                "Could not update metrics for processor %s after payment %s",
                processor_id,
                request.payment_id,
            )
