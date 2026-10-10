"""Pick the one thing worth saying today.

Each candidate gets a score for how unusual it is. Types used in the last few
days are penalised so the account doesn't post the same observation all week.
Every finding carries English post text plus an Indonesian gloss for Galih.
"""
import math
import time
from datetime import datetime

from . import hl
from .common import DATA, NY, fmt_pct, fmt_usd, load_json, save_json, site_cfg

HISTORY = DATA / "daily_history.json"


def money(v):
    return fmt_usd(v).replace(".00M", "M").replace(".00T", "T")


def _pick(options, seed):
    return options[seed % len(options)]


def ratio(metrics):
    a, o = metrics.get("io:ANTH"), metrics.get("io:OAI")
    if not a or not o:
        return None
    return a["valuation_usd"] / o["valuation_usd"]


def ratio_week_ago():
    """ANTH/OAI from daily closes ~7 days back (None if not enough history)."""
    now = int(time.time() * 1000)
    start = now - 9 * 86400 * 1000
    try:
        a = hl.candles("io:ANTH", "1d", start, now)
        o = hl.candles("io:OAI", "1d", start, now)
    except RuntimeError:
        return None
    if len(a) < 8 or len(o) < 8:
        return None
    return float(a[-8]["c"]) / float(o[-8]["c"])


def candidates(metrics, funding, stocks, ratio_then, seed=0):
    out = []
    by_short = {m["short"]: m for m in metrics.values()}

    for m in metrics.values():
        share = m["oi_usd"] / m["oi_cap_usd"] if m["oi_cap_usd"] else 0
        if share >= 0.7:
            en = _pick([
                f"${m['short']} open interest on Entropy is at {share:.0%} of its {money(m['oi_cap_usd'])} cap. "
                f"Not a lot of room left for new positions.",
                f"{share:.0%}. That's how full the ${m['short']} perp is: {money(m['oi_usd'])} open "
                f"against a {money(m['oi_cap_usd'])} cap.",
            ], seed)
            idn = (f"Open interest ${m['short']} di Entropy sudah {share:.0%} dari batas {money(m['oi_cap_usd'])}. "
                   f"Ruang buat posisi baru tinggal sedikit.")
            out.append({"type": "oi_cap", "score": 1 + (share - 0.7) * 10, "en": en, "id": idn})

        if abs(m["change_24h"] or 0) >= 0.03:
            c = m["change_24h"]
            word = "up" if c > 0 else "down"
            en = (f"Implied ${m['short']} valuation is {word} {abs(c):.1%} in 24h, now {money(m['valuation_usd'])} "
                  f"({m['multiple']:.2f}x its last round).")
            idn = (f"Valuasi implied ${m['short']} {'naik' if c > 0 else 'turun'} {abs(c):.1%} dalam 24 jam, "
                   f"sekarang {money(m['valuation_usd'])} ({m['multiple']:.2f}x ronde terakhir).")
            out.append({"type": "move", "score": abs(c) * 40, "en": en, "id": idn})

        if m.get("prev_multiple") is not None:
            lo, hi = sorted([m["prev_multiple"], m["multiple"]])
            mark = math.floor(hi * 4) / 4
            if lo < mark <= hi and mark >= 1:
                up = m["multiple"] > m["prev_multiple"]
                en = (f"${m['short']} just {'went above' if up else 'fell below'} {mark:g}x its last private round "
                      f"on Entropy. Now {money(m['valuation_usd'])} vs {money(m['last_round_usd'])}.")
                idn = (f"${m['short']} baru saja {'tembus ke atas' if up else 'jatuh di bawah'} {mark:g}x ronde "
                       f"privat terakhirnya di Entropy. Sekarang {money(m['valuation_usd'])} vs {money(m['last_round_usd'])}.")
                out.append({"type": "milestone", "score": 3.0, "en": en, "id": idn})

    a, o = by_short.get("ANTH"), by_short.get("OAI")
    if a and o and a["funding_apr"] > 0 and o["funding_apr"] > 0:
        hi_m, lo_m = (a, o) if a["funding_apr"] > o["funding_apr"] else (o, a)
        x = hi_m["funding_apr"] / lo_m["funding_apr"]
        if x >= 1.8:
            cheaper = hi_m["valuation_usd"] < lo_m["valuation_usd"]
            tail = ("to be long the smaller company." if cheaper else f"to hold the same kind of bet on {hi_m['name'].split(' (')[0]}.")
            en = (f"Longs on ${hi_m['short']} are paying {fmt_pct(hi_m['funding_apr'], 1, sign=False)} APR in funding, "
                  f"vs {fmt_pct(lo_m['funding_apr'], 1, sign=False)} on ${lo_m['short']}. About {x:.1f}x more {tail}")
            idn = (f"Long ${hi_m['short']} bayar funding {fmt_pct(hi_m['funding_apr'], 1, sign=False)} APR, "
                   f"sedangkan ${lo_m['short']} {fmt_pct(lo_m['funding_apr'], 1, sign=False)}. Sekitar {x:.1f}x lebih mahal"
                   f"{' padahal perusahaannya lebih kecil' if cheaper else ''}.")
            out.append({"type": "funding_gap", "score": 0.8 + math.log(x), "en": en, "id": idn})

    for sym, f in (funding or {}).items():
        if not f or f.get("pos_share", 0) < 0.9:
            continue
        short = sym.split(":")[1]
        since = datetime.strptime(f["since"], "%Y-%m-%d").strftime("%b %-d")
        en = _pick([
            f"Since ${short} listed on Entropy ({since}), longs have paid shorts in {f['pos_share']:.0%} of hours. "
            f"Last 7 days: {fmt_pct(f['apr_7d'], 1)} APR. Being long has cost money almost every single hour.",
            f"{f['pos_share']:.0%} of hours since {since}: that's how often ${short} longs have paid funding on Entropy. "
            f"7-day average {fmt_pct(f['apr_7d'], 1)} APR.",
        ], seed)
        idn = (f"Sejak ${short} listing di Entropy ({since}), long bayar ke short di {f['pos_share']:.0%} jam. "
               f"Rata-rata 7 hari {fmt_pct(f['apr_7d'], 1)} APR.")
        out.append({"type": f"longs_pay_{short}", "score": 0.6 + (f["pos_share"] - 0.9) * 10, "en": en, "id": idn})

    for s in stocks:
        if s["oi_usd"] >= 250_000 and s["funding_apr"] >= 0.5:
            en = (f"Funding on the {s['name']} perp is running at {fmt_pct(s['funding_apr'], 0, sign=False)} APR on Entropy "
                  f"({money(s['oi_usd'])} open). Someone really wants to be long ${s['short']}.")
            idn = (f"Funding perp {s['name']} di Entropy {fmt_pct(s['funding_apr'], 0)} APR "
                   f"({money(s['oi_usd'])} open interest). Ada yang ngotot long ${s['short']}.")
            out.append({"type": "stock_funding", "score": 0.5 + s["funding_apr"], "en": en, "id": idn})

    r = ratio(metrics)
    if r and ratio_then:
        d = r / ratio_then - 1
        if abs(d) >= 0.02:
            en = (f"On Entropy, Anthropic is now valued at {r:.2f}x OpenAI. A week ago it was {ratio_then:.2f}x.")
            idn = f"Di Entropy, Anthropic sekarang dihargai {r:.2f}x OpenAI. Seminggu lalu {ratio_then:.2f}x."
            out.append({"type": "ratio", "score": 1 + abs(d) * 20, "en": en, "id": idn})

    if r and a and o:
        en = (f"Entropy's pre-IPO perps have Anthropic at {money(a['valuation_usd'])} and OpenAI at "
              f"{money(o['valuation_usd'])}. Both roughly {min(a['multiple'], o['multiple']):.0f}x their last rounds.")
        idn = (f"Perp pre-IPO Entropy menilai Anthropic {money(a['valuation_usd'])} dan OpenAI "
               f"{money(o['valuation_usd'])}. Dua-duanya sekitar {min(a['multiple'], o['multiple']):.0f}x ronde terakhir.")
        out.append({"type": "baseline", "score": 0.1, "en": en, "id": idn})
    return out


def choose(cands, history, today):
    """Highest score after penalising types used recently."""
    recent = {}
    for h in history:
        age = (datetime.fromisoformat(today) - datetime.fromisoformat(h["date"])).days
        if 0 < age <= 7:
            recent[h["type"]] = min(recent.get(h["type"], 99), age)
    best, best_s = None, -1
    for c in cands:
        s = c["score"]
        age = recent.get(c["type"])
        if age is not None:
            s *= 0.25 if age <= 3 else 0.6
        if s > best_s:
            best, best_s = c, s
    return best


def compose(finding, metrics, handle):
    r = ratio(metrics)
    sig = f"ANTH/OAI {r:.2f}x" if r and finding["type"] != "ratio" else ""
    tail = " · ".join(x for x in (sig, handle) if x)
    return f"{finding['en']}\n\n{tail}"


def stock_rows(snap):
    cfg = site_cfg()
    skip = set(cfg["pre_ipo"])
    rows = []
    for sym, m in snap["m"].items():
        if sym in skip or not m["mark"]:
            continue
        rows.append({"symbol": sym, "short": sym.split(":")[1], "name": cfg["names"].get(sym, sym),
                     "oi_usd": m["oi"] * m["mark"], "funding_apr": m["funding"] * 24 * 365})
    return rows


def today_finding(metrics, snap, record=True):
    today = datetime.now(NY).date().isoformat()
    funding = (load_json(DATA / "funding.json") or {}).get("assets", {})
    history = load_json(HISTORY, [])
    seed = datetime.now(NY).toordinal()
    cands = candidates(metrics, funding, stock_rows(snap), ratio_week_ago(), seed)
    pick = choose(cands, history, today)
    if record and pick:
        history = [h for h in history if h["date"] != today][-30:] + [{"date": today, "type": pick["type"]}]
        save_json(HISTORY, history, indent=1)
    return pick
