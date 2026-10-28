"""Builds a throwaway database (mf_test) from synthetic NAV series with known answers,
runs the real schema and metric views on it, and hands the engine to the tests."""
import logging

import numpy as np
import pandas as pd
import pytest
import sqlalchemy as sa

from src.db import get_engine
from src.load import write_tables
from src.metrics.build import create_views

logging.getLogger("pgserver").setLevel(logging.WARNING)

TEST_DB = "mf_test"
START, END = "2015-01-01", "2021-12-31"
RF = 0.065

# Scheme codes in the toy universe
INDEX, ACTIVE_12, REGULAR_11, DRAWDOWN, YOUNG, GAPPY, NOISY, DEAD = 1, 2, 3, 4, 5, 6, 7, 8


def weekdays(start=START, end=END) -> pd.DatetimeIndex:
    return pd.bdate_range(start, end)


def constant_growth(rate: float, dates: pd.DatetimeIndex, nav0: float = 100.0) -> np.ndarray:
    """NAV growing at exactly `rate` a year on a calendar-day basis."""
    days = (dates - dates[0]).days.to_numpy()
    return nav0 * (1 + rate) ** (days / 365)


def drawdown_series(dates: pd.DatetimeIndex) -> np.ndarray:
    """Flat at 100 until 2018-01-01, then a straight climb to 200, a fall to 150 (-25%),
    and back to 200 by the end."""
    t = np.linspace(0, 1, len(dates))
    nav = np.full(len(dates), 100.0)
    a = dates >= "2018-01-01"
    ta = (t[a] - t[a][0]) / (t[a][-1] - t[a][0])
    nav[a] = np.interp(ta, [0, 0.4, 0.7, 1.0], [100, 200, 150, 200])
    return nav


def noisy_series(dates: pd.DatetimeIndex) -> np.ndarray:
    rng = np.random.default_rng(42)
    return 100 * np.cumprod(1 + rng.normal(0.0005, 0.01, len(dates)))


def toy_tables():
    d = weekdays()
    young = weekdays("2019-01-01")
    dead = weekdays(end="2019-06-28")
    gappy = d[~((d >= "2020-01-01") & (d < "2020-03-01"))]  # two months of missing NAVs
    series = {
        INDEX: (d, constant_growth(0.10, d)),
        ACTIVE_12: (d, constant_growth(0.12, d)),
        REGULAR_11: (d, constant_growth(0.11, d)),
        DRAWDOWN: (d, drawdown_series(d)),
        YOUNG: (young, constant_growth(0.15, young)),
        GAPPY: (gappy, constant_growth(0.12, gappy)),
        NOISY: (d, noisy_series(d)),
        DEAD: (dead, constant_growth(0.08, dead)),
    }
    # Round like the NUMERIC(18,6) column, so reference calculations see the stored values.
    series = {c: (dt, np.round(v, 6)) for c, (dt, v) in series.items()}
    nav = pd.concat([pd.DataFrame({"scheme_code": c, "nav_date": dt.date, "nav": v})
                     for c, (dt, v) in series.items()], ignore_index=True)
    rows = [
        (INDEX, "Toy Index Fund - Direct - Growth", "Index Fund", "direct", "toy|index", True),
        (ACTIVE_12, "Toy Active Fund - Direct - Growth", "Large Cap", "direct", "toy|active", False),
        (REGULAR_11, "Toy Active Fund - Regular - Growth", "Large Cap", "regular", "toy|active", False),
        (DRAWDOWN, "Toy Drawdown Fund - Direct - Growth", "Large Cap", "direct", "toy|drawdown", False),
        (YOUNG, "Toy Young Fund - Direct - Growth", "Large Cap", "direct", "toy|young", False),
        (GAPPY, "Toy Gappy Fund - Direct - Growth", "Large Cap", "direct", "toy|gappy", False),
        (NOISY, "Toy Noisy Fund - Direct - Growth", "Large Cap", "direct", "toy|noisy", False),
        (DEAD, "Toy Merged Fund - Direct - Growth", "Large Cap", "direct", "toy|dead", False),
    ]
    schemes = pd.DataFrame(rows, columns=["scheme_code", "scheme_name", "category", "plan_type",
                                          "base_scheme_key", "is_benchmark"])
    schemes.insert(2, "fund_house", "Toy AMC")
    schemes["option_type"] = "growth"
    spans = nav.groupby("scheme_code")["nav_date"].agg(["min", "max"])
    schemes["first_nav_date"] = schemes["scheme_code"].map(spans["min"])
    schemes["last_nav_date"] = schemes["scheme_code"].map(spans["max"])
    bench = pd.DataFrame([{"category": "Large Cap", "scheme_code": INDEX, "index_name": "Toy 50"}])
    params = pd.DataFrame({
        "key": ["risk_free_rate", "analysis_years", "risk_window_years", "min_coverage", "min_windows", "sip_amount"],
        "value": [RF, 5, 3, 0.95, 1, 10000],
    })
    flags = pd.DataFrame(columns=["scheme_code", "nav_date", "flag_type", "nav", "prev_nav", "pct_change"])
    log = pd.DataFrame(columns=["scheme_code", "scheme_name", "base_scheme_key", "plan_type", "issue"])
    return schemes, nav, flags, log, bench, params, series


@pytest.fixture(scope="session")
def toy():
    admin = get_engine().execution_options(isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.exec_driver_sql(f"DROP DATABASE IF EXISTS {TEST_DB} WITH (FORCE)")
        conn.exec_driver_sql(f"CREATE DATABASE {TEST_DB}")
    engine = sa.create_engine(get_engine().url.set(database=TEST_DB))
    schemes, nav, flags, log, bench, params, series = toy_tables()
    write_tables(engine, schemes, nav, flags, log, bench, params)
    create_views(engine)
    yield engine, series
    engine.dispose()


def query(engine, sql: str) -> pd.DataFrame:
    return pd.read_sql(sa.text(sql), engine)
