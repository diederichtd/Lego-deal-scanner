"""Known German LEGO retailers. Extraction is uniform (JSON-LD first); this is
mostly display metadata plus per-shop quirks/notes."""
from __future__ import annotations

import re
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


# brickmerge cloaks the real product link behind a /go2/ redirect that 403s when
# clicked from outside their site. So we send the user straight to the shop's own
# search for the set - lands on the product without the brickmerge detour.
_SHOP_SEARCH = {
    "proshop": "https://www.proshop.de/?s=LEGO+{n}",
    "amazon": "https://www.amazon.de/s?k=LEGO+{n}",
    "coolshop": "https://www.coolshop.de/suche/?q=LEGO+{n}",
    "alza": "https://www.alza.de/search.htm?exps=LEGO+{n}",
    "alternate": "https://www.alternate.de/listing.xhtml?q=LEGO%20{n}",
    "galeria": "https://www.galeria.de/search/?q=LEGO+{n}",
    "mueller": "https://www.mueller.de/search/?q=LEGO%20{n}",
    "müller": "https://www.mueller.de/search/?q=LEGO%20{n}",
    "otto": "https://www.otto.de/suche/lego-{n}/",
    "computersalg": "https://www.computersalg.de/search?search=LEGO+{n}",
    "toymi": "https://www.toymi.eu/search?sSearch=LEGO+{n}",
    "toymi.eu": "https://www.toymi.eu/search?sSearch=LEGO+{n}",
    "joybuy": "https://www.joybuy.com/search?keyword=LEGO%20{n}",
    "smyths": "https://www.smythstoys.com/de/de-de/search/?text=LEGO%20{n}",
    "thalia": "https://www.thalia.de/suche?sq=LEGO+{n}",
    "jb spielwaren": "https://www.jbspielwaren.de/index.php?cl=search&searchparam=LEGO+{n}",
    "steinehelden": "https://www.steinehelden.de/search?sSearch=LEGO+{n}",
    "holy brick": "https://holy-brick.de/search?sSearch=LEGO+{n}",
    "duo-shop": "https://www.duo-shop.de/search?sSearch=LEGO+{n}",
    "office-partner": "https://www.office-partner.de/search?sSearch=LEGO+{n}",
    "playzeug": "https://www.playzeug.de/search?sSearch=LEGO+{n}",
    "lucky bricks": "https://www.lucky-bricks.de/search?sSearch=LEGO+{n}",
}


def shop_product_url(merchant: str, set_num: str) -> str:
    """Fallback link when we can't resolve the exact product URL.

    A Google search for "LEGO <set> <shop>" - the first organic result is
    almost always the shop's own product page, so it's one click to the item
    and works for every shop, unlike each shop's clunky/bot-walled search.
    """
    m = re.sub(r"\s*\(.*?\)\s*", "", (merchant or "")).strip() or "kaufen"
    q = f"LEGO {set_num} {m}".replace(" ", "+")
    return f"https://www.google.com/search?q={q}"


def set_image(set_num: str, override: str | None = None) -> str:
    """A photo URL for a set. BrickLink's set image is a stable free fallback."""
    if override:
        return override
    return f"https://img.bricklink.com/ItemImage/SN/0/{set_num}-1.png"


def make_deal(set_num: str, name: str, shop_key: str, url: str, price: float,
              ref: float, available, state: str, source: str,
              image: str | None = None, shop_name: str | None = None,
              note: str | None = None) -> dict:
    shop = shop_for(shop_key)
    saving = round(ref - price, 2)
    return {
        "set_num": set_num,
        "name": name,
        "shop": shop_key,
        "shop_name": shop_name or shop.name,
        "note": note or "",
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
