from __future__ import annotations

import abc
from dataclasses import dataclass
from typing import Iterator, Optional


@dataclass
class RawListing:
    source: str
    listing_id: str
    title: str
    url: str
    price_eur: Optional[float] = None
    shipping_eur: Optional[float] = None
    description: str = ""
    location: str = ""
    posted_at: Optional[str] = None
    condition_hint: str = ""
    image_url: str = ""

    @property
    def text(self) -> str:
        return f"{self.title}\n{self.description}\n{self.condition_hint}"


class Source(abc.ABC):
    name = "base"

    def __init__(self, cfg: dict | None = None):
        self.cfg = cfg or {}

    @abc.abstractmethod
    def search(self, query: str) -> Iterator[RawListing]:
        """Yield listings for a single search term."""
        raise NotImplementedError
