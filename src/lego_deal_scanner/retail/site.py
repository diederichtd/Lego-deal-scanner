"""Render the standalone deals page: index.html + deals.json + feed.xml.

Deliberately minimal: one line per deal (set, shop, price, how much under your
price), the whole row links straight to the shop. The only JS marks rows that
are new or cheaper since your last visit.
"""
from __future__ import annotations

import html
import json
import re
from email.utils import format_datetime
from datetime import datetime, timezone
from pathlib import Path
_CSS = """
:root{
  --bg:#fbfbfa; --fg:#1a1a19; --dim:#6b6b66; --line:#e6e5e1;
  --hi:#f2f1ec; --accent:#177a3a; --new:#c8102e; --tile:#efeee9;
}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
  --bg:#141413; --fg:#eceae4; --dim:#928e85; --line:#2b2a27;
  --hi:#1e1d1b; --accent:#57c27a; --new:#f2637a; --tile:#232220;
}}
:root[data-theme="dark"]{
  --bg:#141413; --fg:#eceae4; --dim:#928e85; --line:#2b2a27;
  --hi:#1e1d1b; --accent:#57c27a; --new:#f2637a; --tile:#232220;
}
*{box-sizing:border-box;margin:0;padding:0}
html{background:var(--bg)}
body{background:var(--bg);color:var(--fg);
  font:15px/1.5 ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
  -webkit-font-smoothing:antialiased}
.wrap{max-width:680px;margin:0 auto;padding:30px 20px 64px}
header{display:flex;align-items:flex-start;justify-content:space-between;gap:12px}
h1{font-size:19px;font-weight:650;letter-spacing:-.01em}
h1 span{color:var(--dim);font-weight:500}
.sub{color:var(--dim);font-size:13px;margin-top:4px}
.theme{flex:none;font:12px/1 inherit;color:var(--dim);background:var(--tile);
  border:1px solid var(--line);border-radius:7px;padding:6px 9px;cursor:pointer}
.theme:hover{color:var(--fg)}
.newbar{margin:16px 0 0;font-size:13px;color:var(--accent)}
.newbar a{color:var(--dim);text-decoration:underline;cursor:pointer;margin-left:8px}
main{margin-top:16px;border-top:1px solid var(--line)}
.row{display:flex;align-items:center;gap:13px;padding:12px 4px;
  border-bottom:1px solid var(--line);color:inherit;text-decoration:none}
.row:hover{background:var(--hi)}
.thumb{flex:none;width:46px;height:46px;border-radius:8px;background:var(--tile);
  border:1px solid var(--line);display:flex;align-items:center;justify-content:center;
  overflow:hidden;position:relative}
.thumb img{width:100%;height:100%;object-fit:contain}
.thumb b{font:11px/1 ui-monospace,SFMono-Regular,Menlo,monospace;color:var(--dim)}
.name{flex:1;min-width:0}
.name .t{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;
  font-weight:500}
.name .m{color:var(--dim);font-size:12.5px;margin-top:2px}
.row.is-new .name .t::after{content:" · new";color:var(--new);font-size:12px;
  font-weight:600}
.fig{flex:none;text-align:right;white-space:nowrap;line-height:1.25}
.fig .buy{font:14px/1 ui-monospace,SFMono-Regular,Menlo,monospace;color:var(--dim)}
.fig .gap{display:block;margin-top:3px;font-size:20px;font-weight:700;
  color:var(--accent);letter-spacing:-.01em}
.fig .gap small{font-size:12px;font-weight:600;color:var(--dim)}
.empty{color:var(--dim);padding:44px 4px;text-align:center}
.gone{color:var(--dim);font-size:12.5px;margin-top:18px}
footer{margin-top:34px;color:var(--dim);font-size:12px;line-height:1.6}
@media(max-width:520px){.fig .gap{font-size:18px}.thumb{width:40px;height:40px}}
"""

_JS = r"""
(function(){
  var root=document.documentElement;
  var LS={g:function(k){try{return localStorage.getItem(k)}catch(e){return null}},
          s:function(k,v){try{localStorage.setItem(k,v)}catch(e){}}};

  var modes=[['','Auto'],['light','Light'],['dark','Dark']];
  var tb=document.getElementById('theme'), cur=LS.g('lds-theme')||'';
  function apply(m){
    if(m) root.setAttribute('data-theme',m); else root.removeAttribute('data-theme');
    var f=modes.filter(function(x){return x[0]===m})[0]||modes[0];
    if(tb) tb.textContent=f[1];
  }
  apply(cur);
  if(tb) tb.addEventListener('click',function(){
    var i=0; for(var j=0;j<modes.length;j++){if(modes[j][0]===cur)i=j;}
    cur=modes[(i+1)%modes.length][0]; LS.s('lds-theme',cur); apply(cur);
  });

  var rows=[].slice.call(document.querySelectorAll('.row'));
  var prev={}; try{prev=JSON.parse(LS.g('lds')||'{}')||{}}catch(e){}
  var first=!Object.keys(prev).length, n=0, cmap={};
  rows.forEach(function(r){
    var k=r.dataset.key, p=parseFloat(r.dataset.price)||0; cmap[k]=p;
    if(first) return;
    if(!(k in prev) || p<prev[k]-0.01){ r.classList.add('is-new'); n++; }
  });
  var bar=document.getElementById('new');
  if(bar && n){
    bar.hidden=false;
    bar.innerHTML=n+' new or cheaper since your last visit <a id="x">clear</a>';
    var x=document.getElementById('x');
    if(x) x.onclick=function(){rows.forEach(function(r){r.classList.remove('is-new')});bar.hidden=true;};
  }
  function snap(){LS.s('lds',JSON.stringify(cmap));}
  setTimeout(snap,45000);
  window.addEventListener('beforeunload',snap);
})();
"""


def _bricklink(set_num: str) -> str:
    return f"https://img.bricklink.com/ItemImage/SN/0/{set_num}-1.png"


def _row(d: dict) -> str:
    name = html.escape(d["name"])
    shop = html.escape(d.get("shop_name") or d.get("shop") or "")
    url = html.escape(d["url"], quote=True)
    sn = html.escape(d["set_num"])
    key = html.escape(f'{d["set_num"]}|{d.get("shop", "")}', quote=True)
    img = html.escape(d.get("image_url") or _bricklink(d["set_num"]), quote=True)

    net = d.get("net_profit_eur")
    if net is not None:
        fig = f'~&euro;{net:.0f} <small>profit</small>'
    else:
        g = d.get("margin_vs_ebay_eur")
        fig = (f'&euro;{g:.0f} <small>under</small>' if g is not None
               else f'&minus;{d["saving_pct"] * 100:.0f}%')

    return (
        f'<a class="row" href="{url}" target="_blank" rel="noopener" '
        f'data-key="{key}" data-price="{d["price_eur"]:.2f}">'
        f'<span class="thumb"><img src="{img}" alt="" loading="lazy" '
        f'onerror="this.style.display=\'none\'"><b>{sn}</b></span>'
        f'<span class="name"><span class="t">{name}</span>'
        f'<span class="m">{sn} &middot; {shop}</span></span>'
        f'<span class="fig"><span class="buy">&euro;{d["price_eur"]:.0f}</span>'
        f'<span class="gap">{fig}</span></span></a>'
    )


def render_html(result: dict, cfg: dict) -> str:
    title = html.escape(cfg.get("title", "LEGO deals"))
    deals = result.get("deals") or []
    seller = result.get("seller")
    who = f'<span>&middot; {html.escape(seller)}</span>' if seller else ""

    note = (f'<p class="sub" style="color:var(--new)">{html.escape(result["health"])}</p>'
            if result.get("health") else "")

    body = "\n".join(_row(d) for d in deals) or \
        '<p class="empty">Nothing cheaper than your prices right now.</p>'

    gone = (f'<p class="gone">{len(result["stale"])} looked good but sold out or '
            f'jumped in price since.</p>' if result.get("stale") else "")

    return f"""<!doctype html>
<html lang="de"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<style>{_CSS}</style></head>
<body><div class="wrap">
<header>
  <div>
    <h1>LEGO deals {who}</h1>
    <p class="sub">{len(deals)} sets a German shop has cheaper than you sell them
      &middot; updated {html.escape(result.get('generated_at', ''))}</p>
    {note}
  </div>
  <button id="theme" class="theme" type="button">Auto</button>
</header>
<div id="new" class="newbar" hidden></div>
<main>
{body}
</main>
{gone}
<footer>Links go to the shop's page for that set &mdash; confirm the set, price
and stock before buying. Prices via brickmerge.de, minutes to hours old. Not
affiliated with the LEGO Group.</footer>
</div>
<script>{_JS}</script>
</body></html>
"""


def render_rss(result: dict, cfg: dict) -> str:
    base = (cfg.get("public_url") or cfg.get("base_url") or "").rstrip("/")
    now = format_datetime(datetime.now(timezone.utc))
    items = []
    for d in result["deals"]:
        extra = ""
        if d.get("margin_vs_ebay_eur") is not None:
            extra = f" · margin vs your eBay €{d['margin_vs_ebay_eur']:.2f}"
        t = (f"{d['set_num']} {d['name']} — {d['shop_name']} €{d['price_eur']:.2f} "
             f"(−{d['saving_pct'] * 100:.0f}%)")
        desc = (f"LEGO.de €{d['lego_price_eur']:.2f}, now €{d['price_eur']:.2f} at "
                f"{d['shop_name']}. Save €{d['saving_eur']:.2f}{extra}.")
        guid = f"{d['url']}|{int(result['generated_ts'])}"
        items.append(
            f"<item><title>{html.escape(t)}</title>"
            f"<link>{html.escape(d['url'], quote=True)}</link>"
            f'<guid isPermaLink="false">{html.escape(guid)}</guid>'
            f"<description>{html.escape(desc)}</description>"
            f"<pubDate>{now}</pubDate></item>"
        )
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
<title>{html.escape(cfg.get('title', 'LEGO Deals DE'))}</title>
<link>{html.escape(base or 'about:blank')}</link>
<description>LEGO sets currently priced below LEGO.de</description>
<lastBuildDate>{now}</lastBuildDate>
{''.join(items)}
</channel></rss>
"""


def render_fragment(result: dict, cfg: dict) -> str:
    """Same page, but without the <!doctype>/<html>/<head>/<body> wrapper -
    ready to publish as a Claude Artifact (its skeleton is added at publish time)."""
    full = render_html(result, cfg)
    title = re.search(r"<title>(.*?)</title>", full, re.S)
    link = re.search(r'<link rel="stylesheet"[^>]*>', full)
    style = re.search(r"<style>.*?</style>", full, re.S)
    body = re.search(r"<body>(.*)</body>", full, re.S)   # includes the trailing <script>
    parts = [
        f"<title>{title.group(1) if title else 'LEGO Deals DE'}</title>",
        link.group(0) if link else "",
        style.group(0) if style else "",
        (body.group(1).strip() if body else ""),
    ]
    return "\n".join(p for p in parts if p) + "\n"


def build_site(result: dict, site_cfg: dict) -> Path:
    outdir = Path(site_cfg.get("outdir", "site_out"))
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "index.html").write_text(render_html(result, site_cfg), encoding="utf-8")
    (outdir / "artifact.html").write_text(render_fragment(result, site_cfg), encoding="utf-8")
    (outdir / ".nojekyll").write_text("", encoding="utf-8")
    (outdir / "deals.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (outdir / "feed.xml").write_text(render_rss(result, site_cfg), encoding="utf-8")
    return outdir
