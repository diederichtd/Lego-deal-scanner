from lego_deal_scanner.classify import detect_condition
from lego_deal_scanner.scoring import ScoreConfig, score
from lego_deal_scanner.valuation import Reference

CFG = ScoreConfig.from_dict(
    {
        "marketplace_fee_pct": 0.11,
        "packaging_eur": 1.20,
        "resale_haircut_pct": 0.08,
        "assumed_shipping_in_eur": 5.49,
        "default_shipping_out_eur": 6.99,
        "shipping_out_by_weight": {1000: 4.99, 2000: 5.99, 5000: 6.99, 31500: 10.49},
        "min_profit_eur": 20.0,
        "min_roi": 0.30,
        "watch_roi": 0.15,
    }
)

REF = Reference(set_num="10300", name="Time Machine", rrp_eur=199.99,
                mv_new_eur=215, mv_used_eur=150, weight_g=1600)


def test_cheap_sealed_set_is_a_deal():
    d = score(REF, "new_sealed", asking_eur=120.0, shipping_in_eur=5.49, cfg=CFG)
    assert d.verdict == "DEAL"
    assert d.net_profit_eur > 20
    assert d.roi >= 0.30


def test_overpriced_set_is_skip():
    d = score(REF, "new_sealed", asking_eur=210.0, shipping_in_eur=5.49, cfg=CFG)
    assert d.verdict == "SKIP"
    assert d.net_profit_eur < 0


def test_weight_tier_selects_shipping():
    heavy = Reference(set_num="x", name="x", mv_new_eur=100, weight_g=9000)
    d = score(heavy, "new_sealed", asking_eur=10.0, shipping_in_eur=0.0, cfg=CFG)
    # 9000 g -> 31500 tier -> 10.49 outbound; costs = 92*0.11 + 10.49 + 1.20
    assert abs(d.selling_costs_eur - (92 * 0.11 + 10.49 + 1.20)) < 0.01


def test_unknown_condition_valued_as_used():
    d = score(REF, "unknown", asking_eur=50.0, shipping_in_eur=0.0, cfg=CFG)
    assert d.resale_ref_eur == 150
    assert "condition unknown - valued as used" in d.notes


def test_detect_condition():
    assert detect_condition("NEU OVP versiegelt") == "new_sealed"
    assert detect_condition("gebraucht, komplett") == "used_complete"
    assert detect_condition("neuwertig, einmal aufgebaut") == "used_complete"
    assert detect_condition("Teile fehlen leider") == "used_incomplete"
    assert detect_condition("LEGO 10300 DeLorean") == "unknown"
