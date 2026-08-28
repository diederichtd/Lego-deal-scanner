# LEGO Deal Scanner

Two tools in one package:

- **`watch`** — retail drop monitor. Checks German shops (Otto, Müller, Thalia,
  Joybuy, Smyths, Proshop, Galeria, …) plus the mydealz community feed,
  flags any set priced **below LEGO.de**, and rewrites a standalone deals website
  every run. This is the main thing.
- **`scan`** — used-marketplace flipper. Scores second-hand listings (eBay.de,
  Kleinanzeigen) for resale profit after fees. Secondary; see [SCAN.md](SCAN.md).

---

## watch — how it works

Each run finds catalog sets on sale, three ways:

1. Read `data/catalog.csv` — ~45 sets ship in `catalog.example.csv`; add your own.
   Each row has a `set_num`, `rrp_eur`, `lego_url`, and optional per-shop URLs.
2. **Reference price** = LEGO.de live (or the `rrp_eur` column when the fetch is
   blocked).
3. **Explicit URLs** — for any `shop=url` pairs in the catalog row, fetch the
   product page, read price + stock (JSON-LD → meta → regex).
4. **Discovery** — for each URL in `retail.sale_pages`, scrape the shop's whole
   LEGO-sale listing and pull out *every* discounted set at once. No per-set URL
   needed; a set only counts if it's in your catalog.
5. **mydealz** — ingest the RSS feed(s) for deals at shops you don't scrape.
6. Keep anything **≥ `min_discount_pct` below LEGO.de** (default 12%) and
   **≥ `min_price_eur`** (default €25).
7. **eBay seller mode (optional)** — restrict the board to the set numbers you
   currently list, and show the margin between your eBay price and each deal.
8. Diff against last run (SQLite): tag **NEW / PRICE DROP / BACK IN STOCK**, keep
   price history.
9. Write `site_out/index.html` + `deals.json` + `feed.xml`, then deploy.

The page has set photos (BrickLink), client-side **sort** (discount % / € saved /
margin / price), **shop filter** chips, an **in-stock** toggle, a **Copy list**
button, a **theme toggle** (system / light / dark, remembered), an **Update**
button (reloads to the latest hourly run) with optional **auto-refresh**, and a
**"new / cheaper since your last visit"** banner (tracked in your browser). Every
row links to the retailer's page; in seller mode each row also links to your own
listing.

## Install

```bash
cd lego-deal-scanner
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

## Set up

```bash
lego-deal-scanner init                        # writes config.yaml
cp data/catalog.example.csv data/catalog.csv  # then edit it
lego-deal-scanner watch -c config.yaml        # one run
open site_out/index.html
```

### catalog.csv

```
set_num,name,rrp_eur,lego_url,retailer_urls
10300,Back to the Future Time Machine,199.99,https://www.lego.com/de-de/product/back-to-the-future-time-machine-10300,
10307,Eiffel Tower,629.99,https://www.lego.com/de-de/product/eiffel-tower-10307,otto=https://www.otto.de/p/...
```

`retailer_urls` is optional `shop=url` pairs joined by `|` (shop keys:
`otto mueller thalia joybuy smyths proshop galeria amazon`). Leave it
empty and rely on **discovery + mydealz** to find that set on sale.

`data/catalog.example.csv` has ~45 well-known sets ready to use. **Verify the
`rrp_eur` values** — they're best-effort and LEGO adjusts RRPs; the live
`lego_url` fetch overrides them when it works.

### Only show sets you sell (eBay seller mode)

```yaml
retail:
  ebay_seller:
    enabled: true
    seller: "knoppers55"          # your eBay username
    mode: browse_api              # browse_api (free keys) | html (keyless, brittle)
    client_id: "..."              # developer.ebay.com application keys
    client_secret: "..."
    require_below_ebay: false      # true = only sets cheaper than your own price
```

The scanner pulls your active LEGO listings (public data — no seller login),
reads the set number from each title, and filters the whole board down to those
sets. Each row then shows **your eBay price** and **± margin vs your price**
(retailer price minus your price, *before* eBay's ~11% fee and shipping).

`image` on a photo is BrickLink's set image; add an `image_url` column to
`catalog.csv` to override per set.

### brickmerge (recommended default source)

`retail.brickmerge.enabled: true` fetches `brickmerge.de/{set}-1_x` once per set —
that page aggregates every German shop (Otto, Müller, Proshop, Galeria, Smyths,
JB Spielwaren, …) and is **not bot-walled**, and it gives the current UVP so no
LEGO.de fetch is needed. `max_sets` caps how many per run (highest `ebay_sold`
first); raise toward your full catalog for complete coverage.

With an `ebay_price_eur` column in the catalog, a set is flagged only when
`your eBay price − brickmerge best price ≥ retail.min_flip_margin_eur` (default
€15) — i.e. a real buy-to-resell margin. `data/knoppers55_catalog.csv` (408 of
your live listings, scraped 2026-08-28) is set up this way; `config.yaml` points
at it.

```bash
lego-deal-scanner watch -c config.yaml       # one pass
```

### sale_pages (discovery)

```yaml
retail:
  sale_pages:
    otto: ["https://www.otto.de/spielzeug/lego/lego-angebote/"]
    galeria: ["https://www.galeria.de/marken/lego/sale/"]
```

Point these at each shop's LEGO sale / clearance page. Discovery reads the
JSON-LD product list off the page and reports every catalogued set that's
≥ `min_discount_pct` off. This is what "show everything on sale" needs.

## Run it hourly on this Mac

```bash
lego-deal-scanner install-agent -c "$(pwd)/config.yaml"
# then run the launchctl load line it prints
```

Writes `~/Library/LaunchAgents/com.lego-deal-scanner.watch.plist` (StartInterval
3600). Logs to `data/watch.log`. Only runs while the Mac is awake. Preview the
plist first with `--print`.

Prefer cron? `0 * * * * cd /path/to/lego-deal-scanner && .venv/bin/lego-deal-scanner watch -c config.yaml --quiet`

## Publish it as a web page

`watch` deploys `site_out/` after every run when `site.deploy.mode` is set.
`lego-deal-scanner publish` deploys the current folder without re-scanning.

| mode | config keys | needs |
| --- | --- | --- |
| `git` | `remote_url`, `branch` (default `gh-pages`) | a git host; GitHub Pages gives `you.github.io/repo` |
| `rsync` | `target` = `user@host:/var/www/legodeals/` | SSH access to a web server |
| `netlify` | `site_id` (optional) | `npx netlify` + a logged-in Netlify CLI |
| `folder` | `dest` | a synced folder (iCloud/Dropbox) or another local path |

Set `site.public_url` to the final address — it's printed after each deploy and
used as the RSS feed's link.

### GitHub Pages walkthrough (free, driven from your Mac)

1. Create an empty repo, e.g. `github.com/you/lego-deals`.
2. In `config.yaml`:
   ```yaml
   site:
     public_url: "https://you.github.io/lego-deals/"
     deploy:
       mode: git
       branch: gh-pages
       remote_url: "git@github.com:you/lego-deals.git"
   ```
3. `lego-deal-scanner watch -c config.yaml` — first run inits `site_out/` as a
   repo and force-pushes the `gh-pages` branch.
4. Repo → Settings → Pages → Branch: `gh-pages` / root. Live in ~1 min.
5. The hourly launchd agent now updates the page every hour.

Rather not host it yourself? A styled preview of the exact page is here:
https://claude.ai/code/artifact/72cfc69a-62f8-4221-a186-055a6fecb6e3 — but that
URL is a static snapshot, not the hourly-updating site.

## ⚠️ Bot protection — read this

Plain HTTP requests get **HTTP 403 from lego.com and thalia.de**, and likely
otto.de / galeria.de too — they sit behind Akamai / Cloudflare bot walls. Out of
the box `watch` will only reliably read the smaller shops and mydealz, and will
fall back to the `rrp_eur` column for the LEGO reference.

To scrape the walled shops you need one of:

| approach | effort | notes |
| --- | --- | --- |
| **Headless browser fetcher** (Playwright + Chromium) | medium | defeats most 403s; ~300 MB install; runs locally |
| `rrp_eur` column as the reference, browser only for retailers | low | reference price goes stale when LEGO changes RRP |
| Official APIs (Amazon PA-API, Otto partner feed) | medium | ToS-clean, needs accounts, partial coverage |
| Paid price-data API (idealo/geizhals partner, etc.) | low code | costs money |

A Playwright backend for `retail/http.py` is the recommended next step — ask and
it gets added.

## mydealz feed

The default feed URL is a guess. Open a LEGO group or saved search on
mydealz.de, copy its **RSS** link, and put the real URL in
`retail.mydealz.feeds`. If it 403s, mydealz is Cloudflared too and needs the
browser fetcher.

## Deal rule

A set is shown when **all** hold:

- price is **≥ `min_discount_pct`** below LEGO.de (default `0.12` → 12%; set
  `0.15` to only show 15%+)
- price is **≥ `min_price_eur`** (default `€25` — skip cheap sets)
- the set is in `catalog.csv` (keeps "worth buying" curated)

Not yet implemented, easy to add: below-historical-low, retired-set-at-RRP.

## Tests

```bash
pytest        # 22 tests, all offline
```

## Layout

```
src/lego_deal_scanner/
  cli.py               watch / scan / init / install-agent
  config.py            YAML over defaults
  retail/
    catalog.py         catalog.csv loader
    http.py            polite fetcher (per-domain throttle, retries)
    extract.py         price + stock from a product page
    shops.py           retailer registry
    mydealz.py         RSS ingest
    run.py             the watch pipeline
    site.py            index.html + deals.json + feed.xml
  store.py             SQLite: price history + state diffing
  sources/, scoring.py, valuation.py, setnum.py, classify.py   -> used by `scan`
```

## Disclaimer

Prices are scraped from public pages and go stale between runs; shops
misprice and restrict stock. Verify every deal before buying. Not affiliated with
the LEGO Group. Respect each site's terms of service.
