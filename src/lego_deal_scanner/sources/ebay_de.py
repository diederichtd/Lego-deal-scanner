"""eBay.de source. Prefers the official Browse API; falls back to HTML search.

Browse API needs an application client id / secret from developer.ebay.com.
The API is the supported, ToS-compliant path - use it.
"""
from __future__ import annotations

import base64
import logging
import time
from typing import Iterator
from urllib.parse import quote_plus

from ..parse import parse_price_eur
from .base import RawListing, Source

log = logging.getLogger(__name__)

_OAUTH_URL = "https://api.ebay.com/identity/v1/oauth2/token"
_SEARCH_URL = "https://api.ebay.com/buy/browse/v1/item_summary/search"
_SCOPE = "https://api.ebay.com/oauth/api_scope"


class EbayDeSource(Source):
    name = "ebay_de"

    def __init__(self, cfg: dict | None = None):
        super().__init__(cfg)
        self._token: str | None = None
        self._token_exp: float = 0.0

    def search(self, query: str) -> Iterator[RawListing]:
        try:
            import requests  # noqa: F401
        except ImportError:
            log.warning("ebay_de source needs 'requests'")
            return
        mode = self.cfg.get("mode", "browse_api")
        if mode == "browse_api":
            yield from self._search_api(query)
        else:
            yield from self._search_html(query)

    # --- Browse API -----------------------------------------------------------
    def _get_token(self) -> str | None:
        import requests

        if self._token and time.time() < self._token_exp - 60:
            return self._token
        cid = self.cfg.get("client_id")
        secret = self.cfg.get("client_secret")
        if not cid or not secret:
            log.warning("ebay_de: browse_api mode needs client_id and client_secret")
            return None
        basic = base64.b64encode(f"{cid}:{secret}".encode()).decode()
        try:
            resp = requests.post(
                _OAUTH_URL,
                headers={
                    "Authorization": f"Basic {basic}",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                data={"grant_type": "client_credentials", "scope": _SCOPE},
                timeout=20,
            )
            resp.raise_for_status()
            js = resp.json()
            self._token = js["access_token"]
            self._token_exp = time.time() + float(js.get("expires_in", 7200))
            return self._token
        except Exception as exc:  # noqa: BLE001
            log.warning("ebay_de: token request failed: %s", exc)
            return None

    def _search_api(self, query: str) -> Iterator[RawListing]:
        import requests

        token = self._get_token()
        if not token:
            return
        pmin = self.cfg.get("price_min")
        pmax = self.cfg.get("price_max")
        filt = f"price:[{pmin or 0}..{pmax or ''}],priceCurrency:EUR,buyingOptions:{{FIXED_PRICE}}"
        params = {
            "q": query,
            "limit": min(int(self.cfg.get("max_results", 100)), 200),
            "filter": filt,
            "sort": "price",
        }
        try:
            resp = requests.get(
                _SEARCH_URL,
                headers={
                    "Authorization": f"Bearer {token}",
                    "X-EBAY-C-MARKETPLACE-ID": "EBAY_DE",
                },
                params=params,
                timeout=25,
            )
            resp.raise_for_status()
            summaries = resp.json().get("itemSummaries") or []
        except Exception as exc:  # noqa: BLE001
            log.warning("ebay_de: search failed: %s", exc)
            return

        for it in summaries:
            price = it.get("price") or {}
            ship = None
            opts = it.get("shippingOptions") or []
            if opts:
                sc = (opts[0].get("shippingCost") or {}).get("value")
                ship = float(sc) if sc is not None else None
            yield RawListing(
                source=self.name,
                listing_id=str(it.get("itemId", "")),
                title=it.get("title", ""),
                url=it.get("itemWebUrl", ""),
                price_eur=float(price["value"]) if price.get("value") else None,
                shipping_eur=ship,
                description=it.get("shortDescription", "") or "",
                location=(it.get("itemLocation") or {}).get("country", ""),
                condition_hint=it.get("condition", "") or "",
                image_url=(it.get("image") or {}).get("imageUrl", ""),
            )

    # --- HTML fallback ------------------------------------------------------
    def _search_html(self, query: str) -> Iterator[RawListing]:
        import requests
        from bs4 import BeautifulSoup

        url = f"https://www.ebay.de/sch/i.html?_nkw={quote_plus(query)}&_sop=15"
        try:
            resp = requests.get(
                url,
                headers={"User-Agent": "Mozilla/5.0", "Accept-Language": "de-DE"},
                timeout=20,
            )
            resp.raise_for_status()
        except Exception as exc:  # noqa: BLE001
            log.warning("ebay_de html: request failed: %s", exc)
            return
        soup = BeautifulSoup(resp.text, "html.parser")
        for li in soup.select("li.s-item"):
            a = li.select_one("a.s-item__link")
            title_el = li.select_one(".s-item__title")
            price_el = li.select_one(".s-item__price")
            if not a or not title_el:
                continue
            title = title_el.get_text(" ", strip=True)
            if title.lower().startswith("shop on ebay"):
                continue
            href = a.get("href", "")
            lid = href.split("/itm/")[-1].split("?")[0] if "/itm/" in href else href
            yield RawListing(
                source=self.name,
                listing_id=str(lid),
                title=title,
                url=href,
                price_eur=parse_price_eur(price_el.get_text(" ", strip=True)) if price_el else None,
                description="",
                location="",
            )
