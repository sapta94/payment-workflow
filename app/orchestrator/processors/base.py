from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal


@dataclass
class ProcessorPaymentRequest:
    """
    Normalized payment request used internally by
    the orchestration system.
    """

    payment_id: int

    merchant_id: int

    amount: Decimal

    currency: str

    # Routing context only; the processor never receives a PAN or CVV.
    card_network: str

    geography: str

    payment_token: str


@dataclass
class ProcessorPaymentResult:
    """
    Normalized result returned by every processor.
    """

    success: bool

    processor: str | None

    processor_transaction_id: str | None

    status: str

    error_code: str | None = None

    error_message: str | None = None


class PaymentProcessor(ABC):
    """
    Base interface that every processor must implement.
    """

    @abstractmethod
    async def process_payment(
        self,
        request: ProcessorPaymentRequest,
    ) -> ProcessorPaymentResult:
        """
        Execute payment through this processor.
        """
        raise NotImplementedError
