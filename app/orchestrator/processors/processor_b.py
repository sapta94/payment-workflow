import uuid

from app.orchestrator.processors.base import (
    PaymentProcessor,
    ProcessorPaymentRequest,
    ProcessorPaymentResult,
)


class ProcessorB(PaymentProcessor):
    """
    Processor B implementation.
    """

    async def process_payment(
        self,
        request: ProcessorPaymentRequest,
    ) -> ProcessorPaymentResult:

        print(
            f"[Processor B] Processing payment "
            f"{request.payment_id}"
        )

        processor_transaction_id = (
            f"PB-{uuid.uuid4()}"
        )

        return ProcessorPaymentResult(
            success=True,
            processor="PROCESSOR_B",
            processor_transaction_id=(
                processor_transaction_id
            ),
            status="CAPTURED",
        )