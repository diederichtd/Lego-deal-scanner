import copy

import pytest

from lego_deal_scanner.config import DEFAULTS
from lego_deal_scanner.retail.brickmerge import parse
from lego_deal_scanner.retail.run import run_watch
from lego_deal_scanner.store import Store


def _page(title, body):
    return f"<html><head><title>{title}</title></head><body>{body}</body></html>"


TOP_SHOP = (
    '<p>Top-Angebot:</p><div class="topprice">'
    '<a href="/go2/?m=440&i=75394-1" rel="nofollow sponsored" class="tooltipster" '
    'target="_blank" title="Link zu Proshop.de - 40,99 &euro; (24%) gespart - '
    'Preisangabe vom 28.08., 19:41 Uhr: 99,00 &euro;* - der aktuelle Preis kann '
    'h&ouml;her sein.">'
    '<img src="/img/merchants/proshop.de_ico.gif" alt="Proshop.de" /></a></div>'
)
PAGE_75394 = _page(
    "LEGO Star Wars 75394 Imperialer Sternzerst&ouml;rer Preisvergleich ab 99,00 &euro; / 42% gespart",
    "75394 kostet aktuell ab 99,00 &euro; statt UVP 169,99 &euro;. akt. UVP: 169,99 &euro;. "
    "Deal-Score: 75 " + TOP_SHOP,
)

TOP_EBAY = (
    '<p>Top-Angebot:</p><div class="topprice">'
    '<a href="/index.php?find=10255-1&go2i=10255-1&go2m=332" '
    'onclick="setTimeout(function(){window.location.href=\'/go2/?m=332&i=10255-1\';},100);" '
    'rel="nofollow sponsored" class="tooltipster" target="_blank" '
    'title="Link zu eBay.de - 74,39 &euro; (25%) gespart - Preisangabe vom 28.08., '
    '19:41 Uhr: 225,60 &euro; + Versand 10,49 &euro;* - der aktuelle Preis kann h&ouml;her '
    'sein. Der genannten Preis gilt nur zusammen mit einem Gutscheincode!">'
    '<img src="/img/merchants/ebay.de_ico.gif" alt="eBay.de" /></a></div>'
)
PAGE_10255 = _page(
    "LEGO Creator 10255 Assembly Square Preisvergleich ab 225,60 &euro; / 25% gespart",
    "10255 kostet aktuell ab 225,60 &euro; statt UVP 299,99 &euro;. akt. UVP: 299,99 &euro;. "
    "Deal-Score: 80 " + TOP_EBAY,
)


class FakeFetcher:
    def __init__(self, mapping):
        self.mapping = mapping

    def get(self, url):
        return self.mapping.get(url)


def test_parse_reads_real_shop_offer():
    bp = parse(PAGE_75394, "75394", "u")
    assert bp.merchant == "Proshop.de"
    assert bp.best_eur == 99.0
    assert bp.offer_url == "https://www.brickmerge.de/go2/?m=440&i=75394-1"
    assert bp.uvp_eur == 169.99
    assert bp.deal_score == 75
    assert bp.coupon_only is False
    assert bp.marketplace is False
    assert "19:41" in bp.priced_at


def test_parse_flags_ebay_and_coupon_offer():
    bp = parse(PAGE_10255, "10255", "u")
    assert bp.merchant == "eBay.de"
    assert bp.marketplace is True          # -> caller skips it
    assert bp.coupon_only is True
    assert bp.best_eur == pytest.approx(236.09, abs=0.01)   # 225.60 + 10.49 shipping


@pytest.fixture
def cfg(tmp_path):
    cat = tmp_path / "catalog.csv"
    cat.write_text(
        "set_num,name,rrp_eur,lego_url,retailer_urls,ebay_price_eur,ebay_sold\n"
        "75394,Imperial Star Destroyer,,,,156.74,1086\n"
        "10255,Assembly Square,,,,294.39,1645\n",
        encoding="utf-8",
    )
    c = copy.deepcopy(DEFAULTS)
    c["retail"]["catalog_csv"] = str(cat)
    c["retail"]["mydealz"]["enabled"] = False
    c["retail"]["http"]["min_delay_seconds"] = 0
    c["retail"]["brickmerge"]["enabled"] = True
    c["retail"]["min_flip_margin_eur"] = 15.0
    c["retail"]["ebay_sold"]["enabled"] = False
    c["retail"]["verify_top_n"] = 0
    c["store"]["path"] = str(tmp_path / "s.sqlite3")
    c["site"]["outdir"] = str(tmp_path / "site")
    return c


def test_flip_reports_real_shop_and_skips_ebay(cfg):
    fetch = FakeFetcher({
        "https://www.brickmerge.de/75394-1_x": PAGE_75394,
        "https://www.brickmerge.de/10255-1_x": PAGE_10255,
    })
    with Store(cfg["store"]["path"]) as store:
        result = run_watch(cfg, store, fetcher=fetch)

    sets = [d["set_num"] for d in result["deals"]]
    assert "75394" in sets            # real Proshop offer, 99 vs eBay 156.74
    assert "10255" not in sets        # top offer was an eBay coupon listing -> skipped
    d = next(d for d in result["deals"] if d["set_num"] == "75394")
    assert d["shop_name"] == "Proshop.de"
    assert d["url"] == "https://www.brickmerge.de/go2/?m=440&i=75394-1"
    assert d["net_profit_eur"] is not None and d["net_profit_eur"] > 10
    assert d["resale_source"] == "your listed price"   # ebay_sold disabled in this cfg
    assert "verify at the shop" in d["note"]
