"""Offline source that replays a bundled JSON file. Always works, no network."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterator

from .base import RawListing, Source


class FixtureSource(Source):
    name = "fixture"

    def __init__(self, cfg: dict | None = None):
        super().__init__(cfg)
        self.path = Path(self.cfg.get("path") or "data/fixture_listings.json")
        self._items = self._load()

    def _load(self) -> list[dict]:
        if not self.path.exists():
            raise FileNotFoundError(f"fixture file not found: {self.path}")
        data = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            raise ValueError("fixture file must be a JSON array of listings")
        return data

    def search(self, query: str) -> Iterator[RawListing]:
        terms = [t for t in query.lower().split() if t not in {"lego"}]
        for it in self._items:
            hay = f"{it.get('title', '')} {it.get('description', '')}".lower()
            if terms and not any(t in hay for t in terms):
                continue
            yield RawListing(
                source=self.name,
                listing_id=str(it["listing_id"]),
                title=it.get("title", ""),
                url=it.get("url", ""),
                price_eur=it.get("price_eur"),
                shipping_eur=it.get("shipping_eur"),
                description=it.get("description", ""),
                location=it.get("location", ""),
                posted_at=it.get("posted_at"),
                condition_hint=it.get("condition_hint", ""),
                image_url=it.get("image_url", ""),
            )
