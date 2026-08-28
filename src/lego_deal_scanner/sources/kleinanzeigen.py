"""kleinanzeigen.de search scraper.

WARNING: kleinanzeigen.de has no public API and its Terms of Service prohibit
automated access. It also actively blocks bots. This module exists so the tool
*can* be pointed at it for personal, low-volume use if you accept that risk.
Keep ``delay_seconds`` high and ``max_pages`` low. HTML structure changes often;
on any parse failure this source logs a warning and yields nothing.
"""
from __future__ import annotations

import logging
import time
from typing import Iterator
from urllib.parse import urljoin

from ..parse import parse_price_eur
from .base import RawListing, Source

log = logging.getLogger(__name__)
BASE = "https://www.kleinanzeigen.de"


class KleinanzeigenSource(Source):
    name = "kleinanzeigen"

    def _url(self, query: str, page: int) -> str:
        slug = "-".join(query.lower().split())
        pmin = self.cfg.get("price_min")
        pmax = self.cfg.get("price_max")
        segs = ["s"]
        if page > 1:
            segs.append(f"seite:{page}")
        if pmin or pmax:
            segs.append(f"preis:{pmin or ''}:{pmax or ''}")
        prefix = "/".join(segs)
        return f"{BASE}/{prefix}/{slug}/k0"

    def search(self, query: str) -> Iterator[RawListing]:
        try:
            import requests
            from bs4 import BeautifulSoup
        except ImportError:
            log.warning("kleinanzeigen source needs 'requests' and 'beautifulsoup4'")
            return

        headers = {
            "User-Agent": self.cfg.get("user_agent", "Mozilla/5.0"),
            "Accept-Language": "de-DE,de;q=0.9",
            "Accept": "text/html,application/xhtml+xml",
        }
        delay = float(self.cfg.get("delay_seconds", 8.0))
        max_pages = int(self.cfg.get("max_pages", 2))
        seen: set[str] = set()

        for page in range(1, max_pages + 1):
            url = self._url(query, page)
            try:
                resp = requests.get(url, headers=headers, timeout=20)
            except Exception as exc:  # noqa: BLE001
                log.warning("kleinanzeigen request failed for %s: %s", url, exc)
                return
            if resp.status_code != 200:
                log.warning("kleinanzeigen returned HTTP %s for %s", resp.status_code, url)
                return

            soup = BeautifulSoup(resp.text, "html.parser")
            articles = soup.select("article.aditem, li.ad-listitem article")
            if not articles:
                log.info("kleinanzeigen: no results parsed on page %s (layout change?)", page)
                return

            for art in articles:
                item = self._parse_article(art, urljoin)
                if item and item.listing_id not in seen:
                    seen.add(item.listing_id)
                    yield item

            if page < max_pages:
                time.sleep(delay)

    def _parse_article(self, art, urljoin_fn) -> RawListing | None:
        try:
            adid = art.get("data-adid") or art.get("data-id") or ""
            link = art.select_one("a.ellipsis") or art.select_one("h2 a") or art.select_one("a")
            if not link:
                return None
            title = link.get_text(" ", strip=True)
            href = urljoin_fn(BASE, link.get("href", ""))
            if not adid:
                adid = href.rstrip("/").split("/")[-1]

            price_el = art.select_one(
                ".aditem-main--middle--price-shipping--price, .aditem-main--middle--price"
            )
            price = parse_price_eur(price_el.get_text(" ", strip=True)) if price_el else None

            desc_el = art.select_one(".aditem-main--middle--description")
            desc = desc_el.get_text(" ", strip=True) if desc_el else ""

            loc_el = art.select_one(".aditem-main--top--left")
            loc = loc_el.get_text(" ", strip=True) if loc_el else ""

            ship_el = art.select_one(".aditem-main--middle--price-shipping--shipping")
            ship_txt = ship_el.get_text(" ", strip=True).lower() if ship_el else ""
            shipping = 0.0 if "abholung" in ship_txt else None

            return RawListing(
                source=self.name,
                listing_id=str(adid),
                title=title,
                url=href,
                price_eur=price,
                shipping_eur=shipping,
                description=desc,
                location=loc,
            )
        except Exception as exc:  # noqa: BLE001
            log.debug("kleinanzeigen: could not parse an article: %s", exc)
            return None
