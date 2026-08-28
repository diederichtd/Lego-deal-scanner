"""Render the standalone deals page: index.html + deals.json + feed.xml.

An inventory board - scanned fast, several times a day: photo, discount depth,
which shop, in stock, and (in eBay-seller mode) the margin against your own
listing. Sort / filter / copy controls are client-side vanilla JS; the page
works without JS too.
"""
from __future__ import annotations

import html
import json
import re
from email.utils import format_datetime
from datetime import datetime, timezone
from pathlib import Path

_FONTS = (
    "https://fonts.googleapis.com/css2?"
    "family=Archivo:wght@600;700;800&"
    "family=IBM+Plex+Mono:wght@500;600&"
    "family=IBM+Plex+Sans:wght@400;500;600&display=swap"
)

_STATE = {
    "new": ("NEW", "b-good", "--save"),
    "price_drop": ("PRICE DROP", "b-good", "--save"),
    "back_in_stock": ("BACK IN STOCK", "b-info", "--info"),
    "price_rise": ("STILL UNDER", "b-warn", "--warn"),
    "unchanged": ("", "", "--line"),
    "went_out_of_stock": ("OUT OF STOCK", "b-oos", "--oos"),
}

_CSS = """
*{box-sizing:border-box;margin:0;padding:0}
:root{
  --paper:#f6f4f0; --raise:#fdfcfa; --ink:#201c1a; --muted:#6f665f; --line:#e5dfd6;
  --card:#fff; --accent:#c8102e; --accent-ink:#c8102e;
  --save:#1f7a3d; --info:#1256a0; --warn:#8a5a00; --oos:#b0342c;
  --shadow:0 1px 2px rgba(32,28,26,.05),0 10px 30px rgba(32,28,26,.07);
}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
  --paper:#171310; --raise:#1f1a16; --ink:#f1ece6; --muted:#9c9188;
  --line:#352d27; --card:#221d19; --accent:#f2455c; --accent-ink:#ff6b74;
  --save:#4cc271; --info:#5aa7e6; --warn:#d8a13a; --oos:#e56a60;
  --shadow:0 1px 2px rgba(0,0,0,.35),0 12px 32px rgba(0,0,0,.4);
}}
:root[data-theme="dark"]{
  --paper:#171310; --raise:#1f1a16; --ink:#f1ece6; --muted:#9c9188; --line:#352d27;
  --card:#221d19; --accent:#f2455c; --accent-ink:#ff6b74;
  --save:#4cc271; --info:#5aa7e6; --warn:#d8a13a; --oos:#e56a60;
  --shadow:0 1px 2px rgba(0,0,0,.35),0 12px 32px rgba(0,0,0,.4);
}
html{background:var(--paper)}
body{background:var(--paper);color:var(--ink);
  font:400 15px/1.55 "IBM Plex Sans",system-ui,-apple-system,sans-serif;
  -webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility}
.wrap{max-width:940px;margin:0 auto;padding:0 20px 100px}
a{color:inherit;text-decoration:none}

.mast{position:sticky;top:0;z-index:20;
  background:linear-gradient(var(--paper),var(--paper) 78%,transparent);
  padding:22px 0 12px}
.mast .wrap{padding-bottom:0}
.brand{font:800 22px/1 "Archivo",sans-serif;letter-spacing:-.015em;display:flex;
  align-items:baseline;gap:9px;flex-wrap:wrap}
.brand b{color:var(--accent-ink)}
.brand .tag{font:600 11px/1 "IBM Plex Mono",monospace;letter-spacing:.13em;
  color:var(--muted);border:1px solid var(--line);padding:3px 6px;border-radius:5px;
  transform:translateY(-2px)}
.brand .who{color:var(--muted);font-weight:600;font-size:15px}
.lede{color:var(--muted);font-size:13.5px;margin-top:8px;max-width:64ch}

.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;
  margin:18px 0 6px}
.tile{background:var(--raise);border:1px solid var(--line);border-radius:12px;
  padding:13px 15px}
.tile .n{font:800 24px/1.05 "Archivo",sans-serif;font-variant-numeric:tabular-nums;
  letter-spacing:-.02em}
.tile .l{font:500 11.5px/1.3 "IBM Plex Sans",sans-serif;color:var(--muted);
  margin-top:5px;text-transform:uppercase;letter-spacing:.05em}
.tile.good .n{color:var(--save)}

.ribbon{margin:14px 0 0;padding:10px 14px;border:1px dashed var(--accent);
  border-radius:10px;color:var(--accent-ink);
  font:600 13px/1.45 "IBM Plex Sans",sans-serif;
  background:color-mix(in srgb,var(--accent) 7%,transparent)}

.controls{display:flex;flex-wrap:wrap;gap:8px;align-items:center;
  margin:20px 0 14px;padding-top:14px;border-top:1px solid var(--line)}
.controls select,.controls button{font:500 13px/1 "IBM Plex Sans",sans-serif;
  color:var(--ink);background:var(--raise);border:1px solid var(--line);
  border-radius:8px;padding:8px 11px;cursor:pointer}
.controls button:hover,.chip:hover{border-color:var(--accent)}
.chip{font:500 12px/1 "IBM Plex Sans",sans-serif;color:var(--muted);
  background:var(--raise);border:1px solid var(--line);border-radius:999px;
  padding:6px 11px;cursor:pointer;user-select:none}
.chip[aria-pressed="true"]{color:#fff;background:var(--accent);border-color:var(--accent)}
.controls label{font:500 13px/1 "IBM Plex Sans",sans-serif;color:var(--muted);
  display:flex;align-items:center;gap:6px;cursor:pointer}
.count{margin-left:auto;font:600 13px/1 "IBM Plex Mono",monospace;color:var(--muted);
  font-variant-numeric:tabular-nums}

.board{display:flex;flex-direction:column;gap:9px}
.row{position:relative;display:grid;
  grid-template-columns:56px 64px 1fr auto auto;gap:15px;align-items:center;
  padding:12px 16px 12px 18px;background:var(--card);border:1px solid var(--line);
  border-radius:12px;box-shadow:var(--shadow);
  transition:transform .12s ease,border-color .12s ease}
.row::before{content:"";position:absolute;left:0;top:0;bottom:0;width:4px;
  border-radius:12px 0 0 12px;background:var(--stripe,var(--line))}
.row:hover{transform:translateY(-1px);
  border-color:color-mix(in srgb,var(--accent) 42%,var(--line))}
.hit{position:absolute;inset:0;z-index:1;border-radius:12px}
.row:focus-within{outline:2px solid var(--accent);outline-offset:2px}
.thumb{width:56px;height:56px;border-radius:9px;background:var(--raise);
  border:1px solid var(--line);display:flex;align-items:center;justify-content:center;
  overflow:hidden;position:relative}
.thumb img{width:100%;height:100%;object-fit:contain}
.thumb b{font:700 12px/1 "IBM Plex Mono",monospace;color:var(--muted)}
.setno{font:600 16px/1 "IBM Plex Mono",monospace;color:var(--muted);
  font-variant-numeric:tabular-nums}
.meta{min-width:0}
.pname{font:600 15px/1.3 "IBM Plex Sans",sans-serif;display:block;
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.tags{display:flex;flex-wrap:wrap;gap:6px;margin-top:5px;align-items:center}
.shop{font:600 12px/1 "IBM Plex Sans",sans-serif;color:var(--muted);
  display:flex;align-items:center;gap:5px}
.shop::before{content:"";width:7px;height:7px;border-radius:50%;background:var(--accent)}
.badge{font:600 10px/1 "IBM Plex Mono",monospace;letter-spacing:.07em;
  padding:3px 6px;border-radius:999px;border:1px solid currentColor}
.b-good{color:var(--save)} .b-info{color:var(--info)}
.b-warn{color:var(--warn)} .b-oos{color:var(--oos)}
.src{font:500 10px/1 "IBM Plex Mono",monospace;color:var(--muted);opacity:.75}
.note{display:block;margin-top:4px;font:400 10.5px/1.3 "IBM Plex Sans",sans-serif;
  color:var(--warn)}
.prices{text-align:right}
.now{font:600 17px/1 "IBM Plex Mono",monospace;font-variant-numeric:tabular-nums;
  display:block}
.rrp{font:500 11px/1.4 "IBM Plex Mono",monospace;color:var(--muted);
  margin-top:3px;display:block}
.rrp s{text-decoration:line-through}
.mine{color:var(--accent-ink)}
.save{text-align:right;min-width:104px}
.amt{font:600 16px/1 "IBM Plex Mono",monospace;color:var(--save);
  font-variant-numeric:tabular-nums;display:block}
.amt.pos{color:var(--save)} .amt.neg{color:var(--oos)}
.pct{font:500 11px/1 "IBM Plex Mono",monospace;color:var(--muted);display:block;
  margin-top:3px}
.bar{display:block;height:3px;margin-top:6px;background:var(--line);border-radius:2px;
  overflow:hidden}
.bar i{display:block;height:100%;background:var(--save)}
.margin{margin-top:6px;font:600 11px/1 "IBM Plex Mono",monospace;display:block}
.margin.pos{color:var(--save)} .margin.neg{color:var(--oos)}
.mylink{position:relative;z-index:2;font:600 11px/1 "IBM Plex Sans",sans-serif;
  color:var(--accent-ink);margin-top:4px;display:inline-block}
.mylink:hover{text-decoration:underline}

.empty{text-align:center;color:var(--muted);padding:56px 20px;border:1px dashed var(--line);
  border-radius:14px}
.empty b{color:var(--ink);font:600 16px/1.4 "Archivo",sans-serif;display:block;
  margin-bottom:6px}

.aux{margin-top:44px}
.aux h2{font:700 12px/1 "IBM Plex Mono",monospace;letter-spacing:.11em;
  text-transform:uppercase;color:var(--muted);margin-bottom:12px}
.aux table{width:100%;border-collapse:collapse;font-size:13px}
.aux td,.aux th{text-align:left;padding:8px 10px;border-bottom:1px solid var(--line)}
.aux th{font:600 11px/1 "IBM Plex Mono",monospace;letter-spacing:.06em;
  text-transform:uppercase;color:var(--muted)}
.aux td:nth-child(2){font-family:"IBM Plex Mono",monospace;
  font-variant-numeric:tabular-nums;white-space:nowrap}
.aux a{color:var(--accent-ink);font-weight:600}
.aux ul{list-style:none;font-size:13px;color:var(--muted)}
.aux li{padding:6px 0;border-bottom:1px solid var(--line)}

footer{margin-top:60px;padding-top:20px;border-top:1px solid var(--line);
  font:400 12px/1.6 "IBM Plex Sans",sans-serif;color:var(--muted)}

@media (max-width:660px){
  .row{grid-template-columns:52px 1fr;
    grid-template-areas:"t m" "t s" "p p" "v v";row-gap:9px}
  .thumb{grid-area:t;width:52px;height:52px}.setno{display:none}
  .meta{grid-area:m}.tags{grid-area:s}
  .prices{grid-area:p;text-align:left}.save{grid-area:v;text-align:left;min-width:0}
  .now{display:inline;margin-right:10px}.rrp{display:inline}
  .count{width:100%;margin:4px 0 0}
}
.acts{margin-left:auto;display:flex;gap:8px}
.mini{font:600 12px/1 "IBM Plex Sans",sans-serif;color:var(--ink);background:var(--raise);
  border:1px solid var(--line);border-radius:8px;padding:7px 11px;cursor:pointer}
.mini:hover{border-color:var(--accent)}
.since{margin:14px 0 0;padding:9px 13px;border:1px solid var(--save);border-radius:10px;
  background:color-mix(in srgb,var(--save) 9%,transparent);color:var(--save);
  font:600 12.5px/1.4 "IBM Plex Sans",sans-serif;display:flex;gap:10px;align-items:center}
.since a{color:var(--muted);font-weight:500;cursor:pointer;text-decoration:underline}
.cov{margin:12px 0 0;font:500 12.5px/1.5 "IBM Plex Sans",sans-serif;color:var(--muted)}
.cov b{color:var(--ink);font-family:"IBM Plex Mono",monospace;
  font-variant-numeric:tabular-nums}
.cov .warn{color:var(--warn)}
.row.seen-new::before{background:var(--save)}
.row.seen-new{border-color:color-mix(in srgb,var(--save) 45%,var(--line))}
.vb{font:600 10px/1 "IBM Plex Mono",monospace;letter-spacing:.05em;padding:3px 6px;
  border-radius:999px;color:var(--save);border:1px solid currentColor;white-space:nowrap}
.row:hover .pname::after{content:" \\2197";color:var(--muted);font-weight:400}
@media (prefers-reduced-motion:no-preference){
  .row{animation:rise .38s cubic-bezier(.2,.7,.2,1) backwards}
  @keyframes rise{from{opacity:0;transform:translateY(6px)}}
}
"""

_JS = r"""
(function(){
  var root=document.documentElement;
  var LS={g:function(k){try{return localStorage.getItem(k)}catch(e){return null}},
          s:function(k,v){try{localStorage.setItem(k,v)}catch(e){}}};

  /* theme: system -> light -> dark */
  var modes=[['','◐ Auto'],['light','☀ Light'],['dark','☾ Dark']];
  var tbtn=document.getElementById('theme');
  var cur=LS.g('lds-theme')||'';
  function applyTheme(m){
    if(m) root.setAttribute('data-theme',m); else root.removeAttribute('data-theme');
    var hit=modes.filter(function(x){return x[0]===m;})[0]||modes[0];
    if(tbtn) tbtn.textContent=hit[1];
  }
  applyTheme(cur);
  if(tbtn) tbtn.addEventListener('click',function(){
    var i=0; for(var j=0;j<modes.length;j++){if(modes[j][0]===cur)i=j;}
    cur=modes[(i+1)%modes.length][0]; LS.s('lds-theme',cur); applyTheme(cur);
  });

  /* update + auto-refresh */
  var ub=document.getElementById('update');
  if(ub) ub.addEventListener('click',function(){location.reload();});
  var auto=document.getElementById('auto'), timer=null;
  if(auto){
    auto.checked=LS.g('lds-auto')==='1';
    function arm(){clearTimeout(timer); if(auto.checked) timer=setTimeout(function(){
      location.reload();},900000);}
    auto.addEventListener('change',function(){LS.s('lds-auto',auto.checked?'1':'0');arm();});
    arm();
  }

  var board=document.getElementById('board'); if(!board) return;
  var rows=[].slice.call(board.querySelectorAll('.row'));
  var sortSel=document.getElementById('sort'), okonly=document.getElementById('confonly'),
      count=document.getElementById('count'), copyBtn=document.getElementById('copy');
  var chips=[].slice.call(document.querySelectorAll('.chip')); var active=new Set();
  function num(r,k){var v=parseFloat(r.dataset[k]); return isNaN(v)?0:v;}
  function apply(){
    var key=sortSel?sortSel.value:'net';
    var asc=(key==='price');
    rows.sort(function(a,b){return asc?num(a,key)-num(b,key):num(b,key)-num(a,key);});
    rows.forEach(function(r){board.appendChild(r);});
    var shown=0;
    rows.forEach(function(r){
      var ok=true;
      if(active.size && !active.has(r.dataset.shop)) ok=false;
      if(okonly && okonly.checked && r.dataset.verified!=='1') ok=false;
      r.style.display=ok?'':'none'; if(ok) shown++;
    });
    if(count) count.textContent=shown+(shown===1?' deal':' deals');
  }
  if(sortSel) sortSel.addEventListener('change',apply);
  if(okonly) okonly.addEventListener('change',apply);
  chips.forEach(function(c){c.addEventListener('click',function(){
    var s=c.dataset.shop, on=c.getAttribute('aria-pressed')==='true';
    c.setAttribute('aria-pressed',!on);
    if(on) active.delete(s); else active.add(s);
    apply();
  });});
  if(copyBtn) copyBtn.addEventListener('click',function(){
    var lines=rows.filter(function(r){return r.style.display!=='none';})
      .map(function(r){return [r.dataset.set,r.dataset.shopname,
        '€'+r.dataset.price,r.dataset.pct+'%off'].join('\t');});
    navigator.clipboard.writeText(lines.join('\n')).then(function(){
      copyBtn.textContent='Copied '+lines.length;
      setTimeout(function(){copyBtn.textContent='Copy list';},1500);
    });
  });

  /* new / cheaper since last visit */
  var since=document.getElementById('since');
  var prev={}; try{prev=JSON.parse(LS.g('lds-seen')||'{}')||{};}catch(e){}
  var first=!Object.keys(prev).length, nNew=0, nDrop=0, curMap={};
  rows.forEach(function(r){
    var k=r.dataset.set+'|'+r.dataset.shop, p=num(r,'price'); curMap[k]=p;
    if(first) return;
    var tags=r.querySelector('.tags');
    if(!(k in prev)){ r.classList.add('seen-new'); nNew++;
      if(tags) tags.insertAdjacentHTML('beforeend',' <span class="vb">NEW SINCE LAST VISIT</span>'); }
    else if(p < prev[k]-0.01){ r.classList.add('seen-new'); nDrop++;
      if(tags) tags.insertAdjacentHTML('beforeend',' <span class="vb">↓ CHEAPER SINCE LAST VISIT</span>'); }
  });
  if(since && (nNew||nDrop)){
    since.hidden=false;
    since.innerHTML=nNew+' new'+(nDrop?' · '+nDrop+' cheaper':'')+
      ' since your last visit <a id="clr">clear</a>';
    var clr=document.getElementById('clr');
    if(clr) clr.addEventListener('click',function(){
      rows.forEach(function(r){r.classList.remove('seen-new');});
      [].slice.call(document.querySelectorAll('.vb')).forEach(function(e){e.remove();});
      since.hidden=true;
    });
  }
  function snap(){LS.s('lds-seen',JSON.stringify(curMap));}
  setTimeout(snap,60000); window.addEventListener('beforeunload',snap);

  apply();
})();
"""


def _depth(pct: float) -> int:
    return max(4, min(100, round(pct * 250)))


def _row(d: dict, seller: bool) -> str:
    label, bcls, stripe = _STATE.get(d.get("state", "unchanged"), ("", "", "--line"))
    badge = f'<span class="badge {bcls}">{label}</span>' if label else ""
    oos = "" if d.get("available") is not False else \
        '<span class="badge b-oos">SOLD OUT</span>'
    url = html.escape(d["url"], quote=True)
    name = html.escape(d["name"])
    shop = html.escape(d.get("shop_name") or d["shop"])
    img = html.escape(d.get("image_url") or "", quote=True)
    src = html.escape(d.get("source", ""))
    instock = "0" if d.get("available") is False else "1"

    net = d.get("net_profit_eur")
    sell = d.get("resale_eur") or d.get("ebay_price_eur")
    src = html.escape(d.get("resale_source") or d.get("source", ""))
    mine = (f'<span class="rrp mine">sell ~&euro;{sell:.0f} &middot; {src}</span>'
            if sell else "")

    v = d.get("verified")
    vbadge = ('<span class="badge b-info">&check; in stock</span>' if v is True
              else '<span class="badge b-warn">unconfirmed</span>' if v is None
              and "verify_reason" in d else "")
    fdays = d.get("falling_days") or 0
    fall = f'<span class="badge b-good">falling {fdays}d</span>' if fdays >= 2 else ""

    if net is not None:
        pcls = "pos" if net > 0 else "neg"
        amt = f'<span class="amt {pcls}">~&euro;{net:.0f}</span><span class="pct">profit</span>'
    else:
        amt = (f'<span class="amt">&minus;&euro;{d["saving_eur"]:.0f}</span>'
               f'<span class="pct">&minus;{d["saving_pct"] * 100:.0f}%</span>')

    my_link = (f'<a class="mylink" href="{html.escape(d["ebay_url"], quote=True)}" '
               f'target="_blank" rel="noopener">your listing &rsaquo;</a>'
               if d.get("ebay_url") else "")

    return f"""<div class="row" style="--stripe:var({stripe})"
  data-shop="{html.escape((d.get('shop_name') or d['shop']).lower())}" data-shopname="{shop}"
  data-set="{html.escape(d['set_num'])}" data-price="{d['price_eur']:.2f}"
  data-pct="{d['saving_pct'] * 100:.1f}" data-saved="{d['saving_eur']:.2f}"
  data-margin="{d.get('margin_vs_ebay_eur') or 0:.2f}"
  data-net="{net if net is not None else -999:.2f}"
  data-instock="{instock}" data-verified="{'1' if d.get('verified') is True else '0'}">
  <a class="hit" href="{url}" target="_blank" rel="noopener"
     aria-label="Open {name} at {shop}"></a>
  <span class="thumb">{'<img src="' + img + '" alt="" loading="lazy" onerror="this.remove()">' if img else ''}<b>{html.escape(d['set_num'])}</b></span>
  <span class="setno">{html.escape(d['set_num'])}</span>
  <span class="meta">
    <span class="pname">{name}</span>
    <span class="tags"><span class="shop">{shop}</span>{badge}{vbadge}{fall}{oos}</span>
    {f'<span class="note">{html.escape(d["note"])}</span>' if d.get("note") else ""}
  </span>
  <span class="prices">
    <span class="now">&euro;{d['price_eur']:.2f}</span>
    {mine}
  </span>
  <span class="save">
    {amt}
    <span class="bar"><i style="width:{_depth(d['saving_pct'])}%"></i></span>
    {my_link}
  </span>
</div>"""


def render_html(result: dict, cfg: dict) -> str:
    title = html.escape(cfg.get("title", "LEGO Deals DE"))
    deals = result["deals"]
    seller = result.get("seller")
    thr = result.get("threshold_pct", 0.0)
    biggest = max((d["saving_pct"] for d in deals), default=0.0)
    nets = [d["net_profit_eur"] for d in deals if d.get("net_profit_eur") is not None]
    total_profit = sum(n for n in nets if n > 0)
    best_profit = max(nets) if nets else 0
    confirmed = sum(1 for d in deals if d.get("verified") is True)

    shops = sorted({(d.get("shop_name") or d["shop"]) for d in deals}, key=str.lower)
    chips = "".join(
        f'<span class="chip" role="button" aria-pressed="false" '
        f'data-shop="{html.escape(n.lower())}">{html.escape(n)}</span>' for n in shops
    )

    who = f'<span class="who">· {html.escape(seller)}</span>' if seller else ""
    if seller:
        lede = (f'Sets <b>{html.escape(seller)}</b> sells that you can buy cheaper right '
                f'now at a German shop. &ldquo;profit&rdquo; = expected resale minus the '
                f'shop price, eBay&rsquo;s ~12% fee, and postage. Verify stock before buying.')
    else:
        lede = (f'LEGO sets currently {thr * 100:.0f}%+ below LEGO.de across German '
                f'shops. Updated hourly.')

    hbanner = (f'<div class="ribbon">&#9888; {html.escape(result["health"])}</div>'
               if result.get("health") else "")

    tiles = f"""<div class="tiles">
    <div class="tile"><div class="n">{len(deals)}</div><div class="l">worth flipping</div></div>
    <div class="tile good"><div class="n">&euro;{best_profit:.0f}</div><div class="l">best single profit</div></div>
    <div class="tile good"><div class="n">&euro;{total_profit:.0f}</div><div class="l">total if you bought all</div></div>
    <div class="tile"><div class="n">{confirmed}</div><div class="l">stock confirmed</div></div>
  </div>"""

    board = "\n".join(_row(d, bool(seller)) for d in deals) or (
        f'<div class="empty"><b>Nothing {thr * 100:.0f}%+ below LEGO.de right now</b>'
        f'{"None of your eBay sets are on sale elsewhere. " if seller else ""}'
        'Check back after the next hourly run.</div>'
    )

    ribbon = ""
    if cfg.get("preview_note"):
        ribbon = f'<div class="ribbon">{html.escape(cfg["preview_note"])}</div>'

    cov_html = ""
    cov = result.get("coverage")
    if cov:
        n_un = len(result.get("uncovered") or [])
        gap = (f' · <span class="warn">{n_un} not checked (see bottom)</span>'
               if n_un else " · every listed set checked")
        cov_html = (
            f'<div class="cov">Coverage: <b>{cov["listed"]}</b> LEGO sets you list · '
            f'<b>{cov["priced"]}</b> with a reference price · '
            f'<b>{cov["with_route"]}</b> reachable at a retailer · '
            f'<b>{cov["on_sale"]}</b> on sale now{gap}</div>'
        )

    sort_opts = [("net", "profit"), ("price", "shop price"), ("pct", "% off UVP")]
    sort_html = "".join(f'<option value="{v}">{lbl}</option>' for v, lbl in sort_opts)

    controls = f"""<div class="controls">
    <select id="sort" aria-label="Sort by">{sort_html}</select>
    {chips}
    <label><input type="checkbox" id="confonly"> stock-confirmed only</label>
    <label><input type="checkbox" id="auto"> auto-refresh</label>
    <button id="copy" type="button">Copy list</button>
    <span class="count" id="count">{len(deals)} deals</span>
  </div>"""

    aux = ""
    if result.get("unverified"):
        rows = "\n".join(
            f"<tr><td>{html.escape(u['title'][:88])}</td>"
            f"<td>&euro;{u['price']:.2f}</td><td>{html.escape(u.get('merchant', '') or '—')}</td>"
            f'<td><a href="{html.escape(u["url"], quote=True)}" target="_blank" '
            f'rel="noopener">open &rsaquo;</a></td></tr>'
            for u in result["unverified"][:40]
        )
        aux += f"""<section class="aux"><h2>Community posts · check manually</h2>
  <table><thead><tr><th>From mydealz</th><th>Price</th><th>Shop</th><th></th></tr></thead>
  <tbody>{rows}</tbody></table></section>"""
    if result.get("uncovered"):
        items = "\n".join(
            f"<li>{html.escape(u.get('set_num', ''))} {html.escape(u.get('name', ''))}"
            f" — {html.escape(u['reason'])}</li>"
            for u in result["uncovered"][:80]
        )
        aux += (f'<section class="aux"><h2>Your sets not yet checked '
                f'({len(result["uncovered"])})</h2><ul>{items}</ul></section>')

    if result.get("thin"):
        rows = "\n".join(
            f"<tr><td>{html.escape(t['set_num'])} {html.escape(t['name'][:44])}</td>"
            f"<td>&euro;{t['price_eur']:.0f} {html.escape(t.get('shop_name', ''))}</td>"
            f"<td>~&euro;{t.get('net_profit_eur', 0):.0f}</td>"
            f'<td><a href="{html.escape(t["url"], quote=True)}" target="_blank" '
            f'rel="noopener">open &rsaquo;</a></td></tr>'
            for t in result["thin"][:40]
        )
        aux += (f'<section class="aux"><h2>Thin margin ({len(result["thin"])}) &mdash; '
                f'small profit, only if your fees are low</h2>'
                f"<table><thead><tr><th>Set</th><th>Buy</th><th>Est. profit</th><th></th>"
                f"</tr></thead><tbody>{rows}</tbody></table></section>")

    if result.get("stale"):
        items = "\n".join(
            f"<li>{html.escape(s['set_num'])} {html.escape(s['name'][:44])} — "
            f"{html.escape(s.get('shop_name', ''))}: {html.escape(s.get('verify_reason', 'gone'))}</li>"
            for s in result["stale"][:40]
        )
        aux += (f'<section class="aux"><h2>Looked good but not confirmed '
                f'({len(result["stale"])})</h2><ul>{items}</ul></section>')

    if result.get("errors"):
        items = "\n".join(
            f"<li>{html.escape(e.get('set_num', ''))} {html.escape(e.get('name', ''))}"
            f" — {html.escape(e.get('shop', '') or '')} ({html.escape(e['reason'])})</li>"
            for e in result["errors"][:40]
        )
        aux += f'<section class="aux"><h2>Could not read</h2><ul>{items}</ul></section>'

    return f"""<!doctype html>
<html lang="de"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="{_FONTS}">
<style>{_CSS}</style></head>
<body>
<header class="mast"><div class="wrap">
  <div class="brand">LEGO&nbsp;<b>Deals</b><span class="tag">DE</span>{who}
    <span class="acts">
      <button id="theme" class="mini" type="button" aria-label="Theme">&#9680; Auto</button>
      <button id="update" class="mini" type="button">&#8635; Update</button>
    </span>
  </div>
  <p class="lede">{lede} · <a href="deals.json">JSON</a> · <a href="feed.xml">RSS</a>
    · updated {html.escape(result['generated_at'])}</p>
</div></header>
<div class="wrap">
{hbanner}
{ribbon}
{tiles}
{cov_html}
<div id="since" class="since" hidden></div>
{controls}
<section class="board" id="board">
{board}
</section>
{aux}
<footer>Prices scraped from public product pages and go stale between runs; shops
misprice and limit stock, and condition may differ from your listings. Verify
every price before buying. Not affiliated with the LEGO Group.</footer>
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
