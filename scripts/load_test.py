"""Opt-in load test runner for the tokenized payment endpoint.

This runner creates real Payment rows and can call processor services. Use it
only against an isolated development/staging environment with test cards.
"""

import argparse
import asyncio
import json
import math
import os
import statistics
import sys
import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from time import perf_counter
from urllib.parse import urlsplit

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

CREATE_TEST_RUNS_TABLE = """
CREATE TABLE IF NOT EXISTS test_runs (
    test_run_id BIGINT NOT NULL AUTO_INCREMENT,
    scenario_id CHAR(36) NOT NULL,
    target_url VARCHAR(500) NOT NULL,
    requested_rps INT NOT NULL,
    duration_seconds INT NOT NULL,
    total_requests INT NOT NULL,
    completed_requests INT NOT NULL,
    http_success_count INT NOT NULL,
    http_error_count INT NOT NULL,
    payment_success_count INT NOT NULL,
    payment_failure_count INT NOT NULL,
    transport_error_count INT NOT NULL,
    achieved_rps DECIMAL(10,2) NOT NULL,
    average_latency_ms DECIMAL(10,2) NOT NULL,
    p50_latency_ms DECIMAL(10,2) NOT NULL,
    p95_latency_ms DECIMAL(10,2) NOT NULL,
    p99_latency_ms DECIMAL(10,2) NOT NULL,
    min_latency_ms DECIMAL(10,2) NOT NULL,
    max_latency_ms DECIMAL(10,2) NOT NULL,
    per_second_metrics JSON NOT NULL,
    started_at DATETIME(6) NOT NULL,
    completed_at DATETIME(6) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (test_run_id),
    KEY idx_test_runs_scenario (scenario_id),
    KEY idx_test_runs_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""

INSERT_TEST_RUN = text(
    """
    INSERT INTO test_runs (
        scenario_id, target_url, requested_rps, duration_seconds,
        total_requests, completed_requests, http_success_count,
        http_error_count, payment_success_count, payment_failure_count,
        transport_error_count, achieved_rps, average_latency_ms,
        p50_latency_ms, p95_latency_ms, p99_latency_ms, min_latency_ms,
        max_latency_ms, per_second_metrics, started_at, completed_at
    ) VALUES (
        :scenario_id, :target_url, :requested_rps, :duration_seconds,
        :total_requests, :completed_requests, :http_success_count,
        :http_error_count, :payment_success_count, :payment_failure_count,
        :transport_error_count, :achieved_rps, :average_latency_ms,
        :p50_latency_ms, :p95_latency_ms, :p99_latency_ms, :min_latency_ms,
        :max_latency_ms, :per_second_metrics, :started_at, :completed_at
    )
    """,
)


@dataclass(frozen=True)
class RequestSample:
    """Outcome and latency of one HTTP request."""

    completed_offset_seconds: float
    latency_ms: float
    http_success: bool
    payment_success: bool
    payment_failure: bool
    transport_error: bool


@dataclass(frozen=True)
class PhaseResult:
    """Metrics persisted for one requested-RPS phase."""

    requested_rps: int
    duration_seconds: int
    total_requests: int
    completed_requests: int
    http_success_count: int
    http_error_count: int
    payment_success_count: int
    payment_failure_count: int
    transport_error_count: int
    achieved_rps: float
    average_latency_ms: float
    p50_latency_ms: float
    p95_latency_ms: float
    p99_latency_ms: float
    min_latency_ms: float
    max_latency_ms: float
    per_second_metrics: list[dict[str, float | int]]
    started_at: datetime
    completed_at: datetime


def build_payment_payloads(arguments: argparse.Namespace) -> list[dict[str, object]]:
    """Build valid, deterministic payment bodies for the chosen test profile.

    ``capability-mix`` deliberately covers the active capability combinations:

    - payment method 2: VISA
    - payment method 3: MASTERCARD

    The API derives the user from the shared JWT; user_id is never sent in a
    body. All profiles use the same merchant supplied on the command line.
    """
    if arguments.request_profile == "single":
        if arguments.payment_method_id is None:
            raise ValueError("--payment-method-id is required for --request-profile single")
        return [
            {
                "merchant_id": arguments.merchant_id,
                "payment_method_id": arguments.payment_method_id,
                "amount": arguments.amount,
                "currency": arguments.currency.upper(),
                "geography": arguments.geography.upper(),
            },
        ]

    # Each of these matches a known active ProcessorCapability tuple. Amounts
    # differ too, so load-test Payment rows represent realistic variation.
    return [
        {
            "merchant_id": arguments.merchant_id,
            "payment_method_id": 2,  # VISA / IN / INR -> processors A, B, C
            "amount": "50000.00",
            "currency": "INR",
            "geography": "IN",
        },
        {
            "merchant_id": arguments.merchant_id,
            "payment_method_id": 3,  # MASTERCARD / IN / INR -> processors A, C
            "amount": "25000.00",
            "currency": "INR",
            "geography": "IN",
        },
        {
            "merchant_id": arguments.merchant_id,
            "payment_method_id": 2,  # VISA / IN / USD -> processor A
            "amount": "10000.00",
            "currency": "USD",
            "geography": "IN",
        },
        {
            "merchant_id": arguments.merchant_id,
            "payment_method_id": 2,  # VISA / US / USD -> processors B, C
            "amount": "5000.00",
            "currency": "USD",
            "geography": "US",
        },
    ]


def parse_rates(value: str) -> list[int]:
    """Parse comma-separated positive request rates."""
    try:
        rates = [int(rate.strip()) for rate in value.split(",")]
    except ValueError as error:
        raise argparse.ArgumentTypeError("Rates must be comma-separated integers") from error
    if not rates or any(rate <= 0 for rate in rates):
        raise argparse.ArgumentTypeError("Every request rate must be greater than zero")
    return rates


def percentile(values: list[float], percent: float) -> float:
    """Return an interpolated percentile from a non-empty latency sample."""
    if not values:
        return 0.0
    ordered = sorted(values)
    index = (len(ordered) - 1) * percent
    lower = math.floor(index)
    upper = math.ceil(index)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (index - lower)


def is_safe_default_target(target_url: str) -> bool:
    """Allow local/Docker service targets without an extra override flag."""
    hostname = urlsplit(target_url).hostname
    return hostname in {"localhost", "127.0.0.1", "::1", "payment-api"}


async def send_payment(
    client: httpx.AsyncClient,
    target_url: str,
    token: str,
    payload: dict[str, object],
    idempotency_key: str,
    phase_started_at: float,
) -> RequestSample:
    """Send one load-test payment and capture a safe, compact outcome."""
    request_started_at = perf_counter()
    try:
        response = await client.post(
            target_url,
            json=payload,
            headers={
                "Authorization": f"Bearer {token}",
                "Idempotency-Key": idempotency_key,
            },
        )
        completed_at = perf_counter()
        http_success = 200 <= response.status_code < 300
        payment_status = ""
        if http_success:
            try:
                response_payload = response.json()
                payment_status = str(response_payload.get("payment_status", ""))
            except ValueError:
                # A 2xx API response with an invalid body remains an HTTP
                # success but is not classified as a payment success/failure.
                pass
        return RequestSample(
            completed_offset_seconds=completed_at - phase_started_at,
            latency_ms=(completed_at - request_started_at) * 1_000,
            http_success=http_success,
            payment_success=payment_status == "SUCCESS",
            payment_failure=payment_status == "FAILED",
            transport_error=False,
        )
    except httpx.HTTPError:
        completed_at = perf_counter()
        return RequestSample(
            completed_offset_seconds=completed_at - phase_started_at,
            latency_ms=(completed_at - request_started_at) * 1_000,
            http_success=False,
            payment_success=False,
            payment_failure=False,
            transport_error=True,
        )


async def run_phase(
    client: httpx.AsyncClient,
    target_url: str,
    token: str,
    payloads: list[dict[str, object]],
    scenario_id: str,
    requested_rps: int,
    duration_seconds: int,
    max_concurrency: int,
) -> PhaseResult:
    """Run an open-loop phase while bounding in-flight requests."""
    total_requests = requested_rps * duration_seconds
    phase_started_wall_time = datetime.utcnow()
    phase_started_at = perf_counter()
    pending: set[asyncio.Task[RequestSample]] = set()
    samples: list[RequestSample] = []

    for request_number in range(total_requests):
        scheduled_at = phase_started_at + (request_number / requested_rps)
        delay = scheduled_at - perf_counter()
        if delay > 0:
            await asyncio.sleep(delay)

        # Keeping a hard cap prevents the driver itself from exhausting local
        # file descriptors or memory when the target becomes slow.
        while len(pending) >= max_concurrency:
            completed, pending = await asyncio.wait(
                pending,
                return_when=asyncio.FIRST_COMPLETED,
            )
            samples.extend(task.result() for task in completed)

        idempotency_key = f"load-{scenario_id}-{requested_rps}-{request_number}-{uuid.uuid4().hex}"
        pending.add(
            asyncio.create_task(
                send_payment(
                    client=client,
                    target_url=target_url,
                    token=token,
                    # Round-robin preserves an even capability distribution
                    # at every load level without relying on random chance.
                    payload=payloads[request_number % len(payloads)],
                    idempotency_key=idempotency_key,
                    phase_started_at=phase_started_at,
                ),
            ),
        )

    if pending:
        samples.extend(await asyncio.gather(*pending))

    phase_completed_at = perf_counter()
    phase_completed_wall_time = datetime.utcnow()
    return summarize_phase(
        requested_rps=requested_rps,
        duration_seconds=duration_seconds,
        total_requests=total_requests,
        samples=samples,
        elapsed_seconds=phase_completed_at - phase_started_at,
        started_at=phase_started_wall_time,
        completed_at=phase_completed_wall_time,
    )


def summarize_phase(
    requested_rps: int,
    duration_seconds: int,
    total_requests: int,
    samples: list[RequestSample],
    elapsed_seconds: float,
    started_at: datetime,
    completed_at: datetime,
) -> PhaseResult:
    """Calculate summary and per-second metrics from individual samples."""
    latencies = [sample.latency_ms for sample in samples]
    buckets: defaultdict[int, list[RequestSample]] = defaultdict(list)
    for sample in samples:
        buckets[int(sample.completed_offset_seconds)].append(sample)

    per_second_metrics = []
    for second in range(max(duration_seconds, max(buckets, default=0) + 1)):
        bucket = buckets[second]
        bucket_latencies = [sample.latency_ms for sample in bucket]
        per_second_metrics.append(
            {
                "second": second + 1,
                "completed_requests": len(bucket),
                "http_error_count": sum(not sample.http_success for sample in bucket),
                "average_latency_ms": round(statistics.fmean(bucket_latencies), 2)
                if bucket_latencies
                else 0.0,
                "p95_latency_ms": round(percentile(bucket_latencies, 0.95), 2),
            },
        )

    http_success_count = sum(sample.http_success for sample in samples)
    transport_error_count = sum(sample.transport_error for sample in samples)
    return PhaseResult(
        requested_rps=requested_rps,
        duration_seconds=duration_seconds,
        total_requests=total_requests,
        completed_requests=len(samples),
        http_success_count=http_success_count,
        http_error_count=len(samples) - http_success_count,
        payment_success_count=sum(sample.payment_success for sample in samples),
        payment_failure_count=sum(sample.payment_failure for sample in samples),
        transport_error_count=transport_error_count,
        achieved_rps=round(len(samples) / elapsed_seconds, 2) if elapsed_seconds else 0.0,
        average_latency_ms=round(statistics.fmean(latencies), 2) if latencies else 0.0,
        p50_latency_ms=round(percentile(latencies, 0.50), 2),
        p95_latency_ms=round(percentile(latencies, 0.95), 2),
        p99_latency_ms=round(percentile(latencies, 0.99), 2),
        min_latency_ms=round(min(latencies), 2) if latencies else 0.0,
        max_latency_ms=round(max(latencies), 2) if latencies else 0.0,
        per_second_metrics=per_second_metrics,
        started_at=started_at,
        completed_at=completed_at,
    )


async def ensure_results_table(engine) -> None:
    """Create the results table when it has not been created yet."""
    async with engine.begin() as connection:
        await connection.execute(text(CREATE_TEST_RUNS_TABLE))


async def store_phase_result(
    engine,
    scenario_id: str,
    target_url: str,
    result: PhaseResult,
) -> None:
    """Persist a phase summary and per-second graph data in ``test_runs``."""
    parameters = {
        "scenario_id": scenario_id,
        "target_url": target_url,
        **result.__dict__,
        "per_second_metrics": json.dumps(result.per_second_metrics),
    }
    async with engine.begin() as connection:
        await connection.execute(INSERT_TEST_RUN, parameters)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run an opt-in payment API load test")
    parser.add_argument(
        "--target-url",
        default=os.getenv(
            "LOAD_TEST_TARGET_URL",
            "http://localhost:8000/api/payment/make-payment",
        ),
    )
    parser.add_argument("--rates", type=parse_rates, default=[100, 500, 1000])
    parser.add_argument("--duration-seconds", type=int, default=10)
    parser.add_argument("--cooldown-seconds", type=int, default=5)
    parser.add_argument("--max-concurrency", type=int, default=2_000)
    parser.add_argument("--merchant-id", type=int, required=True)
    parser.add_argument(
        "--request-profile",
        choices=("capability-mix", "single"),
        default="capability-mix",
        help="Use all valid capability combinations, or one custom body",
    )
    parser.add_argument("--payment-method-id", type=int)
    parser.add_argument("--amount", default="1.00")
    parser.add_argument("--currency", default="INR")
    parser.add_argument("--geography", default="IN")
    parser.add_argument("--timeout-seconds", type=float, default=30.0)
    parser.add_argument("--allow-remote-target", action="store_true")
    parser.add_argument("--confirm-load-test", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser


async def async_main(arguments: argparse.Namespace) -> int:
    """Validate configuration, execute phases, and persist each result."""
    if arguments.duration_seconds <= 0 or arguments.cooldown_seconds < 0:
        raise ValueError("Duration must be positive and cooldown cannot be negative")
    if arguments.max_concurrency <= 0:
        raise ValueError("Max concurrency must be greater than zero")
    if not arguments.allow_remote_target and not is_safe_default_target(arguments.target_url):
        raise ValueError(
            "Refusing a non-local target. Use --allow-remote-target only for "
            "an approved test environment.",
        )

    token = os.getenv("LOAD_TEST_ACCESS_TOKEN")
    database_url = os.getenv("LOAD_TEST_DATABASE_URL") or os.getenv("DATABASE_URL")
    if not token:
        raise ValueError("Set LOAD_TEST_ACCESS_TOKEN to a test user's JWT before running")
    if not database_url:
        raise ValueError("Set LOAD_TEST_DATABASE_URL or DATABASE_URL before running")
    if not arguments.confirm_load_test:
        raise ValueError("Pass --confirm-load-test to create real payment traffic")

    payloads = build_payment_payloads(arguments)
    scenario_id = str(uuid.uuid4())
    print(
        f"Scenario {scenario_id}: {arguments.rates} RPS, "
        f"{arguments.duration_seconds}s per phase, target={arguments.target_url}",
    )
    print("Request profiles (round-robin):")
    for payload in payloads:
        print(f"  {payload}")
    if arguments.dry_run:
        print("Dry run complete. No HTTP requests or database writes were made.")
        return 0

    engine = create_async_engine(database_url, pool_pre_ping=True)
    try:
        await ensure_results_table(engine)
        limits = httpx.Limits(
            max_connections=arguments.max_concurrency,
            max_keepalive_connections=arguments.max_concurrency,
        )
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(arguments.timeout_seconds),
            limits=limits,
        ) as client:
            for phase_number, requested_rps in enumerate(arguments.rates):
                result = await run_phase(
                    client=client,
                    target_url=arguments.target_url,
                    token=token,
                    payloads=payloads,
                    scenario_id=scenario_id,
                    requested_rps=requested_rps,
                    duration_seconds=arguments.duration_seconds,
                    max_concurrency=arguments.max_concurrency,
                )
                await store_phase_result(engine, scenario_id, arguments.target_url, result)
                print(
                    f"{requested_rps} RPS: achieved={result.achieved_rps}, "
                    f"p95={result.p95_latency_ms}ms, errors={result.http_error_count}",
                )
                if phase_number < len(arguments.rates) - 1:
                    await asyncio.sleep(arguments.cooldown_seconds)
    finally:
        await engine.dispose()

    print(
        "Create the visual report with: "
        f"python scripts/generate_load_test_report.py --scenario-id {scenario_id}",
    )
    return 0


def main() -> None:
    arguments = build_parser().parse_args()
    try:
        raise SystemExit(asyncio.run(async_main(arguments)))
    except ValueError as error:
        print(f"Configuration error: {error}", file=sys.stderr)
        raise SystemExit(2) from error


if __name__ == "__main__":
    main()
