from app.orchestrator.processors.base import PaymentProcessor
from app.orchestrator.processors.processor_a import ProcessorA
from app.orchestrator.processors.processor_b import ProcessorB
from app.orchestrator.processors.processor_c import  ProcessorC


class ProcessorRegistry:
    """
    Central registry containing all available processors.
    """

    def __init__(self):

        self.processors: dict[
            str,
            PaymentProcessor
        ] = {
            "PROCESSOR_A": ProcessorA(),
            "PROCESSOR_B": ProcessorB(),
            "PROCESSOR_C": ProcessorC()
        }

    def get(
        self,
        processor_name: str,
    ) -> PaymentProcessor:

        processor = self.processors.get(
            processor_name
        )

        if processor is None:
            raise ValueError(
                f"Unknown processor: {processor_name}"
            )

        return processor

    def all(self) -> dict[
        str,
        PaymentProcessor
    ]:

        return self.processors