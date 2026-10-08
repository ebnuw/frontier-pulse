"""Append one compact snapshot of all io markets to data/snapshots.jsonl.

Idempotent: if the last snapshot is younger than MIN_GAP_S it is left alone,
so running this from cron every 15 minutes (or from run.sh at any time) is safe.
"""
import json
import sys
import time

from . import hl
from .common import DATA

SNAP = DATA / "snapshots.jsonl"
MIN_GAP_S = 120


def last_snapshot():
    if not SNAP.exists():
        return None
    last = None
    with SNAP.open() as f:
        for line in f:
            if line.strip():
                last = line
    return json.loads(last) if last else None


def build_snapshot(markets, ts):
    m = {}
    for x in markets:
        m[x["name"]] = {
            "mark": float(x["markPx"]),
            "oracle": float(x["oraclePx"]),
            "mid": float(x["midPx"]) if x.get("midPx") else None,
            "prev": float(x["prevDayPx"]),
            "funding": float(x["funding"]),
            "premium": float(x["premium"]) if x.get("premium") is not None else None,
            "oi": float(x["openInterest"]),
            "vol": float(x["dayNtlVlm"]),
            "lev": x["maxLeverage"],
        }
    return {"ts": ts, "m": m}


def run(force=False):
    DATA.mkdir(exist_ok=True)
    now = int(time.time())
    last = last_snapshot()
    if last and not force and now - last["ts"] < MIN_GAP_S:
        return SNAP, False
    snap = build_snapshot(hl.meta_and_ctxs(), now)
    with SNAP.open("a") as f:
        f.write(json.dumps(snap, separators=(",", ":")) + "\n")
    return SNAP, True


if __name__ == "__main__":
    path, wrote = run(force="--force" in sys.argv)
    print(path if wrote else f"{path} (fresh, skipped)")
