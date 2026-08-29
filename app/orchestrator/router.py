from dataclasses import dataclass
from decimal import Decimal


@dataclass
class RoutingDecision:
    """
    Result produced by the routing engine.
    """

    processor: str

    reason: str


class PaymentRouter:
    """
    Smart routing engine.

    Determines which processor should receive
    the payment.
    """

    def select_processor(
        self,
        amount: Decimal,
        currency: str,
        merchant_id: int,
    ) -> RoutingDecision:

        # ---------------------------------------------
        # Initial routing rules
        # ---------------------------------------------

        if currency == "INR":

            return RoutingDecision(
                processor="PROCESSOR_A",
                reason="INR transaction",
            )
        elif currency in ('EUR','GBP'):
            return RoutingDecision(
                processor="PROCESSOR_B",
                reason="EUR/GBP transaction",
            )
        else:
            return RoutingDecision(
                processor="PROCESSOR_C",
                reason="USD transaction",
            )