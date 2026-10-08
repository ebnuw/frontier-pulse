# Frontier Pulse — build brief

Public, free analytics site + X-post generator for **Entropy** (entropy.io), a Hyperliquid HIP-3 perp deployer (dex name `io`) listing US equities 24/7 and **pre-IPO perps** (ANTHROPIC `io:ANTH`, OPENAI `io:OAI`). Goal: content that Entropy's team wants to share. Not affiliated with Entropy; say so in the footer with "Not financial advice".

Work dir: /home/ubuntu/work/frontier-pulse (git repo already initialised, do NOT add remotes or push). Python: use `.venv/bin/python` (matplotlib 3.11 installed; stdlib otherwise — no other pip installs unless essential; if you add one, list it in requirements.txt). No secrets anywhere. Never run sub-agents in the background. Append a short line to PROGRESS.md after each milestone.

## Data facts (verified)
- POST https://api.hyperliquid.xyz/info
  - `{"type":"metaAndAssetCtxs","dex":"io"}` → `[meta, ctxs]`; `meta.universe[i].name` like `io:ANTH`, `maxLeverage`; ctx has `markPx, oraclePx, midPx, funding` (hourly rate), `openInterest` (in coins), `dayNtlVlm`, `premium`, `prevDayPx`. Skip markets with zero OI and zero volume (io:SBE, io:PRL currently).
  - `{"type":"candleSnapshot","req":{"coin":"io:ANTH","interval":"1d"|"1h"|"15m","startTime":ms,"endTime":ms}}` → list of `{t,T,o,h,l,c,v,n}` (max ~5000 candles per call). ANTH daily history starts ~2026-08-19.
  - `{"type":"fundingHistory","coin":"io:ANTH","startTime":ms}` → `[{fundingRate, premium, time}]` hourly.
- Funding settles hourly → APR = rate × 24 × 365.
- **Pre-IPO perps: $1 of price = $1B market cap.** ANTH mark 2086 ⇒ implied valuation ≈ $2.09T.
- Pre-IPO spec (docs.entropy.io/asset-directory/pre-ipo-assets): ANTH bounds L=300/U=4200, OI cap 50M, no-IPO resolution 2028-08-18; OAI L=200/U=3000, OI cap 12M, resolution 2028-09-02.
- Equity perps: during the US regular session the oracle is pinned to the public price and mark = (public + 3-min EMA of mid)/2. Outside hours the market keeps trading 24/7 (price discovery), mark clipped to last_close × (1 ± 1/maxLeverage) (LULD). So Monday's first regular-session prints reflect the real open.
- io:TCNT is Tencent (HKEX hours) — exclude it from the US weekend report.

## Reference valuations — put in `config/valuations.json` (editable, with sources)
- ANTH: last primary round $965B post-money, Series H, 2026-05-28, https://www.anthropic.com/news/series-h . Earlier: Series G $380B 2026-02-12.
- OAI: $852B post-money, primary round closed 2026-03-31, reaffirmed by ~$7B employee tender 2026-08-10, https://www.cnbc.com/2026/08/10/openai-wraps-7-billion-share-sale-ahead-of-potential-ipo-.html
Also `config/site.json`: site name, X handle placeholders, `referral_url` (empty string = hide the CTA), list of US weekend-report symbols (all io equity markets except TCNT; build the list dynamically but allow an exclude list).

## Deliverables
1. `fp/collector.py` — snapshot `metaAndAssetCtxs` into `data/snapshots.jsonl` (one line per run, compact: ts + per-market mark/oracle/funding/oi/vol). Idempotent, safe to run every 15 min. Also `fp/hl.py` small client with retries/timeouts.
2. `fp/weekend.py` — **Weekend Gap report** for each US equity market, for every weekend with data (use 15m candles; America/New_York via zoneinfo, DST-correct):
   - Fri close ref = close of the 15:45–16:00 ET candle on the last trading day before the weekend.
   - Pre-open (Entropy's 24/7 "prediction") = close of the 09:15–09:30 ET candle on the next trading day.
   - Open ref = close of the 09:30–09:45 ET candle that day.
   - predicted move = preopen/fri−1, actual = open/fri−1, direction hit (same sign, treat |actual|<0.1% as flat), abs error in pp, and "captured share" = predicted/actual when same sign.
   - Handle US market holidays simply (hardcode 2026–2027 NYSE holidays; if the next day is a holiday move on). Skip weekends lacking candles.
   - Aggregate: hit rate, mean abs error, per symbol and overall; output JSON `data/weekend.json`.
3. `fp/build_site.py` → static site in `site/` (index.html + assets, plus `site/data/*.json`). Single page, mobile-first (owner reads on a phone), dark clean design, Chart.js from a CDN. Sections:
   - Hero: "What the market says Anthropic and OpenAI are worth — live, 24/7". Big cards per pre-IPO: implied valuation ($T/$B), × multiple vs last round, % premium vs last round, 24h change, funding APR, OI ($), 24h volume, distance to L/U bounds, days to no-IPO resolution. Link to source of last round.
   - Chart: implied valuation history (daily candles close since launch) per pre-IPO with a dashed horizontal line at the last round valuation. Also "ANTH vs OAI" ratio line (Anthropic valued at X× OpenAI).
   - Equities table: symbol, name, mark, 24h %, funding APR, OI $, 24h vol $, session state (US open/closed now; HK for TCNT).
   - Weekend Gap section: latest weekend table + all-time hit rate and mean error, short plain explanation.
   - Footer: updated-at (UTC + WIB), data source (Hyperliquid API, Entropy docs), "Unofficial community dashboard, not affiliated with Entropy. Not financial advice.", optional referral CTA.
   - Also emit `site/og.png` (1200×630 social card made with matplotlib showing both implied valuations vs last round) and use it for og:image / twitter:card meta.
4. `fp/posts.py` → X post drafts in `out/posts/YYYY-MM-DD-<kind>.md` + PNG card in the same folder:
   - `daily`: pre-IPO implied valuations, multiple vs last round, 24h change, funding; ≤ 270 chars; ends with `@entropyIO`; one card image (1200×675).
   - `weekend` (run Monday after 10:00 ET): weekend predicted vs actual per symbol, hit rate; card image with a bar chart predicted vs actual.
   - Plain, factual tone, no hype emojis spam (max 1–2), no "NFA" clutter, no hashtags except optionally `$ANTH`-style cashtags.
   - Print the final post path(s) on stdout.
5. `run.sh` — `collector → weekend → build_site` (+ `posts.py daily|weekend` when passed as arg). Exits non-zero on failure, quiet on success except paths.
6. `publish.sh` — builds then force-pushes `site/` as an orphan commit to branch `gh-pages` of remote `git@github-frontierpulse:0xmago77/frontier-pulse.git` (write it but DON'T run the push part; add a `--dry-run` flag). Before pushing scan the tree for 64-hex strings / PEM blocks and abort on a hit (allow Ethereum addresses = 40 hex).
7. `README.md` (what it is, how it works, methodology for valuation + weekend gap, disclaimers), `.gitignore` (.venv, data/*.jsonl, out/, __pycache__), `tests/` with a few pytest-free unittest tests for the weekend math and APR/valuation math (`python -m unittest`).

## Done means
`./run.sh daily` runs green against the live API; `site/index.html` exists and renders real numbers; `data/weekend.json` contains ≥ 3 weekends for at least SNDK/NBIS; `python -m unittest` passes; `out/posts/` has a daily draft + card. Commit everything (not data/out/site) to `main` with message "Frontier Pulse v0.1". In your final message list: files, the actual daily post text, the weekend summary numbers, and anything uncertain.
