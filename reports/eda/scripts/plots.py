"""Figures for the clickhouse-analytics EDA (matplotlib OO style, Agg backend).

Reads the full-table aggregates written by full_aggregates.py / funnel_exact.py
and re-queries DuckDB only for the per-product revenue vector.

Run:
    /Users/nikitaboarkin/Desktop/00 ide/00 portfolio/.eda-tools/.venv/bin/python \
        reports/eda/scripts/plots.py
"""

from __future__ import annotations

import json
from pathlib import Path

import duckdb
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
FIG = HERE.parent / "figures"
FIG.mkdir(parents=True, exist_ok=True)

agg = json.loads((HERE / "aggregates.json").read_text())
fun = json.loads((HERE / "funnel_exact.json").read_text())

plt.rcParams.update(
    {
        "font.family": ["DejaVu Sans", "sans-serif"],
        "axes.unicode_minus": False,
        "axes.grid": True,
        "grid.alpha": 0.3,
        "figure.dpi": 120,
    }
)

# ---------------------------------------------------------------------------
# Figure 1 — amount distribution: all events (zero-inflated) vs purchases only
# ---------------------------------------------------------------------------
con = duckdb.connect()
sample = con.execute(
    "SELECT amount, event_type FROM read_parquet("
    "'/private/var/folders/pg/3tkd56hn1h56w17r97f6bfqr0000gn/T/opencode/seed_sample500k.parquet')"
).fetchnumpy()
amt_all = sample["amount"]
amt_buy = amt_all[sample["event_type"] == 4]

fig, axes = plt.subplots(1, 2, figsize=(12, 4.5), layout="constrained")
axes[0].hist(amt_all, bins=80, color="C0", edgecolor="white")
axes[0].set_yscale("log")
axes[0].set(
    xlabel="amount",
    ylabel="events (log scale)",
    title="Amount across all 500k sampled events",
)
axes[0].annotate(
    "82% of events have amount = 0\n(non-purchase events)",
    xy=(10, 3.5e5),
    xytext=(120, 2e5),
    fontsize=9,
    arrowprops={"arrowstyle": "->", "color": "0.4"},
)
axes[1].hist(amt_buy, bins=80, color="C2", edgecolor="white")
axes[1].set(
    xlabel="amount",
    ylabel="purchase events",
    title="Amount on purchase events (event_type = 4)",
)
axes[1].annotate(
    "uniform(5, 500): mean 252.5 ≈ median 252.6",
    xy=(250, 600),
    xytext=(60, 900),
    fontsize=9,
    arrowprops={"arrowstyle": "->", "color": "0.4"},
)
fig.suptitle("Primary metric `amount` — zero-inflated overall, uniform on purchases")
fig.savefig(FIG / "fig1_amount_distribution.png", dpi=300, bbox_inches="tight")
plt.close(fig)

# ---------------------------------------------------------------------------
# Figure 2 — windowFunnel(86400): cumulative funnel (lead finding)
# ---------------------------------------------------------------------------
raw = dict(fun["distribution"])
reached = [
    1_000_000,
    raw["2"] + raw["3"] + raw["4"],
    raw["3"] + raw["4"],
    raw["4"],
]
labels = ["1 visit", "2 cart", "3 checkout", "4 purchase"]
pct = [100 * v / reached[0] for v in reached]

fig, ax = plt.subplots(figsize=(9, 5.5), layout="constrained")
bars = ax.bar(
    labels,
    reached,
    color=["#4C72B0", "#55A868", "#C44E52", "#8172B2"],
    edgecolor="black",
)
ax.set_yscale("log")
ax.set(
    ylabel="users reaching step (log scale)",
    title="24h conversion funnel — windowFunnel(86400), 1,000,000 users",
)
for b, v, p in zip(bars, reached, pct):
    ax.annotate(
        f"{v:,}\n({p:.2f}%)",
        (b.get_x() + b.get_width() / 2, v),
        ha="center",
        va="bottom",
        fontsize=9,
    )
ax.set_ylim(200, 3e6)
fig.savefig(FIG / "fig2_funnel.png", dpi=300, bbox_inches="tight")
plt.close(fig)

# ---------------------------------------------------------------------------
# Figure 3 — revenue by channel (flat by construction)
# ---------------------------------------------------------------------------
ch = agg["rev_by_channel"]
ch_sorted = sorted(ch, key=lambda r: -r[2])
names = [f"ch{r[0]}" for r in ch_sorted]
rev = [r[2] / 1e6 for r in ch_sorted]
shares = [r[3] for r in ch_sorted]

fig, ax = plt.subplots(figsize=(8, 5), layout="constrained")
bars = ax.bar(names, rev, color="C0", edgecolor="black")
ax.set(
    xlabel="channel",
    ylabel="revenue, $M",
    title="Revenue by channel — flat (no channel effect)",
)
for b, v, s in zip(bars, rev, shares):
    ax.annotate(
        f"{v:.0f}M\n{s:.1f}%",
        (b.get_x() + b.get_width() / 2, v),
        ha="center",
        va="bottom",
        fontsize=9,
    )
ax.set_ylim(0, max(rev) * 1.18)
fig.savefig(FIG / "fig3_revenue_by_channel.png", dpi=300, bbox_inches="tight")
plt.close(fig)

# ---------------------------------------------------------------------------
# Figure 4 — weekly trend: revenue and events (partial edge weeks flagged)
# ---------------------------------------------------------------------------
wk = agg["weekly"]
weeks = [w[0][:10] for w in wk]
rev_w = [w[4] / 1e6 for w in wk]
ev_w = [w[1] / 1e6 for w in wk]

fig, ax = plt.subplots(figsize=(12, 5), layout="constrained")
ax.plot(weeks, rev_w, marker="o", color="C0", label="revenue, $M")
ax.set(
    xlabel="week start (Mon)",
    ylabel="weekly revenue, $M",
    title="Weekly revenue & event volume — stable, edge weeks partial",
)
ax.set_xticks(range(len(weeks)))
ax.set_xticklabels(weeks, rotation=90)
for i in (0, len(weeks) - 1):
    ax.axvspan(i - 0.5, i + 0.5, color="0.85", zorder=0)
ax.annotate(
    "partial weeks\n(6 of 7 days)",
    xy=(len(weeks) - 1, rev_w[-1]),
    xytext=(len(weeks) - 6, rev_w[-1] - 6),
    fontsize=9,
    arrowprops={"arrowstyle": "->", "color": "0.4"},
)
ax2 = ax.twinx()
ax2.plot(weeks, ev_w, marker="s", color="C3", alpha=0.7, label="events, M")
ax2.set_ylabel("weekly events, M", color="C3")
ax2.grid(False)
h1, l1 = ax.get_legend_handles_labels()
h2, l2 = ax2.get_legend_handles_labels()
ax.legend(h1 + h2, l1 + l2, frameon=False, loc="lower left")
fig.savefig(FIG / "fig4_weekly_trend.png", dpi=300, bbox_inches="tight")
plt.close(fig)

# ---------------------------------------------------------------------------
# Figure 5 — per-product revenue distribution (uniform, no concentration)
# ---------------------------------------------------------------------------
prod = (
    con.execute(
        f"""SELECT sum(amount) rev FROM read_parquet('{ROOT / "data" / "seed.parquet"}')
       WHERE event_type = 4 GROUP BY product_id ORDER BY rev DESC"""
    ).fetchnumpy()["rev"]
    / 1e6
)

fig, ax = plt.subplots(figsize=(9, 5), layout="constrained")
ax.plot(np.arange(1, len(prod) + 1), prod, color="C4")
ax.axhline(prod.mean(), color="k", ls="--", lw=1, label=f"mean {prod.mean():.2f}M")
ax.set(
    xlabel="product rank (1 = highest revenue)",
    ylabel="revenue over 180 days, $M",
    title="Per-product revenue — flat (1000 products, max/min = 1.08)",
)
ax.legend(frameon=False)
fig.savefig(FIG / "fig5_product_revenue.png", dpi=300, bbox_inches="tight")
plt.close(fig)

print("figures written to", FIG)
for p in sorted(FIG.glob("*.png")):
    print(" ", p.name, f"{p.stat().st_size / 1024:.0f} KB")
