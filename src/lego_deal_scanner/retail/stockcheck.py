"""Open a shop's search page for the set, find the actual product link, and
confirm it's really buyable near the expected price."""
from __future__ import annotations

import logging
import re

from .extract import extract_price, extract_products

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


def _product_link(html: str, set_num: str) -> str | None:
    """Best guess at the product-page URL for `set_num` from a shop page."""
    for p in extract_products(html):
        if set_num in (p.get("name") or "") and p.get("url", "").startswith("http"):
            return p["url"]
    # fall back: an <a href> that mentions the set number and looks like a product
    for m in re.finditer(r'href="(https?://[^"]*?%s[^"]*)"' % re.escape(set_num), html):
        u = m.group(1)
        if not re.search(r"/(search|suche|s\?|listing)", u, re.I):
            return u
    return None


def resolve_and_verify(search_url: str, set_num: str, expected_eur: float,
                       fetcher, tol: float = 0.18) -> dict:
    """Returns {product_url, ok, price, reason}.

    product_url: the real product page if we could find it, else None (keep the
                 search URL). ok: True in stock ~expected, False gone/pricier,
                 None couldn't tell.
    """
    html = fetcher.get(search_url)
    if not html:
        return {"product_url": None, "ok": None, "price": None, "reason": "no response"}

    prod_url = _product_link(html, set_num)
    page_html = html
    if prod_url and prod_url != search_url:
        got = fetcher.get(prod_url)
        if got:
            page_html = got

    low = page_html.lower()
    got = extract_price(page_html)
    price = got.get("price")
    if got.get("available") is False or (_OOS.search(low) and not _INSTOCK.search(low)):
        return {"product_url": prod_url, "ok": False, "price": price,
                "reason": "shows out of stock"}
    if price is not None and price > expected_eur * (1 + tol):
        return {"product_url": prod_url, "ok": False, "price": price,
                "reason": f"now EUR {price:.2f}, was EUR {expected_eur:.2f}"}
    if price is not None:
        return {"product_url": prod_url, "ok": True, "price": price,
                "reason": "in stock, price matches"}
    return {"product_url": prod_url, "ok": None, "price": None,
            "reason": "found the page, price not readable"}
