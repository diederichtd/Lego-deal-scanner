"""Small parsing helpers for German marketplace text."""
from __future__ import annotations

import re

_PRICE_RE = re.compile(r"(\d{1,3}(?:[.\s]\d{3})*|\d+)(?:,(\d{1,2}))?\s*(?:€|eur)?", re.I)


def parse_price_eur(text: str | None) -> float | None:
    """Turn '1.250,00 €', '120 € VB', 'VB', 'Zu verschenken' into a float or None."""
    if text is None:
        return None
    s = str(text).strip().lower()
    if not s:
        return None
    if "verschenk" in s:
        return 0.0
    if s in {"vb", "preis auf anfrage", "auf anfrage"}:
        return None
    m = _PRICE_RE.search(s)
    if not m:
        return None
    whole = re.sub(r"[.\s]", "", m.group(1))
    if not whole.isdigit():
        return None
    cents = (m.group(2) or "0").ljust(2, "0")[:2]
    try:
        return float(f"{whole}.{cents}")
    except ValueError:
        return None


_PICKUP_ONLY_RE = re.compile(r"nur abholung|kein versand|abholung only|no shipping", re.I)
_PICKUP_RE = re.compile(r"abholung|selbstabholung|pickup", re.I)
_SHIPPING_RE = re.compile(r"versand|shipping|verschick|paket", re.I)


def infer_inbound_shipping(text: str, listed: float | None, assumed: float) -> tuple[float, str]:
    """Guess what it costs to get the set to you. Returns (eur, note)."""
    if listed is not None:
        return float(listed), "listed inbound shipping"
    t = text or ""
    if _PICKUP_ONLY_RE.search(t):
        return 0.0, "local pickup only"
    if _PICKUP_RE.search(t) and not _SHIPPING_RE.search(t):
        return 0.0, "local pickup"
    return float(assumed), "assumed inbound shipping"
