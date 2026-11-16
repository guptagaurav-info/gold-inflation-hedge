"""Stock-bond correlation and inflation: data assembly and statistics.
Monthly 1871-2026: Shiller S&P 500 (price, dividends, 10-year yield, CPI) + BLS CPI (datasets/cpi-us) + US Treasury 10-year
(defeatbeta mirror) + SPY total return after the Shiller dividend series ends. Daily 2002-2026: SPY and TLT total returns."""
import numpy as np
import pandas as pd

RAW = "data/raw/"


def par_bond_return(y0, y1, years=10.0, m=12):
    """One-month total return of a par bond with coupon y0 (annual, decimal), repriced at y1 with `years - 1/m` left."""
    n = int(round((years - 1.0 / m) * 2))                        # semi-annual coupons remaining
    c, r = y0 / 2, y1 / 2
    price = c * (1 - (1 + r) ** -n) / r + (1 + r) ** -n
    return price - 1 + y0 / m


def spy_monthly_tr():
    import duckdb
    px = duckdb.sql(f"select cast(report_date as date) d, cast(close as double) c from '{RAW}stock_prices.parquet' where symbol='SPY'").df()
    dv = duckdb.sql(f"select cast(report_date as date) d, cast(amount as double) a from '{RAW}stock_dividend_events.parquet' where symbol='SPY'").df()
    px["d"] = pd.to_datetime(px.d); dv["d"] = pd.to_datetime(dv.d)
    s = px.set_index("d").c.sort_index(); a = dv.groupby("d").a.sum().reindex(s.index).fillna(0.0)
    tr = (s + a) / s.shift(1) - 1
    return (1 + tr).resample("MS").prod() - 1, s


def load_monthly():
    sh = pd.read_csv(RAW + "shiller.csv", parse_dates=["Date"]).set_index("Date")
    cpi = pd.read_csv(RAW + "cpi.csv", parse_dates=["Date"]).set_index("Date")["Index"].asfreq("MS")   # BLS skipped Oct 2025 (shutdown): keep the gap
    t = pd.read_parquet(RAW + "daily_treasury_yield.parquet"); t["d"] = pd.to_datetime(t.report_date)
    y_us = t.set_index("d").bc_10year.astype(float).resample("MS").mean()          # monthly average, like Shiller's GS10
    y = (sh["Long Interest Rate"].where(sh["Long Interest Rate"] > 0) / 100).combine_first(y_us)
    p = sh.SP500; dvd = sh.Dividend.where(sh.Dividend > 0)
    stock = (p + dvd / 12).div(p.shift(1)) - 1                                      # Shiller convention: monthly dividend = annual/12
    spy, _ = spy_monthly_tr()
    stock = stock.where(dvd.notna()).combine_first(spy)                             # SPY total return after Shiller dividends end
    bond = pd.Series(par_bond_return(y.shift(1).values, y.values), index=y.index)
    sh_cpi = sh["Consumer Price Index"].where(sh["Consumer Price Index"] > 0)
    infl = cpi.pct_change(12, fill_method=None).combine_first(sh_cpi.asfreq("MS").pct_change(12, fill_method=None))          # BLS CPI from 1914, Shiller CPI before
    df = pd.DataFrame({"stock": stock, "bond": bond, "y10": y, "infl": infl, "cpi": cpi}).loc["1872":]
    src = pd.Series("Shiller", index=df.index); src[dvd.reindex(df.index).isna()] = "SPY"
    df["stock_src"] = src
    return df.dropna(subset=["stock", "bond"])


def rolling_corr(df, win=36):
    return df.stock.rolling(win).corr(df.bond)


def blocks(df, win=36, start=None):
    """Non-overlapping windows: trailing inflation known at the window start, correlation realised over the window."""
    d = df.loc[start:] if start else df
    out = []
    for i in range(win, len(d) - win + 1, win):
        past, fut = d.iloc[i - win:i], d.iloc[i:i + win]
        out.append({"start": fut.index[0], "infl_prior": past.infl.mean(), "infl_during": fut.infl.mean(),
                    "corr": fut.stock.corr(fut.bond), "n": len(fut)})  # mean() skips the missing Oct 2025 CPI month
    return pd.DataFrame(out)


BANDS = [(-np.inf, 0.025, "Below 2.5%"), (0.025, 0.04, "2.5% to 4%"), (0.04, np.inf, "Above 4%")]


def band(x):
    for lo, hi, name in BANDS:
        if lo <= x < hi:
            return name
    return None


def regime_table(df, col="infl_lag"):
    d = df.dropna(subset=[col]).copy(); d["band"] = d[col].map(band)
    rows = []
    for _, _, name in BANDS:
        g = d[d.band == name]
        worst = g[g.stock <= g.stock.quantile(0.1)]
        rows.append({"band": name, "months": len(g), "corr": g.stock.corr(g.bond),
                     "bond_in_worst_stock_months_pct": worst.bond.mean() * 100, "share_bond_up_in_worst": (worst.bond > 0).mean()})
    return pd.DataFrame(rows)


def perf(r, ppy=12):
    r = r.dropna(); g = (1 + r).cumprod()
    return {"cagr": g.iloc[-1] ** (ppy / len(r)) - 1, "vol": r.std() * np.sqrt(ppy), "max_dd": (g / g.cummax() - 1).min()}


def boot_corr_diff(df, col="infl_lag", hi="Above 4%", lo="Below 2.5%", draws=2000, block=12, seed=0):
    """Moving-block bootstrap (12-month blocks) of corr(high band) - corr(low band). Returns 95% CI and share of draws <= 0."""
    d = df.dropna(subset=[col]).copy(); d["band"] = d[col].map(band)
    rng = np.random.default_rng(seed); n = len(d); idx = np.arange(n); out = []
    starts = np.arange(n - block + 1)
    for _ in range(draws):
        pick = np.concatenate([idx[s:s + block] for s in rng.choice(starts, n // block + 1)])[:n]
        b = d.iloc[pick]; h, l = b[b.band == hi], b[b.band == lo]
        out.append(h.stock.corr(h.bond) - l.stock.corr(l.bond))
    out = np.array(out)
    return float(np.percentile(out, 2.5)), float(np.percentile(out, 97.5)), float((out <= 0).mean())


def daily_spy_tlt():
    import duckdb
    q = lambda s: duckdb.sql(f"select cast(report_date as date) d, cast(close as double) c from '{RAW}stock_prices.parquet' where symbol='{s}'").df()
    dv = duckdb.sql(f"select symbol, cast(report_date as date) d, cast(amount as double) a from '{RAW}stock_dividend_events.parquet' where symbol in ('SPY','TLT')").df()
    out = {}
    for s in ("SPY", "TLT"):
        px = q(s); px["d"] = pd.to_datetime(px.d); p = px.set_index("d").c.sort_index()
        a = dv[dv.symbol == s].assign(d=lambda x: pd.to_datetime(x.d)).groupby("d").a.sum().reindex(p.index).fillna(0.0)
        out[s] = (p + a) / p.shift(1) - 1
    return pd.DataFrame(out).dropna()
