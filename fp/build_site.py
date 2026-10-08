"""Build the static site into site/."""
import html
import json
import shutil
import time
from datetime import datetime, timezone

from . import cards, hl
from .collector import last_snapshot
from .common import (DATA, NY, NYSE_EARLY_CLOSE, NYSE_HOLIDAYS, ROOT, SITE, WIB, fmt_pct, fmt_usd, funding_apr,
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
            "funding_apr": funding_apr(m["funding"]), "oi_usd": m["oi"] * m["mark"], "vol_usd": m["vol"],
            "market": "HK" if sym in cfg["hk_symbols"] else "US",
        })
    rows.sort(key=lambda r: -r["vol_usd"])
    return rows


def px(v):
    return f"{v:,.2f}" if v >= 10 else f"{v:,.4f}"


def card_html(m):
    chg = m["change_24h"]
    cls = "up" if (chg or 0) >= 0 else "down"
    cap_pct = m["oi_usd"] / m["oi_cap_usd"]
    return f"""<article class="card {m['short'].lower()}">
  <h3>{E(m['name'])} <span class="tick">io:{E(m['short'])}</span></h3>
  <div class="big">{fmt_usd(m['valuation_usd'])}</div>
  <div class="sub">implied valuation · mark {px(m['mark'])}</div>
  <div class="row2"><div><b>{m['multiple']:.2f}×</b><small>vs last round</small></div>
  <div><b class="{'up' if m['premium'] >= 0 else 'down'}">{fmt_pct(m['premium'])}</b><small>premium to {fmt_usd(m['last_round_usd'])}</small></div></div>
  <dl>
    <dt>24h change</dt><dd class="{cls}">{fmt_pct(chg)}</dd>
    <dt>Funding APR</dt><dd>{fmt_pct(m['funding_apr'])}</dd>
    <dt>Open interest</dt><dd>{fmt_usd(m['oi_usd'])} <small>({cap_pct * 100:.0f}% of {fmt_usd(m['oi_cap_usd'])} cap)</small></dd>
    <dt>24h volume</dt><dd>{fmt_usd(m['vol_24h_usd'])}</dd>
    <dt>Lower bound</dt><dd>{m['lower']:,} <small>({fmt_pct(m['to_lower'], 0)} = {fmt_usd(m['lower'] * 1e9)})</small></dd>
    <dt>Upper bound</dt><dd>{m['upper']:,} <small>({fmt_pct(m['to_upper'], 0)} = {fmt_usd(m['upper'] * 1e9)})</small></dd>
    <dt>No-IPO resolution</dt><dd>{m['resolution_date']} <small>({m['days_to_resolution']:,} days)</small></dd>
  </dl>
  <p class="src">Last round: {E(m['last_round_label'])}, {m['last_round_date']} · <a href="{E(m['source_url'])}" rel="noopener">source</a></p>
</article>"""


def equities_html(rows):
    out = []
    for r in rows:
        cls = "up" if (r["change_24h"] or 0) >= 0 else "down"
        out.append(f"""<tr data-mkt="{r['market']}"><td><b>{E(r['ticker'])}</b><br><small>{E(r['name'])}</small></td>
<td>{px(r['mark'])}</td><td class="{cls}">{fmt_pct(r['change_24h'])}</td><td>{fmt_pct(r['funding_apr'])}</td>
<td>{fmt_usd(r['oi_usd'])}</td><td>{fmt_usd(r['vol_usd'])}</td><td class="sess">—</td></tr>""")
    return "\n".join(out)


def weekend_html(rep):
    if not rep or not rep["weekends"]:
        return "<p>No complete weekends yet.</p>", ""
    w = rep["weekends"][-1]
    rows = []
    for r in w["rows"]:
        hit = "flat" if r["hit"] is None else ("✓" if r["hit"] else "✗")
        cap = f"{r['captured'] * 100:.0f}%" if r["captured"] is not None else "—"
        rows.append(f"<tr><td><b>{E(r['symbol'].split(':')[1])}</b></td><td>{fmt_pct(r['predicted'], 2)}</td>"
                    f"<td>{fmt_pct(r['actual'], 2)}</td><td class=\"{'up' if r['hit'] else 'down' if r['hit'] is False else ''}\">{hit}</td>"
                    f"<td>{r['abs_err_pp']:.2f}</td><td>{cap}</td></tr>")
    o = rep["overall"]
    stats = (f"<div class=\"stats\"><div><b>{o['hit_rate'] * 100:.0f}%</b><small>direction hit rate ({o['hits']}/{o['n_scored']})</small></div>"
             f"<div><b>{o['mean_abs_err_pp']:.2f} pp</b><small>mean abs error</small></div>"
             f"<div><b>{len(rep['weekends'])}</b><small>weekends tracked</small></div></div>")
    sym = "".join(f"<tr><td><b>{E(s.split(':')[1])}</b></td><td>{v['n']}</td><td>{v['hit_rate'] * 100:.0f}%</td><td>{v['mean_abs_err_pp']:.2f}</td></tr>"
                  for s, v in rep["by_symbol"].items() if v["hit_rate"] is not None)
    body = f"""{stats}
<h3>Latest: Fri {w['friday']} → Mon {w['monday']}</h3>
<div class="scroll"><table><thead><tr><th>Symbol</th><th>Predicted</th><th>Actual</th><th>Dir.</th><th>Abs err (pp)</th><th>Captured</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div>
<h3>All-time by symbol</h3>
<div class="scroll"><table><thead><tr><th>Symbol</th><th>Weekends</th><th>Hit rate</th><th>Mean abs err (pp)</th></tr></thead><tbody>{sym}</tbody></table></div>"""
    return body, w["friday"]


def build():
    cfg, vcfg = site_cfg(), valuations_cfg()
    snap = last_snapshot()
    if not snap:
        raise SystemExit("no snapshot; run collector first")
    SITE.mkdir(exist_ok=True)
    (SITE / "data").mkdir(exist_ok=True)
    metrics = pre_ipo_metrics(snap)
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

    wk_body, _ = weekend_html(wk)
    ref = cfg.get("referral_url", "")
    cta = (f'<p class="cta"><a href="{E(ref)}" rel="noopener sponsored">Trade these on Entropy →</a></p>' if ref else "")
    site_url = cfg.get("site_url", "")
    anth, oai = metrics.get("io:ANTH"), metrics.get("io:OAI")
    ratio_now = anth["valuation_usd"] / oai["valuation_usd"] if anth and oai else None
    desc = (f"Anthropic implied {fmt_usd(anth['valuation_usd'])} ({anth['multiple']:.2f}× last round), OpenAI implied "
            f"{fmt_usd(oai['valuation_usd'])} ({oai['multiple']:.2f}×) — from Entropy's 24/7 pre-IPO perps.") if anth and oai else cfg["tagline"]
    holidays = sorted(d.isoformat() for d in NYSE_HOLIDAYS)
    page_data = {"hist": hist, "holidays": holidays, "early": sorted(d.isoformat() for d in NYSE_EARLY_CLOSE),
                 "ids": cfg["pre_ipo"], "names": {k: v["short"] for k, v in vcfg["assets"].items()},
                 "updated_ts": snap["ts"]}
    tpl = (ROOT / "fp" / "template.html").read_text()
    repl = {
        "__TITLE__": E(f"{cfg['site_name']} — {cfg['tagline']}"),
        "__DESC__": E(desc),
        "__OG__": E((site_url.rstrip("/") + "/" if site_url else "") + "og.png"),
        "__SITE_NAME__": E(cfg["site_name"]),
        "__TAGLINE__": E(cfg["tagline"]),
        "__CARDS__": "\n".join(card_html(m) for m in metrics.values()),
        "__RATIO__": f"Anthropic is currently valued at <b>{ratio_now:.2f}×</b> OpenAI." if ratio_now else "",
        "__EQUITIES__": equities_html(eq),
        "__WEEKEND__": wk_body,
        "__UPDATED__": f"{updated.strftime('%Y-%m-%d %H:%M')} UTC · {updated.astimezone(WIB).strftime('%Y-%m-%d %H:%M')} WIB",
        "__ENTROPY__": E(cfg["entropy_url"]),
        "__CTA__": cta,
        "__DATA__": json.dumps(page_data).replace("</", "<\\/"),
    }
    for k, v in repl.items():
        tpl = tpl.replace(k, v)
    (SITE / "index.html").write_text(tpl)
    return SITE / "index.html"


if __name__ == "__main__":
    print(build())
