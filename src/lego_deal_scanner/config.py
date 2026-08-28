"""Load YAML config, merged over defaults."""
from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import yaml

DEFAULTS: dict[str, Any] = {
    "watchlist": ["lego"],
    "sources": {
        "fixture": {"enabled": True, "path": "data/fixture_listings.json"},
        "kleinanzeigen": {
            "enabled": False,
            "max_pages": 2,
            "delay_seconds": 8.0,
            "price_min": 20,
            "price_max": 2000,
            "user_agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
            ),
        },
        "ebay_de": {
            "enabled": False,
            "mode": "browse_api",
            "client_id": None,
            "client_secret": None,
            "max_results": 100,
            "price_min": 20,
            "price_max": 2000,
        },
    },
    "valuation": {
        "reference_csv": "data/reference_prices.csv",
        "prefer": "market",
        "bricklink": {
            "enabled": False,
            "consumer_key": None,
            "consumer_secret": None,
            "token": None,
            "token_secret": None,
        },
    },
    "scoring": {
        "marketplace_fee_pct": 0.11,
        "payment_fee_pct": 0.0,
        "payment_fee_fixed": 0.0,
        "packaging_eur": 1.20,
        "resale_haircut_pct": 0.08,
        "assumed_shipping_in_eur": 5.49,
        "default_shipping_out_eur": 6.99,
        "shipping_out_by_weight": {1000: 4.99, 2000: 5.99, 5000: 6.99, 31500: 10.49},
        "refurb_cost_used_eur": 0.0,
        "min_profit_eur": 20.0,
        "min_roi": 0.30,
        "watch_roi": 0.15,
    },
    "store": {"path": "data/scanner.sqlite3"},
    "notify": {"console": True, "json_out": "data/deals.latest.json", "webhook_url": None},
    "retail": {
        "catalog_csv": "data/catalog.csv",
        "min_saving_eur": 3.0,
        "min_discount_pct": 0.12,     # only sets at least 12% below LEGO.de
        "min_price_eur": 25.0,        # skip cheap sets not worth flipping
        "shops_enabled": [
            "lego", "otto", "mueller", "thalia", "joybuy",
            "smyths", "proshop", "galeria",
        ],
        "sale_pages": {
            # shop -> LEGO sale/clearance listing URLs. Discovery reads every
            # discounted set off these pages; no per-set URL needed.
            # "otto": ["https://www.otto.de/spielzeug/lego/lego-angebote/"],
            # "galeria": ["https://www.galeria.de/marken/lego/sale/"],
        },
        "http": {
            "user_agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
            ),
            "timeout": 20,
            "min_delay_seconds": 3.0,
            "max_retries": 2,
        },
        "min_flip_margin_eur": 12.0,  # pre-filter: min (your price - retail price)
        "min_net_profit_eur": 5.0,    # main list: net profit after fees + postage >= this
        "verify_top_n": 15,           # check the shop actually has the N best deals in stock
        "economics": {
            "ebay_fee_pct": 0.11,     # eBay.de FVF - lower for a commercial shop-abo account
            "ebay_fee_fixed": 0.35,
            "outbound_ship_eur": 6.50,
            "outbound_ship_big_eur": 10.49,
            "big_threshold_eur": 120.0,
            "packaging_eur": 1.00,
        },
        "ebay_sold": {
            "enabled": True,          # value sets at their real eBay sold price, not your list
            "days": 90,
            "min_solds": 2,           # need at least this many sold comps to trust it
            "cache_days": 7,
        },
        "brickmerge": {
            "enabled": True,          # aggregates all German shops, not bot-walled
            "max_sets": 120,          # per run; bestsellers (highest ebay_sold) first
            "min_deal_score": 0,      # optionally require brickmerge Deal-Score >= N
        },
        "amazon": {"enabled": False},
        "mydealz": {
            "enabled": True,
            "feeds": ["https://www.mydealz.de/gruppe/lego-rss"],
        },
        "ebay_seller": {
            "enabled": False,
            "seller": "",             # your eBay username, e.g. knoppers55
            "mode": "browse_api",     # browse_api (needs keys) | html
            "client_id": None,
            "client_secret": None,
            "require_below_ebay": False,  # True = only show retailer price < your price
        },
    },
    "site": {
        "outdir": "site_out",
        "title": "LEGO Deals DE",
        "public_url": "",
        "base_url": "",
        "preview_note": "",
        "deploy": {
            "mode": "none",           # none | folder | rsync | netlify | git
            "branch": "gh-pages",
            "remote_url": "",         # git mode: git@github.com:you/lego-deals.git
            "target": "",             # rsync mode: you@host:/var/www/legodeals/
            "site_id": "",            # netlify mode
            "dest": "",               # folder mode
        },
    },
}


def _deep_merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def load_config(path: str | Path | None) -> dict:
    if path is None:
        return copy.deepcopy(DEFAULTS)
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"config not found: {p}")
    user = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    if not isinstance(user, dict):
        raise ValueError(f"config must be a mapping, got {type(user).__name__}")
    return _deep_merge(DEFAULTS, user)
