import uuid

from app.orchestrator.processors.base import (
    PaymentProcessor,
    ProcessorPaymentRequest,
    ProcessorPaymentResult,
)


class ProcessorA(PaymentProcessor):
    """
    Processor A implementation.

    This is initially a mock processor.
    """

    async def process_payment(
        self,
        request: ProcessorPaymentRequest,
    ) -> ProcessorPaymentResult:

        print(
            f"[Processor A] Processing payment "
            f"{request.payment_id}"
        )

        processor_transaction_id = (
            f"PA-{uuid.uuid4()}"
        )

        return ProcessorPaymentResult(
            success=True,
            processor="PROCESSOR_A",
            processor_transaction_id=(
                processor_transaction_id
            ),
            status="CAPTURED",
        )