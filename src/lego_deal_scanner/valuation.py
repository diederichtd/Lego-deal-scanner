"""Reference values for LEGO sets: a CSV book plus an optional BrickLink lookup."""
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class Reference:
    set_num: str
    name: str
    year: Optional[int] = None
    pieces: Optional[int] = None
    rrp_eur: Optional[float] = None
    mv_new_eur: Optional[float] = None
    mv_used_eur: Optional[float] = None
    weight_g: Optional[int] = None
    source: str = "csv"


def _f(v) -> Optional[float]:
    v = ("" if v is None else str(v)).strip()
    try:
        return float(v) if v else None
    except ValueError:
        return None


def _i(v) -> Optional[int]:
    f = _f(v)
    return int(f) if f is not None else None


class ReferenceBook:
    def __init__(self, rows: dict[str, Reference]):
        self.rows = rows

    @classmethod
    def from_csv(cls, path: str | Path) -> "ReferenceBook":
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"reference csv not found: {p}")
        rows: dict[str, Reference] = {}
        with p.open(newline="", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                sn = (r.get("set_num") or "").strip()
                if not sn:
                    continue
                rows[sn] = Reference(
                    set_num=sn,
                    name=(r.get("name") or "").strip(),
                    year=_i(r.get("year")),
                    pieces=_i(r.get("pieces")),
                    rrp_eur=_f(r.get("rrp_eur")),
                    mv_new_eur=_f(r.get("mv_new_eur")),
                    mv_used_eur=_f(r.get("mv_used_eur")),
                    weight_g=_i(r.get("weight_g")),
                )
        return cls(rows)

    def known_numbers(self) -> set[str]:
        return set(self.rows)

    def get(self, set_num: str) -> Optional[Reference]:
        return self.rows.get(str(set_num).strip())


def resale_value(ref: Reference, condition: str, prefer: str = "market") -> Optional[float]:
    """Realistic amount you could resell this set for, in EUR, before fees."""
    new_v = ref.rrp_eur if prefer == "rrp" and ref.rrp_eur else (ref.mv_new_eur or ref.rrp_eur)
    used_v = ref.mv_used_eur
    if used_v is None and ref.rrp_eur:
        used_v = round(ref.rrp_eur * 0.6, 2)

    if condition == "new_sealed":
        return new_v
    if condition == "used_complete":
        return used_v
    if condition == "used_incomplete":
        return round(used_v * 0.7, 2) if used_v else None
    # unknown -> value conservatively as used
    return used_v


def bricklink_price(cfg: dict, set_num: str, new_or_used: str = "N",
                    currency: str = "EUR") -> Optional[float]:
    """6-month average *sold* price from BrickLink. Needs OAuth1 creds + extra.

    Returns None (and never raises) if disabled, unconfigured, or the call fails.
    """
    if not cfg or not cfg.get("enabled"):
        return None
    keys = ("consumer_key", "consumer_secret", "token", "token_secret")
    if not all(cfg.get(k) for k in keys):
        return None
    try:
        import requests
        from requests_oauthlib import OAuth1
    except ImportError:
        return None
    auth = OAuth1(cfg["consumer_key"], cfg["consumer_secret"],
                  cfg["token"], cfg["token_secret"])
    url = f"https://api.bricklink.com/api/store/v1/items/SET/{set_num}-1/price"
    params = {"guide_type": "sold", "new_or_used": new_or_used, "currency_code": currency}
    try:
        resp = requests.get(url, params=params, auth=auth, timeout=15)
        resp.raise_for_status()
        data = resp.json().get("data") or {}
        avg = data.get("avg_price")
        return float(avg) if avg else None
    except Exception:
        return None
