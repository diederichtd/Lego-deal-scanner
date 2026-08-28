"""brickmerge.de price aggregator.

One fetch per set covers every German shop brickmerge lists (Otto, Müller,
Proshop, Galeria, Smyths, JB Spielwaren, ...) and it is NOT bot-walled - unlike
lego.com / thalia / otto directly. It also hands us the current UVP, so no
LEGO.de fetch is needed for a reference price.

Parses from the set page ``brickmerge.de/{set}-1_x`` (any slug redirects):
  - current best price ("kostet aktuell ab X €" / the <title>)
  - current UVP
  - 30-day best price
  - brickmerge Deal-Score (0-100)
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Optional

log = logging.getLogger(__name__)

BASE = "https://www.brickmerge.de"

_EURO = r"(?:€|&euro;|&#8364;)"
_TAG = r"\s*(?:<[^>]+>\s*)?"      # whitespace + one optional inline tag (values sit in <strong>)
_PATTERNS = {
    "best": [
        re.compile(r"kostet aktuell ab" + _TAG + r"\s*([\d.]+,\d{2})\s*" + _EURO),
        re.compile(r"<title>[^<]*?\bab\s+([\d.]+,\d{2})\s*" + _EURO, re.I),
        re.compile(r"\bab" + _TAG + r"\s*([\d.]+,\d{2})\s*" + _EURO),
    ],
    "uvp": [
        re.compile(r"akt\.\s*UVP:" + _TAG + r"([\d.]+,\d{2})\s*" + _EURO),
        re.compile(r"unter UVP\).{0,80}?statt UVP" + _TAG + r"([\d.]+,\d{2})\s*" + _EURO),
        re.compile(r"statt UVP" + _TAG + r"([\d.]+,\d{2})\s*" + _EURO),
    ],
    "d30": [re.compile(r"30[ -]Tage[ -]?Bestpreis[:\s]*" + _TAG + r"([\d.]+,\d{2})\s*" + _EURO)],
}
_SCORE = re.compile(r"Deal-?Score:?" + _TAG + r"\s*(\d{1,3})(?:\s*(?:von|/)\s*100)?", re.I)


def _eur(s: str | None) -> Optional[float]:
    if not s:
        return None
    try:
        v = float(s.replace(".", "").replace(",", "."))
    except ValueError:
        return None
    return v if 1 <= v <= 100000 else None


def _first(html: str, key: str) -> Optional[float]:
    for rx in _PATTERNS[key]:
        m = rx.search(html)
        if m:
            return _eur(m.group(1))
    return None


@dataclass
class BrickmergePrice:
    set_num: str
    best_eur: Optional[float]
    uvp_eur: Optional[float]
    best_30d_eur: Optional[float]
    deal_score: Optional[int]
    url: str


def parse(html: str, set_num: str, url: str) -> BrickmergePrice:
    html = html or ""
    sm = _SCORE.search(html)
    return BrickmergePrice(
        set_num=set_num,
        best_eur=_first(html, "best"),
        uvp_eur=_first(html, "uvp"),
        best_30d_eur=_first(html, "d30"),
        deal_score=int(sm.group(1)) if sm else None,
        url=url,
    )


def fetch(set_num: str, fetcher) -> Optional[BrickmergePrice]:
    url = f"{BASE}/{set_num}-1_x"
    html = fetcher.get(url)
    if not html:
        log.info("brickmerge: no data for %s", set_num)
        return None
    bp = parse(html, set_num, url)
    if bp.best_eur is None and bp.uvp_eur is None:
        log.info("brickmerge: could not parse prices for %s", set_num)
        return None
    return bp
