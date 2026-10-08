"""Derive display metrics from the latest snapshot + config (shared by site and posts)."""
from datetime import date, datetime

from .collector import last_snapshot
from .common import funding_apr, funding_apr_24h, implied_valuation_usd, pct_change, site_cfg, valuations_cfg


def pre_ipo_metrics(snap=None, today=None):
    snap = snap or last_snapshot()
    vcfg = valuations_cfg()
    today = today or datetime.utcfromtimestamp(snap["ts"]).date()
    out = {}
    for sym, a in vcfg["assets"].items():
        m = snap["m"].get(sym)
        if not m:
            continue
        mark = m["mark"]
        val = implied_valuation_usd(mark, vcfg["usd_per_price_point"])
        last_round = a["last_round_usd"]
        res = date.fromisoformat(a["resolution_date"])
        out[sym] = {
            "symbol": sym, "short": a["short"], "name": a["name"],
            "mark": mark, "oracle": m["oracle"],
            "valuation_usd": val,
            "last_round_usd": last_round,
            "last_round_label": a["last_round_label"],
            "last_round_date": a["last_round_date"],
            "source_url": a["source_url"],
            "multiple": val / last_round,
            "premium": val / last_round - 1,
            "change_24h": pct_change(mark, m["prev"]),
            "funding_hourly": m["funding"],
            "funding_apr": funding_apr_24h(sym, m["funding"]),
            "funding_apr_live": funding_apr(m["funding"]),
            "oi_usd": m["oi"] * mark,
            "oi_cap_usd": a["oi_cap_usd"],
            "vol_24h_usd": m["vol"],
            "lower": a["lower_bound"], "upper": a["upper_bound"],
            "to_lower": a["lower_bound"] / mark - 1,
            "to_upper": a["upper_bound"] / mark - 1,
            "resolution_date": a["resolution_date"],
            "days_to_resolution": (res - today).days,
        }
    return out
