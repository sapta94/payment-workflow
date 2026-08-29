from app.orchestrator.processors.base import (
    ProcessorPaymentRequest,
    ProcessorPaymentResult,
)
from app.orchestrator.processors.registry import ProcessorRegistry
from app.orchestrator.router import PaymentRouter


class PaymentOrchestrator:
    """
    Coordinates payment execution.

    Responsibilities:

        1. Ask router which processor to use.
        2. Get processor from registry.
        3. Send normalized request.
        4. Receive normalized result.
        5. Return result to payment service.
    """

    def __init__(self):

        self.router = PaymentRouter()

        self.registry = ProcessorRegistry()

    async def process_payment(
        self,
        request: ProcessorPaymentRequest,
    ) -> ProcessorPaymentResult:

        # ---------------------------------------------
        # Ask smart routing engine
        # ---------------------------------------------

        decision = self.router.select_processor(
            amount=request.amount,
            currency=request.currency,
            merchant_id=request.merchant_id,
        )

        print(
            f"Routing payment "
            f"{request.payment_id} "
            f"to {decision.processor}"
        )

        print(
            f"Routing reason: {decision.reason}"
        )

        # ---------------------------------------------
        # Get selected processor
        # ---------------------------------------------

        processor = self.registry.get(
            decision.processor
        )

        # ---------------------------------------------
        # Execute payment
        # ---------------------------------------------

        result = await processor.process_payment(
            request
        )

        # ---------------------------------------------
        # Return normalized result
        # ---------------------------------------------

        return result
