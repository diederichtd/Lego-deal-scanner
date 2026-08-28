import copy
from pathlib import Path

import pytest

from lego_deal_scanner.config import DEFAULTS
from lego_deal_scanner.cli import run_scan
from lego_deal_scanner.store import Store

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def cfg(tmp_path):
    c = copy.deepcopy(DEFAULTS)
    c["watchlist"] = ["lego"]
    c["sources"]["fixture"]["enabled"] = True
    c["sources"]["fixture"]["path"] = str(ROOT / "data" / "fixture_listings.json")
    c["valuation"]["reference_csv"] = str(ROOT / "data" / "reference_prices.csv")
    c["store"]["path"] = str(tmp_path / "s.sqlite3")
    c["notify"]["json_out"] = str(tmp_path / "out.json")
    return c


def _by_set(result):
    out = {}
    for d in result["deals"]:
        out.setdefault(d["set_num"], d["verdict"])
    return out


def test_fixture_scan_finds_expected_deals(cfg, tmp_path):
    with Store(cfg["store"]["path"]) as store:
        result = run_scan(cfg, store, only_source="fixture")

    verdicts = _by_set(result)
    # two clearly underpriced sealed DeLoreans
    assert verdicts.get("10300") == "DEAL"
    # underpriced sealed Colosseum
    assert verdicts.get("10276") == "DEAL"
    # used sets priced for a thin margin -> WATCH, not DEAL
    assert verdicts.get("75192") == "WATCH"
    # sealed Lambo listed above market -> never surfaces
    assert "42115" not in verdicts
    # kilo lot with no set number -> unvalued, not a deal
    assert any("Konvolut" in u["title"] for u in result["unvalued"])


def test_new_only_filters_second_pass(cfg):
    with Store(cfg["store"]["path"]) as store:
        first = run_scan(cfg, store, only_source="fixture")
        assert first["deals"]
        second = run_scan(cfg, store, only_source="fixture", new_only=True)
    assert second["deals"] == []


def test_incomplete_set_is_discounted(cfg):
    with Store(cfg["store"]["path"]) as store:
        result = run_scan(cfg, store, only_source="fixture")
    # 21330 Home Alone listed with "Teile fehlen" -> valued low, should not be a DEAL
    assert _by_set(result).get("21330") != "DEAL"
