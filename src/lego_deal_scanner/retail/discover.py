"""Discovery: read each shop's LEGO sale / clearance listing pages and pull out
*every* discounted set at once - no per-set URL needed.

Config: retail.sale_pages = {shop_key: [listing_url, ...]}. A discovered set is
only reported if it's in your catalog (so "worth buying" stays curated) and the
discount clears retail.min_discount_pct.
"""
from __future__ import annotations

import logging
from typing import Iterable

from ..setnum import extract_set_numbers
from .extract import extract_products
from .shops import make_deal

log = logging.getLogger(__name__)


def discover(
    sale_pages: dict,
    fetcher,
    catalog_by_set: dict,
    ref_prices: dict,
    store,
    *,
    enabled: Iterable[str],
    min_pct: float,
    min_price: float,
    seen_urls: set,
) -> list[dict]:
    enabled = set(enabled)
    known = set(catalog_by_set)
    deals: list[dict] = []
    pages = 0

    for shop_key, urls in (sale_pages or {}).items():
        if shop_key not in enabled:
            continue
        for page_url in urls or []:
            html = fetcher.get(page_url)
            if not html:
                log.warning("discover: no data from %s", page_url)
                continue
            products = extract_products(html)
            pages += 1
            if not products:
                log.info("discover: no JSON-LD products on %s", page_url)
            for prod in products:
                nums = extract_set_numbers(prod["name"], known)
                row = next((catalog_by_set[n] for n in nums if n in catalog_by_set), None)
                if row is None:
                    continue
                ref = (ref_prices.get(row.set_num) or {}).get("price") or row.rrp_eur
                price = prod["price"]
                if not ref or price is None or price < min_price:
                    continue
                saving = ref - price
                if saving <= 0 or saving / ref < min_pct:
                    continue
                url = prod["url"] or page_url
                if url in seen_urls:
                    continue
                seen_urls.add(url)
                state = store.record_retail_price(
                    shop_key, row.set_num, price, prod.get("available")
                )["state"]
                deals.append(make_deal(row.set_num, row.name, shop_key, url, price, ref,
                                       prod.get("available"), state, "sale-page",
                                       image=row.image_url or prod.get("image")))
    log.debug("discover: scanned %s listing pages, %s deals", pages, len(deals))
    return deals
