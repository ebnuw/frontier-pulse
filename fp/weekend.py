"""Weekend Gap report.

For each weekend and each US equity perp on Entropy:
  fri_close  = close of the last 15m candle of the last session before the weekend (15:45 ET; 12:45 on early closes)
  preopen    = close of the 09:15-09:30 ET candle on the next trading day (Entropy's 24/7 "prediction")
  open_ref   = close of the 09:30-09:45 ET candle that day
"""
import time
from datetime import date, datetime, timedelta

from . import hl
from .common import (DATA, NY, NYSE_EARLY_CLOSE, load_json, next_trading_day, prev_trading_day,
                     save_json, site_cfg, now_utc)

FLAT = 0.001  # |actual| below 0.1% counts as flat


def candle_close_at(by_start, d, hh, mm):
    """Close of the 15m candle starting at hh:mm ET on date d, or None."""
    start = datetime(d.year, d.month, d.day, hh, mm, tzinfo=NY)
    c = by_start.get(int(start.timestamp() * 1000))
    return float(c["c"]) if c else None


def weekend_row(by_start, sat):
    """Compute one weekend for a given Saturday date. None if candles are missing."""
    fri = prev_trading_day(sat)
    mon = next_trading_day(sat + timedelta(days=1))
    last_hh, last_mm = (12, 45) if fri in NYSE_EARLY_CLOSE else (15, 45)
    f = candle_close_at(by_start, fri, last_hh, last_mm)
    p = candle_close_at(by_start, mon, 9, 15)
    o = candle_close_at(by_start, mon, 9, 30)
    if None in (f, p, o) or f <= 0:
        return None
    pred, actual = p / f - 1, o / f - 1
    flat = abs(actual) < FLAT
    same = (pred > 0) == (actual > 0) and pred != 0
    return {
        "friday": fri.isoformat(), "monday": mon.isoformat(),
        "fri_close": f, "preopen": p, "open": o,
        "predicted": pred, "actual": actual,
        "flat": flat,
        "hit": None if flat else bool(same),
        "abs_err_pp": abs(pred - actual) * 100,
        "captured": (pred / actual) if (not flat and same) else None,
    }


def saturdays(first, last):
    d = first
    while d.weekday() != 5:
        d += timedelta(days=1)
    while d <= last:
        yield d
        d += timedelta(days=7)


def compute(candles_by_symbol):
    """candles_by_symbol: {symbol: [candle,...]} -> report dict."""
    weekends = {}
    for sym, cs in candles_by_symbol.items():
        if not cs:
            continue
        by_start = {c["t"]: c for c in cs}
        first = datetime.fromtimestamp(cs[0]["t"] / 1000, NY).date()
        last = datetime.fromtimestamp(cs[-1]["t"] / 1000, NY).date()
        for sat in saturdays(first, last):
            row = weekend_row(by_start, sat)
            if row:
                row["symbol"] = sym
                weekends.setdefault(row["friday"], []).append(row)
    return aggregate(weekends)


def _stats(rows):
    scored = [r for r in rows if r["hit"] is not None]
    hits = sum(1 for r in scored if r["hit"])
    caps = [r["captured"] for r in rows if r["captured"] is not None]
    return {
        "n": len(rows), "n_scored": len(scored), "n_flat": len(rows) - len(scored), "hits": hits,
        "hit_rate": hits / len(scored) if scored else None,
        "mean_abs_err_pp": sum(r["abs_err_pp"] for r in rows) / len(rows) if rows else None,
        "mean_captured": sum(caps) / len(caps) if caps else None,
    }


def aggregate(weekends):
    out_weekends = []
    all_rows = []
    by_sym = {}
    for fri in sorted(weekends):
        rows = sorted(weekends[fri], key=lambda r: r["symbol"])
        out_weekends.append({"friday": fri, "monday": rows[0]["monday"], "rows": rows, "summary": _stats(rows)})
        all_rows.extend(rows)
        for r in rows:
            by_sym.setdefault(r["symbol"], []).append(r)
    return {
        "generated": now_utc().isoformat(timespec="seconds"),
        "method": {
            "fri_close": "close of 15:45-16:00 ET candle (12:45 on early-close days), last trading day before the weekend",
            "preopen": "close of 09:15-09:30 ET candle, next trading day",
            "open": "close of 09:30-09:45 ET candle, next trading day",
            "flat_threshold": FLAT,
        },
        "overall": _stats(all_rows),
        "by_symbol": {s: _stats(r) for s, r in sorted(by_sym.items())},
        "weekends": out_weekends,
    }


def symbols():
    """All io markets with activity, minus the exclude list (US equities only)."""
    cfg = site_cfg()
    excl = set(cfg["weekend_exclude"])
    return [m["name"] for m in hl.meta_and_ctxs()
            if m["name"] not in excl and (float(m["openInterest"]) > 0 or float(m["dayNtlVlm"]) > 0)]


def run():
    now_ms = int(time.time() * 1000)
    start = now_ms - 400 * 86400 * 1000
    cands = {s: hl.candles(s, "15m", start, now_ms) for s in symbols()}
    report = compute(cands)
    DATA.mkdir(exist_ok=True)
    save_json(DATA / "weekend.json", report)
    return DATA / "weekend.json", report


if __name__ == "__main__":
    path, rep = run()
    print(path)
