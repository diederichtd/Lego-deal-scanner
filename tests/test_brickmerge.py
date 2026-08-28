import copy

import pytest

from lego_deal_scanner.config import DEFAULTS
from lego_deal_scanner.retail.brickmerge import parse
from lego_deal_scanner.retail.run import run_watch
from lego_deal_scanner.store import Store

PAGE_71043 = """<html><head>
<title>LEGO® Harry Potter 71043 Schloss Hogwarts Preisvergleich ab 353,00 € / 25% gespart</title>
</head><body>
LEGO Harry Potter 71043 kostet aktuell ab 353,00 € (zzgl. Versand). Ersparnis 116,99 € (25%) statt UVP 469,99 €
akt. UVP: 469,99 € (7,81 ct/Teil)
30 Tage Bestpreis: 341,23 € / 27% vor 11 Tagen
brickmerge LEGO Deal-Score: 65/100
</body></html>"""

PAGE_10255 = """<html><head><title>LEGO Creator 10255 Assembly Square Preisvergleich ab 225,60 € / 25% gespart</title></head>
<body>10255 kostet aktuell ab 225,60 € statt UVP 229,99 €. Deal-Score: 40</body></html>"""


class FakeFetcher:
    def __init__(self, mapping):
        self.mapping = mapping

    def get(self, url):
        return self.mapping.get(url)


def test_parse_pulls_best_uvp_score():
    bp = parse(PAGE_71043, "71043", "u")
    assert bp.best_eur == 353.0
    assert bp.uvp_eur == 469.99
    assert bp.best_30d_eur == 341.23
    assert bp.deal_score == 65


@pytest.fixture
def cfg(tmp_path):
    cat = tmp_path / "catalog.csv"
    cat.write_text(
        "set_num,name,rrp_eur,lego_url,retailer_urls,ebay_price_eur,ebay_sold\n"
        "71043,Hogwarts Castle,,,,409.99,1774\n"
        "10255,Assembly Square,,,,319.99,1645\n",
        encoding="utf-8",
    )
    c = copy.deepcopy(DEFAULTS)
    c["retail"]["catalog_csv"] = str(cat)
    c["retail"]["mydealz"]["enabled"] = False
    c["retail"]["http"]["min_delay_seconds"] = 0
    c["retail"]["brickmerge"]["enabled"] = True
    c["retail"]["min_flip_margin_eur"] = 15.0
    c["retail"]["min_discount_pct"] = 0.12
    c["store"]["path"] = str(tmp_path / "s.sqlite3")
    c["site"]["outdir"] = str(tmp_path / "site")
    return c


def test_brickmerge_flip_uses_ebay_price_column(cfg):
    fetch = FakeFetcher({
        "https://www.brickmerge.de/71043-1_x": PAGE_71043,
        "https://www.brickmerge.de/10255-1_x": PAGE_10255,
    })
    with Store(cfg["store"]["path"]) as store:
        result = run_watch(cfg, store, fetcher=fetch)

    by = {d["set_num"]: d for d in result["deals"]}
    # 10255: retail 225.60 vs your eBay 319.99 -> margin 94.39 -> flip
    assert "10255" in by
    assert by["10255"]["shop"] == "brickmerge"
    assert by["10255"]["margin_vs_ebay_eur"] == pytest.approx(94.39, abs=0.01)
    assert by["10255"]["lego_price_eur"] == 229.99            # UVP as reference
    # 71043: retail 353 vs eBay 409.99 -> margin 56.99 (> 15) -> also a flip
    assert "71043" in by
    assert by["71043"]["margin_vs_ebay_eur"] == pytest.approx(56.99, abs=0.01)
    # sorted by margin, biggest first
    assert [d["set_num"] for d in result["deals"][:2]] == ["10255", "71043"]


def test_brickmerge_no_flip_when_retail_not_below_ebay(cfg):
    fetch = FakeFetcher({
        "https://www.brickmerge.de/71043-1_x": PAGE_71043.replace("353,00", "402,00"),
        "https://www.brickmerge.de/10255-1_x": PAGE_10255.replace("225,60", "310,00"),
    })
    with Store(cfg["store"]["path"]) as store:
        result = run_watch(cfg, store, fetcher=fetch)
    # 71043 margin 7.99 (<15); 10255 margin 9.99 (<15) -> nothing actionable
    assert [d["set_num"] for d in result["deals"] if d["shop"] == "brickmerge"] == []
