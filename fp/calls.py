"""Monday call: post the weekend perp's prediction before the US open, then score it.

`python -m fp.calls call [--force]` prints the call text (empty outside the window).
`python -m fp.calls receipt [--force]` prints the result text once the open is in.
State lives in data/calls.json keyed by the session date (ET).
"""
import sys
import time
from datetime import datetime, time as dtime, timedelta

from . import hl
from .common import DATA, NY, fmt_pct, is_trading_day, load_json, prev_trading_day, save_json, site_cfg
from .weekend import FLAT, candle_close_at, symbols

CALLS = DATA / "calls.json"
CALL_WINDOW = (dtime(8, 30), dtime(9, 25))


def first_session_after_break(d):
    """True for the first trading day after a weekend or holiday."""
    return is_trading_day(d) and not is_trading_day(d - timedelta(days=1))


def fri_closes(syms, session):
    fri = prev_trading_day(session)
    from .common import NYSE_EARLY_CLOSE
    hh, mm = (12, 45) if fri in NYSE_EARLY_CLOSE else (15, 45)
    start = int(datetime(fri.year, fri.month, fri.day, 12, 0, tzinfo=NY).timestamp() * 1000)
    end = start + 6 * 3600 * 1000
    out = {}
    for s in syms:
        cs = hl.candles(s, "15m", start, end)
        c = candle_close_at({x["t"]: x for x in cs}, fri, hh, mm)
        if c:
            out[s] = c
    return fri, out


def make_call(now=None, force=False):
    now = now or datetime.now(NY)
    session = now.date()
    if not force and (not first_session_after_break(session) or not (CALL_WINDOW[0] <= now.time() <= CALL_WINDOW[1])):
        return None
    calls = load_json(CALLS, {})
    if session.isoformat() in calls and not force:
        return None
    syms = symbols()
    fri, closes = fri_closes(syms, session)
    marks = {m["name"]: float(m["markPx"]) for m in hl.meta_and_ctxs()}
    rows = []
    for s, f in sorted(closes.items()):
        if s in marks and f > 0:
            rows.append({"symbol": s, "fri_close": f, "call_price": marks[s], "predicted": marks[s] / f - 1})
    if not rows:
        return None
    calls[session.isoformat()] = {"made_at": now.isoformat(timespec="seconds"), "friday": fri.isoformat(), "rows": rows}
    save_json(CALLS, calls, indent=1)
    return calls[session.isoformat()]


def call_text(call, overall=None, handle="@entropyIO"):
    lines = [f"{r['symbol'].split(':')[1]} {fmt_pct(r['predicted'], 1)}" for r in call["rows"]]
    rec = ""
    if overall and overall.get("n_scored"):
        rec = f"\nTrack record so far: {overall['hits']}/{overall['n_scored']} on direction."
    text = ("Calling the US open before it happens.\n"
            "Entropy's perps traded all weekend. Where they say these open vs Friday's close:\n\n"
            + "\n".join(lines)
            + f"\n\nReceipts after the bell.{rec} {handle}")
    if len(text) > 280:
        text = text.replace("Entropy's perps traded all weekend. Where they say these open vs Friday's close:",
                            "Weekend perp price vs Friday's close:")
    return text


def call_text_id(call):
    lines = ", ".join(f"{r['symbol'].split(':')[1]} {fmt_pct(r['predicted'], 1)}" for r in call["rows"])
    return ("Nebak pembukaan bursa US sebelum terjadi. Perp Entropy jalan terus sepanjang weekend; "
            f"menurut harganya, saham-saham ini bakal buka segini dibanding penutupan Jumat: {lines}. "
            "Hasilnya diposting setelah bursa buka.")


def score(call, opens):
    """opens: {symbol: open_ref price}. Returns scored rows."""
    rows = []
    for r in call["rows"]:
        o = opens.get(r["symbol"])
        if o is None:
            continue
        actual = o / r["fri_close"] - 1
        # a near-zero call or a near-zero open says nothing about direction, so neither is scored
        flat = abs(actual) < FLAT or abs(r["predicted"]) < FLAT
        hit = None if flat else (r["predicted"] > 0) == (actual > 0)
        rows.append({**r, "actual": actual, "flat": flat, "hit": hit})
    return rows


def open_refs(syms, session):
    start = int(datetime(session.year, session.month, session.day, 9, 0, tzinfo=NY).timestamp() * 1000)
    out = {}
    for s in syms:
        cs = hl.candles(s, "15m", start, start + 2 * 3600 * 1000)
        by = {x["t"]: x for x in cs}
        c = candle_close_at(by, session, 9, 30)
        # the 09:30 candle only counts once it has closed
        closed_at = datetime(session.year, session.month, session.day, 9, 45, tzinfo=NY)
        if c and datetime.now(NY) >= closed_at:
            out[s] = c
    return out


def make_receipt(now=None, force=False):
    now = now or datetime.now(NY)
    session = now.date()
    calls = load_json(CALLS, {})
    call = calls.get(session.isoformat())
    if not call or (call.get("receipt_sent") and not force):
        return None
    rows = score(call, open_refs([r["symbol"] for r in call["rows"]], session))
    if len(rows) < len(call["rows"]):
        return None  # open not in yet for every symbol; try again on the next run
    call["receipt"] = rows
    call["receipt_sent"] = now.isoformat(timespec="seconds")
    save_json(CALLS, calls, indent=1)
    return call


def ledger(calls):
    rows = [r for c in calls.values() for r in c.get("receipt", [])]
    scored = [r for r in rows if r["hit"] is not None]
    return sum(1 for r in scored if r["hit"]), len(scored), len([c for c in calls.values() if c.get("receipt")])


def receipt_text(call, calls, handle="@entropyIO"):
    def mark(r):
        return "flat" if r["hit"] is None else ("✓" if r["hit"] else "✗")
    lines = [f"{r['symbol'].split(':')[1]} {fmt_pct(r['predicted'], 1)} → {fmt_pct(r['actual'], 1)} {mark(r)}"
             for r in call["receipt"]]
    scored = [r for r in call["receipt"] if r["hit"] is not None]
    hits = sum(1 for r in scored if r["hit"])
    h, n, weeks = ledger(calls)
    run = f" Called live so far: {h}/{n} over {weeks} Mondays." if weeks > 1 else ""
    return (f"Receipts. Called vs actual open:\n\n" + "\n".join(lines)
            + f"\n\nRight direction on {hits} of {len(scored)}.{run} {handle}")


def receipt_text_id(call, calls):
    scored = [r for r in call["receipt"] if r["hit"] is not None]
    hits = sum(1 for r in scored if r["hit"])
    h, n, weeks = ledger(calls)
    run = f" Total tebakan live: {h}/{n} dari {weeks} Senin." if weeks > 1 else ""
    return (f"Hasilnya: tebakan tadi vs harga buka sebenarnya. Arah benar {hits} dari {len(scored)}.{run} "
            "(✓ = arah benar, ✗ = salah, flat = tebakan atau gerakan < 0.1%, tidak dihitung)")


if __name__ == "__main__":
    kind = sys.argv[1] if len(sys.argv) > 1 else ""
    force = "--force" in sys.argv
    handle = site_cfg()["entropy_handle"]
    if kind == "call":
        c = make_call(force=force)
        if c:
            overall = (load_json(DATA / "weekend.json") or {}).get("overall")
            print(call_text(c, overall, handle))
            print("---ID---")
            print(call_text_id(c))
    elif kind == "receipt":
        c = make_receipt(force=force)
        if c:
            calls = load_json(CALLS, {})
            print(receipt_text(c, calls, handle))
            print("---ID---")
            print(receipt_text_id(c, calls))
    else:
        raise SystemExit("usage: python -m fp.calls call|receipt [--force]")
