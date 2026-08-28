"""One pass: find catalog sets on sale below LEGO.de - via explicit retailer
URLs, shop sale-pages (discovery), and the mydealz feed. Optionally restrict the
output to the set numbers an eBay seller currently lists."""
from __future__ import annotations

import logging
import time
from typing import Optional

from ..store import Store
from .catalog import CatalogRow, load_catalog
from .discover import discover
from .economics import Economics, net_profit
from .http import Fetcher
from .extract import extract_price
from .ebay_sold import sold_value
from .mydealz import fetch_posts
from .shops import make_deal, shop_product_url
from .stockcheck import verify

log = logging.getLogger(__name__)


def _lego_price(row: CatalogRow, fetcher: Fetcher, want_lego: bool) -> tuple[Optional[float], str]:
    if want_lego and row.lego_url:
        html = fetcher.get(row.lego_url)
        got = extract_price(html or "")
        if got["price"] is not None:
            return got["price"], f"lego.de live ({got['method']})"
    if row.rrp_eur is not None:
        return row.rrp_eur, "catalog rrp_eur fallback"
    return None, "no reference price"


def _load_seller(rcfg: dict, by_set: dict, catalog: list, fetcher: Fetcher):
    """Returns (seller_name, {set_num: SellerListing}) or (None, {})."""
    scfg = rcfg.get("ebay_seller") or {}
    if not scfg.get("enabled") or not scfg.get("seller"):
        return None, {}
    from .ebay_seller import EbaySeller

    listings = EbaySeller(scfg).listings(set(by_set), fetcher)
    index = {x.set_num: x for x in listings}
    # make every set the seller lists watchable, even if not in catalog.csv
    for sn, x in index.items():
        if sn not in by_set:
            row = CatalogRow(set_num=sn, name=x.title[:70])
            by_set[sn] = row
            catalog.append(row)
    return scfg.get("seller"), index


def run_watch(cfg: dict, store: Store, fetcher: Optional[Fetcher] = None) -> dict:
    rcfg = cfg["retail"]
    catalog = load_catalog(rcfg["catalog_csv"])
    by_set = {r.set_num: r for r in catalog}
    fetcher = fetcher or Fetcher(rcfg.get("http"))

    enabled = set(rcfg.get("shops_enabled") or [])
    amazon_ok = bool((rcfg.get("amazon") or {}).get("enabled"))
    min_saving = float(rcfg.get("min_saving_eur", 1.0))
    min_pct = float(rcfg.get("min_discount_pct", 0.0))
    min_price = float(rcfg.get("min_price_eur", 0.0))
    min_flip = float(rcfg.get("min_flip_margin_eur", 15.0))
    bmcfg = rcfg.get("brickmerge") or {}
    brickmerge_on = bool(bmcfg.get("enabled"))

    seller_name, seller_ix = _load_seller(rcfg, by_set, catalog, fetcher)
    known = set(by_set)

    deals: list[dict] = []
    checked = 0
    errors: list[dict] = []
    lego_prices: dict[str, dict] = {}
    seen_urls: set[str] = set()

    def keep(ref: float, price: float) -> bool:
        saving = ref - price
        return (price >= min_price and saving >= min_saving
                and (saving / ref if ref else 0.0) >= min_pct)

    # 1) reference prices + explicit per-retailer URLs -------------------------
    for row in catalog:
        ref, ref_src = _lego_price(row, fetcher, "lego" in enabled)
        lego_prices[row.set_num] = {"name": row.name, "price": ref, "source": ref_src,
                                    "url": row.lego_url}
        if ref is None:
            if not brickmerge_on:
                errors.append({"set_num": row.set_num, "name": row.name,
                               "reason": "no reference price - add rrp_eur (or enable brickmerge)"})
            continue
        store.record_retail_price("lego", row.set_num, ref, True)

        for shop_key, url in row.retailer_urls.items():
            if shop_key not in enabled or (shop_key == "amazon" and not amazon_ok):
                continue
            got = extract_price(fetcher.get(url) or "")
            price, avail = got["price"], got["available"]
            state = store.record_retail_price(shop_key, row.set_num, price, avail)["state"]
            checked += 1
            if price is None:
                errors.append({"set_num": row.set_num, "name": row.name, "shop": shop_key,
                               "url": url, "reason": f"could not read price ({got['method']})"})
                continue
            if keep(ref, price):
                deal = make_deal(row.set_num, row.name, shop_key, url, price, ref, avail,
                                 state, "retailer", image=row.image_url or got.get("image"))
                deals.append(deal)
                seen_urls.add(url)
                store.record_deal(shop_key, url, {"verdict": "RETAIL_DEAL", **deal})

    # 2) discovery: scrape each shop's LEGO sale pages -----------------------
    disc = discover(rcfg.get("sale_pages") or {}, fetcher, by_set, lego_prices, store,
                    enabled=enabled, min_pct=min_pct, min_price=min_price,
                    seen_urls=seen_urls)
    for d in disc:
        deals.append(d)
        store.record_deal(d["shop"], d["url"], {"verdict": "RETAIL_DEAL", **d})
    checked += len(disc)

    # 2.5) brickmerge aggregator: one fetch per set = all German shops -------
    bm_total = bm_ok = 0
    if brickmerge_on:
        from .brickmerge import fetch as bm_fetch

        cap = int(bmcfg.get("max_sets", 120))
        min_score = int(bmcfg.get("min_deal_score", 0))
        order = sorted(catalog, key=lambda r: -(r.sold or 0))
        for row in order[:cap]:
            bp = bm_fetch(row.set_num, fetcher)
            checked += 1
            bm_total += 1
            if not bp or bp.best_eur is None:
                continue
            bm_ok += 1
            if bp.marketplace or bp.coupon_only:
                # not a plain buy-from-a-shop price (eBay listing / coupon-only) - skip
                continue
            ref = ((lego_prices.get(row.set_num) or {}).get("price")
                   or bp.uvp_eur or row.rrp_eur or row.ebay_price_eur or bp.best_eur)
            if not ref:
                continue
            lego_prices.setdefault(row.set_num,
                                   {"name": row.name, "url": bp.url})["price"] = ref
            state = store.record_retail_price("brickmerge", row.set_num,
                                              bp.best_eur, True)["state"]
            if bp.url in seen_urls:
                continue
            ep = row.ebay_price_eur
            ref_for_sanity = ep or ref
            if ref_for_sanity and bp.best_eur < ref_for_sanity * 0.30:
                # a price this far below the sale value is a parse error, a single
                # polybag priced as a "30er Box", or a wrong SKU match - not a deal
                log.info("brickmerge: %s EUR %.2f is <30%% of EUR %.2f - skipping as bad data",
                         row.set_num, bp.best_eur, ref_for_sanity)
                continue
            if ep is not None:
                # you told us your selling price: only flag a real buy-to-resell margin
                take = (ep - bp.best_eur) >= min_flip
            else:
                score_ok = not min_score or (bp.deal_score or 0) >= min_score
                take = keep(ref, bp.best_eur) and score_ok
            if not take:
                continue
            link = shop_product_url(bp.merchant, row.set_num) if bp.merchant else bp.url
            note = (f"{bp.merchant} had it cheapest as of {bp.priced_at} - "
                    f"confirm the set + price on the shop page") if bp.priced_at else \
                   "confirm the set + price on the shop page"
            d = make_deal(row.set_num, row.name, "brickmerge",
                          link, bp.best_eur, ref, True, state,
                          "brickmerge", image=row.image_url,
                          shop_name=bp.merchant or "brickmerge", note=note)
            d["compare_url"] = bp.url        # brickmerge price list, as a backup
            d["deal_score"] = bp.deal_score
            if ep:
                d["ebay_price_eur"] = ep
                d["margin_vs_ebay_eur"] = round(ep - bp.best_eur, 2)
            deals.append(d)
            seen_urls.add(bp.url)
            store.record_deal("brickmerge", bp.url, {"verdict": "RETAIL_DEAL", **d})

    # 3) mydealz community feed -------------------------------------------
    unverified: list[dict] = []
    mcfg = rcfg.get("mydealz") or {}
    if mcfg.get("enabled"):
        for post in fetch_posts(mcfg.get("feeds") or [], fetcher, known):
            if post.expired or not post.price or post.url in seen_urls:
                continue
            matched = False
            for sn in post.set_nums:
                info = lego_prices.get(sn)
                ref = info["price"] if info else None
                if ref is None:
                    continue
                matched = True
                if keep(ref, post.price):
                    row = by_set.get(sn)
                    deal = make_deal(sn, row.name if row else info["name"],
                                     post.merchant or "mydealz", post.url, post.price, ref,
                                     None, "new", "mydealz",
                                     image=row.image_url if row else None)
                    deal["title"] = post.title
                    deals.append(deal)
                    seen_urls.add(post.url)
            if not matched:
                unverified.append({"title": post.title, "url": post.url,
                                   "price": post.price, "merchant": post.merchant,
                                   "set_nums": post.set_nums})

    # de-dupe (same set at same shop can arrive from two paths), best saving wins
    best: dict[tuple, dict] = {}
    for d in deals:
        k = (d["set_num"], d["shop"])
        if k not in best or d["saving_eur"] > best[k]["saving_eur"]:
            best[k] = d
    has_margin = any(d.get("margin_vs_ebay_eur") is not None for d in best.values())
    if has_margin:
        merged = sorted(best.values(),
                        key=lambda d: -(d.get("margin_vs_ebay_eur") or -1e9))
    else:
        merged = sorted(best.values(), key=lambda d: -d["saving_pct"])

    # 4) restrict to the seller's inventory + add arbitrage margin -----------
    if seller_name is not None:
        merged = [d for d in merged if d["set_num"] in seller_ix]
        for d in merged:
            x = seller_ix[d["set_num"]]
            d["ebay_price_eur"] = x.ebay_price_eur
            d["ebay_url"] = x.url
            d["ebay_condition"] = x.condition
            d["ebay_title"] = x.title
            if x.ebay_price_eur:
                d["margin_vs_ebay_eur"] = round(x.ebay_price_eur - d["price_eur"], 2)
        if (rcfg.get("ebay_seller") or {}).get("require_below_ebay"):
            merged = [d for d in merged if (d.get("margin_vs_ebay_eur") or 0) > 0]
        merged.sort(key=lambda d: -(d.get("margin_vs_ebay_eur") or d["saving_eur"]))

    # 5) enrich: eBay sold value, price trend, and (optionally) a net-profit model
    profit_on = bool(rcfg.get("profit_model", False))
    econ = Economics.from_dict(rcfg.get("economics"))
    sold_cfg = rcfg.get("ebay_sold") or {}
    min_solds = int(sold_cfg.get("min_solds", 2))
    min_net = float(rcfg.get("min_net_profit_eur", 0.0))
    priced = [d for d in merged if d.get("ebay_price_eur")]
    for d in priced:
        sv = sold_value(d["set_num"], fetcher, store, sold_cfg) if profit_on else None
        if sv and sv.get("median") and (sv.get("count") or 0) >= min_solds:
            resale = sv["median"]
            d["resale_source"] = f"eBay sold ~{sv['count']}x/{sold_cfg.get('days', 90)}d"
            d["sold_count"] = sv["count"]
        else:
            resale = d["ebay_price_eur"]
            d["resale_source"] = "your listed price"
            d["sold_count"] = sv["count"] if sv else None
        if profit_on:
            d.update(net_profit(resale, d["price_eur"], econ))
        else:
            d["net_profit_eur"] = None
            d["resale_eur"] = round(resale, 2)
        d["falling_days"] = store.falling_days(d["shop"], d["set_num"])

    if profit_on:
        _n = lambda d: d.get("net_profit_eur")
        kept = sorted((d for d in priced if _n(d) is not None and _n(d) >= min_net),
                      key=lambda d: -_n(d))
        thin = sorted((d for d in priced if _n(d) is not None and 0 <= _n(d) < min_net),
                      key=lambda d: -_n(d))
    else:
        # simple mode: everything that passed the min_flip_margin gate, biggest gap first
        kept = sorted(priced, key=lambda d: -(d.get("margin_vs_ebay_eur") or 0))
        thin = []

    # 6) verify the best N are actually in stock at that price
    for d in kept[: int(rcfg.get("verify_top_n", 0))]:
        v = verify(d["url"], d["price_eur"], fetcher)
        d["verified"] = v["ok"]
        d["verify_reason"] = v["reason"]
    live = [d for d in kept if d.get("verified") is not False]
    stale = [d for d in kept if d.get("verified") is False]

    merged = live if priced else merged

    health = None
    if bm_total >= 40 and (bm_ok / bm_total) < 0.35:
        health = (f"brickmerge parsed only {bm_ok}/{bm_total} pages - the site layout "
                  f"may have changed; results are unreliable this run")

    result = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M"),
        "generated_ts": time.time(),
        "checked": checked,
        "threshold_pct": min_pct,
        "deals": merged,
        "thin": thin,
        "stale": stale,
        "health": health,
        "brickmerge_ok": bm_ok,
        "brickmerge_total": bm_total,
        "unverified": [] if seller_name else unverified,
        "errors": errors,
        "lego_prices": lego_prices,
    }
    label = seller_name or rcfg.get("seller_label")
    if label:
        result["seller"] = label
    if seller_name:
        result["seller_set_count"] = len(seller_ix)
        result["coverage"], result["uncovered"] = _coverage(
            seller_ix, by_set, lego_prices, rcfg, enabled, amazon_ok, len(merged)
        )
    return result


def _coverage(seller_ix, by_set, lego_prices, rcfg, enabled, amazon_ok, on_sale):
    """Did we actually have a way to check every set the seller lists?"""
    sale_pages = rcfg.get("sale_pages") or {}
    has_discovery = any(urls and shop in enabled for shop, urls in sale_pages.items())
    mydealz_on = bool((rcfg.get("mydealz") or {}).get("enabled"))
    if (rcfg.get("brickmerge") or {}).get("enabled"):
        has_discovery = True
    priced = with_route = 0
    uncovered: list[dict] = []
    for sn in seller_ix:
        row = by_set.get(sn)
        ref = (lego_prices.get(sn) or {}).get("price")
        has_url = bool(row and any(
            k in enabled and (k != "amazon" or amazon_ok) for k in row.retailer_urls
        ))
        route = has_url or has_discovery or mydealz_on
        if ref is not None:
            priced += 1
        if route:
            with_route += 1
        name = row.name if row else ""
        if ref is None:
            uncovered.append({"set_num": sn, "name": name,
                              "reason": "no reference price - add rrp_eur to catalog.csv"})
        elif not route:
            uncovered.append({"set_num": sn, "name": name,
                              "reason": "no retail route - add a retailer URL or a sale_pages entry"})
    cov = {"listed": len(seller_ix), "priced": priced,
           "with_route": with_route, "on_sale": on_sale}
    return cov, uncovered
