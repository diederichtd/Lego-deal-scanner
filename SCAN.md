# `scan` — used-marketplace flipper

Secondary tool. Scores second-hand LEGO listings for resale profit after fees,
shipping and a resale haircut. Verdicts: **DEAL** / **WATCH** / **SKIP**.

```bash
python -m lego_deal_scanner scan --source fixture      # offline demo
lego-deal-scanner scan -c config.yaml --new-only --interval 30
```

Sources: `fixture` (offline sample), `ebay_de` (Browse API with keys, HTML
fallback), `kleinanzeigen` (best-effort scraper, **off by default** — no API,
ToS forbids automation, blocks bots).

Valuation from `data/reference_prices.csv`
(`set_num,name,year,pieces,rrp_eur,mv_new_eur,mv_used_eur,weight_g`), optionally
overridden per lookup by the BrickLink price guide
(`pip install ".[bricklink]"` + OAuth1 keys in `valuation.bricklink`).

Cost model lives in `scoring.*` in the config: `marketplace_fee_pct`,
`resale_haircut_pct`, `shipping_out_by_weight` tiers, `min_profit_eur`,
`min_roi`, `watch_roi`.
