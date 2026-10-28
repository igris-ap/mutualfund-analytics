"""Turn the raw cache into clean tables: schemes, nav_daily, nav_flags, scheme_log."""
import logging

import pandas as pd

from src.clean.nav import clean_nav
from src.clean.schemes import base_scheme_key, classify_option, classify_plan, map_category, pair_plans
from src.config import benchmarks, settings
from src.ingest.mfapi import fetch_scheme, scheme_path
from src.ingest.run import UNIVERSE_PATH

log = logging.getLogger(__name__)


def _str(v):
    return v if isinstance(v, str) else None


def build():
    cfg = settings()
    universe = pd.read_csv(UNIVERSE_PATH)
    bench = {b["scheme_code"]: cat for cat, b in benchmarks().items()}
    candidates = [(r.scheme_code, r.amfi_category, _str(r.amfi_plan), _str(r.amfi_option), _str(r.history_name))
                  for r in universe.itertuples()]
    candidates += [(code, None, None, None, None) for code in bench]

    schemes, navs, flags, issues = [], [], [], []

    def skip(code, name, issue):
        issues.append({"scheme_code": code, "scheme_name": name, "issue": issue})

    for code, amfi_cat, amfi_plan, amfi_option, history_name in candidates:
        if not scheme_path(code).exists():
            skip(code, None, "not_fetched")
            continue
        payload = fetch_scheme(code)
        meta = payload["meta"]
        name = meta["scheme_name"].strip()
        is_bench = code in bench
        mfapi_cat = map_category(meta.get("scheme_category"))
        category = "Index Fund" if is_bench else mfapi_cat or amfi_cat
        if not is_bench and mfapi_cat != amfi_cat:
            skip(code, name, f"category_mismatch: mfapi={meta.get('scheme_category')!r}, used {category}")
        # A bare current name ('Motilal Oswal Midcap Fund') falls back to the full AMFI history name.
        if classify_option(name, amfi_option) is None and history_name:
            name = history_name
        option = classify_option(name, amfi_option)
        if option != "growth":
            skip(code, name, f"not_growth_option: {option or 'institutional, legacy or unlabelled plan'}")
            continue
        nav, f = clean_nav(code, payload["data"], cfg["nav_start_date"], cfg["jump_threshold"])
        if nav.empty:
            skip(code, name, "no_nav_in_range")
            continue
        navs.append(nav)
        flags.append(f)
        schemes.append({
            "scheme_code": code,
            "scheme_name": name,
            "fund_house": meta["fund_house"].strip(),
            "category": category,
            "plan_type": classify_plan(name, amfi_plan),
            "option_type": option,
            "base_scheme_key": base_scheme_key(meta["fund_house"], name),
            "is_benchmark": is_bench,
            "first_nav_date": nav["nav_date"].min().date(),
            "last_nav_date": nav["nav_date"].max().date(),
        })

    schemes = pd.DataFrame(schemes)
    names = schemes.set_index("scheme_code")["scheme_name"]
    active, pairing_log = pair_plans(schemes[~schemes["is_benchmark"]])
    schemes = pd.concat([active, schemes[schemes["is_benchmark"]]], ignore_index=True)
    pairing_log["scheme_name"] = pairing_log["scheme_code"].map(names)
    scheme_log = pd.concat([pd.DataFrame(issues), pairing_log], ignore_index=True)

    missing = set(bench) - set(schemes["scheme_code"])
    if missing:
        raise RuntimeError(f"benchmark schemes missing after cleaning: {missing}")
    kept = set(schemes["scheme_code"])  # pairing can drop legacy share classes
    navs = pd.concat(navs, ignore_index=True)
    flags = pd.concat(flags, ignore_index=True)
    log.info("clean: %d schemes kept, %d log entries", len(schemes), len(scheme_log))
    return schemes, navs[navs["scheme_code"].isin(kept)], flags[flags["scheme_code"].isin(kept)], scheme_log
