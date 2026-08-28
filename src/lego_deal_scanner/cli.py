"""Command line entry point and the scan pipeline."""
from __future__ import annotations

import argparse
import dataclasses
import json
import logging
import shutil
import sys
import time
from pathlib import Path

from .classify import detect_condition
from .config import DEFAULTS, load_config
from .notify import send_digest, send_webhook
from .parse import infer_inbound_shipping
from .scoring import ScoreConfig, score
from .setnum import extract_set_numbers
from .sources import build_sources
from .store import Store
from .valuation import ReferenceBook, bricklink_price

log = logging.getLogger("lego_deal_scanner")

_ACTIONABLE = ("DEAL", "WATCH")


def run_scan(cfg: dict, store: Store | None = None, only_source: str | None = None,
             new_only: bool = False) -> dict:
    """Run one pass over every enabled source. Returns a result dict."""
    book = ReferenceBook.from_csv(cfg["valuation"]["reference_csv"])
    known = book.known_numbers()
    prefer = cfg["valuation"].get("prefer", "market")
    bl_cfg = cfg["valuation"].get("bricklink") or {}
    score_cfg = ScoreConfig.from_dict(cfg["scoring"])
    sources = build_sources(cfg["sources"], only=only_source)

    deals: list[dict] = []
    unvalued: list[dict] = []
    scanned = 0
    owns_store = False
    if store is None:
        store = Store(cfg["store"]["path"])
        owns_store = True

    try:
        for src in sources:
            for query in cfg["watchlist"]:
                for raw in src.search(query):
                    scanned += 1
                    state = store.seen_state(raw.source, raw.listing_id, raw.price_eur)
                    is_new = state != "seen"

                    nums = extract_set_numbers(raw.text, known)
                    ref = next((book.get(n) for n in nums if book.get(n)), None)
                    if ref is None:
                        unvalued.append({
                            "source": raw.source, "listing_id": raw.listing_id,
                            "title": raw.title, "url": raw.url, "price_eur": raw.price_eur,
                            "reason": "no known LEGO set number in title/description",
                        })
                        continue

                    if bl_cfg.get("enabled"):
                        blp = bricklink_price(bl_cfg, ref.set_num,
                                              "N" if "new" in detect_condition(raw.text) else "U")
                        if blp:
                            ref = dataclasses.replace(
                                ref,
                                mv_new_eur=blp if "new" in detect_condition(raw.text) else ref.mv_new_eur,
                                mv_used_eur=blp if "new" not in detect_condition(raw.text) else ref.mv_used_eur,
                                source="bricklink",
                            )

                    condition = detect_condition(raw.text)
                    ship_in, ship_note = infer_inbound_shipping(
                        raw.text, raw.shipping_eur, score_cfg.assumed_shipping_in_eur
                    )
                    deal = score(ref, condition, raw.price_eur or 0.0, ship_in, score_cfg,
                                 prefer=prefer, extra_notes=[ship_note])
                    if deal is None:
                        unvalued.append({
                            "source": raw.source, "listing_id": raw.listing_id,
                            "title": raw.title, "url": raw.url, "price_eur": raw.price_eur,
                            "reason": f"set {ref.set_num} matched but no usable price/value",
                        })
                        continue

                    row = dataclasses.asdict(deal)
                    row.update({
                        "source": raw.source, "listing_id": raw.listing_id,
                        "title": raw.title, "url": raw.url, "location": raw.location,
                        "posted_at": raw.posted_at, "is_new": is_new, "seen_state": state,
                        "matched_from": nums,
                    })
                    if deal.verdict in _ACTIONABLE:
                        if new_only and not is_new:
                            continue
                        deals.append(row)
                        store.record_deal(raw.source, raw.listing_id, row)
    finally:
        if owns_store:
            store.close()

    deals.sort(key=lambda d: (d["verdict"] != "DEAL", -d["roi"]))
    return {
        "scanned": scanned,
        "deals": deals,
        "unvalued": unvalued,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }


# --------------------------------------------------------------------------- #
# rendering
# --------------------------------------------------------------------------- #
def render(result: dict, quiet: bool = False) -> None:
    deals = result["deals"]
    try:
        from rich.console import Console
        from rich.table import Table

        console = Console()
        if not deals:
            console.print(f"[dim]scanned {result['scanned']} listings - no DEAL/WATCH hits[/dim]")
        else:
            table = Table(title=f"LEGO deals ({result['generated_at']})")
            for col in ("verdict", "set", "name", "cond", "ask", "ship", "ref", "net", "ROI", "new"):
                table.add_column(col)
            for d in deals:
                style = "bold green" if d["verdict"] == "DEAL" else "yellow"
                table.add_row(
                    f"[{style}]{d['verdict']}[/{style}]", d["set_num"], d["name"][:28],
                    d["condition"].replace("_", " "), f"{d['asking_eur']:.0f}",
                    f"{d['shipping_in_eur']:.0f}", f"{d['resale_ref_eur']:.0f}",
                    f"{d['net_profit_eur']:.0f}", f"{d['roi'] * 100:.0f}%",
                    "yes" if d["is_new"] else "-",
                )
            console.print(table)
        if not quiet and result["unvalued"]:
            console.print(f"[dim]{len(result['unvalued'])} listings skipped (no reference match)[/dim]")
    except ImportError:
        print(f"scanned {result['scanned']} listings; {len(deals)} actionable")
        for d in deals:
            print(f"  {d['verdict']:5} {d['set_num']:>7} {d['name'][:30]:30} "
                  f"ask {d['asking_eur']:>6.0f}  net {d['net_profit_eur']:>6.0f}  "
                  f"ROI {d['roi'] * 100:>4.0f}%  {d['url']}")


def _write_json(path: str | None, result: dict) -> None:
    if not path:
        return
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")


# --------------------------------------------------------------------------- #
# argparse
# --------------------------------------------------------------------------- #
def _cmd_init(args: argparse.Namespace) -> int:
    example = Path(__file__).resolve().parents[2] / "config.example.yaml"
    dest = Path(args.config or "config.yaml")
    if dest.exists() and not args.force:
        print(f"{dest} already exists (use --force to overwrite)")
        return 1
    if not example.exists():
        print("bundled config.example.yaml not found")
        return 1
    data_dir = example.parent / "data"
    text = example.read_text(encoding="utf-8")
    # point read-only sample data at the bundled copies so `scan` works from any cwd
    text = text.replace("data/reference_prices.csv", str(data_dir / "reference_prices.csv"))
    text = text.replace("data/fixture_listings.json", str(data_dir / "fixture_listings.json"))
    dest.write_text(text, encoding="utf-8")
    print(f"wrote {dest} - edit it, then run: lego-deal-scanner scan -c {dest}")
    return 0


def _cmd_scan(args: argparse.Namespace) -> int:
    cfg = load_config(args.config) if args.config else _fallback_cfg()
    if args.json_out:
        cfg["notify"]["json_out"] = args.json_out

    def once() -> dict:
        with Store(cfg["store"]["path"]) as store:
            result = run_scan(cfg, store, only_source=args.source, new_only=args.new_only)
        render(result, quiet=args.quiet)
        _write_json(cfg["notify"].get("json_out"), result)
        if cfg["notify"].get("webhook_url") and result["deals"]:
            ok = send_webhook(cfg["notify"]["webhook_url"], result["deals"])
            if not args.quiet:
                print("webhook sent" if ok else "webhook failed")
        return result

    if args.interval:
        print(f"monitoring every {args.interval} min - Ctrl+C to stop")
        try:
            while True:
                once()
                time.sleep(args.interval * 60)
        except KeyboardInterrupt:
            print("\nstopped")
        return 0

    result = once()
    return 0 if result["deals"] or not args.fail_empty else 2


def _fallback_cfg() -> dict:
    import copy

    cfg = copy.deepcopy(DEFAULTS)
    root = Path(__file__).resolve().parents[2]
    cfg["valuation"]["reference_csv"] = str(root / "data" / "reference_prices.csv")
    cfg["sources"]["fixture"]["path"] = str(root / "data" / "fixture_listings.json")
    cfg["store"]["path"] = str(root / "data" / "scanner.sqlite3")
    cfg["notify"]["json_out"] = str(root / "data" / "deals.latest.json")
    cfg["retail"]["catalog_csv"] = str(root / "data" / "catalog.example.csv")
    return cfg


def _cmd_watch(args: argparse.Namespace) -> int:
    from .retail import build_site, deploy, run_watch

    cfg = load_config(args.config) if args.config else _fallback_cfg()
    if args.outdir:
        cfg["site"]["outdir"] = args.outdir
    # env overrides (handy for cloud routines / CI - keeps secrets out of the repo)
    import os

    if os.environ.get("LEGO_DEAL_WEBHOOK"):
        cfg["notify"]["webhook_url"] = os.environ["LEGO_DEAL_WEBHOOK"]
    if os.environ.get("LEGO_DEAL_PUBLIC_URL"):
        cfg["site"]["public_url"] = os.environ["LEGO_DEAL_PUBLIC_URL"]
    if os.environ.get("LEGO_DEAL_DEPLOY_REMOTE"):
        cfg["site"].setdefault("deploy", {})
        cfg["site"]["deploy"]["mode"] = "git"
        cfg["site"]["deploy"]["remote_url"] = os.environ["LEGO_DEAL_DEPLOY_REMOTE"]
    if getattr(args, "no_deploy", False):
        cfg["site"].setdefault("deploy", {})["mode"] = "none"

    def once() -> dict:
        with Store(cfg["store"]["path"]) as store:
            result = run_watch(cfg, store)
        outdir = build_site(result, cfg["site"])
        _write_json(cfg["notify"].get("json_out"), result)
        url = deploy(outdir, cfg["site"])
        if not args.quiet:
            _render_watch(result, outdir)
            if url:
                print(f"published: {url}")
        hook = cfg["notify"].get("webhook_url")
        if hook:
            digest = bool(os.environ.get("LEGO_DEAL_DIGEST")
                          or cfg["notify"].get("digest"))
            if digest:
                ok = send_digest(hook, result)
                if not args.quiet:
                    print("digest sent" if ok else "digest failed")
            elif result["deals"]:
                fresh = [d for d in result["deals"] if d["state"] in
                         ("new", "price_drop", "back_in_stock")]
                if fresh:
                    send_webhook(hook, _webhook_rows(fresh))
        return result

    if args.interval:
        print(f"watching every {args.interval} min - Ctrl+C to stop")
        try:
            while True:
                once()
                time.sleep(args.interval * 60)
        except KeyboardInterrupt:
            print("\nstopped")
        return 0

    result = once()
    return 0 if result["deals"] or not args.fail_empty else 2


def _webhook_rows(deals: list[dict]) -> list[dict]:
    out = []
    for d in deals:
        margin = d.get("margin_vs_ebay_eur")
        ref = d.get("ebay_price_eur") if margin is not None else d["lego_price_eur"]
        gain = margin if margin is not None else d["saving_eur"]
        out.append({
            "verdict": d["state"].replace("_", " ").upper(),
            "set_num": d["set_num"], "name": d["name"], "condition": d["shop_name"],
            "asking_eur": d["price_eur"], "shipping_in_eur": 0.0,
            "resale_ref_eur": ref,
            "net_profit_eur": gain, "roi": d["saving_pct"], "url": d["url"],
        })
    return out


def _render_watch(result: dict, outdir: Path) -> None:
    deals = result["deals"]
    try:
        from rich.console import Console
        from rich.table import Table

        console = Console()
        if deals:
            table = Table(title=f"below LEGO.de price ({result['generated_at']})")
            for col in ("state", "set", "name", "shop", "price", "LEGO.de", "save", "%"):
                table.add_column(col)
            for d in deals:
                table.add_row(
                    d["state"].replace("_", " "), d["set_num"], d["name"][:26],
                    d["shop_name"], f"{d['price_eur']:.2f}", f"{d['lego_price_eur']:.2f}",
                    f"{d['saving_eur']:.2f}", f"{d['saving_pct'] * 100:.0f}%",
                )
            console.print(table)
        else:
            console.print("[dim]no sets below LEGO.de price[/dim]")
        console.print(f"[dim]{result['checked']} retailer checks, "
                      f"{len(result['errors'])} unreadable[/dim]")
        console.print(f"site: {outdir / 'index.html'}")
    except ImportError:
        print(f"{len(deals)} deals; site at {outdir / 'index.html'}")
        for d in deals:
            print(f"  {d['set_num']:>7} {d['shop_name']:<14} "
                  f"{d['price_eur']:>8.2f}  save {d['saving_eur']:>7.2f} "
                  f"({d['saving_pct'] * 100:.0f}%)  {d['url']}")


def _cmd_publish(args: argparse.Namespace) -> int:
    """Deploy the already-built site_out/ without re-scanning."""
    from .retail import deploy

    cfg = load_config(args.config) if args.config else _fallback_cfg()
    outdir = Path(args.outdir or cfg["site"]["outdir"])
    if not (outdir / "index.html").exists():
        print(f"no site at {outdir} - run `watch` first")
        return 1
    url = deploy(outdir, cfg["site"])
    print(f"published: {url}" if url else
          "deploy mode is 'none' or it failed - see site.deploy in config")
    return 0 if url else 1


def _cmd_install_agent(args: argparse.Namespace) -> int:
    """Write a launchd plist that runs `watch` hourly on this Mac."""
    venv_bin = Path(sys.prefix) / "bin" / "lego-deal-scanner"
    exe = str(venv_bin) if venv_bin.exists() else "lego-deal-scanner"
    cfg_path = str(Path(args.config).resolve()) if args.config else ""
    workdir = str(Path.cwd())
    label = "com.lego-deal-scanner.watch"
    prog_args = [f"        <string>{exe}</string>", "        <string>watch</string>"]
    if cfg_path:
        prog_args += ["        <string>-c</string>", f"        <string>{cfg_path}</string>"]
    prog_args.append("        <string>--quiet</string>")
    env_block = ""
    if getattr(args, "webhook", None):
        env_block = (
            "    <key>EnvironmentVariables</key><dict>\n"
            f"        <key>LEGO_DEAL_WEBHOOK</key><string>{args.webhook}</string>\n"
            "    </dict>\n"
        )
    plist = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
    <key>Label</key><string>{label}</string>
    <key>ProgramArguments</key><array>
{chr(10).join(prog_args)}
    </array>
{env_block}    <key>WorkingDirectory</key><string>{workdir}</string>
    <key>StartInterval</key><integer>3600</integer>
    <key>RunAtLoad</key><true/>
    <key>StandardOutPath</key><string>{workdir}/data/watch.log</string>
    <key>StandardErrorPath</key><string>{workdir}/data/watch.err.log</string>
</dict></plist>
"""
    dest = Path.home() / "Library" / "LaunchAgents" / f"{label}.plist"
    if args.print:
        print(plist)
        return 0
    if dest.exists() and not args.force:
        print(f"{dest} exists (use --force). Preview with --print.")
        return 1
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(plist, encoding="utf-8")
    print(f"wrote {dest}\n\nload it:\n  launchctl unload {dest} 2>/dev/null; "
          f"launchctl load {dest}\n\nstop it:\n  launchctl unload {dest}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="lego-deal-scanner", description=__doc__)
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="cmd")

    pi = sub.add_parser("init", help="write a config.yaml from the bundled example")
    pi.add_argument("-c", "--config", default="config.yaml")
    pi.add_argument("--force", action="store_true")
    pi.set_defaults(func=_cmd_init)

    ps = sub.add_parser("scan", help="run one scan (or loop with --interval)")
    ps.add_argument("-c", "--config", help="path to config.yaml (default: bundled sample)")
    ps.add_argument("--source", help="only run this source (fixture|kleinanzeigen|ebay_de)")
    ps.add_argument("--new-only", action="store_true", help="alert only on first-seen listings")
    ps.add_argument("--interval", type=float, help="minutes between scans (keeps running)")
    ps.add_argument("--json-out", help="override notify.json_out path")
    ps.add_argument("--quiet", action="store_true")
    ps.add_argument("--fail-empty", action="store_true", help="exit 2 when no deals found")
    ps.set_defaults(func=_cmd_scan)

    pw = sub.add_parser("watch", help="check retailers vs LEGO.de, rebuild the deals site")
    pw.add_argument("-c", "--config", help="path to config.yaml (default: bundled sample)")
    pw.add_argument("--outdir", help="override site.outdir")
    pw.add_argument("--interval", type=float, help="minutes between runs (keeps running)")
    pw.add_argument("--no-deploy", action="store_true", help="build the site but don't publish")
    pw.add_argument("--quiet", action="store_true")
    pw.add_argument("--fail-empty", action="store_true", help="exit 2 when no deals found")
    pw.set_defaults(func=_cmd_watch)

    pp = sub.add_parser("publish", help="deploy the existing site_out/ (no re-scan)")
    pp.add_argument("-c", "--config", help="path to config.yaml")
    pp.add_argument("--outdir", help="folder to deploy (default: site.outdir)")
    pp.set_defaults(func=_cmd_publish)

    pa = sub.add_parser("install-agent", help="write a launchd plist to run watch hourly")
    pa.add_argument("-c", "--config", help="config.yaml the agent should use")
    pa.add_argument("--webhook", help="Discord/Slack webhook URL (baked into the plist, "
                                      "not the repo) for hourly deal alerts")
    pa.add_argument("--print", action="store_true", help="print the plist, don't write it")
    pa.add_argument("--force", action="store_true")
    pa.set_defaults(func=_cmd_install_agent)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if getattr(args, "verbose", False) else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )
    if not getattr(args, "cmd", None):
        args = build_parser().parse_args((argv or []) + ["scan"])
    return args.func(args)
