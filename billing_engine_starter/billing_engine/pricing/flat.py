"""
FlatRate — same charge every period regardless of usage.

Example: ₹999/month subscription, no matter how much the customer uses.
"""

from billing_engine.money import Money
from billing_engine.pricing.base import PricingStrategy


class FlatRate(PricingStrategy):
    def __init__(self, amount):

        if not isinstance(amount, Money):
            raise TypeError("amount must be Money")

        if amount.is_negative():
            raise ValueError("amount cannot be negative")

        self.amount = amount

    def calculate(self, quantity):
        return self.amount

