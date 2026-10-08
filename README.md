# Frontier Pulse

Free, public analytics site and X-post generator for [Entropy](https://entropy.io), a Hyperliquid HIP-3 perp deployer (dex `io`) that lists US equities 24/7 and **pre-IPO perps** (`io:ANTH` Anthropic, `io:OAI` OpenAI).

Unofficial community project, not affiliated with Entropy. Not financial advice.

## How it works

```
./run.sh [daily|weekend]     collector -> weekend -> build_site  (+ post draft)
./publish.sh [--dry-run]     build, scan for secrets, force-push site/ to gh-pages
python -m unittest           math tests (stdlib only)
```

| Module | Role |
| --- | --- |
| `fp/hl.py` | Hyperliquid `/info` client (retries, timeouts, candle paging) |
| `fp/collector.py` | Appends one compact snapshot to `data/snapshots.jsonl` (skips if the last one is under 2 min old; safe from cron every 15 min) |
| `fp/weekend.py` | Weekend Gap report -> `data/weekend.json` |
| `fp/build_site.py` | Static single page in `site/` (Chart.js from CDN), `site/data/*.json`, `site/og.png` |
| `fp/posts.py` | X drafts + PNG cards in `out/posts/` |

Config lives in `config/` (`valuations.json` for last-round valuations with sources, `site.json` for names, handles, `referral_url`, and the weekend exclude list). Only the Python standard library and matplotlib are used (see `requirements.txt`).

## Methodology

**Implied valuation.** Pre-IPO perps are specified so that $1 of price = $1B of market cap, so valuation = mark price x $1B. "Multiple" is that figure divided by the last primary-round post-money valuation in `config/valuations.json`; "premium" is multiple - 1. Perp prices can also be pushed by leverage, funding and liquidity, so they are a market signal, not an appraisal. Bounds (L/U), OI caps and resolution dates come from the [Entropy docs](https://docs.entropy.io/asset-directory/pre-ipo-assets).

**Funding APR.** Funding settles hourly, so APR = hourly rate x 24 x 365 (simple, not compounded). Positive means longs pay shorts.

**Weekend Gap.** For each US equity perp and each weekend with 15-minute candles (America/New_York, DST-correct; 2026-2027 NYSE holidays and early closes hardcoded):

- *Friday close* = close of the 15:45-16:00 ET candle on the last trading day before the weekend (12:45-13:00 on early-close days).
- *Pre-open* (Entropy's 24/7 "prediction") = close of the 09:15-09:30 ET candle on the next trading day (Tuesday if Monday is a holiday).
- *Open ref* = close of the 09:30-09:45 ET candle that day.
- predicted = pre-open / Friday - 1; actual = open / Friday - 1.
- Direction hit = same sign. Weekends where |actual| < 0.1% are "flat" and excluded from the hit rate (reported as `n_flat`).
- Abs error = |predicted - actual| in percentage points. Captured share = predicted / actual when the signs match.
- Weekends missing any of the three candles are skipped. Tencent (HK hours) and the pre-IPO perps are excluded.

Caveat: small sample (weekly observations since the markets launched in Aug 2026) and Entropy's equity oracle is pinned to the public price only in regular hours, so treat hit rates as descriptive.

## Disclaimers

Unofficial community dashboard, not affiliated with Entropy. Not financial advice. Data may be delayed or wrong; check the primary sources.
