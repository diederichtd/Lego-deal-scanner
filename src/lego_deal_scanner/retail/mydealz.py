"""Ingest mydealz.de RSS feeds (LEGO group / saved searches).

mydealz is a community deal board. Its feeds surface price drops across shops we
have no scraper for. Grab the RSS URL from the site (there's an RSS link on any
group or search page) and put it in config under retail.mydealz.feeds.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Iterable, Optional
from xml.etree import ElementTree as ET

from ..setnum import extract_set_numbers

log = logging.getLogger(__name__)

_PRICE_RE = re.compile(r"(\d{1,4}(?:[.\s]\d{3})*(?:[.,]\d{2})?)\s*€")
_MERCHANT_RE = re.compile(r"(?:H[äa]ndler|Shop|bei)\s*:?\s*([A-Za-z0-9ÄÖÜäöü .&'-]{2,40})")
_TAG_RE = re.compile(r"<[^>]+>")


@dataclass
class DealPost:
    title: str
    url: str
    price_eur: Optional[float]
    merchant: str
    set_nums: list[str]
    published: str
    expired: bool


def _price(text: str) -> Optional[float]:
    m = _PRICE_RE.search(text or "")
    if not m:
        return None
    s = m.group(1).replace(" ", "").replace(".", "").replace(",", ".") if "," in m.group(1) \
        else m.group(1).replace(" ", "").replace(".", "")
    try:
        v = float(s)
    except ValueError:
        return None
    return v if 1 <= v <= 100000 else None


def parse_feed(xml_text: str, known_sets: Iterable[str] = ()) -> list[DealPost]:
    known = set(known_sets)
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        log.warning("mydealz: bad RSS: %s", exc)
        return []

    posts: list[DealPost] = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        desc_raw = item.findtext("description") or ""
        desc = _TAG_RE.sub(" ", desc_raw)
        blob = f"{title} {desc}"
        merch = _MERCHANT_RE.search(blob)
        posts.append(
            DealPost(
                title=title,
                url=link,
                price_eur=_price(title) or _price(desc),
                merchant=(merch.group(1).strip() if merch else ""),
                set_nums=extract_set_numbers(blob, known),
                published=(item.findtext("pubDate") or "").strip(),
                expired=bool(re.search(r"abgelaufen|expired", blob, re.I)),
            )
        )
    return posts


def fetch_posts(feeds: list[str], fetcher, known_sets: Iterable[str] = ()) -> list[DealPost]:
    out: list[DealPost] = []
    for url in feeds or []:
        xml = fetcher.get(url)
        if not xml:
            log.warning("mydealz: no data from %s", url)
            continue
        out.extend(parse_feed(xml, known_sets))
    return out
