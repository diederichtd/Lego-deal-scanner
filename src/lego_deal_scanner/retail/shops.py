"""Known German LEGO retailers. Extraction is uniform (JSON-LD first); this is
mostly display metadata plus per-shop quirks/notes."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Shop:
    key: str
    name: str
    domain: str
    reliable: bool = True          # False -> often JS-only / bot-walled
    note: str = ""


SHOPS: dict[str, Shop] = {
    "lego": Shop("lego", "LEGO.de", "lego.com", reliable=True,
                 note="reference price; page is JS-heavy, JSON-LD usually present"),
    "otto": Shop("otto", "Otto.de", "otto.de"),
    "mueller": Shop("mueller", "Mueller.de", "mueller.de"),
    "thalia": Shop("thalia", "Thalia.de", "thalia.de"),
    "joybuy": Shop("joybuy", "Joybuy", "joybuy.com", reliable=False,
                   note="cross-border marketplace - non-EUR pricing and overseas "
                        "shipping/customs vary; treat prices with caution"),
    "smyths": Shop("smyths", "Smyths Toys", "smythstoys.com"),
    "proshop": Shop("proshop", "Proshop.de", "proshop.de"),
    "galeria": Shop("galeria", "Galeria.de", "galeria.de"),
    "amazon": Shop("amazon", "Amazon.de", "amazon.de", reliable=False,
                   note="scraping is unreliable and often blocked - use the "
                        "Product Advertising API (affiliate account) instead"),
    "mydealz": Shop("mydealz", "mydealz", "mydealz.de", reliable=True,
                    note="community deal feed - covers shops without a scraper"),
}


def shop_for(key: str) -> Shop:
    return SHOPS.get(key, Shop(key, key, key))


def set_image(set_num: str, override: str | None = None) -> str:
    """A photo URL for a set. BrickLink's set image is a stable free fallback."""
    if override:
        return override
    return f"https://img.bricklink.com/ItemImage/SN/0/{set_num}-1.png"


def make_deal(set_num: str, name: str, shop_key: str, url: str, price: float,
              ref: float, available, state: str, source: str,
              image: str | None = None) -> dict:
    shop = shop_for(shop_key)
    saving = round(ref - price, 2)
    return {
        "set_num": set_num,
        "name": name,
        "shop": shop_key,
        "shop_name": shop.name,
        "url": url,
        "price_eur": round(price, 2),
        "lego_price_eur": round(ref, 2),
        "saving_eur": saving,
        "saving_pct": round(saving / ref, 4) if ref else 0.0,
        "available": available,
        "state": state,
        "source": source,
        "image_url": set_image(set_num, image),
    }
