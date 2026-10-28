"""Shared by the findings notebook and the dashboard: view loaders and the chart palette."""
import logging

import pandas as pd
import sqlalchemy as sa

from src.db import get_engine

logging.getLogger("pgserver").setLevel(logging.WARNING)

# One meaning per color across every chart: blue = direct plan, orange = regular plan,
# gray = the index fund / reference marks. Positive vs negative uses the blue/red diverging pair.
COLORS = {
    "direct": "#2a78d6",
    "regular": "#eb6834",
    "index": "#8a8984",
    "positive": "#2a78d6",
    "negative": "#e34948",
    "text": "#0b0b0b",
    "text_secondary": "#52514e",
    "grid": "#e4e3df",
    "surface": "#fcfcfb",
}
CATEGORIES = ["Large Cap", "Flexi Cap", "Mid Cap"]


def query(sql: str, **params) -> pd.DataFrame:
    return pd.read_sql(sa.text(sql), get_engine(), params=params)


def view(name: str) -> pd.DataFrame:
    return query(f"SELECT * FROM {name}")


def headline() -> pd.Series:
    return view("headline").iloc[0]


def beat_share_over_time(window_years: int) -> pd.DataFrame:
    """Share of funds beating the index fund in each rolling window, by window end date."""
    return query("""
        SELECT category, plan_type, end_date, AVG(beat::int) AS share_beating, COUNT(*) AS n_funds
        FROM excess_returns
        WHERE window_years = :y
        GROUP BY category, plan_type, end_date
        ORDER BY end_date
    """, y=window_years)


def fund_excess_series(scheme_code: int) -> pd.DataFrame:
    return query("""
        SELECT window_years, end_date, fund_cagr, bench_cagr, excess_return
        FROM excess_returns WHERE scheme_code = :c ORDER BY window_years, end_date
    """, c=scheme_code)
