from lego_deal_scanner.retail.site import render_html

BASE = {
    "generated_at": "29 Aug 09:00", "generated_ts": 1.0, "checked": 40,
    "threshold_pct": 0.12, "unverified": [], "errors": [], "lego_prices": {},
}


def _deal(**kw):
    d = dict(set_num="10300", name="Time Machine", shop="proshop", shop_name="Proshop",
             url="https://www.google.com/search?q=LEGO+10300+Proshop", price_eur=149.99,
             lego_price_eur=199.99, saving_eur=50.0, saving_pct=0.25, available=True,
             state="new", source="brickmerge", margin_vs_ebay_eur=35.0,
             net_profit_eur=None)
    d.update(kw)
    return d


def test_row_is_one_link_to_the_product_search():
    html = render_html({**BASE, "deals": [_deal()], "seller": "knoppers55"}, {"title": "t"})
    assert html.count('class="row"') == 1
    assert 'href="https://www.google.com/search?q=LEGO+10300+Proshop"' in html
    assert 'target="_blank"' in html
    assert "10300" in html and "Time Machine" in html and "Proshop" in html


def test_row_has_a_thumbnail():
    html = render_html({**BASE, "deals": [_deal()]}, {"title": "t"})
    assert 'class="thumb"' in html
    assert "img.bricklink.com/ItemImage/SN/0/10300-1.png" in html
    assert "onerror=" in html


def test_theme_toggle_present():
    html = render_html({**BASE, "deals": [_deal()]}, {"title": "t"})
    assert 'id="theme"' in html
    assert "lds-theme" in html
    assert 'data-theme="dark"' in html and 'data-theme="light"' in html  # CSS blocks


def test_simple_mode_says_under_not_profit():
    html = render_html({**BASE, "deals": [_deal()], "seller": "knoppers55"}, {"title": "t"})
    assert "&euro;35 <small>under</small>" in html
    assert "profit" not in html.lower()


def test_profit_mode_says_profit():
    html = render_html({**BASE, "deals": [_deal(net_profit_eur=18.0)], "seller": "x"},
                       {"title": "t"})
    assert "~&euro;18 <small>profit</small>" in html


def test_no_old_clutter():
    html = render_html({**BASE, "deals": [_deal()], "seller": "knoppers55"}, {"title": "t"})
    for gone in ('id="update"', 'Copy list', 'unconfirmed', 'stock-confirmed',
                 'class="chip"', 'class="tile"'):
        assert gone not in html


def test_empty_state():
    html = render_html({**BASE, "deals": []}, {"title": "t"})
    assert "Nothing cheaper" in html


def test_new_since_last_visit_present():
    html = render_html({**BASE, "deals": [_deal(), _deal(set_num="75355")]}, {"title": "t"})
    assert 'id="new"' in html and "'lds'" in html


def test_health_banner():
    html = render_html({**BASE, "deals": [], "health": "brickmerge parsed only 3/50"},
                       {"title": "t"})
    assert "brickmerge parsed only 3/50" in html
