"""Ingest: build the in-scope scheme universe and cache NAV history for each scheme.

Universe = every scheme code that AMFI lists under Large Cap, Flexi Cap or Mid Cap in
the current NAV file or in any quarterly NAV history snapshot since nav_start_date.
Including past snapshots brings in schemes that later merged or closed, which reduces
(but cannot remove) survivorship bias. Only growth options are fetched.
"""
import logging
from datetime import date

import pandas as pd

from src.clean.schemes import classify_option, map_category
from src.config import RAW_DIR, benchmarks, settings
from src.ingest import amfi, mfapi

log = logging.getLogger(__name__)

UNIVERSE_PATH = RAW_DIR / "universe.csv"


def snapshot_dates(start: date, end: date) -> list[date]:
    return [d.date() for d in pd.date_range(start, end, freq="QS")]


def build_universe() -> pd.DataFrame:
    start = pd.Timestamp(settings()["nav_start_date"]).date()
    frames = []
    for d in snapshot_dates(start, date.today()):
        snap = amfi.fetch_history_snapshot(d)
        if not snap.empty:
            frames.append(snap.assign(seen=d))
    frames.append(amfi.fetch_navall().assign(seen=date.today()))
    rows = pd.concat(frames, ignore_index=True)
    rows = rows[rows["scheme_type"].str.lower() == "open ended"]
    rows["category_mapped"] = rows["category"].map(map_category)
    in_scope = rows.dropna(subset=["category_mapped"]).copy()

    # Unmapped old-category equity schemes are context for the survivorship note.
    later = set(in_scope["scheme_code"])
    old = rows[rows["category"].str.contains("growth|equity", case=False, na=False)
               & rows["category_mapped"].isna() & ~rows["scheme_code"].isin(later)]
    old.groupby("scheme_code").agg(category=("category", "last"), name=("name", "last"),
                                   last_seen=("seen", "max")).to_csv(RAW_DIR / "universe_unmapped_equity.csv")

    in_scope = in_scope.sort_values("seen")
    # NAVAll gives the bare scheme name ('Motilal Oswal Midcap Fund'); history files give
    # the full plan name ('...-Direct Plan-Growth Option'), which classification can fall back on.
    in_scope["history_name"] = in_scope["name"].where(in_scope["seen"] < date.today())
    universe = in_scope.groupby("scheme_code").agg(
        history_name=("history_name", "last"),
        amfi_category=("category_mapped", "last"),
        amfi_name=("name", "last"),
        amfi_plan=("plan", "last"),
        amfi_option=("option", "last"),
        fund_house=("fund_house", "last"),
        first_seen=("seen", "min"),
        last_seen=("seen", "max"),
    ).reset_index()
    universe["option_guess"] = [
        classify_option(n, o if isinstance(o, str) else None)
        or (classify_option(h) if isinstance(h, str) else None)
        for n, o, h in zip(universe["amfi_name"], universe["amfi_option"], universe["history_name"])
    ]
    # Fetch growth and ambiguous options; IDCW is never needed.
    universe = universe[universe["option_guess"] != "idcw"]
    universe.to_csv(UNIVERSE_PATH, index=False)
    log.info("universe: %d in-scope non-IDCW scheme codes", len(universe))
    return universe


def run(sample: int | None = None, refresh: bool = False) -> None:
    mfapi.fetch_scheme_list(refresh=True)  # kept for cross-checking codes
    universe = build_universe()
    codes = list(universe["scheme_code"])
    if sample:
        codes = codes[:sample]
    codes += [b["scheme_code"] for b in benchmarks().values()]
    failed = []
    for i, code in enumerate(codes, 1):
        try:
            mfapi.fetch_scheme(code, refresh=refresh)
        except Exception as exc:  # keep going; a rerun retries only the missing ones
            log.warning("scheme %s: %s", code, exc)
            failed.append(code)
        if i % 50 == 0:
            log.info("fetched %d/%d", i, len(codes))
    log.info("ingest done: %d schemes cached, %d failed %s", len(codes) - len(failed), len(failed), failed or "")
