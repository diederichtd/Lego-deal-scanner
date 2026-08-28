# Setup — run the knoppers55 flip-watch 24/7

## Recommended: GitHub Actions (free, always-on, real web page)

The Anthropic "cloud routine" can't reach shopping sites (its sandbox blocks
outbound web requests), so we use GitHub Actions instead. It runs the scan
hourly, DMs you on Discord, and publishes the deals page to GitHub Pages.

**One-time, ~3 minutes:**

1. **Add the Discord webhook as a secret.**
   Repo → **Settings** → **Secrets and variables** → **Actions** →
   **New repository secret**
   - Name: `LEGO_DEAL_WEBHOOK`
   - Value: your `https://discord.com/api/webhooks/...` URL

2. **Run it once.** Repo → **Actions** tab → **LEGO flip watch** →
   **Run workflow**. Wait ~10–15 min for it to finish (green check).

3. **Turn on the web page.** Repo → **Settings** → **Pages** →
   Source: *Deploy from a branch*, Branch: **gh-pages** / **/ (root)** → **Save**.
   Your live page: `https://diederichtd.github.io/Lego-deal-scanner/`

After that it runs by itself every hour. History is cached between runs, so
you get "new / cheaper / falling" instead of the same list each time.

Tune anything in `config.yaml` and push — the next run picks it up.

---

## Alternative: local agent on this Mac

Only runs while the Mac is awake, but needs no GitHub setup.

```bash
cd /Users/tdennis/lego-deal-scanner
.venv/bin/lego-deal-scanner install-agent -c "$(pwd)/config.yaml" \
  --webhook "https://discord.com/api/webhooks/XXXX" --force

launchctl unload ~/Library/LaunchAgents/com.lego-deal-scanner.watch.plist 2>/dev/null
launchctl load  ~/Library/LaunchAgents/com.lego-deal-scanner.watch.plist
```

Deals page: open `site_out/index.html`. Logs: `data/watch.log`.
Stop: `launchctl unload ~/Library/LaunchAgents/com.lego-deal-scanner.watch.plist`

---

## Knobs (`config.yaml`)

| key | default | what it does |
| --- | --- | --- |
| `retail.min_net_profit_eur` | 5 | main list needs at least this profit after fees + postage |
| `retail.economics.ebay_fee_pct` | 0.11 | your eBay final-value fee — lower it if your shop account pays less |
| `retail.brickmerge.max_sets` | 408 | how many of your sets to check per run |
| `retail.ebay_sold.enabled` | true | value sets at real eBay sold price (falls back to your list price if blocked) |
| `retail.verify_top_n` | 15 | double-check the N best deals are really in stock |
| `retail.http.min_delay_seconds` | 1.5 | politeness gap between requests |
