"""Funding history for the pre-IPO perps: who pays whom, and how it moves.

Pulls hourly funding from Hyperliquid since each listing, caches to
data/funding.json (refresh hourly). Weeks are 7-day buckets counted from
the first funding hour, so "week 2" means days 8-14 after listing.
"""
import json
import time

from . import hl
from .common import DATA, save_json, site_cfg

FUNDING = DATA / "funding.json"
HOURS_YEAR = 24 * 365
REFRESH_S = 3600


def _history(coin, now_ms):
    rows, start = [], now_ms - 120 * 86400 * 1000
    while True:
        batch = hl.funding_history(coin, start)
        if not batch:
            break
        rows.extend(batch)
        nxt = batch[-1]["time"] + 1
        if len(batch) < 500 or nxt >= now_ms:
            break
        start = nxt
    by_t = {r["time"]: r for r in rows}
    return [by_t[t] for t in sorted(by_t)]


def apr(rates):
    return sum(rates) / len(rates) * HOURS_YEAR if rates else None


def summarize(rows):
    """rows: [{'time': ms, 'fundingRate': str}] sorted by time."""
    if not rows:
        return None
    rates = [float(r["fundingRate"]) for r in rows]
    t0 = rows[0]["time"]
    weeks = []
    for i in range(0, len(rates), 168):
        chunk = rates[i:i + 168]
        weeks.append({
            "n": i // 168 + 1,
            "start": time.strftime("%Y-%m-%d", time.gmtime(rows[i]["time"] / 1000)),
            "hours": len(chunk),
            "apr": apr(chunk),
            "pos_share": sum(1 for x in chunk if x > 0) / len(chunk),
        })
    return {
        "since": time.strftime("%Y-%m-%d", time.gmtime(t0 / 1000)),
        "hours": len(rates),
        "pos_share": sum(1 for x in rates if x > 0) / len(rates),
        "apr_all": apr(rates),
        "apr_7d": apr(rates[-168:]),
        "apr_24h": apr(rates[-24:]),
        "weeks": weeks,
    }


def fetch_all():
    now_ms = int(time.time() * 1000)
    out = {}
    for sym in site_cfg()["pre_ipo"]:
        try:
            s = summarize(_history(sym, now_ms))
        except Exception:
            s = None
        if s:
            out[sym] = s
    payload = {"ts": time.time(), "assets": out}
    if out:  # never overwrite good data with an empty fetch
        save_json(FUNDING, payload)
    return payload


def load():
    try:
        return json.loads(FUNDING.read_text())
    except Exception:
        return {"ts": 0, "assets": {}}


def run(force=False):
    DATA.mkdir(exist_ok=True)
    cur = load()
    if not force and cur.get("ts") and time.time() - cur["ts"] < REFRESH_S:
        return FUNDING, False
    fetch_all()
    return FUNDING, True


if __name__ == "__main__":
    import sys
    p, wrote = run(force="--force" in sys.argv)
    print(p if wrote else f"{p} (fresh, skipped)")
    for sym, s in load()["assets"].items():
        print(sym, f"since {s['since']} pos {s['pos_share']:.0%} all {s['apr_all']:.1%} 7d {s['apr_7d']:.1%}",
              "weeks:", " ".join(f"{w['apr'] * 100:.0f}" for w in s["weeks"]))
