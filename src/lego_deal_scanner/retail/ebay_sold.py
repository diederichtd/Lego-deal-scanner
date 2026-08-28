"""Estimate a set's real resale value from recent eBay.de *sold* listings.

Scrapes the sold/completed search page. eBay has no free API for sold prices,
so this is best-effort: on any failure it returns None and the caller falls
back to the seller's own listed price. Results are cached in the store.
"""
from __future__ import annotations

import logging
import re
import statistics
from dataclasses import dataclass
from typing import Optional
from urllib.parse import quote_plus

log = logging.getLogger(__name__)

_PRICE = re.compile(r"EUR\s*([\d.]+,\d{2})")
_RANGE = re.compile(r"bis|to", re.I)


def _eur(s: str) -> Optional[float]:
    try:
        v = float(s.replace(".", "").replace(",", "."))
    except ValueError:
        return None
    return v if 3 <= v <= 20000 else None


@dataclass
class SoldStats:
    set_num: str
    median: Optional[float]
    count: int
    low: Optional[float]
    high: Optional[float]


def _search_url(set_num: str, days: int) -> str:
    q = quote_plus(f"LEGO {set_num}")
    return (f"https://www.ebay.de/sch/i.html?_nkw={q}&LH_Sold=1&LH_Complete=1"
            f"&_ipg=60&_sop=13&LH_ItemCondition=1000")  # 1000 = new


def fetch_sold(set_num: str, fetcher, days: int = 90) -> Optional[SoldStats]:
    html = fetcher.get(_search_url(set_num, days))
    if not html:
        return None
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        log.warning("ebay_sold needs beautifulsoup4")
        return None

    soup = BeautifulSoup(html, "html.parser")
    cards = soup.select(".s-card, li.s-item")
    prices: list[float] = []
    for c in cards:
        title = (c.select_one(".s-card__title, .s-item__title") or c).get_text(" ", strip=True)
        if set_num not in title:
            continue                        # avoid bundles / wrong sets
        pel = c.select_one(".s-card__price, .s-item__price")
        if not pel:
            continue
        ptxt = pel.get_text(" ", strip=True)
        if _RANGE.search(ptxt):             # "EUR 10 bis EUR 20" ranges -> skip
            continue
        m = _PRICE.search(ptxt)
        v = _eur(m.group(1)) if m else None
        if v:
            prices.append(v)

    prices = [p for p in prices if p]
    if not prices:
        return SoldStats(set_num, None, 0, None, None)
    # trim the wildest 10% each end before the median
    prices.sort()
    k = max(0, len(prices) // 10)
    core = prices[k:len(prices) - k] or prices
    return SoldStats(
        set_num=set_num,
        median=round(statistics.median(core), 2),
        count=len(prices),
        low=round(min(prices), 2),
        high=round(max(prices), 2),
    )


def sold_value(set_num: str, fetcher, store, cfg: dict) -> Optional[dict]:
    """Cached wrapper. Returns {'median','count','low','high','age_days'} or None."""
    if not cfg.get("enabled"):
        return None
    cache_days = float(cfg.get("cache_days", 7))
    hit = store.get_sold_cache(set_num, cache_days)
    if hit is not None:
        return hit
    st = fetch_sold(set_num, fetcher, int(cfg.get("days", 90)))
    if st is None:
        return None
    store.put_sold_cache(set_num, st.median, st.count, st.low, st.high)
    return {"median": st.median, "count": st.count, "low": st.low, "high": st.high,
            "age_days": 0.0}
