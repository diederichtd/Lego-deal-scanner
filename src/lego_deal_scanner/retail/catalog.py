"""Load the watch catalog: which sets to track and where."""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class CatalogRow:
    set_num: str
    name: str
    lego_url: str = ""
    rrp_eur: Optional[float] = None          # fallback if lego_url fetch fails
    retailer_urls: dict[str, str] = field(default_factory=dict)
    image_url: str = ""                       # optional; falls back to BrickLink
    ebay_price_eur: Optional[float] = None    # optional: your current selling price
    sold: Optional[int] = None                # optional: lifetime sold (checked first)


def _parse_retailer_urls(raw: str) -> dict[str, str]:
    """`otto=https://..|mueller=https://..` -> {'otto': '...', 'mueller': '...'}."""
    out: dict[str, str] = {}
    for chunk in (raw or "").split("|"):
        chunk = chunk.strip()
        if not chunk or "=" not in chunk:
            continue
        key, _, url = chunk.partition("=")
        key, url = key.strip().lower(), url.strip()
        if key and url:
            out[key] = url
    return out


def load_catalog(path: str | Path) -> list[CatalogRow]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"catalog csv not found: {p}")
    rows: list[CatalogRow] = []
    with p.open(newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            sn = (r.get("set_num") or "").strip()
            if not sn:
                continue
            rrp = (r.get("rrp_eur") or "").strip()
            ebay = (r.get("ebay_price_eur") or "").strip()
            sold = (r.get("ebay_sold") or r.get("sold") or "").strip()
            rows.append(
                CatalogRow(
                    set_num=sn,
                    name=(r.get("name") or "").strip(),
                    lego_url=(r.get("lego_url") or "").strip(),
                    rrp_eur=float(rrp) if rrp else None,
                    retailer_urls=_parse_retailer_urls(r.get("retailer_urls", "")),
                    image_url=(r.get("image_url") or "").strip(),
                    ebay_price_eur=float(ebay) if ebay else None,
                    sold=int(float(sold)) if sold else None,
                )
            )
    return rows
