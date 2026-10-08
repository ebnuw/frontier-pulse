"""matplotlib image cards (OG image, post cards)."""
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from .common import fmt_pct, fmt_usd

BG, FG, MUTED = "#0b0f17", "#e8edf5", "#8b97ab"
COLORS = {"io:ANTH": "#d98b5f", "io:OAI": "#4fc3a1"}
UP, DOWN = "#3ddc97", "#ff6b6b"


def _fig(w, h):
    fig = plt.figure(figsize=(w / 100, h / 100), dpi=100, facecolor=BG)
    return fig


def valuation_card(path, metrics, size=(1200, 630), title="Implied valuation vs last funding round", footer="frontierpulse · unofficial · data: Hyperliquid / Entropy"):
    w, h = size
    fig = _fig(w, h)
    fig.text(0.05, 0.9, title, color=FG, fontsize=28, fontweight="bold", va="center")
    fig.text(0.05, 0.835, "Entropy pre-IPO perps · live, 24/7", color=MUTED, fontsize=16, va="center")
    ax = fig.add_axes([0.06, 0.2, 0.55, 0.58], facecolor=BG)
    items = list(metrics.values())
    xs = range(len(items))
    width = 0.34
    ax.bar([x - width / 2 for x in xs], [i["last_round_usd"] / 1e12 for i in items], width, color="#3a4458", label="Last round")
    ax.bar([x + width / 2 for x in xs], [i["valuation_usd"] / 1e12 for i in items], width,
           color=[COLORS.get(i["symbol"], "#7aa2ff") for i in items], label="Implied now")
    for x, i in zip(xs, items):
        ax.text(x - width / 2, i["last_round_usd"] / 1e12 + 0.03, fmt_usd(i["last_round_usd"]), color=MUTED, ha="center", fontsize=13)
        ax.text(x + width / 2, i["valuation_usd"] / 1e12 + 0.03, fmt_usd(i["valuation_usd"]), color=FG, ha="center", fontsize=15, fontweight="bold")
    ax.set_xticks(list(xs), [i["name"] for i in items], color=FG, fontsize=15)
    ax.set_ylim(0, max(i["valuation_usd"] for i in items) / 1e12 * 1.35)
    ax.tick_params(axis="y", colors=MUTED, labelsize=11)
    ax.set_ylabel("$ trillion", color=MUTED)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color("#2a3345")
    ax.legend(frameon=False, labelcolor=MUTED, loc="upper left", fontsize=12)
    y = 0.68
    for i in items:
        c = COLORS.get(i["symbol"], FG)
        fig.text(0.66, y, f"{i['short']}  {i['multiple']:.2f}× last round", color=c, fontsize=19, fontweight="bold")
        ch = i["change_24h"]
        fig.text(0.66, y - 0.075, f"24h {fmt_pct(ch)}", color=UP if (ch or 0) >= 0 else DOWN, fontsize=14)
        fig.text(0.66, y - 0.14, f"funding {fmt_pct(i['funding_apr'])} APR (24h avg)", color=MUTED, fontsize=14)
        y -= 0.24
    fig.text(0.05, 0.06, footer, color=MUTED, fontsize=12)
    fig.savefig(path, facecolor=BG)
    plt.close(fig)


def weekend_card(path, rows, summary, monday, size=(1200, 675)):
    w, h = size
    fig = _fig(w, h)
    fig.text(0.05, 0.92, f"Weekend gap: predicted vs actual (Mon {monday})", color=FG, fontsize=26, fontweight="bold", va="center")
    fig.text(0.05, 0.86, "Entropy 24/7 pre-open (09:15 ET) vs real open (09:30 ET), % vs Friday close", color=MUTED, fontsize=14, va="center")
    ax = fig.add_axes([0.07, 0.17, 0.88, 0.58], facecolor=BG)
    n = len(rows)
    xs = list(range(n))
    bw = 0.38
    ax.bar([x - bw / 2 for x in xs], [r["predicted"] * 100 for r in rows], bw, color="#7aa2ff", label="Predicted (24/7 perp)")
    ax.bar([x + bw / 2 for x in xs], [r["actual"] * 100 for r in rows], bw, color="#d98b5f", label="Actual open")
    ax.axhline(0, color="#2a3345", lw=1)
    ax.set_xticks(xs, [r["symbol"].split(":")[1] for r in rows], color=FG, fontsize=14)
    ax.tick_params(axis="y", colors=MUTED, labelsize=11)
    ax.set_ylabel("%", color=MUTED)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color("#2a3345")
    ax.legend(frameon=False, labelcolor=MUTED, fontsize=12, loc="best")
    hr = summary.get("hit_rate")
    fig.text(0.05, 0.06, f"Direction hit rate this weekend: {summary['hits']}/{summary['n_scored']}"
             + (f" ({hr * 100:.0f}%)" if hr is not None else "")
             + f"   ·   mean abs error {summary['mean_abs_err_pp']:.2f} pp   ·   unofficial, data: Hyperliquid", color=MUTED, fontsize=12)
    fig.savefig(path, facecolor=BG)
    plt.close(fig)
