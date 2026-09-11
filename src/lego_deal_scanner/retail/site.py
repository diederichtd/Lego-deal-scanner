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
  --bg:#faf9f7; --card:#fff; --fg:#1b1a18; --dim:#726c63; --line:#eceae4;
  --accent:#0b7a3b; --new:#c8102e; --pill:#f3f1ec;
  --sh:0 1px 2px rgba(20,18,15,.04),0 4px 14px rgba(20,18,15,.05);
  --shh:0 2px 6px rgba(20,18,15,.07),0 12px 30px rgba(20,18,15,.10);
}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
  --bg:#131211; --card:#1c1b19; --fg:#efece5; --dim:#9a938a; --line:#2c2a26;
  --accent:#54c47a; --new:#f2637a; --pill:#262420;
  --sh:0 1px 2px rgba(0,0,0,.3),0 6px 20px rgba(0,0,0,.35);
  --shh:0 2px 8px rgba(0,0,0,.4),0 16px 40px rgba(0,0,0,.45);
}}
:root[data-theme="dark"]{
  --bg:#131211; --card:#1c1b19; --fg:#efece5; --dim:#9a938a; --line:#2c2a26;
  --accent:#54c47a; --new:#f2637a; --pill:#262420;
  --sh:0 1px 2px rgba(0,0,0,.3),0 6px 20px rgba(0,0,0,.35);
  --shh:0 2px 8px rgba(0,0,0,.4),0 16px 40px rgba(0,0,0,.45);
}
*{box-sizing:border-box;margin:0;padding:0}
html{background:var(--bg)}
body{background:var(--bg);color:var(--fg);
  font:16px/1.55 ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  -webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility}
.wrap{max-width:820px;margin:0 auto;padding:38px 18px 80px}
header{display:flex;align-items:flex-start;justify-content:space-between;gap:14px;
  margin-bottom:4px}
h1{font-size:25px;font-weight:750;letter-spacing:-.02em}
h1 span{color:var(--dim);font-weight:500;font-size:18px}
.sub{color:var(--dim);font-size:14px;margin-top:7px}
.theme{flex:none;font:13px/1 inherit;color:var(--dim);background:var(--pill);
  border:1px solid var(--line);border-radius:9px;padding:8px 12px;cursor:pointer}
.theme:hover{color:var(--fg)}
.newbar{margin:18px 0 2px;font-size:14px;font-weight:600;color:var(--accent)}
.newbar a{color:var(--dim);font-weight:400;text-decoration:underline;cursor:pointer;
  margin-left:8px}
main{margin-top:20px;display:grid;grid-template-columns:1fr 1fr;gap:14px}
.row{display:flex;flex-direction:column;padding:16px;background:var(--card);
  border:1px solid var(--line);border-radius:18px;box-shadow:var(--sh);
  color:inherit;text-decoration:none;transition:transform .12s,box-shadow .12s}
.row:hover{transform:translateY(-2px);box-shadow:var(--shh)}
.thumb{width:100%;aspect-ratio:1/1;border-radius:13px;background:var(--pill);
  border:1px solid var(--line);display:flex;align-items:center;justify-content:center;
  overflow:hidden;margin-bottom:13px}
.thumb img{width:100%;height:100%;object-fit:contain;padding:12px}
.thumb b{font:20px/1 ui-monospace,SFMono-Regular,Menlo,monospace;color:var(--dim)}
.name{min-width:0}
.name .t{display:-webkit-box;-webkit-box-orient:vertical;-webkit-line-clamp:2;
  overflow:hidden;font-size:15.5px;font-weight:650;line-height:1.32}
.name .m{margin-top:7px;display:flex;align-items:center;gap:8px;font-size:13px;
  color:var(--dim)}
.name .m .num{font:11.5px/1 ui-monospace,SFMono-Regular,Menlo,monospace;
  background:var(--pill);border:1px solid var(--line);padding:3px 7px;border-radius:6px}
.row.is-new .name .t::after{content:" NEW";font-size:11px;font-weight:800;
  color:var(--new);letter-spacing:.05em}
.fig{margin-top:auto;padding-top:14px;text-align:left}
.fig .buy{font:12.5px/1 ui-monospace,SFMono-Regular,Menlo,monospace;color:var(--dim)}
.fig .gap{display:block;margin-top:6px;font-size:32px;font-weight:800;
  color:var(--accent);letter-spacing:-.02em}
.fig .gap small{display:block;font-size:11px;font-weight:700;color:var(--dim);
  letter-spacing:.09em;text-transform:uppercase;margin-top:3px}
.empty{grid-column:1/-1;color:var(--dim);padding:60px 4px;text-align:center;font-size:16px}
.tools{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-top:18px}
.tools input,.tools select{font:13.5px/1 inherit;color:var(--fg);background:var(--pill);
  border:1px solid var(--line);border-radius:9px;padding:8px 11px;outline:none}
.tools input:focus,.tools select:focus{border-color:var(--accent)}
.tools input[type=search]{flex:1;min-width:150px}
.tools input[type=number]{width:96px}
.tools .count{margin-left:auto;font-size:13px;color:var(--dim);
  font-variant-numeric:tabular-nums}
.tools button{font:13.5px/1 inherit;color:var(--dim);background:var(--pill);
  border:1px solid var(--line);border-radius:9px;padding:8px 11px;cursor:pointer}
.tools button:hover{color:var(--fg)}
footer{margin-top:44px;color:var(--dim);font-size:12.5px;line-height:1.7}
@media(max-width:640px){
  main{grid-template-columns:1fr 1fr;gap:10px}
  h1{font-size:21px}
  .row{padding:12px;border-radius:15px}
  .thumb{margin-bottom:10px}
  .thumb b{font-size:15px}
  .name .t{font-size:13.5px}
  .fig .gap{font-size:22px}
  .fig .buy{font-size:11px}
  .tools .count{margin-left:0;width:100%}
}
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

  var board=document.getElementById('board');
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

  /* ---- filter + sort toolbar ---- */
  var q=document.getElementById('q'), shop=document.getElementById('shop'),
      sort=document.getElementById('sort'), min=document.getElementById('min'),
      count=document.getElementById('count'), copy=document.getElementById('copy');
  function num(r,k){var v=parseFloat(r.dataset[k]);return isNaN(v)?0:v;}
  function run(){
    if(!board) return;
    var s=(q&&q.value||'').trim().toLowerCase();
    var sh=shop&&shop.value||'', mn=parseFloat(min&&min.value)||0;
    var key=sort&&sort.value||'gap', asc=(key==='price'||key==='num');
    rows.sort(function(a,b){return asc?num(a,key)-num(b,key):num(b,key)-num(a,key);});
    rows.forEach(function(r){board.appendChild(r);});
    var shown=0;
    rows.forEach(function(r){
      var ok=true;
      if(s && r.dataset.q.indexOf(s)<0) ok=false;
      if(sh && r.dataset.shop!==sh) ok=false;
      if(mn && num(r,'gap')<mn) ok=false;
      r.style.display=ok?'':'none'; if(ok) shown++;
    });
    if(count) count.textContent=shown+' of '+rows.length;
    LS.s('lds-sort',key); LS.s('lds-shop',sh);
  }
  if(sort){var ss=LS.g('lds-sort'); if(ss) sort.value=ss;}
  if(shop){var sv=LS.g('lds-shop'); if(sv) shop.value=sv;}
  [q,shop,sort,min].forEach(function(el){ if(el) el.addEventListener('input',run); });
  if(copy) copy.addEventListener('click',function(){
    var t=rows.filter(function(r){return r.style.display!=='none';}).map(function(r){
      return [r.dataset.num, r.querySelector('.name .t').textContent.trim(),
              r.dataset.shop, '€'+r.dataset.price,
              '€'+Math.round(num(r,'gap'))+' under'].join('\t');
    }).join('\n');
    navigator.clipboard.writeText(t).then(function(){
      copy.textContent='Copied '+t.split('\n').filter(Boolean).length;
      setTimeout(function(){copy.textContent='Copy';},1500);
    });
  });
  run();
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
        gap_val, fig = net, f'~&euro;{net:.0f}<small>profit</small>'
    else:
        g = d.get("margin_vs_ebay_eur")
        gap_val = g or 0
        fig = (f'&euro;{g:.0f}<small>under your price</small>' if g is not None
               else f'&minus;{d["saving_pct"] * 100:.0f}%')
    haystack = html.escape(f'{d["set_num"]} {d["name"]} {shop}'.lower(), quote=True)

    return (
        f'<a class="row" href="{url}" target="_blank" rel="noopener" '
        f'data-key="{key}" data-price="{d["price_eur"]:.2f}" '
        f'data-gap="{gap_val:.2f}" data-shop="{html.escape(shop.lower(), quote=True)}" '
        f'data-num="{sn}" data-q="{haystack}">'
        f'<span class="thumb"><img src="{img}" alt="" loading="lazy" '
        f'onerror="this.style.display=\'none\'"><b>{sn}</b></span>'
        f'<span class="name"><span class="t">{name}</span>'
        f'<span class="m"><span class="num">{sn}</span>{shop}</span></span>'
        f'<span class="fig"><span class="buy">shop &euro;{d["price_eur"]:.0f}</span>'
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

    shops = sorted({(d.get("shop_name") or d.get("shop") or "") for d in deals},
                   key=str.lower)
    shop_opts = "".join(f'<option value="{html.escape(s.lower())}">{html.escape(s)}</option>'
                        for s in shops if s)
    tools = f"""<div class="tools">
    <input type="search" id="q" placeholder="Search set or name">
    <select id="shop"><option value="">All shops</option>{shop_opts}</select>
    <select id="sort">
      <option value="gap">Biggest gap</option>
      <option value="price">Cheapest first</option>
      <option value="num">Set number</option>
    </select>
    <input type="number" id="min" min="0" step="10" placeholder="min &euro;">
    <button id="copy" type="button">Copy</button>
    <span class="count" id="count">{len(deals)}</span>
  </div>""" if deals else ""

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
{tools}
<main id="board">
{body}
</main>
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
