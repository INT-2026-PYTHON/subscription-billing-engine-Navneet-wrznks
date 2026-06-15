"""
FixedAmountDiscount — e.g., flat ₹500 off.

CAPPING RULE: if the fixed amount exceeds the subtotal, return subtotal
(so the discounted total never goes below zero).
"""

from billing_engine.money import Money
from billing_engine.discounts.base import Discount, DiscountContext


class FixedAmountDiscount(Discount):
    def __init__(self, amount: Money) -> None:
        # Validate Money instance
        if not isinstance(amount, Money):
            raise TypeError("amount must be a Money instance")
        
        # Validate non-negative
        if amount.is_negative():
            raise ValueError("amount must be non-negative")
        self.amount = amount

    def apply(self, subtotal: Money, context: DiscountContext) -> Money:
        # amount.currency == subtotal.currency
        if self.amount.currency != subtotal.currency:
            raise ValueError("Currency mismatch")

        return min(self.amount, subtotal)
