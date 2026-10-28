"""Database connection.

Uses DATABASE_URL when set (e.g. the Docker Compose Postgres). Otherwise, when
USE_EMBEDDED_PG=1, uses an embedded Postgres from the pgserver wheel. Its data
directory defaults to ~/.mf-analytics/pgdata (override with EMBEDDED_PG_DIR), kept
out of the repo because sync tools such as OneDrive lock files Postgres needs.
By default each process starts it on demand and it stops when the last one exits;
`python -m src.db start` keeps it running (faster dashboard start-up) until
`python -m src.db stop`.
"""
import os
import sys
from functools import lru_cache
from pathlib import Path

import sqlalchemy as sa

import src.config  # noqa: F401  (loads .env)

PGDATA = Path(os.getenv("EMBEDDED_PG_DIR", Path.home() / ".mf-analytics" / "pgdata"))


def _embedded_server(cleanup_mode: str | None = "stop"):
    import pgserver

    PGDATA.mkdir(parents=True, exist_ok=True)
    return pgserver.get_server(PGDATA, cleanup_mode=cleanup_mode)


def database_url(dbname: str | None = None) -> str:
    url = os.getenv("DATABASE_URL")
    if not url:
        if os.getenv("USE_EMBEDDED_PG", "1") != "1":
            raise RuntimeError("Set DATABASE_URL in .env, or USE_EMBEDDED_PG=1 to use embedded Postgres.")
        server = _embedded_server()
        url = server.get_uri()
        _keepalive.append(server)
    url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    if dbname:
        url = sa.engine.make_url(url).set(database=dbname).render_as_string(hide_password=False)
    return url


_keepalive: list = []


@lru_cache(maxsize=None)
def get_engine(dbname: str | None = None) -> sa.Engine:
    return sa.create_engine(database_url(dbname), future=True)


def run_sql_file(engine: sa.Engine, path) -> None:
    """Execute a .sql file containing one or more statements."""
    sql = open(path, encoding="utf-8").read()
    with engine.begin() as conn:
        conn.exec_driver_sql(sql)


if __name__ == "__main__":
    action = sys.argv[1] if len(sys.argv) > 1 else "start"
    if action == "start":
        print("embedded Postgres running at", _embedded_server(cleanup_mode=None).get_uri())
    elif action == "stop":
        _embedded_server(cleanup_mode="stop")  # this process is the last user, so exiting stops it
        print("embedded Postgres stopped")
    else:
        sys.exit("usage: python -m src.db [start|stop]")
