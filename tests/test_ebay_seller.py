import copy

import pytest

from lego_deal_scanner.config import DEFAULTS
from lego_deal_scanner.retail.ebay_seller import EbaySeller
from lego_deal_scanner.retail.run import run_watch
from lego_deal_scanner.store import Store


class FakeFetcher:
    def __init__(self, mapping):
        self.mapping = mapping

    def get(self, url):
        return self.mapping.get(url)


SALE_PAGE = """<html><head><script type="application/ld+json">
{"@type":"ItemList","itemListElement":[
 {"item":{"@type":"Product","name":"LEGO Icons 10300 Back to the Future",
   "url":"https://otto.test/p/10300","image":"https://img.test/10300.jpg",
   "offers":{"price":"149.99","availability":"https://schema.org/InStock"}}},
 {"item":{"@type":"Product","name":"LEGO Ideas 21318 Baumhaus",
   "url":"https://otto.test/p/21318",
   "offers":{"price":"150.00","availability":"https://schema.org/InStock"}}}
]}</script></head><body>x</body></html>"""


def test_listings_dedupe_by_set_and_extract_number(monkeypatch):
    raw = [
        {"title": "LEGO Icons 10300 DeLorean NEU OVP", "price": 189.0,
         "url": "https://ebay.de/itm/1", "condition": "Neu", "quantity": 2},
        {"title": "LEGO 10300 Back to the Future gebraucht", "price": 150.0,
         "url": "https://ebay.de/itm/2", "condition": "Gebraucht", "quantity": 1},
        {"title": "LEGO Star Wars 75355 X-Wing Starfighter", "price": 210.0,
         "url": "https://ebay.de/itm/3", "condition": "Neu", "quantity": None},
        {"title": "LEGO Konvolut 5 kg gemischt", "price": 40.0,
         "url": "https://ebay.de/itm/4", "condition": "", "quantity": None},
    ]
    monkeypatch.setattr(EbaySeller, "_browse", lambda self, known: raw)
    seller = EbaySeller({"seller": "knoppers55", "mode": "browse_api"})
    got = {x.set_num: x for x in seller.listings({"10300", "75355", "21318"})}

    assert set(got) == {"10300", "75355"}         # konvolut has no set number
    assert got["10300"].ebay_price_eur == 150.0   # cheaper of the two 10300 rows
    assert got["75355"].url == "https://ebay.de/itm/3"


@pytest.fixture
def seller_cfg(tmp_path):
    catalog = tmp_path / "catalog.csv"
    catalog.write_text(
        "set_num,name,rrp_eur,lego_url,retailer_urls\n"
        "10300,Time Machine,199.99,,\n"
        "21318,Tree House,199.99,,\n"
        "75355,X-Wing,239.99,,\n",
        encoding="utf-8",
    )
    c = copy.deepcopy(DEFAULTS)
    c["retail"]["catalog_csv"] = str(catalog)
    c["retail"]["mydealz"]["enabled"] = False
    c["retail"]["http"]["min_delay_seconds"] = 0
    c["retail"]["sale_pages"] = {"otto": ["https://otto.test/sale"]}
    c["retail"]["ebay_seller"] = {"enabled": True, "seller": "knoppers55",
                                  "mode": "browse_api", "require_below_ebay": False}
    c["store"]["path"] = str(tmp_path / "s.sqlite3")
    c["site"]["outdir"] = str(tmp_path / "site")
    return c


def test_watch_restricts_to_seller_inventory_and_adds_margin(seller_cfg, monkeypatch):
    monkeypatch.setattr(EbaySeller, "_browse", lambda self, known: [
        {"title": "LEGO 10300 DeLorean Zeitmaschine", "price": 185.0,
         "url": "https://ebay.de/itm/aa", "condition": "Neu", "quantity": 1},
    ])
    fetch = FakeFetcher({"https://otto.test/sale": SALE_PAGE})
    with Store(seller_cfg["store"]["path"]) as store:
        result = run_watch(seller_cfg, store, fetcher=fetch)

    assert result["seller"] == "knoppers55"
    # 21318 is on sale too but the seller doesn't list it -> excluded
    assert [d["set_num"] for d in result["deals"]] == ["10300"]
    d = result["deals"][0]
    assert d["ebay_price_eur"] == 185.0
    assert d["margin_vs_ebay_eur"] == pytest.approx(35.01, abs=0.01)
    assert d["ebay_url"] == "https://ebay.de/itm/aa"
    assert d["image_url"] == "https://img.test/10300.jpg"
    # coverage: the one set the seller lists was reachable and priced
    assert result["coverage"] == {"listed": 1, "priced": 1, "with_route": 1, "on_sale": 1}
    assert result["uncovered"] == []


def test_coverage_flags_seller_sets_without_a_reference_price(seller_cfg, monkeypatch):
    monkeypatch.setattr(EbaySeller, "_browse", lambda self, known: [
        {"title": "LEGO 10300 DeLorean", "price": 180.0, "url": "https://ebay.de/itm/a",
         "condition": "Neu", "quantity": 1},
        {"title": "LEGO 99999 Some Set I List But You Don't Track", "price": 60.0,
         "url": "https://ebay.de/itm/b", "condition": "Neu", "quantity": 1},
    ])
    fetch = FakeFetcher({"https://otto.test/sale": SALE_PAGE})
    with Store(seller_cfg["store"]["path"]) as store:
        result = run_watch(seller_cfg, store, fetcher=fetch)

    assert result["coverage"]["listed"] == 2
    assert result["coverage"]["priced"] == 1
    reasons = {u["set_num"]: u["reason"] for u in result["uncovered"]}
    assert "99999" in reasons and "reference price" in reasons["99999"]


def test_require_below_ebay_filters_thin_margins(seller_cfg, monkeypatch):
    # seller prices 10300 UNDER the retailer sale price -> no arbitrage
    monkeypatch.setattr(EbaySeller, "_browse", lambda self, known: [
        {"title": "LEGO 10300 DeLorean", "price": 120.0, "url": "https://ebay.de/itm/aa",
         "condition": "Neu", "quantity": 1},
    ])
    seller_cfg["retail"]["ebay_seller"]["require_below_ebay"] = True
    fetch = FakeFetcher({"https://otto.test/sale": SALE_PAGE})
    with Store(seller_cfg["store"]["path"]) as store:
        result = run_watch(seller_cfg, store, fetcher=fetch)
    assert result["deals"] == []
