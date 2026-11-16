"""Gold (World Bank Pink Sheet / Timothy Green monthly, via datasets/gold-prices) against US CPI (BLS via datasets/cpi-us),
US stocks (Shiller then SPY) and a 10-year par Treasury, monthly from the end of the gold window (Aug 1971)."""
import numpy as np, pandas as pd
from .sbc_core import load_monthly

START = "1971-09-01"   # first month after the US closed the gold window (15 Aug 1971); fixed in advance


def gold_monthly():
    g = pd.read_csv("data/raw/monthly.csv"); g["Date"] = pd.to_datetime(g.Date + "-01")
    return g.set_index("Date").Price.astype(float)


def panel():
    m = load_monthly()
    g = gold_monthly()
    d = pd.DataFrame({"gold_px": g}).join(m[["stock", "bond", "cpi"]], how="inner")
    # BLS published no CPI for October 2025 (federal shutdown): fill that one month log-linearly; no other gaps
    d["cpi"] = np.exp(np.log(d.cpi).interpolate(limit=1, limit_area="inside"))
    d["gold"] = d.gold_px.pct_change()
    d["cpi_ret"] = d.cpi.pct_change(fill_method=None)
    d = d.loc[START:].dropna(subset=["gold", "cpi_ret", "stock", "bond"])
    return d


def horizon_table(d, years=(1, 5, 10, 20)):
    """Overlapping h-year windows: share where gold beat inflation; median and worst real return a year;
    correlation of gold's h-year return with h-year inflation."""
    lg = np.log1p(d.gold).cumsum(); lc = np.log1p(d.cpi_ret).cumsum()
    ls, lb = np.log1p(d.stock).cumsum(), np.log1p(d.bond).cumsum()
    rows = []
    for h in years:
        k = 12 * h
        g, c, s, b = (x.diff(k).dropna() for x in (lg, lc, ls, lb))
        real = (g - c) / h; idx = real.index
        rows.append(dict(years=h, windows=len(real), beat_inflation=(real > 0).mean(),
                         median_real_ann=np.expm1(real.median()), worst_real_ann=np.expm1(real.min()), best_real_ann=np.expm1(real.max()),
                         corr_with_inflation=np.corrcoef(g, c.loc[g.index])[0, 1],
                         stocks_beat_inflation=(((s - c.loc[s.index]) / h) > 0).mean(),
                         bonds_beat_inflation=(((b - c.loc[b.index]) / h) > 0).mean(),
                         independent=len(real) // k))
    return pd.DataFrame(rows).set_index("years")


def inflation_beta(d, freq="YE"):
    """Annual (calendar-year) returns: regress gold return on CPI inflation, both in %; beta 1 = a one-for-one hedge."""
    a = (1 + d[["gold", "cpi_ret", "stock", "bond"]]).resample(freq).prod() - 1
    a = a[a.index.year < 2026]                     # full years only
    x, y = a.cpi_ret * 100, a.gold * 100
    b = np.polyfit(x, y, 1); r = np.corrcoef(x, y)[0, 1]
    n = len(a); t = r * np.sqrt((n - 2) / (1 - r ** 2))
    return dict(years=n, beta=b[0], intercept=b[1], corr=r, t=t), a


def regime_table(d, bands=(0.025, 0.04)):
    """Calendar-year gold real return by that year's CPI inflation band (contemporaneous) and by the prior year's (known in advance)."""
    _, a = inflation_beta(d)
    real = (1 + a.gold) / (1 + a.cpi_ret) - 1
    cut = lambda s: pd.cut(s, [-1, bands[0], bands[1], 1], labels=["Below 2.5%", "2.5% to 4%", "Above 4%"])
    out = {}
    for nm, key in (("same_year", cut(a.cpi_ret)), ("prior_year", cut(a.cpi_ret.shift(1)))):
        out[nm] = pd.DataFrame({"years": real.groupby(key, observed=False).size(), "gold_real": real.groupby(key, observed=False).mean(),
                                "stock_real": ((1 + a.stock) / (1 + a.cpi_ret) - 1).groupby(key, observed=False).mean(),
                                "bond_real": ((1 + a.bond) / (1 + a.cpi_ret) - 1).groupby(key, observed=False).mean()})
    return out, a


def valuation(d, h=10):
    """Real gold price (gold / CPI, today's dollars) vs its average since 1971, and the next h-year real return a year.
    The ratio uses only data to that month except the full-sample mean (stated as a limit); an expanding-mean version is also reported."""
    rp = d.gold_px / d.cpi * d.cpi.iloc[-1]
    ratio_full = rp / rp.mean(); ratio_exp = rp / rp.expanding(60).mean()
    k = 12 * h
    fwd = (np.log(rp.shift(-k)) - np.log(rp)) / h
    x = pd.DataFrame({"ratio_full": ratio_full, "ratio_exp": ratio_exp, "fwd": np.expm1(fwd)}).dropna(subset=["ratio_full", "fwd"])
    quint = pd.qcut(x.ratio_full, 5, labels=["Cheapest 20%", "2", "3", "4", "Dearest 20%"])
    tbl = pd.DataFrame({"months": x.fwd.groupby(quint, observed=False).size(), "ratio_mid": x.ratio_full.groupby(quint, observed=False).median(),
                        "fwd_real_ann": x.fwd.groupby(quint, observed=False).median()})
    corr_full = np.corrcoef(np.log(x.ratio_full), x.fwd)[0, 1]; xe = x.dropna(subset=["ratio_exp"]); corr_exp = np.corrcoef(np.log(xe.ratio_exp), xe.fwd)[0, 1]
    return dict(real_price_now=rp.iloc[-1], ratio_now=ratio_full.iloc[-1], ratio_exp_now=ratio_exp.iloc[-1], max_ratio_before=ratio_full.iloc[:-1].max(),
                corr_full=corr_full, corr_exp=corr_exp, independent=len(x) // k), tbl, rp, x


def drawdowns(d):
    rp = d.gold_px / d.cpi
    dd = rp / rp.cummax() - 1
    trough = dd.idxmin(); peak = rp.loc[:trough].idxmax()
    rec = rp.loc[trough:][rp.loc[trough:] >= rp.loc[peak]]
    return dict(max_real_dd=dd.min(), peak=peak.date().isoformat(), trough=trough.date().isoformat(),
                recovered=rec.index[0].date().isoformat() if len(rec) else None,
                years_under=((rec.index[0] if len(rec) else rp.index[-1]) - peak).days / 365.25)
