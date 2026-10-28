"""Metric views checked against synthetic NAV series whose answers are known."""
import numpy as np
import pandas as pd
import pytest

from tests.conftest import (ACTIVE_12, DEAD, DRAWDOWN, GAPPY, INDEX, NOISY, REGULAR_11, RF, YOUNG,
                            query, weekdays)

TOL = 1e-7  # NAVs carry 6 decimals


def rolling(engine, code, years):
    return query(engine, f"SELECT * FROM rolling_returns WHERE scheme_code = {code} AND window_years = {years}")


@pytest.mark.parametrize("years, n_windows", [(1, 72), (3, 48), (5, 24)])
def test_constant_growth_cagr_is_exact(toy, years, n_windows):
    engine, _ = toy
    r = rolling(engine, ACTIVE_12, years)
    assert len(r) == n_windows  # month-ends from Jan of year (2015 + years) to Dec 2021
    assert np.allclose(r["cagr"], 0.12, atol=TOL)
    assert np.allclose(rolling(engine, INDEX, years)["cagr"], 0.10, atol=TOL)


def test_no_window_longer_than_the_data(toy):
    engine, _ = toy
    assert len(rolling(engine, YOUNG, 1)) == 24  # launched 2019: 1-year windows from Jan 2020 only
    assert rolling(engine, YOUNG, 3).empty
    assert rolling(engine, YOUNG, 5).empty


def test_gaps_never_distort_cagr(toy):
    """Two months of missing NAVs in 2020: windows that span the gap with <95% coverage,
    or start inside it (stale forward-filled NAV), are skipped; every kept window is exact."""
    engine, _ = toy
    one = rolling(engine, GAPPY, 1)
    assert len(one) == 72 - 14  # 1-year windows ending Jan 2020 .. Feb 2021 are dropped
    for years in (1, 3, 5):
        r = rolling(engine, GAPPY, years)
        assert np.allclose(r["cagr"], 0.12, atol=TOL)
        assert (r["coverage"] >= 0.95).all()


def test_forward_fill_only_inside_gaps(toy):
    engine, _ = toy
    f = query(engine, f"SELECT * FROM nav_filled WHERE scheme_code = {GAPPY} ORDER BY nav_date")
    gap = f[(f["nav_date"] >= pd.Timestamp("2020-01-01").date()) & (f["nav_date"] < pd.Timestamp("2020-03-01").date())]
    assert not gap["observed"].any()
    assert (gap["nav"] == f.loc[gap.index[0] - 1, "nav"]).all()
    assert (gap["source_date"] == pd.Timestamp("2019-12-31").date()).all()
    raw = query(engine, f"SELECT COUNT(*) AS n FROM nav_daily WHERE scheme_code = {GAPPY}")["n"][0]
    assert f["observed"].sum() == raw


def test_excess_return_and_beat_rate(toy):
    engine, _ = toy
    b = query(engine, "SELECT * FROM fund_beat_rates").set_index(["scheme_code", "window_years"])
    for years in (1, 3, 5):
        assert b.loc[(ACTIVE_12, years), "beat_rate"] == 1
        assert b.loc[(ACTIVE_12, years), "median_excess"] == pytest.approx(0.02, abs=TOL)
        assert b.loc[(REGULAR_11, years), "median_excess"] == pytest.approx(0.01, abs=TOL)
    assert b.loc[(DEAD, 3), "beat_rate"] == 0  # 8% a year against a 10% index
    assert b.loc[(DEAD, 3), "median_excess"] == pytest.approx(-0.02, abs=TOL)
    assert b.loc[(DEAD, 3), "n_windows"] == 18  # 3-year windows ending Jan 2018 .. Jun 2019
    assert INDEX not in b.index.get_level_values(0)


def test_constant_growth_has_no_drawdown(toy):
    engine, _ = toy
    rm = query(engine, f"SELECT * FROM risk_metrics WHERE scheme_code = {ACTIVE_12}").iloc[0]
    assert rm["cagr"] == pytest.approx(0.12, abs=TOL)
    assert rm["max_drawdown"] == pytest.approx(0, abs=TOL)
    assert rm["volatility"] < 0.01  # only weekend steps (3 days of growth on Mondays)


def test_known_drawdown(toy):
    engine, _ = toy
    rm = query(engine, f"SELECT * FROM risk_metrics WHERE scheme_code = {DRAWDOWN}").iloc[0]
    assert rm["max_drawdown"] == pytest.approx(-0.25, abs=1e-3)  # 200 -> 150


def test_risk_metrics_match_reference(toy):
    """Volatility, Sharpe, Sortino and drawdown on a random walk, recomputed with numpy."""
    engine, series = toy
    dates, nav = series[NOISY]
    s = pd.Series(nav, index=dates)
    end = s.index[-1]
    start = s.index[s.index <= end - pd.DateOffset(years=3)][-1]
    w = s[start:end]
    r = w.pct_change().dropna()
    vol = r.std(ddof=1) * np.sqrt(252)
    excess = r.mean() * 252 - RF
    downside = np.sqrt(np.mean(np.minimum(r - RF / 252, 0) ** 2)) * np.sqrt(252)
    expected = {
        "volatility": vol,
        "sharpe": excess / vol,
        "sortino": excess / downside,
        "max_drawdown": (w / w.cummax() - 1).min(),
        "cagr": (w.iloc[-1] / w.iloc[0]) ** (365 / (end - start).days) - 1,
    }
    rm = query(engine, f"SELECT * FROM risk_metrics WHERE scheme_code = {NOISY}").iloc[0]
    for key, value in expected.items():
        assert rm[key] == pytest.approx(value, rel=1e-9), key


def test_risk_metrics_skip_low_coverage(toy):
    engine, _ = toy
    codes = set(query(engine, "SELECT scheme_code FROM risk_metrics")["scheme_code"])
    assert GAPPY not in codes  # 43 missing days out of ~783: coverage 94.5%
    assert YOUNG not in codes  # under 3 years of data
    assert DEAD not in codes


def test_direct_regular_gap_and_sip(toy):
    engine, series = toy
    g = query(engine, "SELECT * FROM direct_regular_gap")
    assert len(g) == 1
    g = g.iloc[0]
    assert (g["direct_code"], g["regular_code"]) == (ACTIVE_12, REGULAR_11)
    assert g["annual_gap"] == pytest.approx(0.01, abs=TOL)

    dates = weekdays()
    sip_dates = pd.Series(dates, index=dates).groupby(dates.to_period("M")).min().loc["2017-01":"2021-12"]
    assert len(sip_dates) == 60  # analysis_years = 5 in the toy params
    value = {}
    for code in (ACTIVE_12, REGULAR_11):
        nav = pd.Series(series[code][1], index=dates)
        value[code] = (10000 / nav[sip_dates.values]).sum() * nav.iloc[-1]
    assert g["sip_invested"] == 600000
    assert g["sip_direct_value"] == pytest.approx(value[ACTIVE_12], rel=1e-9)
    assert g["sip_rupee_gap"] == pytest.approx(value[ACTIVE_12] - value[REGULAR_11], rel=1e-9)
    assert g["sip_rupee_gap"] > 0


def test_survivorship_counts(toy):
    engine, _ = toy
    s = query(engine, "SELECT * FROM survivorship WHERE category = 'Large Cap' AND plan_type = 'direct'").iloc[0]
    # window: 2016-12-31 .. 2021-12-31; the index fund is not counted
    assert s["schemes_at_start"] == 5  # active, drawdown, gappy, noisy, dead
    assert s["closed_or_merged"] == 1  # dead
    assert s["launched_since"] == 1  # young
    assert s["schemes_at_end"] == 5  # active, drawdown, gappy, noisy, young


def test_category_summary_counts_each_fund_once(toy):
    engine, _ = toy
    c = query(engine, "SELECT * FROM category_summary WHERE window_years = 3 AND plan_type = 'direct'")
    large, total = c.set_index("category").loc[["Large Cap", "All"]].itertuples(index=False)
    assert large == total  # one category, so the 'All' row matches it
    n = query(engine, "SELECT COUNT(*) AS n FROM fund_beat_rates WHERE window_years = 3 AND plan_type = 'direct'")
    assert c.set_index("category").loc["Large Cap", "n_funds"] == n["n"][0]
