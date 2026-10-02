"""Read-only analytics endpoints for processor operations."""

import asyncio
from datetime import datetime, timedelta
from typing import Annotated
from urllib.parse import urlsplit

import httpx
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user_id
from app.database.base import get_db
from app.database.models import Payment, PaymentProcessor, ProcessorMetrics

router = APIRouter()


class ProcessorAnalytics(BaseModel):
    """Current health and aggregate routing performance for one processor."""

    processor_code: str
    processor_name: str
    is_active: bool
    health_status: str
    total_routed: int
    successful_payments: int
    failed_payments: int
    success_percentage: float
    failure_percentage: float
    average_latency_ms: int | None


class TrafficPoint(BaseModel):
    """One day of total and processor-specific payment traffic."""

    date: str
    total_payments: int
    processors: dict[str, int]


class AnalyticsOverviewResponse(BaseModel):
    """Data used by the operations dashboard."""

    generated_at: datetime
    total_routed: int
    total_successful_payments: int
    total_failed_payments: int
    success_percentage: float
    failure_percentage: float
    processors: list[ProcessorAnalytics]
    traffic: list[TrafficPoint]


async def _check_processor_health(
    client: httpx.AsyncClient,
    processor: PaymentProcessor,
) -> str:
    """Return a live health label without sending payment information."""
    if not processor.is_active:
        return "INACTIVE"

    parsed_url = urlsplit(processor.base_url)
    if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
        return "UNHEALTHY"

    try:
        response = await client.get(f"{processor.base_url.rstrip('/')}/health")
        payload = response.json()
    except (httpx.HTTPError, ValueError):
        return "UNHEALTHY"

    if response.is_success and isinstance(payload, dict) and payload.get("status") == "HEALTHY":
        return "HEALTHY"
    return "UNHEALTHY"


@router.get("/overview", response_model=AnalyticsOverviewResponse)
async def get_analytics_overview(
    _: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[AsyncSession, Depends(get_db)],
    days: Annotated[int, Query(ge=1, le=90)] = 14,
) -> AnalyticsOverviewResponse:
    """Return processor health, aggregate outcomes, and daily traffic.

    ``ProcessorMetrics`` counts every routing attempt, including failed
    processors before a failover. The traffic chart uses final ``Payment``
    records because that table contains the payment creation timestamp.
    """
    processors = (
        await db.scalars(
            select(PaymentProcessor).order_by(PaymentProcessor.base_priority),
        )
    ).all()

    metric_rows = await db.execute(
        select(
            ProcessorMetrics.processor_id,
            func.coalesce(func.sum(ProcessorMetrics.total_transactions), 0).label("total"),
            func.coalesce(
                func.sum(ProcessorMetrics.successful_transactions),
                0,
            ).label("successful"),
            func.coalesce(func.sum(ProcessorMetrics.failed_transactions), 0).label("failed"),
            func.coalesce(
                func.sum(
                    ProcessorMetrics.average_latency_ms
                    * ProcessorMetrics.total_transactions,
                ),
                0,
            ).label("latency_weighted_total"),
        ).group_by(ProcessorMetrics.processor_id),
    )
    metrics_by_processor = {
        row.processor_id: row
        for row in metric_rows
    }

    # Health requests run concurrently and contain no customer/payment data.
    async with httpx.AsyncClient(timeout=httpx.Timeout(2.0)) as client:
        health_statuses = await asyncio.gather(
            *[_check_processor_health(client, processor) for processor in processors],
        )

    processor_analytics: list[ProcessorAnalytics] = []
    total_routed = 0
    total_successful = 0
    total_failed = 0
    for processor, health_status in zip(processors, health_statuses):
        metrics = metrics_by_processor.get(processor.processor_id)
        total = int(metrics.total) if metrics else 0
        successful = int(metrics.successful) if metrics else 0
        failed = int(metrics.failed) if metrics else 0
        average_latency = (
            round(int(metrics.latency_weighted_total) / total)
            if metrics and total
            else None
        )
        success_percentage = round((successful / total) * 100, 2) if total else 0.0
        failure_percentage = round((failed / total) * 100, 2) if total else 0.0

        total_routed += total
        total_successful += successful
        total_failed += failed
        processor_analytics.append(
            ProcessorAnalytics(
                processor_code=processor.processor_code,
                processor_name=processor.processor_name,
                is_active=processor.is_active,
                health_status=health_status,
                total_routed=total,
                successful_payments=successful,
                failed_payments=failed,
                success_percentage=success_percentage,
                failure_percentage=failure_percentage,
                average_latency_ms=average_latency,
            ),
        )

    start_date = datetime.utcnow().date() - timedelta(days=days - 1)
    traffic_rows = await db.execute(
        select(
            func.date(Payment.created_at).label("payment_date"),
            Payment.provider,
            func.count(Payment.payment_id).label("count"),
        )
        .where(Payment.created_at >= start_date)
        .group_by(func.date(Payment.created_at), Payment.provider)
        .order_by(func.date(Payment.created_at)),
    )

    processor_codes = [processor.processor_code for processor in processors]
    daily_traffic = {
        (start_date + timedelta(days=offset)).isoformat(): {
            "total_payments": 0,
            "processors": {processor_code: 0 for processor_code in processor_codes},
        }
        for offset in range(days)
    }
    for row in traffic_rows:
        date_key = row.payment_date.isoformat()
        # The query is date-limited, but retain this guard for a DB timezone
        # that returns a boundary date outside the generated range.
        if date_key not in daily_traffic:
            continue
        count = int(row.count)
        daily_traffic[date_key]["total_payments"] += count
        if row.provider in daily_traffic[date_key]["processors"]:
            daily_traffic[date_key]["processors"][row.provider] += count

    traffic = [
        TrafficPoint(
            date=date_key,
            total_payments=values["total_payments"],
            processors=values["processors"],
        )
        for date_key, values in daily_traffic.items()
    ]
    success_percentage = round((total_successful / total_routed) * 100, 2) if total_routed else 0.0
    failure_percentage = round((total_failed / total_routed) * 100, 2) if total_routed else 0.0

    return AnalyticsOverviewResponse(
        generated_at=datetime.utcnow(),
        total_routed=total_routed,
        total_successful_payments=total_successful,
        total_failed_payments=total_failed,
        success_percentage=success_percentage,
        failure_percentage=failure_percentage,
        processors=processor_analytics,
        traffic=traffic,
    )
