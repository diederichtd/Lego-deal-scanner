from lego_deal_scanner.retail.site import render_html

BASE = {
    "generated_at": "28 Aug 12:00", "generated_ts": 1.0, "checked": 12,
    "threshold_pct": 0.12, "unverified": [], "errors": [], "lego_prices": {},
}


def _deal(**kw):
    d = dict(set_num="10300", name="Time Machine", shop="otto", shop_name="Otto.de",
             url="https://otto.de/p/10300", price_eur=149.99, lego_price_eur=199.99,
             saving_eur=50.0, saving_pct=0.25, available=True, state="new",
             source="sale-page", image_url="https://img.test/10300.png")
    d.update(kw)
    return d


def test_render_has_theme_toggle_and_update_button():
    html = render_html({**BASE, "deals": [_deal()]}, {"title": "t"})
    assert 'id="theme"' in html
    assert 'id="update"' in html
    assert 'id="auto"' in html
    assert 'id="since"' in html
    assert "lds-theme" in html and "lds-seen" in html   # localStorage keys in JS


def test_render_shows_photo_and_retailer_link():
    html = render_html({**BASE, "deals": [_deal()]}, {"title": "t"})
    assert 'src="https://img.test/10300.png"' in html
    assert 'href="https://otto.de/p/10300"' in html
    assert 'onerror="this.remove()"' in html


def test_seller_mode_shows_profit_resale_and_own_listing_link():
    d = _deal(ebay_price_eur=185.0, margin_vs_ebay_eur=35.01, net_profit_eur=18.0,
              resale_eur=185.0, resale_source="your listed price",
              ebay_url="https://www.ebay.de/itm/abc", verified=True, falling_days=3)
    html = render_html({**BASE, "deals": [d], "seller": "knoppers55"}, {"title": "t"})
    assert "knoppers55" in html
    assert "~&euro;18" in html and "profit" in html
    assert "sell ~&euro;185" in html
    assert 'href="https://www.ebay.de/itm/abc"' in html
    assert "in stock" in html and "falling 3d" in html
    assert "best single profit" in html   # tile label


def test_health_banner_when_scanner_looks_broken():
    html = render_html({**BASE, "deals": [], "health": "brickmerge parsed only 3/50 pages"},
                       {"title": "t"})
    assert "brickmerge parsed only 3/50" in html


def test_render_shows_coverage_and_uncovered_sets():
    html = render_html({
        **BASE, "deals": [_deal()], "seller": "knoppers55",
        "coverage": {"listed": 40, "priced": 37, "with_route": 33, "on_sale": 1},
        "uncovered": [{"set_num": "99999", "name": "Mystery", "reason": "no reference price"}],
    }, {"title": "t"})
    assert "Coverage:" in html
    assert "40" in html and "on sale" in html
    assert "not yet checked" in html.lower()
    assert "99999" in html


def test_render_without_js_still_lists_rows():
    html = render_html({**BASE, "deals": [_deal(), _deal(set_num="75355", shop="mueller")]},
                       {"title": "t"})
    assert html.count('class="row"') == 2
