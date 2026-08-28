# Setup — run the knoppers55 flip-watch 24/7

Two ways. Do **A** now; add **B** when your repo is on GitHub.

---

## A. Local agent on this Mac (ready now)

The launchd job is already written to
`~/Library/LaunchAgents/com.lego-deal-scanner.watch.plist`. It runs
`lego-deal-scanner watch -c config.yaml` every hour (while the Mac is awake),
rebuilds `site_out/`, and — once a webhook is set — posts new/cheaper flips.

**1. Add your Discord/Slack webhook** (kept in the plist, never in the repo):

```bash
cd /Users/tdennis/lego-deal-scanner
.venv/bin/lego-deal-scanner install-agent -c "$(pwd)/config.yaml" \
  --webhook "https://discord.com/api/webhooks/XXXX/YYYY" --force
```

**2. Start it:**

```bash
launchctl unload ~/Library/LaunchAgents/com.lego-deal-scanner.watch.plist 2>/dev/null
launchctl load  ~/Library/LaunchAgents/com.lego-deal-scanner.watch.plist
```

It runs immediately, then hourly. Logs: `data/watch.log`, `data/watch.err.log`.
Deal list: open `site_out/index.html`. Stop: `launchctl unload …`.

---

## B. Cloud routine (always-on, no Mac needed)

**1. Push the repo:**

```bash
cd /Users/tdennis/lego-deal-scanner
git remote add origin https://github.com/YOU/lego-deal-scanner
git push -u origin main
```

**2. Give Claude the repo URL + webhook** — Claude creates the hourly routine.

The routine, each hour:
- clones the repo, `pip install -e .`
- `export LEGO_DEAL_WEBHOOK=…` (from the routine config, not the repo)
- `lego-deal-scanner watch -c config.yaml` → posts every new/cheaper flip
  (≥ `min_flip_margin_eur`) to the webhook
- if the cloud checkout can push: also updates a `gh-pages` branch for a live
  web page (enable Pages → branch `gh-pages`). If not, keep using **A** for the page.

Manage routines: <https://claude.ai/code/routines>

---

## Tuning `config.yaml`

| key | default | effect |
| --- | --- | --- |
| `retail.min_flip_margin_eur` | 15 | min (your eBay price − retail price) to alert |
| `retail.brickmerge.max_sets` | 120 | sets checked per run (bestsellers first); raise toward 408 |
| `retail.brickmerge.min_deal_score` | 0 | require brickmerge Deal-Score ≥ N (e.g. 60) |
| `retail.http.min_delay_seconds` | 2.0 | politeness gap; `max_sets × this` ≈ run time |

Refresh your inventory + prices: enable `retail.ebay_seller` with free API keys
from developer.ebay.com, or re-scrape and regenerate `data/knoppers55_catalog.csv`.
