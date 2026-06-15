"""
VATCalculator — single-rate VAT (e.g. 19% in Germany).
"""

from decimal import Decimal

from billing_engine.money import Money
from billing_engine.taxes.base import TaxCalculator, TaxContext, TaxBreakdown


class VATCalculator(TaxCalculator):
    def __init__(self, rate: Decimal) -> None:
         # Reject float
        if isinstance(rate, float):
            raise TypeError("rate must be Decimal, not float")
        
        # Require Decimal in [0, 1]
        if not isinstance(rate, Decimal):
            raise TypeError("rate must be a Decimal")

        if not (Decimal("0") <= rate <= Decimal("1")):
            raise ValueError("rate must be between 0 and 1 inclusive")
        self.rate = rate

    def apply(self, taxable: Money, context: TaxContext) -> TaxBreakdown:
         # Calculate VAT amount
        vat = taxable * self.rate

        # Format label exactly as specified
        label = f"VAT {self.rate * 100}%"

        # Return TaxBreakdown
        return TaxBreakdown(components=[(label, vat)], total=vat)
