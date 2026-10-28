"""Metrics: (re)create every materialized view in sql/views, in file-name order."""
import logging
import time

from src.config import SQL_DIR
from src.db import get_engine, run_sql_file

log = logging.getLogger(__name__)


def create_views(engine) -> None:
    for path in sorted((SQL_DIR / "views").glob("*.sql")):
        t0 = time.perf_counter()
        run_sql_file(engine, path)
        log.info("view %s built in %.1fs", path.stem, time.perf_counter() - t0)


def run() -> None:
    create_views(get_engine())
