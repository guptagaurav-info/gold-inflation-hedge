import numpy as np, pandas as pd, sys
sys.path.insert(0, "src")
from gih.core import horizon_table, inflation_beta


def _d(n=360, seed=0, beta=1.0):
    rng = np.random.default_rng(seed); idx = pd.date_range("1980-01-01", periods=n, freq="MS")
    c = rng.normal(0.003, 0.002, n)
    return pd.DataFrame({"gold": beta * c + rng.normal(0, 0.001, n), "cpi_ret": c, "stock": rng.normal(0.008, 0.04, n), "bond": rng.normal(0.004, 0.02, n)}, index=idx)


def test_beta_recovers_one_for_one_hedge():
    b, _ = inflation_beta(_d(beta=1.0)); assert abs(b["beta"] - 1) < 0.15


def test_perfect_hedge_never_loses_real():
    d = _d(); d["gold"] = d.cpi_ret
    t = horizon_table(d, years=(1, 5)); assert (t.median_real_ann.abs() < 1e-9).all()


def test_horizon_counts():
    t = horizon_table(_d(), years=(1, 10)); assert t.loc[1, "windows"] == 360 - 12 and t.loc[10, "windows"] == 360 - 120
