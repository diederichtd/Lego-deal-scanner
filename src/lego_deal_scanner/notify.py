"""Push deal alerts to a Discord/Slack-compatible incoming webhook."""
from __future__ import annotations

import json
import logging
import ssl
import urllib.request

log = logging.getLogger(__name__)


def _post(url: str, payload: dict) -> bool:
    """POST JSON. Prefer requests (bundles CA certs); fall back to urllib."""
    data = json.dumps(payload).encode("utf-8")
    try:
        import requests

        r = requests.post(url, json=payload, timeout=15)
        return 200 <= r.status_code < 300
    except ImportError:
        pass
    except Exception as exc:  # noqa: BLE001
        log.warning("webhook post failed: %s", exc)
        return False
    try:
        ctx = ssl.create_default_context()
        try:
            import certifi

            ctx.load_verify_locations(certifi.where())
        except Exception:  # noqa: BLE001
            pass
        req = urllib.request.Request(
            url, data=data, headers={"Content-Type": "application/json"}, method="POST"
        )
        with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
            return 200 <= resp.status < 300
    except Exception as exc:  # noqa: BLE001
        log.warning("webhook post failed: %s", exc)
        return False


def format_line(d: dict) -> str:
    return (
        f"[{d['verdict']}] {d['set_num']} {d['name']} ({d['condition']})\n"
        f"  ask EUR {d['asking_eur']:.0f} + ship {d['shipping_in_eur']:.0f}  ->  "
        f"net EUR {d['net_profit_eur']:.0f}  ROI {d['roi'] * 100:.0f}%  "
        f"(ref {d['resale_ref_eur']:.0f})\n"
        f"  {d.get('url', '')}"
    )


def send_digest(url: str | None, result: dict, top: int = 12) -> bool:
    """One summary message with the current flip list (state-independent).

    Use this for scheduled runs that start from a clean store every time -
    avoids re-alerting every deal on every run.
    """
    if not url:
        return False
    deals = result.get("deals") or []
    seller = result.get("seller") or "your catalogue"
    when = result.get("generated_at", "")
    head = f":warning: {result['health']}\n\n" if result.get("health") else ""

    thin_n = len(result.get("thin") or [])
    if not deals:
        extra = (f" {thin_n} thin-margin ones on the page." if thin_n else "")
        body = (head + f"LEGO flip watch ({when}) - {result.get('checked', 0)} sets "
                f"checked, no clear-profit flips right now.{extra}")
    else:
        lines = []
        for d in deals[:top]:
            net = d.get("net_profit_eur")
            gain = (f"~EUR {net:.0f} profit" if net is not None
                    else (f"EUR {d['margin_vs_ebay_eur']:.0f} under your price"
                          if d.get("margin_vs_ebay_eur") is not None else ""))
            flags = []
            if d.get("verified") is True:
                flags.append("in stock")
            if (d.get("falling_days") or 0) >= 2:
                flags.append(f"falling {d['falling_days']}d")
            tag = f"  [{', '.join(flags)}]" if flags else ""
            sell = d.get("resale_eur") or d.get("ebay_price_eur") or 0
            lines.append(
                f"- {d['set_num']} {d['name'][:38]}\n"
                f"  buy EUR {d['price_eur']:.0f} at {d.get('shop_name', d['shop'])} "
                f"-> {gain}  (sell ~EUR {sell:.0f}, {d.get('resale_source', '')}){tag}\n"
                f"  {d['url']}"
            )
        more = f"\n...and {len(deals) - top} more" if len(deals) > top else ""
        if thin_n:
            more += f"\n+ {thin_n} thin-margin ones on the page"
        body = (head + f"LEGO flip watch ({when})\n{len(deals)} of {seller}'s sets worth "
                f"buying to re-sell - {result.get('checked', 0)} checked\n\n"
                + "\n".join(lines) + more)
    return _post(url, {"content": body[:1950], "text": body[:1950]})


def send_webhook(url: str | None, deals: list[dict]) -> bool:
    if not url or not deals:
        return False
    body = "LEGO deal scan\n\n" + "\n\n".join(format_line(d) for d in deals)
    return _post(url, {"content": body[:1900], "text": body[:1900]})
