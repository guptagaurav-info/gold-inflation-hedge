"""Run everything: python -m gih.pipeline -> reports/metrics.json + reports/figures/*.png"""
import json, numpy as np, pandas as pd, matplotlib
matplotlib.use("Agg"); import matplotlib.pyplot as plt
from matplotlib.ticker import MultipleLocator, FuncFormatter, NullFormatter
from .core import panel, horizon_table, inflation_beta, regime_table, valuation, drawdowns

FIG = "reports/figures/"; plt.rcParams.update({"font.size": 11, "axes.spines.top": False, "axes.spines.right": False})
NAVY, GOLD, GREY, RED = "#1f3b5a", "#c9a227", "#8a8f98", "#b5523b"


def main():
    d = panel()
    m = {"sample": [d.index[0].date().isoformat(), d.index[-1].date().isoformat()], "months": len(d), "gold_last": float(d.gold_px.iloc[-1])}
    ht = horizon_table(d); m["horizons"] = ht.reset_index().to_dict("records")
    b, a = inflation_beta(d); m["annual_beta"] = b
    rt, _ = regime_table(d); m["regimes"] = {k: v.reset_index().astype({"cpi_ret": str}).to_dict("records") for k, v in rt.items()}
    v, vt, rp, x = valuation(d); m["valuation"] = v; m["valuation_quintiles"] = vt.reset_index().astype({"ratio_full": str}).to_dict("records")
    m["drawdown"] = drawdowns(d)
    vol = lambda r: r.std() * np.sqrt(12)
    m["vol"] = {"gold": vol(d.gold), "stock": vol(d.stock), "bond": vol(d.bond)}
    real = lambda r: ((1 + r).prod() / (1 + d.cpi_ret).prod()) ** (12 / len(d)) - 1
    m["real_cagr"] = {"gold": real(d.gold), "stock": real(d.stock), "bond": real(d.bond)}
    m["rp_peak"] = [rp.idxmax().date().isoformat(), float(rp.max())]; m["rp_1980"] = float(rp.loc["1980-01-01"]); m["rp_mean"] = float(rp.mean())
    json.dump(m, open("reports/metrics.json", "w"), indent=1, default=float)

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(rp.index, rp, color=GOLD, lw=2, label="Gold, in September 2026 dollars")
    ax.axhline(rp.mean(), color=GREY, ls="--", lw=1, label=f"Average since 1971: ${rp.mean():,.0f}")
    ax.set_yscale("log"); ax.set_ylabel("Real gold price, $ per ounce (log scale)")
    ax.set_yticks([500, 1000, 2000, 3000, 5000]); ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"${v:,.0f}")); ax.yaxis.set_minor_formatter(NullFormatter())
    ax.set_title("Gold after inflation: a 45-year round trip, then a record"); ax.legend(frameon=False, loc="upper left")
    fig.tight_layout(); fig.savefig(FIG + "real_price.png", dpi=160); plt.close(fig)

    fig, ax = plt.subplots(figsize=(10, 5)); xs = np.arange(len(ht)); w = 0.27
    for i, (c, lab, col) in enumerate((("beat_inflation", "Gold", GOLD), ("stocks_beat_inflation", "US stocks", NAVY), ("bonds_beat_inflation", "10-year Treasuries", GREY))):
        ax.bar(xs + (i - 1) * w, ht[c] * 100, w, color=col, label=lab)
    ax.set_xticks(xs, [f"{h}-year windows" for h in ht.index]); ax.set_ylabel("% of windows that beat inflation"); ax.set_ylim(0, 105)
    ax.axhline(50, color="k", lw=0.6, ls=":"); ax.set_title("How often each asset beat inflation, rolling windows since 1971"); ax.legend(frameon=False, fontsize=9)
    fig.tight_layout(); fig.savefig(FIG + "horizons.png", dpi=160); plt.close(fig)

    fig, axs = plt.subplots(1, 2, figsize=(11, 4.8), sharey=True)
    for ax, k, ttl in ((axs[0], "same_year", "By inflation in the same year"), (axs[1], "prior_year", "By inflation in the year before (known in advance)")):
        t = rt[k]; xs = np.arange(len(t))
        for i, (c, lab, col) in enumerate((("gold_real", "Gold", GOLD), ("stock_real", "Stocks", NAVY), ("bond_real", "Treasuries", GREY))):
            ax.bar(xs + (i - 1) * 0.27, t[c] * 100, 0.27, color=col, label=lab)
        ax.set_xticks(xs, [f"{i}\n({n} yrs)" for i, n in zip(t.index, t.years)]); ax.axhline(0, color="k", lw=0.8); ax.set_title(ttl, fontsize=11)
    axs[0].set_ylabel("Average real return in the year, %"); axs[0].legend(frameon=False, fontsize=9)
    fig.suptitle("Gold paid most in the inflation year itself", y=1.0); fig.tight_layout(); fig.savefig(FIG + "regimes.png", dpi=160, bbox_inches="tight"); plt.close(fig)

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.scatter(x.ratio_full, x.fwd * 100, s=8, color=NAVY, alpha=0.5, label="Each month, 1971–2016")
    ax.axvline(v["ratio_now"], color=RED, lw=1.5, label=f"September 2026: {v['ratio_now']:.1f}× the average")
    ax.axhline(0, color="k", lw=0.6); ax.set_xscale("log")
    ax.set_xticks([0.4, 0.6, 1, 1.5, 2, 3]); ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}×")); ax.xaxis.set_minor_formatter(NullFormatter())
    ax.set_xlabel("Real gold price relative to its 1971–2026 average (log scale)"); ax.set_ylabel("Real return a year over the next 10 years, %")
    ax.set_title("Expensive gold has been followed by poor real returns"); ax.legend(frameon=False, fontsize=9)
    fig.tight_layout(); fig.savefig(FIG + "valuation.png", dpi=160); plt.close(fig)
    print(json.dumps({k: m[k] for k in ("sample", "vol", "real_cagr", "rp_peak", "rp_1980", "rp_mean")}, default=float))


if __name__ == "__main__":
    main()
