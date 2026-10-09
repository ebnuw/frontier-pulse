"""Build the static site into site/."""
import html
import json
import shutil
import time
from datetime import datetime, timezone

from . import cards, funding as fpfunding, hl, news as fpnews
from .glossary import expand, glossary_html, popover_data, term as T
from .collector import last_snapshot
from .common import (DATA, NY, NYSE_EARLY_CLOSE, NYSE_HOLIDAYS, ROOT, SITE, WIB, fmt_pct, fmt_usd, funding_apr, funding_apr_24h,
                     hk_session_open, implied_valuation_usd, load_json, pct_change, save_json, site_cfg,
                     us_session_open, valuations_cfg)
from .metrics import pre_ipo_metrics

E = html.escape


def history(vcfg, cfg):
    """Daily closes since launch -> implied valuation ($B) series for each pre-IPO perp."""
    now_ms = int(time.time() * 1000)
    series = {}
    for sym in cfg["pre_ipo"]:
        cs = hl.candles(sym, "1d", now_ms - 400 * 86400 * 1000, now_ms)
        series[sym] = {datetime.fromtimestamp(c["t"] / 1000, timezone.utc).strftime("%Y-%m-%d"):
                       implied_valuation_usd(c["c"], vcfg["usd_per_price_point"]) / 1e9 for c in cs}
    dates = sorted(set().union(*[set(s) for s in series.values()]))
    out = {"dates": dates, "series": {}, "last_round_b": {}}
    for sym, s in series.items():
        out["series"][sym] = [round(s[d], 1) if d in s else None for d in dates]
        out["last_round_b"][sym] = vcfg["assets"][sym]["last_round_usd"] / 1e9
    a, o = cfg["pre_ipo"][:2]
    out["ratio"] = [round(x / y, 3) if x and y else None for x, y in zip(out["series"][a], out["series"][o])]
    return out


def equity_rows(snap, cfg):
    rows = []
    for sym, m in snap["m"].items():
        if m["oi"] == 0 and m["vol"] == 0:
            continue
        if sym in cfg["pre_ipo"]:
            continue
        rows.append({
            "symbol": sym, "ticker": sym.split(":")[1], "name": cfg["names"].get(sym, sym.split(":")[1]),
            "mark": m["mark"], "change_24h": pct_change(m["mark"], m["prev"]),
            "funding_apr": funding_apr_24h(sym, m["funding"]), "oi_usd": m["oi"] * m["mark"], "vol_usd": m["vol"],
            "market": "HK" if sym in cfg["hk_symbols"] else "US",
        })
    rows.sort(key=lambda r: -r["vol_usd"])
    for r in rows:
        s = sparkline(r["symbol"])
        r["spark"] = s
        r["change_7d"] = pct_change(s[-1], s[0]) if s and len(s) > 1 else None
    return rows


def sparkline(sym, days=7):
    """Hourly closes for the last `days` days (None on API failure)."""
    now_ms = int(time.time() * 1000)
    try:
        cs = hl.candles(sym, "1h", now_ms - days * 86400 * 1000, now_ms)
        return [float(c["c"]) for c in cs]
    except Exception:
        return None


def spark_svg(vals, w=160, h=36):
    if not vals or len(vals) < 2:
        return '<svg class="spark" viewBox="0 0 160 36"></svg>'
    lo, hi = min(vals), max(vals)
    rng = (hi - lo) or 1
    pts = " ".join(f"{i * w / (len(vals) - 1):.1f},{h - 2 - (v - lo) / rng * (h - 4):.1f}" for i, v in enumerate(vals))
    ch = (vals[-1] - vals[0]) / vals[0] if vals[0] else 0
    cls = "flat" if round(ch * 100, 1) == 0 else ("up" if ch > 0 else "down")
    return (f'<svg class="spark {cls}" viewBox="0 0 {w} {h}" preserveAspectRatio="none" aria-hidden="true">'
            f'<polyline points="{pts}" fill="none" stroke="currentColor" stroke-width="1.6" vector-effect="non-scaling-stroke"/></svg>')


def px(v):
    return f"{v:,.2f}" if v >= 10 else f"{v:,.4f}"


def month_year(iso):
    return datetime.strptime(iso, "%Y-%m-%d").strftime("%b %Y")


def updown(v):
    if v is None or round(v * 100, 1) == 0:
        return "flat"
    return "up" if v > 0 else "down"


def minicards_html(rows):
    out = []
    for r in rows:
        ch7 = r.get("change_7d")
        ch7s = f'<span class="{updown(ch7)}">{fmt_pct(ch7)}</span> {T("change_7d", "7d")}' if ch7 is not None else ""
        out.append(f"""<article class="mini" data-mkt="{r['market']}">
  <div class="mh"><b>{E(r['ticker'])}</b><small>{E(r['name'])}</small></div>
  <div class="sess-line"><span class="dot" aria-hidden="true"></span><span class="sess-txt">Trading 24/7 on Entropy</span></div>
  <div class="mp num">${px(r['mark'])} <span class="{updown(r['change_24h'])}">{fmt_pct(r['change_24h'])}</span></div>
  {spark_svg(r.get('spark'))}
  <div class="mf num"><span>{ch7s}</span><span>{T('volume_24h', 'Vol')} {fmt_usd(r['vol_usd'])}</span><span>{T('oi', 'OI')} {fmt_usd(r['oi_usd'])}</span></div>
</article>""")
    return "\n".join(out)


def plain_summary(metrics):
    """2-3 sentences with the live numbers, generated from metrics (no hardcoded figures)."""
    ms = list(metrics.values())
    if not ms:
        return ""
    first = ms[0]
    parts = [f"Traders on {T('entropy')} currently price {E(first['name'])} at <b>{fmt_usd(first['valuation_usd'])}</b> — about "
             f"<b>{first['multiple']:.1f}×</b> its {T('last_round', 'last funding round')} valuation "
             f"({fmt_usd(first['last_round_usd'])}, {month_year(first['last_round_date'])})."]
    for m in ms[1:]:
        parts.append(f"{E(m['name'])}: <b>{fmt_usd(m['valuation_usd'])}</b>, <b>{m['multiple']:.1f}×</b> its last round "
                     f"({fmt_usd(m['last_round_usd'])}, {month_year(m['last_round_date'])}).")
    if len(ms) >= 2:
        parts.append(f"{E(ms[0]['name'])} is valued at <b>{ms[0]['valuation_usd'] / ms[1]['valuation_usd']:.2f}×</b> {E(ms[1]['name'])}.")
    return " ".join(parts)


def card_html(m):
    cap_pct = m["oi_usd"] / m["oi_cap_usd"]
    scale = max(m["multiple"], 1.0) * 1.08
    fill = m["multiple"] / scale * 100
    mark_at = 1 / scale * 100
    fr = m["funding_apr"]
    who = "" if fr is None or fr == 0 else (" · longs pay shorts" if fr > 0 else " · shorts pay longs")
    return f"""<article class="card {m['short'].lower()}">
  <div class="ch"><h3>{E(m['name'])}</h3><span class="tick">io:{E(m['short'])}</span></div>
  <div class="eyebrow">{T('implied_valuation')}</div>
  <div class="big num">{fmt_usd(m['valuation_usd'])}</div>
  <div class="mult">
    <div class="mult-top"><span><b class="num">{m['multiple']:.2f}×</b> {T('multiple', 'vs last round')}</span>
      <span class="{updown(m['premium'])} num">{fmt_pct(m['premium'])} {T('premium')}</span></div>
    <div class="track" role="img" aria-label="Last round {fmt_usd(m['last_round_usd'])}, now {fmt_usd(m['valuation_usd'])}, {m['multiple']:.2f} times">
      <div class="fill" style="width:{fill:.1f}%"></div><div class="tmark" style="left:{mark_at:.1f}%"></div>
    </div>
    <div class="track-lbl num"><span>{T('last_round', 'Last round')} {fmt_usd(m['last_round_usd'])}</span><span>Now {fmt_usd(m['valuation_usd'])}</span></div>
  </div>
  <dl class="stats-grid">
    <dt>{T('mark')}</dt><dd class="num">{px(m['mark'])} <small>(oracle {px(m['oracle'])})</small></dd>
    <dt>{T('change_24h')}</dt><dd class="num {updown(m['change_24h'])}">{fmt_pct(m['change_24h'])}</dd>
    <dt>{T('funding_apr')}</dt><dd class="num">{fmt_pct(fr)}<small>{who}</small></dd>
    <dt>{T('oi')}</dt><dd class="num">{fmt_usd(m['oi_usd'])} <small>({cap_pct * 100:.0f}% of {fmt_usd(m['oi_cap_usd'])} {T('oi_cap', 'cap')})</small></dd>
    <dt>{T('volume_24h')}</dt><dd class="num">{fmt_usd(m['vol_24h_usd'])}</dd>
    <dt>{T('lower_bound')}</dt><dd class="num">{m['lower']:,} <small>({fmt_pct(m['to_lower'], 0)} = {fmt_usd(m['lower'] * 1e9)})</small></dd>
    <dt>{T('upper_bound')}</dt><dd class="num">{m['upper']:,} <small>({fmt_pct(m['to_upper'], 0)} = {fmt_usd(m['upper'] * 1e9)})</small></dd>
    <dt>{T('no_ipo')}</dt><dd class="num">{m['resolution_date']} <small>({m['days_to_resolution']:,} days)</small></dd>
  </dl>
  <p class="src">Last round: {m['last_round_date']} · {E(m['last_round_label'])} · <a href="{E(m['source_url'])}" rel="noopener">source</a></p>
</article>"""


def equities_html(rows):
    out = []
    for r in rows:
        out.append(f"""<tr data-mkt="{r['market']}"><td><b>{E(r['ticker'])}</b><br><small>{E(r['name'])}</small></td>
<td class="num">{px(r['mark'])}</td><td class="num {updown(r['change_24h'])}">{fmt_pct(r['change_24h'])}</td><td class="num">{fmt_pct(r['funding_apr'])}</td>
<td class="num">{fmt_usd(r['oi_usd'])}</td><td class="num">{fmt_usd(r['vol_usd'])}</td><td class="sess">—</td></tr>""")
    return "\n".join(out)


def weekend_html(rep):
    if not rep or not rep["weekends"]:
        return "<p>No complete weekends yet.</p>"
    w = rep["weekends"][-1]
    o = rep["overall"]
    rows = []
    for r in w["rows"]:
        if r["hit"] is None:
            badge = '<span class="badge flat">– Flat</span>'
        elif r["hit"]:
            badge = '<span class="badge ok">✓ Hit</span>'
        else:
            badge = '<span class="badge bad">✗ Miss</span>'
        cap = f"{r['captured'] * 100:.0f}%" if r["captured"] is not None else "—"
        rows.append(f"<tr><td><b>{E(r['symbol'].split(':')[1])}</b></td>"
                    f"<td class=\"num pred\">{fmt_pct(r['predicted'], 2)}</td><td class=\"num act\">{fmt_pct(r['actual'], 2)}</td>"
                    f"<td>{badge}</td><td class=\"num\">{r['abs_err_pp']:.2f}</td><td class=\"num\">{cap}</td></tr>")
    summary = (f"Over the last <b>{len(rep['weekends'])}</b> weekends, Entropy's weekend price pointed the right way "
               f"<b>{o['hit_rate'] * 100:.0f}%</b> of the time ({o['hits']} of {o['n_scored']} stock-weekends).")
    stats = (f"<div class=\"stats\"><div><b class=\"num\">{o['hit_rate'] * 100:.0f}%</b><small>{T('hit_rate')} ({o['hits']}/{o['n_scored']})</small></div>"
             f"<div><b class=\"num\">{o['mean_abs_err_pp']:.2f} pp</b><small>mean {T('abs_err', 'abs error')}, in {T('pp', 'percentage points')}</small></div>"
             f"<div><b class=\"num\">{len(rep['weekends'])}</b><small>weekends tracked</small></div></div>")
    sym = "".join(f"<tr><td><b>{E(s.split(':')[1])}</b></td><td class=\"num\">{v['n']}</td><td class=\"num\">{v['hit_rate'] * 100:.0f}%</td><td class=\"num\">{v['mean_abs_err_pp']:.2f}</td></tr>"
                  for s, v in rep["by_symbol"].items() if v["hit_rate"] is not None)
    return f"""<p class="wk-sum">{summary}</p>
{stats}
<h3>Latest: Fri {w['friday']} → Mon {w['monday']}</h3>
<div class="scroll"><table class="wk-latest"><thead><tr><th>Symbol</th><th>{T('predicted')}</th><th>{T('actual')}</th><th>Direction</th><th>{T('abs_err')} (pp)</th><th>{T('captured')}</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div>
<h3>All-time by symbol</h3>
<div class="scroll"><table><thead><tr><th>Symbol</th><th>Weekends</th><th>Hit rate</th><th>Mean abs err (pp)</th></tr></thead><tbody>{sym}</tbody></table></div>"""


def news_html(payload):
    """Front page: the day's headlines about market entities."""
    items = payload.get("items", [])
    if not items:
        return ""
    now = time.time()
    rows = []
    for it in items[:6]:
        age_h = (now - it["ts"]) / 3600
        when = f"{int(age_h)}h ago" if age_h < 24 else f"{int(age_h / 24)}d ago"
        tag = f" · {E(it['name'])}" if it["name"].lower() not in it["source"].lower() else ""
        rows.append(
            f'<li><a href="{E(it["url"])}" rel="noopener">{E(it["title"])}</a>'
            f'<span class="meta">{E(it["source"])} · {when}{tag}</span></li>')
    return f'<ol class="headlines">{"".join(rows)}</ol>'


def month_day(iso):
    return datetime.strptime(iso, "%Y-%m-%d").strftime("%b %-d")


def funding_bars(weeks, color, w=420, h=130):
    """Weekly funding APR as bars; zero line, labels on every bar."""
    vals = [wk["apr"] * 100 for wk in weeks]
    top = max(max(vals), 5)
    bot = min(min(vals), 0)
    pad_t = 18
    pad_b = 36 if bot < 0 else 22  # room for a value label under negative bars
    span = (top - bot) or 1
    y0 = pad_t + top / span * (h - pad_t - pad_b)
    bw = w / len(vals)
    parts = [f'<line x1="0" x2="{w}" y1="{y0:.1f}" y2="{y0:.1f}" class="zero"/>']
    for i, (v, wk) in enumerate(zip(vals, weeks)):
        x = i * bw + bw * 0.18
        bh = abs(v) / span * (h - pad_t - pad_b)
        y = y0 - bh if v >= 0 else y0
        partial = wk["hours"] < 168
        parts.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bw * 0.64:.1f}" height="{max(bh, 1):.1f}" '
                     f'fill="{color}"{" opacity=\".45\"" if partial else ""}/>')
        ly = (y - 5) if v >= 0 else (y + bh + 13)
        parts.append(f'<text x="{x + bw * 0.32:.1f}" y="{ly:.1f}" class="bv">{v:.0f}%</text>')
        parts.append(f'<text x="{x + bw * 0.32:.1f}" y="{h - 5}" class="bl">W{wk["n"]}{"*" if partial else ""}</text>')
    return (f'<svg class="fbars" viewBox="0 0 {w} {h}" role="img" '
            f'aria-label="Weekly funding APR">{"".join(parts)}</svg>')


def funding_html(payload, vcfg):
    assets = payload.get("assets", {})
    if not assets:
        return '<p class="nochart">Funding history unavailable right now.</p>'
    colors = {"io:ANTH": "#b4552d", "io:OAI": "#1f6f5c"}
    blocks = []
    for sym, s in assets.items():
        name = vcfg["assets"].get(sym, {}).get("name", sym)
        blocks.append(f"""<div class="fblock">
<h3>{E(name)} <span class="tick">{E(sym)}</span></h3>
<dl class="fstats">
<div><dt>Longs paid</dt><dd class="num">{s['pos_share'] * 100:.0f}%<small> of hours</small></dd></div>
<div><dt>Since {E(month_day(s['since']))}</dt><dd class="num">{fmt_pct(s['apr_all'])}<small> APR</small></dd></div>
<div><dt>Last 7 days</dt><dd class="num">{fmt_pct(s['apr_7d'])}<small> APR</small></dd></div>
</dl>
{funding_bars(s['weeks'], colors.get(sym, '#191610'))}
</div>""")
    return '<div class="fgrid">' + "".join(blocks) + '</div>' + ('<p class="legend">Bars: average funding APR per week since listing '
                              '(W1 = first 7 days). * = week still in progress. '
                              'Positive = longs pay shorts.</p>')


def build():
    cfg, vcfg = site_cfg(), valuations_cfg()
    snap = last_snapshot()
    if not snap:
        raise SystemExit("no snapshot; run collector first")
    SITE.mkdir(exist_ok=True)
    (SITE / "data").mkdir(exist_ok=True)
    metrics = pre_ipo_metrics(snap)
    news_payload = fpnews.load()
    hist = history(vcfg, cfg)
    eq = equity_rows(snap, cfg)
    wk = load_json(DATA / "weekend.json")
    updated = datetime.fromtimestamp(snap["ts"], timezone.utc)

    save_json(SITE / "data" / "pre_ipo.json", {"updated": updated.isoformat(), "assets": metrics}, indent=1)
    save_json(SITE / "data" / "history.json", hist)
    save_json(SITE / "data" / "equities.json", {"updated": updated.isoformat(), "rows": eq}, indent=1)
    if wk:
        save_json(SITE / "data" / "weekend.json", wk)
    cards.valuation_card(SITE / "og.png", metrics)

    ref = cfg.get("referral_url", "")
    cta = (f'<p class="cta"><a href="{E(ref)}" rel="noopener sponsored">Trade these on Entropy →</a></p>' if ref else "")
    handle = cfg.get("x_handle", "")
    built_by = (f' · Built by the community, <a href="https://x.com/{E(handle.lstrip("@"))}" rel="noopener">{E(handle)}</a>'
                if handle and handle != "@YOUR_HANDLE" else "")
    site_url = cfg.get("site_url", "")
    SITE.mkdir(exist_ok=True)
    fav = ROOT / "fp" / "assets" / "favicon.svg"
    if fav.exists():
        shutil.copy(fav, SITE / "favicon.svg")
    anth, oai = metrics.get("io:ANTH"), metrics.get("io:OAI")
    desc = (f"Anthropic implied {fmt_usd(anth['valuation_usd'])} ({anth['multiple']:.2f}× last round), OpenAI implied "
            f"{fmt_usd(oai['valuation_usd'])} ({oai['multiple']:.2f}×) — from Entropy's 24/7 pre-IPO perps.") if anth and oai else cfg["tagline"]
    page_data = {"hist": hist, "holidays": sorted(d.isoformat() for d in NYSE_HOLIDAYS),
                 "early": sorted(d.isoformat() for d in NYSE_EARLY_CLOSE),
                 "ids": cfg["pre_ipo"], "names": {k: v["short"] for k, v in vcfg["assets"].items()},
                 "updated_ts": snap["ts"], "glossary": popover_data()}
    tpl = (ROOT / "fp" / "template.html").read_text()
    repl = {
        "__TITLE__": E(f"{cfg['site_name']} — {cfg['tagline']}"),
        "__DESC__": E(desc),
        "__OG__": E((site_url.rstrip("/") + "/" if site_url else "") + "og.png"),
        "__CANONICAL__": E(site_url),
        "__SITE_NAME__": E(cfg["site_name"]),
        "__TAGLINE__": E(cfg["tagline"]),
        "__SUMMARY__": plain_summary(metrics),
        "__CARDS__": "\n".join(card_html(m) for m in metrics.values()),
        "__EQUITIES__": equities_html(eq),
        "__MINICARDS__": minicards_html(eq),
        "__WEEKEND__": weekend_html(wk),
        "__HEADLINES__": news_html(news_payload),
        "__FUNDING__": funding_html(fpfunding.load(), vcfg),
        "__GLOSSARY__": glossary_html(),
        "__UPDATED_ISO__": updated.isoformat(),
        "__UPDATED__": f"{updated.strftime('%Y-%m-%d %H:%M')} UTC · {updated.astimezone(WIB).strftime('%Y-%m-%d %H:%M')} WIB",
        "__ENTROPY__": E(cfg["entropy_url"]),
        "__CTA__": cta,
        "__BUILTBY__": built_by,
        "__DATA__": json.dumps(page_data).replace("</", "<\\/"),
    }
    tpl = expand(tpl)
    for k, v in repl.items():
        tpl = tpl.replace(k, v)
    (SITE / "index.html").write_text(tpl)
    return SITE / "index.html"


if __name__ == "__main__":
    print(build())
