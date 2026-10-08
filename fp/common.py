"""Shared paths, config loading, math and formatting helpers."""
import json
from datetime import date, datetime, time as dtime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SITE = ROOT / "site"
OUT = ROOT / "out"
NY = ZoneInfo("America/New_York")
HK = ZoneInfo("Asia/Hong_Kong")
WIB = ZoneInfo("Asia/Jakarta")

# NYSE full-day closures (hardcoded, 2026-2027).
NYSE_HOLIDAYS = {
    date(2026, 1, 1), date(2026, 1, 19), date(2026, 2, 16), date(2026, 4, 3), date(2026, 5, 25),
    date(2026, 6, 19), date(2026, 7, 3), date(2026, 9, 7), date(2026, 11, 26), date(2026, 12, 25),
    date(2027, 1, 1), date(2027, 1, 18), date(2027, 2, 15), date(2027, 3, 26), date(2027, 5, 31),
    date(2027, 6, 18), date(2027, 7, 5), date(2027, 9, 6), date(2027, 11, 25), date(2027, 12, 24),
}
# 13:00 ET early closes.
NYSE_EARLY_CLOSE = {date(2026, 11, 27), date(2026, 12, 24), date(2027, 11, 26)}


def load_json(path, default=None):
    p = Path(path)
    if not p.exists():
        return default
    return json.loads(p.read_text())


def save_json(path, obj, indent=None):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, indent=indent, separators=None if indent else (",", ":")))


def site_cfg():
    return load_json(ROOT / "config" / "site.json")


def valuations_cfg():
    return load_json(ROOT / "config" / "valuations.json")


# ---- math -----------------------------------------------------------------

def funding_apr(hourly_rate):
    """Hourly funding rate -> simple annualised rate (fraction)."""
    return float(hourly_rate) * 24 * 365


_F24 = {}


def funding_apr_24h(coin, fallback_hourly):
    """APR from the mean of the last 24 settled hourly fundings; falls back to the live rate."""
    if coin not in _F24:
        try:
            import time
            from . import hl
            rows = hl.funding_history(coin, int((time.time() - 86400) * 1000))
            rates = [float(r["fundingRate"]) for r in rows][-24:]
            _F24[coin] = sum(rates) / len(rates) if rates else None
        except Exception:
            _F24[coin] = None
    h = _F24[coin]
    return funding_apr(h if h is not None else fallback_hourly)


def implied_valuation_usd(price, usd_per_point=1e9):
    """Pre-IPO perps: $1 of price = $1B market cap."""
    return float(price) * usd_per_point


def pct_change(new, old):
    old = float(old)
    return float(new) / old - 1 if old else None


def is_trading_day(d):
    return d.weekday() < 5 and d not in NYSE_HOLIDAYS


def prev_trading_day(d):
    d -= timedelta(days=1)
    while not is_trading_day(d):
        d -= timedelta(days=1)
    return d


def next_trading_day(d):
    d += timedelta(days=1)
    while not is_trading_day(d):
        d += timedelta(days=1)
    return d


def us_session_open(now_utc):
    n = now_utc.astimezone(NY)
    if not is_trading_day(n.date()):
        return False
    close = dtime(13, 0) if n.date() in NYSE_EARLY_CLOSE else dtime(16, 0)
    return dtime(9, 30) <= n.time() < close


def hk_session_open(now_utc):
    n = now_utc.astimezone(HK)
    if n.weekday() >= 5:
        return False
    t = n.time()
    return dtime(9, 30) <= t < dtime(12, 0) or dtime(13, 0) <= t < dtime(16, 0)


# ---- formatting -------------------------------------------------------------

def fmt_usd(v, digits=2):
    v = float(v)
    a = abs(v)
    if a >= 1e12:
        return f"${v / 1e12:.{digits}f}T"
    if a >= 1e9:
        return f"${v / 1e9:.0f}B" if a >= 1e11 else f"${v / 1e9:.{digits - 1}f}B"
    if a >= 1e6:
        return f"${v / 1e6:.2f}M"
    if a >= 1e3:
        return f"${v / 1e3:.1f}K"
    return f"${v:.0f}"


def fmt_pct(v, digits=1, sign=True):
    if v is None:
        return "—"
    return f"{v * 100:+.{digits}f}%" if sign else f"{v * 100:.{digits}f}%"


def now_utc():
    return datetime.now(timezone.utc)
