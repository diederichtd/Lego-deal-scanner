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


def test_parse_flags_foreign_amazon():
    body = ('Top-Angebot:<div class="topprice"><a href="/go2/?m=9&i=60367-1" '
            'title="Link zu amazon (FR) - 20,00 &euro; (20%) gespart - Preisangabe vom '
            '28.08., 12:00 Uhr: 71,89 &euro;*"><img alt="amazon (FR)"></a></div>')
    bp = parse(_page("x ab 71,89 &euro;", body), "60367", "u")
    assert bp.marketplace is True          # foreign Amazon = import -> skipped upstream


def test_run_skips_absurdly_low_price(cfg, tmp_path):
    # a "30er box" polybag priced at EUR 7.71 while the user sells the set for EUR 119
    cat = tmp_path / "cat2.csv"
    cat.write_text(
        "set_num,name,rrp_eur,lego_url,retailer_urls,ebay_price_eur,ebay_sold\n"
        "30727,TIE box,,,,119.70,50\n", encoding="utf-8")
    cfg["retail"]["catalog_csv"] = str(cat)
    bad = _page(
        "LEGO 30727 Preisvergleich ab 7,71 &euro;",
        '30727 kostet aktuell ab 7,71 &euro; statt UVP 15,00 &euro;. akt. UVP: 15,00 &euro;. '
        '<div class="topprice"><a href="/go2/?m=1&i=30727-1" '
        'title="Link zu toymi.eu - 2,00 &euro; (20%) gespart - Preisangabe vom 28.08., '
        '12:00 Uhr: 7,71 &euro;*"><img alt="toymi.eu"></a></div>',
    )
    fetch = FakeFetcher({"https://www.brickmerge.de/30727-1_x": bad})
    with Store(cfg["store"]["path"]) as store:
        result = run_watch(cfg, store, fetcher=fetch)
    assert result["deals"] == [] and (result.get("thin") or []) == []


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
    c["retail"]["profit_model"] = True
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


def test_simple_mode_shows_gap_not_profit(cfg):
    cfg["retail"]["profit_model"] = False          # "remove the profit thing"
    fetch = FakeFetcher({
        "https://www.brickmerge.de/75394-1_x": PAGE_75394,
        "https://www.brickmerge.de/10255-1_x": PAGE_10255,
    })
    with Store(cfg["store"]["path"]) as store:
        result = run_watch(cfg, store, fetcher=fetch)
    assert [d["set_num"] for d in result["deals"]] == ["75394"]
    d = result["deals"][0]
    assert d["net_profit_eur"] is None                       # no profit math
    assert d["margin_vs_ebay_eur"] == pytest.approx(57.74, abs=0.01)  # 156.74 - 99
    assert result["thin"] == []                              # no thin bucket in simple mode
