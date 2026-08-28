"""SQLite persistence: dedupe listings, keep price history, log deals."""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Optional

_SCHEMA = """
CREATE TABLE IF NOT EXISTS listings (
    source TEXT NOT NULL,
    listing_id TEXT NOT NULL,
    title TEXT,
    url TEXT,
    price REAL,
    first_seen REAL,
    last_seen REAL,
    PRIMARY KEY (source, listing_id)
);
CREATE TABLE IF NOT EXISTS price_history (
    source TEXT NOT NULL,
    listing_id TEXT NOT NULL,
    ts REAL NOT NULL,
    price REAL
);
CREATE TABLE IF NOT EXISTS deals (
    ts REAL NOT NULL,
    source TEXT NOT NULL,
    listing_id TEXT NOT NULL,
    set_num TEXT,
    verdict TEXT,
    net_profit REAL,
    roi REAL,
    payload TEXT
);
CREATE TABLE IF NOT EXISTS retail_prices (
    shop TEXT NOT NULL,
    set_num TEXT NOT NULL,
    ts REAL NOT NULL,
    price REAL,
    available INTEGER,
    PRIMARY KEY (shop, set_num)
);
CREATE TABLE IF NOT EXISTS retail_history (
    shop TEXT NOT NULL,
    set_num TEXT NOT NULL,
    ts REAL NOT NULL,
    price REAL,
    available INTEGER
);
CREATE TABLE IF NOT EXISTS sold_cache (
    set_num TEXT PRIMARY KEY,
    ts REAL NOT NULL,
    median REAL,
    count INTEGER,
    low REAL,
    high REAL
);
"""


class Store:
    def __init__(self, path: str | Path = "data/scanner.sqlite3"):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path)
        self.db.executescript(_SCHEMA)
        self.db.commit()

    def close(self) -> None:
        self.db.close()

    def __enter__(self) -> "Store":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def seen_state(self, source: str, listing_id: str, price: Optional[float]) -> str:
        """Record the sighting and report 'new' | 'price_changed' | 'seen'."""
        now = time.time()
        cur = self.db.execute(
            "SELECT price FROM listings WHERE source=? AND listing_id=?",
            (source, listing_id),
        )
        row = cur.fetchone()
        if row is None:
            self.db.execute(
                "INSERT INTO listings (source, listing_id, price, first_seen, last_seen) "
                "VALUES (?,?,?,?,?)",
                (source, listing_id, price, now, now),
            )
            self._history(source, listing_id, price, now)
            self.db.commit()
            return "new"

        old_price = row[0]
        self.db.execute(
            "UPDATE listings SET last_seen=?, price=? WHERE source=? AND listing_id=?",
            (now, price, source, listing_id),
        )
        changed = price is not None and old_price is not None and abs(price - old_price) > 0.001
        if changed:
            self._history(source, listing_id, price, now)
        self.db.commit()
        return "price_changed" if changed else "seen"

    def _history(self, source: str, listing_id: str, price: Optional[float], ts: float) -> None:
        self.db.execute(
            "INSERT INTO price_history (source, listing_id, ts, price) VALUES (?,?,?,?)",
            (source, listing_id, ts, price),
        )

    def record_retail_price(
        self, shop: str, set_num: str, price: Optional[float], available: Optional[bool]
    ) -> dict:
        """Store one shop/set price point. Returns {state, prev_price, prev_available}.

        state is one of: new, price_drop, price_rise, unchanged, back_in_stock,
        went_out_of_stock.
        """
        now = time.time()
        avail_int = None if available is None else int(bool(available))
        cur = self.db.execute(
            "SELECT price, available FROM retail_prices WHERE shop=? AND set_num=?",
            (shop, set_num),
        )
        row = cur.fetchone()
        self.db.execute(
            "INSERT INTO retail_history (shop, set_num, ts, price, available) VALUES (?,?,?,?,?)",
            (shop, set_num, now, price, avail_int),
        )
        if row is None:
            self.db.execute(
                "INSERT INTO retail_prices (shop, set_num, ts, price, available) VALUES (?,?,?,?,?)",
                (shop, set_num, now, price, avail_int),
            )
            self.db.commit()
            return {"state": "new", "prev_price": None, "prev_available": None}

        prev_price, prev_avail = row
        self.db.execute(
            "UPDATE retail_prices SET ts=?, price=?, available=? WHERE shop=? AND set_num=?",
            (now, price, avail_int, shop, set_num),
        )
        self.db.commit()

        state = "unchanged"
        if price is not None and prev_price is not None:
            if price < prev_price - 0.01:
                state = "price_drop"
            elif price > prev_price + 0.01:
                state = "price_rise"
        if prev_avail == 0 and avail_int == 1:
            state = "back_in_stock"
        elif prev_avail == 1 and avail_int == 0:
            state = "went_out_of_stock"
        return {"state": state, "prev_price": prev_price, "prev_available": prev_avail}

    def get_sold_cache(self, set_num: str, max_age_days: float) -> Optional[dict]:
        cur = self.db.execute(
            "SELECT ts, median, count, low, high FROM sold_cache WHERE set_num=?",
            (set_num,),
        )
        row = cur.fetchone()
        if not row:
            return None
        ts, median, count, low, high = row
        if (time.time() - ts) > max_age_days * 86400:
            return None
        return {"median": median, "count": count, "low": low, "high": high,
                "age_days": round((time.time() - ts) / 86400, 1)}

    def put_sold_cache(self, set_num: str, median, count, low, high) -> None:
        self.db.execute(
            "INSERT OR REPLACE INTO sold_cache (set_num, ts, median, count, low, high) "
            "VALUES (?,?,?,?,?,?)",
            (set_num, time.time(), median, count, low, high),
        )
        self.db.commit()

    def falling_days(self, shop: str, set_num: str) -> int:
        """How many consecutive days the recorded price has only gone down (or held)."""
        cur = self.db.execute(
            "SELECT ts, price FROM retail_history WHERE shop=? AND set_num=? "
            "AND price IS NOT NULL ORDER BY ts DESC LIMIT 60",
            (shop, set_num),
        )
        rows = cur.fetchall()
        if len(rows) < 2:
            return 0
        newest_ts = rows[0][0]
        prev = rows[0][1]
        for ts, price in rows[1:]:
            if price < prev - 0.01:          # older price was higher -> still falling
                prev = price
                continue
            if price <= prev + 0.01:         # equal-ish, keep looking back
                prev = price
                continue
            return max(0, int((newest_ts - ts) / 86400))
        return max(0, int((newest_ts - rows[-1][0]) / 86400))

    def price_history(self, set_num: str, limit: int = 40) -> list[dict]:
        cur = self.db.execute(
            "SELECT ts, shop, price FROM retail_history WHERE set_num=? AND price IS NOT NULL "
            "ORDER BY ts DESC LIMIT ?",
            (set_num, limit),
        )
        return [{"ts": ts, "shop": shop, "price": price}
                for ts, shop, price in reversed(cur.fetchall())]

    def record_deal(self, source: str, listing_id: str, deal_dict: dict) -> None:
        self.db.execute(
            "INSERT INTO deals (ts, source, listing_id, set_num, verdict, net_profit, roi, payload) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (
                time.time(),
                source,
                listing_id,
                deal_dict.get("set_num"),
                deal_dict.get("verdict"),
                deal_dict.get("net_profit_eur"),
                deal_dict.get("roi"),
                json.dumps(deal_dict, ensure_ascii=False),
            ),
        )
        self.db.commit()
