"""X post drafts: `python -m fp.posts daily|weekend`."""
import sys
from datetime import datetime

from . import cards
from .common import NY, OUT, fmt_pct, fmt_usd, load_json, DATA, site_cfg, now_utc
from .metrics import pre_ipo_metrics

MAX_LEN = 270


def daily_text(metrics, handle="@entropyIO"):
    lines = []
    for m in metrics.values():
        lines.append(f"${m['short']}: {fmt_usd(m['valuation_usd'])} implied ({m['multiple']:.2f}x last round of "
                     f"{fmt_usd(m['last_round_usd'])}), 24h {fmt_pct(m['change_24h'])}, funding {fmt_pct(m['funding_apr'], 0)} APR (24h avg)")
    head = "What the market says they're worth, 24/7 (Entropy pre-IPO perps):"
    text = head + "\n" + "\n".join(lines) + "\n" + handle
    if len(text) > MAX_LEN:  # drop funding detail first, then the header
        lines = [f"${m['short']}: {fmt_usd(m['valuation_usd'])} implied ({m['multiple']:.2f}x last round), 24h {fmt_pct(m['change_24h'])}"
                 for m in metrics.values()]
        text = head + "\n" + "\n".join(lines) + "\n" + handle
    if len(text) > MAX_LEN:
        text = "\n".join(lines) + "\n" + handle
    assert len(text) <= MAX_LEN, len(text)
    return text


def weekend_text(rep, handle="@entropyIO"):
    w = rep["weekends"][-1]
    s = w["summary"]
    parts = [f"{r['symbol'].split(':')[1]} {fmt_pct(r['predicted'], 1)} vs {fmt_pct(r['actual'], 1)}" for r in w["rows"]]
    o = rep["overall"]
    text = (f"Weekend gap to Mon {w['monday']}: Entropy's 24/7 price pre-open vs the real open (predicted vs actual)\n"
            + "\n".join(parts) + f"\nDirection right {s['hits']}/{s['n_scored']}; "
            f"all-time {o['hits']}/{o['n_scored']} ({o['hit_rate'] * 100:.0f}%)\n{handle}")
    if len(text) > 280:  # keep within one post even with many symbols
        text = text.replace("Entropy's 24/7 price pre-open vs the real open (predicted vs actual)", "pre-open perp vs real open")
    return text


def write(kind, text, make_card):
    d = now_utc().astimezone(NY).date().isoformat()
    OUT.mkdir(exist_ok=True)
    folder = OUT / "posts"
    folder.mkdir(exist_ok=True)
    png = folder / f"{d}-{kind}.png"
    md = folder / f"{d}-{kind}.md"
    make_card(png)
    md.write_text(f"{text}\n\n---\nchars: {len(text)}\nimage: {png.name}\n")
    return md, png


def daily():
    metrics = pre_ipo_metrics()
    text = daily_text(metrics, site_cfg()["entropy_handle"])
    return write("daily", text, lambda p: cards.valuation_card(
        p, metrics, size=(1200, 675), title="What the market says they're worth"))


def weekend():
    rep = load_json(DATA / "weekend.json")
    if not rep or not rep["weekends"]:
        raise SystemExit("no weekend data; run fp.weekend first")
    w = rep["weekends"][-1]
    text = weekend_text(rep, site_cfg()["entropy_handle"])
    return write("weekend", text, lambda p: cards.weekend_card(p, w["rows"], w["summary"], w["monday"]))


if __name__ == "__main__":
    kind = sys.argv[1] if len(sys.argv) > 1 else "daily"
    if kind not in ("daily", "weekend"):
        raise SystemExit("usage: python -m fp.posts daily|weekend")
    md, png = (daily if kind == "daily" else weekend)()
    print(md)
    print(png)
