"""Pull a price + availability out of a retail product page.

Order of attempts: JSON-LD (schema.org Product/Offer), microdata / meta tags,
then a loose regex. German shops are inconsistent, so we try hard and return
None rather than a wrong number.
"""
from __future__ import annotations

import json
import re
from typing import Optional

_JSONLD_RE = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.I | re.S,
)
_META_PRICE_RE = re.compile(
    r'<meta[^>]+(?:itemprop|property)=["\']'
    r'(?:product:price:amount|price)["\'][^>]+content=["\']([\d.,]+)["\']',
    re.I,
)
_LOOSE_PRICE_RE = re.compile(r'"(?:price|lowPrice)"\s*:\s*"?(\d{1,5}(?:[.,]\d{2})?)"?')
_AVAIL_RE = re.compile(
    r'availability["\'\s:]+[^>]*?'
    r'(InStock|OutOfStock|PreOrder|BackOrder|SoldOut|LimitedAvailability)',
    re.I,
)


def _to_float(raw: str) -> Optional[float]:
    s = raw.strip()
    if not s:
        return None
    # "1.299,00" -> 1299.00 ; "1299.00" -> 1299.00 ; "1299,00" -> 1299.00
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        v = float(s)
    except ValueError:
        return None
    return v if 1.0 <= v <= 100000.0 else None


def _walk_jsonld(node) -> tuple[Optional[float], Optional[str]]:
    """Return (price, availability) from a parsed JSON-LD node tree."""
    best_price: Optional[float] = None
    avail: Optional[str] = None
    stack = [node]
    while stack:
        cur = stack.pop()
        if isinstance(cur, list):
            stack.extend(cur)
            continue
        if not isinstance(cur, dict):
            continue
        for key in ("price", "lowPrice"):
            if key in cur:
                p = _to_float(str(cur[key]))
                if p is not None and (best_price is None or p < best_price):
                    best_price = p
        if "availability" in cur and isinstance(cur["availability"], str):
            m = re.search(
                r"(InStock|OutOfStock|PreOrder|BackOrder|SoldOut|LimitedAvailability)",
                cur["availability"], re.I,
            )
            if m:
                avail = m.group(1)
        stack.extend(v for v in cur.values() if isinstance(v, (dict, list)))
    return best_price, avail


def extract_price(html: str) -> dict:
    """{'price': float|None, 'available': bool|None, 'image': str|None, 'method': str}."""
    if not html:
        return {"price": None, "available": None, "image": None, "method": "empty"}

    for block in _JSONLD_RE.findall(html):
        try:
            data = json.loads(block.strip())
        except (json.JSONDecodeError, ValueError):
            continue
        price, avail = _walk_jsonld(data)
        if price is not None:
            return {
                "price": price,
                "available": _avail_bool(avail),
                "image": _first_image(data),
                "method": "json-ld",
            }

    m = _META_PRICE_RE.search(html)
    if m:
        price = _to_float(m.group(1))
        if price is not None:
            am = _AVAIL_RE.search(html)
            return {
                "price": price,
                "available": _avail_bool(am.group(1) if am else None),
                "image": _first_image_html(html),
                "method": "meta",
            }

    m = _LOOSE_PRICE_RE.search(html)
    if m:
        price = _to_float(m.group(1))
        if price is not None:
            am = _AVAIL_RE.search(html)
            return {
                "price": price,
                "available": _avail_bool(am.group(1) if am else None),
                "image": _first_image_html(html),
                "method": "regex",
            }

    return {"price": None, "available": None, "image": None, "method": "not-found"}


_OG_IMAGE_RE = re.compile(
    r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']', re.I,
)


def _first_image_html(html: str) -> Optional[str]:
    m = _OG_IMAGE_RE.search(html or "")
    return m.group(1) if m else None


def _first_image(node) -> Optional[str]:
    """Find an image URL anywhere in a JSON-LD node (str | [str] | {url|contentUrl})."""
    stack = [node]
    while stack:
        cur = stack.pop()
        if isinstance(cur, list):
            stack.extend(cur)
            continue
        if isinstance(cur, dict):
            img = cur.get("image")
            got = _coerce_image(img)
            if got:
                return got
            stack.extend(v for v in cur.values() if isinstance(v, (dict, list)))
    return None


def _coerce_image(img) -> Optional[str]:
    if isinstance(img, str) and img.startswith("http"):
        return img
    if isinstance(img, list):
        for x in img:
            got = _coerce_image(x)
            if got:
                return got
    if isinstance(img, dict):
        for k in ("url", "contentUrl", "@id"):
            v = img.get(k)
            if isinstance(v, str) and v.startswith("http"):
                return v
    return None


def _iter_products(node):
    """Yield every schema.org Product dict anywhere in a JSON-LD tree
    (walks ItemList / @graph / arbitrary nesting)."""
    stack = [node]
    while stack:
        cur = stack.pop()
        if isinstance(cur, list):
            stack.extend(cur)
            continue
        if not isinstance(cur, dict):
            continue
        t = cur.get("@type")
        types = t if isinstance(t, list) else [t]
        if "Product" in types and cur.get("name"):
            yield cur
        stack.extend(v for v in cur.values() if isinstance(v, (dict, list)))


def extract_products(html: str) -> list[dict]:
    """Pull every priced product off a listing / sale / category page.

    Returns [{'name', 'price', 'url', 'available'}]. Relies on JSON-LD, which
    most large German shops embed on category pages; returns [] if there's none.
    """
    if not html:
        return []
    out: list[dict] = []
    seen: set[tuple] = set()
    for block in _JSONLD_RE.findall(html):
        try:
            data = json.loads(block.strip())
        except (json.JSONDecodeError, ValueError):
            continue
        for prod in _iter_products(data):
            name = str(prod.get("name") or "").strip()
            price, avail = _walk_jsonld(prod)
            if not name or price is None:
                continue
            url = str(prod.get("url") or prod.get("@id") or "").strip()
            key = (name, price, url)
            if key in seen:
                continue
            seen.add(key)
            out.append({"name": name, "price": price, "url": url,
                        "available": _avail_bool(avail),
                        "image": _coerce_image(prod.get("image"))})
    return out


def _avail_bool(token: Optional[str]) -> Optional[bool]:
    if not token:
        return None
    t = token.lower()
    if t in {"instock", "limitedavailability", "preorder", "backorder"}:
        return True
    if t in {"outofstock", "soldout"}:
        return False
    return None
