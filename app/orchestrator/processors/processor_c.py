import uuid

from app.orchestrator.processors.base import (
    PaymentProcessor,
    ProcessorPaymentRequest,
    ProcessorPaymentResult,
)


class ProcessorC(PaymentProcessor):
    """
    Processor C implementation.
    """

    async def process_payment(
        self,
        request: ProcessorPaymentRequest,
    ) -> ProcessorPaymentResult:

        print(
            f"[Processor C] Processing payment "
            f"{request.payment_id}"
        )

        processor_transaction_id = (
            f"PB-{uuid.uuid4()}"
        )

        return ProcessorPaymentResult(
            success=True,
            processor="PROCESSOR_C",
            processor_transaction_id=(
                processor_transaction_id
            ),
            status="CAPTURED",
        )