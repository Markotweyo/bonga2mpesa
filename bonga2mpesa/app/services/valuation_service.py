from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class ValuationService:
    """Computes payout amounts and validates profitability."""

    def compute_expected_payout(self, bonga_points: int) -> float:
        """Amount we promise to pay the user."""
        return round(bonga_points * settings.YOUR_RATE, 2)

    def compute_safaricom_inflow(self, bonga_points: int) -> float:
        """Amount Safaricom sends us for the bonga points."""
        return round(bonga_points * settings.SAFARICOM_RATE, 2)

    def is_profitable(
        self,
        safaricom_amount: float,
        payout_amount: float,
        fees: float = 0.0,
    ) -> bool:
        """Ensure we make a profit on this transaction."""
        profit = safaricom_amount - payout_amount - fees
        profitable = profit > 0
        margin = profit / safaricom_amount if safaricom_amount else 0

        logger.info(
            "profitability_check",
            safaricom_amount=safaricom_amount,
            payout_amount=payout_amount,
            fees=fees,
            profit=profit,
            margin=f"{margin:.2%}",
            profitable=profitable,
        )
        return profitable

    def validate_safaricom_amount(
        self,
        bonga_points: int,
        received_amount: float,
        tolerance: float = 0.05,
    ) -> bool:
        """
        Validate amount received matches expected Safaricom conversion.
        Allows ±5% tolerance for rounding differences.
        """
        expected = self.compute_safaricom_inflow(bonga_points)
        diff = abs(received_amount - expected) / expected if expected else 1
        valid = diff <= tolerance

        logger.info(
            "safaricom_amount_validation",
            bonga_points=bonga_points,
            expected=expected,
            received=received_amount,
            diff_pct=f"{diff:.2%}",
            valid=valid,
        )
        return valid
