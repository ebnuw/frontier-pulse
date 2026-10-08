"""Small Hyperliquid info-API client (stdlib only) with retries and timeouts."""
import json
import time
import urllib.error
import urllib.request

URL = "https://api.hyperliquid.xyz/info"
DEX = "io"


def post(body, retries=4, timeout=20):
    data = json.dumps(body).encode()
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                URL, data=data, headers={"Content-Type": "application/json", "User-Agent": "frontier-pulse/0.1"}
            )
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.load(r)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as e:
            last = e
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"Hyperliquid request failed after {retries} tries: {last}")


def meta_and_ctxs(dex=DEX):
    """Return list of dicts: universe entry merged with its asset ctx."""
    meta, ctxs = post({"type": "metaAndAssetCtxs", "dex": dex})
    out = []
    for u, c in zip(meta["universe"], ctxs):
        d = dict(u)
        d.update(c)
        out.append(d)
    return out


def candles(coin, interval, start_ms, end_ms):
    """Candles in [start,end], paging forward past the ~5000 cap."""
    res, cur = [], start_ms
    while True:
        batch = post({"type": "candleSnapshot", "req": {"coin": coin, "interval": interval, "startTime": cur, "endTime": end_ms}})
        if not batch:
            break
        res.extend(batch)
        nxt = batch[-1]["t"] + 1
        if len(batch) < 1000 or nxt >= end_ms:
            break
        cur = nxt
    seen, uniq = set(), []
    for c in res:
        if c["t"] not in seen:
            seen.add(c["t"])
            uniq.append(c)
    return uniq


def funding_history(coin, start_ms):
    return post({"type": "fundingHistory", "coin": coin, "startTime": start_ms})
