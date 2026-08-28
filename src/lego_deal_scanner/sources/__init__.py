"""Marketplace sources. Built lazily so a missing optional dep only breaks
the source that needs it, not the whole run."""
from __future__ import annotations

import logging

from .base import RawListing, Source

log = logging.getLogger(__name__)

__all__ = ["RawListing", "Source", "build_sources", "SOURCE_NAMES"]

SOURCE_NAMES = ("fixture", "kleinanzeigen", "ebay_de")


def build_sources(sources_cfg: dict, only: str | None = None) -> list[Source]:
    out: list[Source] = []
    for name, cfg in (sources_cfg or {}).items():
        if only and name != only:
            continue
        if not cfg or not cfg.get("enabled"):
            continue
        try:
            out.append(_make(name, cfg))
        except Exception as exc:  # noqa: BLE001
            log.warning("skipping source %r: %s", name, exc)
    return out


def _make(name: str, cfg: dict) -> Source:
    if name == "fixture":
        from .fixture import FixtureSource

        return FixtureSource(cfg)
    if name == "kleinanzeigen":
        from .kleinanzeigen import KleinanzeigenSource

        return KleinanzeigenSource(cfg)
    if name == "ebay_de":
        from .ebay_de import EbayDeSource

        return EbayDeSource(cfg)
    raise ValueError(f"unknown source: {name}")
