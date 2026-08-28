import json

import pytest

from lego_deal_scanner.config import DEFAULTS
from lego_deal_scanner.retail.extract import extract_price, extract_products
from lego_deal_scanner.retail.mydealz import parse_feed
from lego_deal_scanner.retail.run import run_watch
from lego_deal_scanner.retail.site import build_site
from lego_deal_scanner.store import Store

LEGO_HTML = """<html><head>
<script type="application/ld+json">
{"@type":"Product","name":"Time Machine",
 "offers":{"@type":"Offer","price":"199.99","priceCurrency":"EUR",
 "availability":"https://schema.org/InStock"}}
</script></head><body>LEGO 10300</body></html>"""

OTTO_HTML = """<html><head>
<script type="application/ld+json">
{"@context":"https://schema.org","@type":"Product","offers":[
 {"@type":"Offer","price":"149.99","availability":"http://schema.org/InStock"}]}
</script></head><body>Otto</body></html>"""

OTTO_HTML_CHEAPER = OTTO_HTML.replace("149.99", "139.00")

META_HTML = '<meta property="product:price:amount" content="1.299,00">' \
            '<link itemprop="availability" href="https://schema.org/OutOfStock">'


class FakeFetcher:
    def __init__(self, mapping):
        self.mapping = mapping
        self.calls = []

    def get(self, url):
        self.calls.append(url)
        return self.mapping.get(url)


# --- extract ---------------------------------------------------------------
def test_extract_jsonld_price_and_stock():
    got = extract_price(LEGO_HTML)
    assert got["price"] == 199.99
    assert got["available"] is True
    assert got["method"] == "json-ld"


def test_extract_meta_german_format():
    got = extract_price(META_HTML)
    assert got["price"] == 1299.0
    assert got["available"] is False


def test_extract_picks_lowest_offer():
    assert extract_price(OTTO_HTML)["price"] == 149.99


def test_extract_gives_up_cleanly():
    assert extract_price("<html>no price here</html>")["price"] is None


# --- mydealz -------------------------------------------------------------
MYDEALZ_RSS = """<?xml version="1.0"?><rss><channel>
<item><title>LEGO Icons 10300 DeLorean für 139,99€ bei Otto</title>
<link>https://www.mydealz.de/deals/lego-10300-123</link>
<description>Händler: Otto - super Preis</description>
<pubDate>Wed, 27 Aug 2026 10:00:00 +0000</pubDate></item>
<item><title>LEGO 99999 Fantasieset 20€</title>
<link>https://www.mydealz.de/deals/x-456</link><description>abgelaufen</description></item>
</channel></rss>"""


def test_parse_feed_extracts_set_and_price():
    posts = parse_feed(MYDEALZ_RSS, known_sets={"10300"})
    assert posts[0].price_eur == 139.99
    assert "10300" in posts[0].set_nums
    assert posts[0].merchant.lower().startswith("otto")
    assert posts[1].expired is True


# --- full run ----------------------------------------------------------
@pytest.fixture
def cfg(tmp_path):
    import copy

    catalog = tmp_path / "catalog.csv"
    catalog.write_text(
        "set_num,name,rrp_eur,lego_url,retailer_urls\n"
        "10300,Time Machine,199.99,https://lego.test/10300,"
        "otto=https://otto.test/10300\n",
        encoding="utf-8",
    )
    c = copy.deepcopy(DEFAULTS)
    c["retail"]["catalog_csv"] = str(catalog)
    c["retail"]["mydealz"]["enabled"] = False
    c["retail"]["http"]["min_delay_seconds"] = 0
    c["store"]["path"] = str(tmp_path / "s.sqlite3")
    c["site"]["outdir"] = str(tmp_path / "site")
    return c


def test_run_watch_flags_below_lego_price(cfg):
    fetch = FakeFetcher({
        "https://lego.test/10300": LEGO_HTML,
        "https://otto.test/10300": OTTO_HTML,
    })
    with Store(cfg["store"]["path"]) as store:
        result = run_watch(cfg, store, fetcher=fetch)

    assert len(result["deals"]) == 1
    d = result["deals"][0]
    assert d["set_num"] == "10300"
    assert d["shop"] == "otto"
    assert d["price_eur"] == 149.99
    assert d["lego_price_eur"] == 199.99
    assert d["saving_eur"] == 50.0
    assert d["state"] == "new"


def test_run_watch_detects_price_drop_on_second_pass(cfg):
    with Store(cfg["store"]["path"]) as store:
        run_watch(cfg, store, fetcher=FakeFetcher({
            "https://lego.test/10300": LEGO_HTML,
            "https://otto.test/10300": OTTO_HTML,
        }))
        result = run_watch(cfg, store, fetcher=FakeFetcher({
            "https://lego.test/10300": LEGO_HTML,
            "https://otto.test/10300": OTTO_HTML_CHEAPER,
        }))
    assert result["deals"][0]["state"] == "price_drop"
    assert result["deals"][0]["price_eur"] == 139.0


def test_run_watch_no_deal_when_not_cheaper(cfg):
    fetch = FakeFetcher({
        "https://lego.test/10300": LEGO_HTML,
        "https://otto.test/10300": LEGO_HTML,  # same price
    })
    with Store(cfg["store"]["path"]) as store:
        result = run_watch(cfg, store, fetcher=fetch)
    assert result["deals"] == []


SALE_PAGE = """<html><head>
<script type="application/ld+json">
{"@context":"https://schema.org","@type":"ItemList","itemListElement":[
 {"@type":"ListItem","position":1,"item":{"@type":"Product",
   "name":"LEGO Icons 10300 Back to the Future Zeitmaschine",
   "url":"https://otto.test/p/10300",
   "offers":{"@type":"Offer","price":"149.99","availability":"https://schema.org/InStock"}}},
 {"@type":"ListItem","position":2,"item":{"@type":"Product",
   "name":"LEGO Ideas 21318 Baumhaus","url":"https://otto.test/p/21318",
   "offers":{"@type":"Offer","price":"189.99","availability":"https://schema.org/InStock"}}},
 {"@type":"ListItem","position":3,"item":{"@type":"Product",
   "name":"LEGO Star Wars 75192 Millennium Falcon","url":"https://otto.test/p/75192",
   "offers":{"@type":"Offer","price":"799.00"}}}
]}</script></head><body>Sale</body></html>"""


def test_extract_products_reads_itemlist():
    prods = extract_products(SALE_PAGE)
    names = {p["name"] for p in prods}
    assert len(prods) == 3
    p10300 = next(p for p in prods if "10300" in p["name"])
    assert p10300["price"] == 149.99
    assert p10300["url"] == "https://otto.test/p/10300"
    assert p10300["available"] is True


@pytest.fixture
def catalog_cfg(tmp_path):
    import copy

    catalog = tmp_path / "catalog.csv"
    catalog.write_text(
        "set_num,name,rrp_eur,lego_url,retailer_urls\n"
        "10300,Time Machine,199.99,,\n"
        "21318,Tree House,199.99,,\n",
        encoding="utf-8",
    )
    c = copy.deepcopy(DEFAULTS)
    c["retail"]["catalog_csv"] = str(catalog)
    c["retail"]["mydealz"]["enabled"] = False
    c["retail"]["http"]["min_delay_seconds"] = 0
    c["retail"]["sale_pages"] = {"otto": ["https://otto.test/sale"]}
    c["store"]["path"] = str(tmp_path / "s.sqlite3")
    c["site"]["outdir"] = str(tmp_path / "site")
    return c


def test_discovery_flags_only_sets_over_threshold(catalog_cfg):
    fetch = FakeFetcher({"https://otto.test/sale": SALE_PAGE})
    with Store(catalog_cfg["store"]["path"]) as store:
        result = run_watch(catalog_cfg, store, fetcher=fetch)

    assert len(result["deals"]) == 1
    d = result["deals"][0]
    assert d["set_num"] == "10300"          # 25% off -> kept
    assert d["source"] == "sale-page"
    assert d["shop"] == "otto"
    assert d["price_eur"] == 149.99
    # 21318 was only 5% off -> dropped; 75192 not in catalog -> dropped
    assert result["threshold_pct"] == 0.12


def test_build_site_writes_files(cfg):
    fetch = FakeFetcher({
        "https://lego.test/10300": LEGO_HTML,
        "https://otto.test/10300": OTTO_HTML,
    })
    with Store(cfg["store"]["path"]) as store:
        result = run_watch(cfg, store, fetcher=fetch)
    outdir = build_site(result, cfg["site"])

    index = (outdir / "index.html").read_text(encoding="utf-8")
    assert "10300" in index and "Otto" in index
    data = json.loads((outdir / "deals.json").read_text(encoding="utf-8"))
    assert data["deals"][0]["saving_eur"] == 50.0
    assert (outdir / "feed.xml").read_text(encoding="utf-8").startswith("<?xml")
