"""Push deal alerts to a Discord/Slack-compatible incoming webhook."""
from __future__ import annotations

import json
import logging
import urllib.request

log = logging.getLogger(__name__)


def format_line(d: dict) -> str:
    return (
        f"[{d['verdict']}] {d['set_num']} {d['name']} ({d['condition']})\n"
        f"  ask EUR {d['asking_eur']:.0f} + ship {d['shipping_in_eur']:.0f}  ->  "
        f"net EUR {d['net_profit_eur']:.0f}  ROI {d['roi'] * 100:.0f}%  "
        f"(ref {d['resale_ref_eur']:.0f})\n"
        f"  {d.get('url', '')}"
    )


def send_webhook(url: str | None, deals: list[dict]) -> bool:
    if not url or not deals:
        return False
    body = "\n\n".join(format_line(d) for d in deals)
    body = "LEGO deal scan\n\n" + body
    payload = {"content": body[:1900], "text": body[:1900]}
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return 200 <= resp.status < 300
    except Exception as exc:  # noqa: BLE001
        log.warning("webhook post failed: %s", exc)
        return False
