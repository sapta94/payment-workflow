"""Capability-based processor ranking for payment orchestration."""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import (
    PaymentProcessor,
    ProcessorCapability,
    ProcessorMetrics,
)
from app.orchestrator.processors.base import ProcessorPaymentRequest


@dataclass(frozen=True)
class RoutingCandidate:
    """An eligible processor server, including its score and execution rank."""

    processor_code: str
    processor_name: str
    base_url: str
    score: Decimal
    base_priority: int
    success_rate: Decimal
    average_latency_ms: int | None
    reason: str


class PaymentRouter:
    """Hard-filter and rank processors for a specific payment context."""

    # Required formula:
    # 0.20 * card-network + 0.15 * geography + 0.15 * currency
    # + 0.30 * reliability + 0.20 * health.
    MATCH_SCORE = Decimal("100")
    HEALTHY_SCORE = Decimal("100")
    SCORE_PRECISION = Decimal("0.01")

    async def rank_processors(
        self,
        db: AsyncSession,
        request: ProcessorPaymentRequest,
    ) -> list[RoutingCandidate]:
        """Return eligible processor servers in execution/failover order.

        The capability must exactly match card network, geography, and currency.
        Inactive processors and inactive capabilities are removed before scores
        are calculated. A processor with no metrics is retained with a
        conservative 0% reliability score.
        """
        metric_match = and_(
            ProcessorMetrics.processor_id == PaymentProcessor.processor_id,
            ProcessorMetrics.card_network == request.card_network,
            ProcessorMetrics.geography == request.geography,
            ProcessorMetrics.currency == request.currency,
        )
        statement = (
            select(PaymentProcessor, ProcessorMetrics)
            .join(
                ProcessorCapability,
                ProcessorCapability.processor_id == PaymentProcessor.processor_id,
            )
            .outerjoin(ProcessorMetrics, metric_match)
            .where(
                PaymentProcessor.is_active.is_(True),
                ProcessorCapability.is_active.is_(True),
                ProcessorCapability.card_network == request.card_network,
                ProcessorCapability.geography == request.geography,
                ProcessorCapability.currency == request.currency,
            )
        )
        rows = (await db.execute(statement)).all()
        candidates = [
            self._build_candidate(processor, metrics)
            for processor, metrics in rows
        ]

        # A lower numeric base_priority wins only when scores are tied.
        return sorted(
            candidates,
            key=lambda candidate: (
                -candidate.score,
                candidate.base_priority,
                candidate.processor_code,
            ),
        )

    def _build_candidate(
        self,
        processor: PaymentProcessor,
        metrics: ProcessorMetrics | None,
    ) -> RoutingCandidate:
        """Calculate the formula after the hard eligibility filters pass."""
        success_rate = metrics.success_rate if metrics is not None else Decimal("0")
        # Invalid metric data must not artificially improve a processor score.
        success_rate = max(Decimal("0"), min(Decimal("100"), success_rate))

        # Network, geography, and currency each exactly matched in Phase 2.
        # Phase 4 keeps only active rows, so their health score is 100.
        score = (
            Decimal("0.20") * self.MATCH_SCORE
            + Decimal("0.15") * self.MATCH_SCORE
            + Decimal("0.15") * self.MATCH_SCORE
            + Decimal("0.30") * success_rate
            + Decimal("0.20") * self.HEALTHY_SCORE
        ).quantize(self.SCORE_PRECISION, rounding=ROUND_HALF_UP)

        latency = metrics.average_latency_ms if metrics is not None else None
        reason = f"{success_rate:.2f}% success rate + healthy"
        if latency is not None:
            reason = f"{reason} ({latency} ms average latency)"

        return RoutingCandidate(
            processor_code=processor.processor_code,
            processor_name=processor.processor_name,
            base_url=processor.base_url,
            score=score,
            base_priority=processor.base_priority,
            success_rate=success_rate,
            average_latency_ms=latency,
            reason=reason,
        )
