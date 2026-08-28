"""Turn a price gap into estimated money in your pocket.

net = resale - eBay final-value fee - payment/fixed - outbound shipping
      - packaging - what you pay the shop (incl. its shipping)
"""
from __future__ import annotations

from dataclasses import dataclass, fields
from typing import Optional


@dataclass
class Economics:
    ebay_fee_pct: float = 0.12          # eBay.de final value fee, toys/games ballpark
    ebay_fee_fixed: float = 0.35        # per-order fixed component
    outbound_ship_eur: float = 6.50     # what it costs you to post the box (flat default)
    outbound_ship_big_eur: float = 10.49
    big_threshold_eur: float = 120.0    # sets pricier than this ship in a bigger box
    packaging_eur: float = 1.00

    @classmethod
    def from_dict(cls, d: dict | None) -> "Economics":
        d = dict(d or {})
        allowed = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in allowed})

    def outbound(self, resale: float) -> float:
        return self.outbound_ship_big_eur if resale >= self.big_threshold_eur \
            else self.outbound_ship_eur


def net_profit(resale: Optional[float], retail_cost: float, econ: Economics) -> dict:
    """retail_cost already includes the shop's shipping (from the brickmerge parse)."""
    if not resale or resale <= 0:
        return {"net_profit_eur": None, "fees_eur": None, "ship_eur": None,
                "resale_eur": resale}
    fee = round(resale * econ.ebay_fee_pct + econ.ebay_fee_fixed, 2)
    ship = econ.outbound(resale)
    net = resale - fee - ship - econ.packaging_eur - retail_cost
    return {
        "net_profit_eur": round(net, 2),
        "fees_eur": fee,
        "ship_eur": round(ship + econ.packaging_eur, 2),
        "resale_eur": round(resale, 2),
    }
