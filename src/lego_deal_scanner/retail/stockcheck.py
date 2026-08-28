"""Follow a deal's link to the actual shop and confirm it's really buyable."""
from __future__ import annotations

import logging
import re

from .extract import extract_price

log = logging.getLogger(__name__)

_OOS = re.compile(
    r"ausverkauft|nicht (?:mehr )?(?:verf[üu]gbar|lieferbar|auf lager)|out of stock|"
    r"sold\s*out|derzeit nicht|vergriffen|currently unavailable|temporarily out",
    re.I,
)
_INSTOCK = re.compile(
    r"auf lager|sofort lieferbar|in den warenkorb|jetzt kaufen|add to (?:cart|basket)|"
    r"lieferbar\b|verf[üu]gbar\b|instock",
    re.I,
)


def verify(url: str, expected_eur: float, fetcher, tol: float = 0.18) -> dict:
    """Returns {'ok': bool|None, 'price': float|None, 'reason': str}.

    ok=True  confirmed in stock near the expected price
    ok=False confirmed gone / much pricier
    ok=None  couldn't tell (blocked, JS-only, redirect) -> keep the deal, just unverified
    """
    html = fetcher.get(url)
    if not html:
        return {"ok": None, "price": None, "reason": "no response"}
    low = html.lower()

    got = extract_price(html)
    price = got.get("price")
    avail = got.get("available")

    if avail is False or (_OOS.search(low) and not _INSTOCK.search(low)):
        return {"ok": False, "price": price, "reason": "shows out of stock"}

    if price is not None:
        if price > expected_eur * (1 + tol):
            return {"ok": False, "price": price,
                    "reason": f"now EUR {price:.2f}, was EUR {expected_eur:.2f}"}
        return {"ok": True, "price": price, "reason": "in stock, price matches"}

    if _INSTOCK.search(low):
        return {"ok": None, "price": None, "reason": "in stock, price not readable"}
    return {"ok": None, "price": None, "reason": "could not read the page"}
