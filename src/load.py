"""Load: clean the raw cache and (re)build the base tables in Postgres.

Idempotent: tables are dropped and recreated each run (their dependent metric views
go with them and are rebuilt by the metrics step).
"""
import io
import logging

import pandas as pd

from src.clean.build import build
from src.config import SQL_DIR, benchmarks, settings
from src.db import get_engine, run_sql_file

log = logging.getLogger(__name__)

TABLES = ["nav_flags", "scheme_log", "benchmarks", "nav_daily", "schemes", "params"]


def copy_df(conn, table: str, df: pd.DataFrame) -> None:
    """Bulk insert with COPY, which is far faster than row inserts for ~1M NAV rows."""
    buf = io.StringIO()
    df.to_csv(buf, index=False, header=False, na_rep="\\N")
    buf.seek(0)
    cols = ", ".join(df.columns)
    with conn.connection.cursor() as cur:
        with cur.copy(f"COPY {table} ({cols}) FROM STDIN WITH (FORMAT csv, NULL '\\N')") as copy:
            copy.write(buf.read())


def write_tables(engine, schemes, nav, flags, scheme_log, bench, params) -> None:
    with engine.begin() as conn:
        conn.exec_driver_sql(f"DROP TABLE IF EXISTS {', '.join(TABLES)} CASCADE")
    run_sql_file(engine, SQL_DIR / "schema.sql")
    with engine.begin() as conn:
        copy_df(conn, "schemes", schemes)
        copy_df(conn, "nav_daily", nav)
        copy_df(conn, "benchmarks", bench)
        copy_df(conn, "nav_flags", flags)
        copy_df(conn, "scheme_log", scheme_log)
        copy_df(conn, "params", params)


def params_frame() -> pd.DataFrame:
    cfg = settings()
    keys = ["risk_free_rate", "analysis_years", "risk_window_years", "min_coverage", "min_windows", "sip_amount"]
    return pd.DataFrame({"key": keys, "value": [float(cfg[k]) for k in keys]})


def run() -> None:
    schemes, nav, flags, scheme_log = build()
    bench = pd.DataFrame([{"category": cat, "scheme_code": b["scheme_code"], "index_name": b["index"]}
                          for cat, b in benchmarks().items()])
    nav = nav.assign(nav_date=nav["nav_date"].dt.date)
    flags = flags.assign(nav_date=pd.to_datetime(flags["nav_date"]).dt.date)
    scheme_log = scheme_log.reindex(columns=["scheme_code", "scheme_name", "base_scheme_key", "plan_type", "issue"])
    write_tables(get_engine(), schemes, nav[["scheme_code", "nav_date", "nav"]], flags, scheme_log, bench, params_frame())
    log.info("load: %d schemes, %d NAV rows, %d flags", len(schemes), len(nav), len(flags))
