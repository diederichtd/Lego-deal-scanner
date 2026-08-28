"""brickmerge.de price aggregator.

One fetch per set page (``brickmerge.de/{set}-1_x`` - any slug redirects) tells
us the single cheapest current offer across the German shops brickmerge tracks,
plus the UVP and Deal-Score. brickmerge is not bot-walled.

We parse the "Top-Angebot" block, which carries the real merchant, the price
*as of a timestamp* (brickmerge itself warns it "kann höher sein"), any separate
shipping, and whether the price needs a coupon code. Offers that are really
eBay/Amazon-marketplace listings, or coupon-only, are flagged so the caller can
skip them - those are not "walk in and buy it" prices.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Optional

log = logging.getLogger(__name__)

BASE = "https://www.brickmerge.de"
_EURO = r"(?:€|&euro;|&#8364;)"
_TAG = r"\s*(?:<[^>]+>\s*)?"

_UVP = [
    re.compile(r"akt\.\s*UVP:" + _TAG + r"([\d.]+,\d{2})\s*" + _EURO),
    re.compile(r"statt UVP" + _TAG + r"([\d.]+,\d{2})\s*" + _EURO),
]
_ABPRICE = re.compile(r"kostet aktuell ab" + _TAG + r"([\d.]+,\d{2})\s*" + _EURO)
_SCORE = re.compile(r"Deal-?Score:?" + _TAG + r"\s*(\d{1,3})", re.I)

# the Top-Angebot anchor: grab its href and its (very informative) title text
_TOP = re.compile(
    r'Top-Angebot:.*?<a\s+href="([^"]+)"[^>]*?\btitle="(Link zu [^"]+)"',
    re.S | re.I,
)
_TITLE_MERCHANT = re.compile(r"Link zu\s+(.+?)\s+-\s")
_TITLE_PRICE = re.compile(r"Uhr:\s*([\d.]+,\d{2})\s*" + _EURO)
_TITLE_SHIP = re.compile(r"\+\s*Versand\s*([\d.]+,\d{2})\s*" + _EURO)
_TITLE_TIME = re.compile(r"Preisangabe vom\s*([\d.]+,?\s*[\d:]+\s*Uhr)")
_GO2 = re.compile(r"(?:go2m=|[?&]m=)(\d+).*?(?:go2i=|[?&]i=)([\w-]+)")

_MARKETPLACE = re.compile(
    r"\bebay\b|marketplace|kleinanzeigen|"
    r"amazon\s*\(\s*(?:fr|es|it|nl|pl|se|be|co\.uk|com|us)\s*\)",  # foreign Amazon = import
    re.I,
)


def _eur(s: str | None) -> Optional[float]:
    if not s:
        return None
    try:
        v = float(s.replace(".", "").replace(",", "."))
    except ValueError:
        return None
    return v if 1 <= v <= 100000 else None


def _first(patterns, html: str) -> Optional[float]:
    for rx in patterns:
        m = rx.search(html)
        if m:
            return _eur(m.group(1))
    return None


@dataclass
class BrickmergePrice:
    set_num: str
    best_eur: Optional[float]        # merchant price + shipping
    merchant: str
    offer_url: str
    uvp_eur: Optional[float]
    deal_score: Optional[int]
    priced_at: str                  # e.g. "28.08., 19:41 Uhr"
    coupon_only: bool
    marketplace: bool               # eBay / Amazon-marketplace / Kleinanzeigen
    url: str                        # the brickmerge page (fallback link)


def parse(html: str, set_num: str, url: str) -> BrickmergePrice:
    html = html or ""
    sm = _SCORE.search(html)
    uvp = _first(_UVP, html)

    merchant, offer_url, price, priced_at = "", url, None, ""
    coupon_only = marketplace = False

    top = _TOP.search(html)
    if top:
        href, title = top.group(1), top.group(2)
        mm = _TITLE_MERCHANT.search(title)
        merchant = mm.group(1).strip() if mm else ""
        pm = _TITLE_PRICE.search(title)
        price = _eur(pm.group(1)) if pm else None
        sh = _TITLE_SHIP.search(title)
        if price is not None and sh:
            price = round(price + (_eur(sh.group(1)) or 0), 2)
        tm = _TITLE_TIME.search(title)
        priced_at = tm.group(1).strip() if tm else ""
        coupon_only = "gutschein" in title.lower()
        marketplace = bool(_MARKETPLACE.search(merchant))
        g = _GO2.search(href)
        offer_url = f"{BASE}/go2/?m={g.group(1)}&i={g.group(2)}" if g else BASE + href

    if price is None:                       # fall back to the headline "ab X €"
        price = _first([_ABPRICE], html)

    return BrickmergePrice(
        set_num=set_num, best_eur=price, merchant=merchant, offer_url=offer_url,
        uvp_eur=uvp, deal_score=int(sm.group(1)) if sm else None,
        priced_at=priced_at, coupon_only=coupon_only, marketplace=marketplace, url=url,
    )


def fetch(set_num: str, fetcher) -> Optional[BrickmergePrice]:
    url = f"{BASE}/{set_num}-1_x"
    html = fetcher.get(url)
    if not html:
        log.info("brickmerge: no data for %s", set_num)
        return None
    bp = parse(html, set_num, url)
    if bp.best_eur is None and bp.uvp_eur is None:
        log.info("brickmerge: could not parse %s", set_num)
        return None
    return bp
