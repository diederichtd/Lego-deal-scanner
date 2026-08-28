"""Read one eBay seller's active LEGO listings (default: your own store).

Gives the watch pipeline a live list of "sets I currently sell" so it can show
only those that are on sale cheaper somewhere else.

Two modes:
  browse_api  - eBay Browse API, filter=sellers:{name} (needs free app keys,
                no seller login: the listings are public). Reliable.
  html        - scrape ebay.de/sch/i.html?_ssn={name}. Keyless, brittle, blockable.
"""
from __future__ import annotations

import base64
import logging
import time
from dataclasses import dataclass
from typing import Iterable, Optional
from urllib.parse import quote_plus

from ..setnum import extract_set_numbers

log = logging.getLogger(__name__)

_OAUTH_URL = "https://api.ebay.com/identity/v1/oauth2/token"
_SEARCH_URL = "https://api.ebay.com/buy/browse/v1/item_summary/search"
_SCOPE = "https://api.ebay.com/oauth/api_scope"


@dataclass
class SellerListing:
    set_num: str
    title: str
    ebay_price_eur: Optional[float]
    url: str
    condition: str = ""
    quantity: Optional[int] = None


class EbaySeller:
    def __init__(self, cfg: dict | None = None):
        self.cfg = cfg or {}
        self.seller = (self.cfg.get("seller") or "").strip()
        self._token: str | None = None
        self._token_exp = 0.0

    def listings(self, known_sets: Iterable[str], fetcher=None) -> list[SellerListing]:
        if not self.seller:
            log.warning("ebay_seller: no seller name configured")
            return []
        known = {str(k) for k in known_sets}
        mode = self.cfg.get("mode", "browse_api")
        raw = self._browse(known) if mode == "browse_api" else self._html(known, fetcher)
        # keep one row per set number (cheapest listing wins)
        best: dict[str, SellerListing] = {}
        for item in raw:
            nums = extract_set_numbers(item["title"], known)
            sn = next((n for n in nums if n in known), nums[0] if nums else None)
            if not sn:
                continue
            price = item.get("price")
            cur = best.get(sn)
            if cur is None or (price is not None and (cur.ebay_price_eur is None
                                                     or price < cur.ebay_price_eur)):
                best[sn] = SellerListing(
                    set_num=sn, title=item["title"], ebay_price_eur=price,
                    url=item.get("url", ""), condition=item.get("condition", ""),
                    quantity=item.get("quantity"),
                )
        log.info("ebay_seller %s: %s LEGO listings, %s distinct sets",
                 self.seller, len(raw), len(best))
        return list(best.values())

    # --- Browse API --------------------------------------------------------
    def _get_token(self) -> str | None:
        try:
            import requests
        except ImportError:
            log.warning("ebay_seller browse_api needs 'requests'")
            return None
        if self._token and time.time() < self._token_exp - 60:
            return self._token
        cid, secret = self.cfg.get("client_id"), self.cfg.get("client_secret")
        if not cid or not secret:
            log.warning("ebay_seller: browse_api needs client_id + client_secret")
            return None
        basic = base64.b64encode(f"{cid}:{secret}".encode()).decode()
        try:
            r = requests.post(
                _OAUTH_URL,
                headers={"Authorization": f"Basic {basic}",
                         "Content-Type": "application/x-www-form-urlencoded"},
                data={"grant_type": "client_credentials", "scope": _SCOPE},
                timeout=20,
            )
            r.raise_for_status()
            js = r.json()
            self._token = js["access_token"]
            self._token_exp = time.time() + float(js.get("expires_in", 7200))
            return self._token
        except Exception as exc:  # noqa: BLE001
            log.warning("ebay_seller: token request failed: %s", exc)
            return None

    def _browse(self, known: set[str]) -> list[dict]:
        import requests

        token = self._get_token()
        if not token:
            return []
        out: list[dict] = []
        offset, limit = 0, 200
        for _ in range(10):  # up to 2000 listings
            try:
                r = requests.get(
                    _SEARCH_URL,
                    headers={"Authorization": f"Bearer {token}",
                             "X-EBAY-C-MARKETPLACE-ID": "EBAY_DE"},
                    params={"q": "lego", "limit": limit, "offset": offset,
                            "filter": f"sellers:{{{self.seller}}}"},
                    timeout=25,
                )
                r.raise_for_status()
                js = r.json()
            except Exception as exc:  # noqa: BLE001
                log.warning("ebay_seller: search failed: %s", exc)
                break
            for it in js.get("itemSummaries") or []:
                price = (it.get("price") or {}).get("value")
                out.append({
                    "title": it.get("title", ""),
                    "price": float(price) if price is not None else None,
                    "url": it.get("itemWebUrl", ""),
                    "condition": it.get("condition", "") or "",
                    "quantity": (it.get("estimatedAvailabilities") or [{}])[0]
                    .get("estimatedAvailableQuantity"),
                })
            total = int(js.get("total", 0))
            offset += limit
            if offset >= total or not js.get("itemSummaries"):
                break
        return out

    # --- HTML fallback ---------------------------------------------------
    def _html(self, known: set[str], fetcher) -> list[dict]:
        if fetcher is None:
            log.warning("ebay_seller html mode needs a fetcher")
            return []
        try:
            from bs4 import BeautifulSoup
        except ImportError:
            log.warning("ebay_seller html mode needs 'beautifulsoup4'")
            return []
        from ..parse import parse_price_eur

        url = (f"https://www.ebay.de/sch/i.html?_ssn={quote_plus(self.seller)}"
               f"&_nkw=lego&_ipg=240")
        html = fetcher.get(url)
        if not html:
            return []
        soup = BeautifulSoup(html, "html.parser")
        out: list[dict] = []
        for li in soup.select("li.s-item"):
            a = li.select_one("a.s-item__link")
            title_el = li.select_one(".s-item__title")
            price_el = li.select_one(".s-item__price")
            if not a or not title_el:
                continue
            title = title_el.get_text(" ", strip=True)
            if title.lower().startswith("shop on ebay"):
                continue
            out.append({
                "title": title,
                "price": parse_price_eur(price_el.get_text(" ", strip=True)) if price_el else None,
                "url": a.get("href", "").split("?")[0],
                "condition": "",
                "quantity": None,
            })
        return out
