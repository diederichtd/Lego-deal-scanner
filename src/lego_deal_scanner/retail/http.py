"""Polite HTTP fetcher: shared session, per-domain rate limit, retries."""
from __future__ import annotations

import logging
import time
from typing import Optional
from urllib.parse import urlsplit

log = logging.getLogger(__name__)

_DEFAULT_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0 Safari/537.36"
)


class Fetcher:
    def __init__(self, cfg: dict | None = None):
        cfg = cfg or {}
        self.ua = cfg.get("user_agent", _DEFAULT_UA)
        self.timeout = float(cfg.get("timeout", 20))
        self.min_delay = float(cfg.get("min_delay_seconds", 3.0))
        self.max_retries = int(cfg.get("max_retries", 2))
        self._last_hit: dict[str, float] = {}
        self._session = None

    def _get_session(self):
        if self._session is None:
            import requests

            self._session = requests.Session()
            self._session.headers.update(
                {
                    "User-Agent": self.ua,
                    "Accept-Language": "de-DE,de;q=0.9,en;q=0.5",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                }
            )
        return self._session

    def _throttle(self, host: str) -> None:
        last = self._last_hit.get(host, 0.0)
        wait = self.min_delay - (time.time() - last)
        if wait > 0:
            time.sleep(wait)
        self._last_hit[host] = time.time()

    def get(self, url: str) -> Optional[str]:
        try:
            import requests  # noqa: F401
        except ImportError:
            log.warning("retail fetch needs 'requests' installed")
            return None
        host = urlsplit(url).netloc
        session = self._get_session()
        for attempt in range(self.max_retries + 1):
            self._throttle(host)
            try:
                resp = session.get(url, timeout=self.timeout)
            except Exception as exc:  # noqa: BLE001
                log.warning("GET %s failed (%s/%s): %s", url, attempt + 1,
                            self.max_retries + 1, exc)
                continue
            if resp.status_code == 200:
                return resp.text
            if resp.status_code in (403, 429) or resp.status_code >= 500:
                log.warning("GET %s -> HTTP %s (attempt %s)", url, resp.status_code,
                            attempt + 1)
                time.sleep(2 * (attempt + 1))
                continue
            log.info("GET %s -> HTTP %s, giving up", url, resp.status_code)
            return None
        return None
