"""
TieredPricing — different price per unit depending on the tier the quantity falls into.

This is the "cumulative" / "stacked" tier model, NOT the "volume" model:
    Tiers: [(0, 1000, ₹2.00), (1000, 5000, ₹1.50), (5000, None, ₹1.00)]
    Quantity = 6000:
        First 1000 units  @ ₹2.00 = ₹2000
        Next  4000 units  @ ₹1.50 = ₹6000
        Last  1000 units  @ ₹1.00 = ₹1000
        ------------------------------------
        Total                     = ₹9000

A tier with `to_units = None` is the open-ended top tier.

Tier boundaries are HALF-OPEN on the right: a tier (from, to, price)
covers units strictly less than `to` (i.e. [from, to)).
"""

from dataclasses import dataclass
from typing import Optional

from billing_engine.money import Money
from billing_engine.pricing.base import PricingStrategy


@dataclass(frozen=True)
class Tier:
    from_units: int
    to_units: Optional[int]   # None means "unlimited" / open-ended
    unit_price: Money


class TieredPricing(PricingStrategy):
    def __init__(self, tiers):
        if len(tiers) == 0:
            raise ValueError("Tier list cannot be empty")

        # Top tier must be open ended
        if tiers[-1].to_units is not None:
            raise ValueError("Top tier must be open ended")

        # Tiers must be contiguous
        for i in range(len(tiers) - 1):
            if tiers[i + 1].from_units != tiers[i].to_units:
                raise ValueError("Tiers must be contiguous")

        # Only last tier can have to_units = None
        for i in range(len(tiers) - 1):
            if tiers[i].to_units is None:
                raise ValueError("Only last tier can have to_units=None")

        # All tiers must use same currency
        currency = tiers[0].unit_price.currency

        for tier in tiers:
            if tier.unit_price.currency != currency:
                raise ValueError("All tiers must have same currency")

        self.tiers = tiers

    
    def calculate(self, quantity):

        if quantity < 0:
            raise ValueError("Quantity cannot be negative")

        currency = self.tiers[0].unit_price.currency
        total = Money.zero(currency)

        for tier in self.tiers:

            if tier.to_units is None:
                count = max(0, quantity - tier.from_units)

            else:
                if quantity > tier.from_units:
                    count = min(quantity, tier.to_units) - tier.from_units
                else:
                    count = 0

            total = total + (tier.unit_price * count)

        return total