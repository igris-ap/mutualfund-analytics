"""Scheme filtering, plan/option classification and direct-regular pairing."""
import logging
import re

import pandas as pd

from src.config import CATEGORIES

log = logging.getLogger(__name__)

_CATEGORY_RE = re.compile(r"^Equity Schemes? - (Large Cap|Flexi Cap|Mid Cap) Fund$", re.I)
_IDCW_RE = re.compile(r"idcw|dividend|\bdiv\b|payout|reinvest|bonus|income distribution", re.I)
_EXCLUDE_RE = re.compile(r"institutional|segregated|unclaimed|wealth plan", re.I)


def map_category(raw: str | None) -> str | None:
    """'Equity Scheme - Large Cap Fund' -> 'Large Cap'; anything out of scope -> None.
    'Large & Mid Cap' does not match, by design."""
    m = _CATEGORY_RE.match((raw or "").strip())
    if not m:
        return None
    return next(c for c in CATEGORIES if c.lower() == m.group(1).lower())


def classify_plan(name: str, amfi_plan: str | None = None) -> str:
    """'direct' or 'regular'. Pre-2013 schemes without a plan label are regular plans."""
    text = f"{amfi_plan or ''} {name}"
    return "direct" if re.search(r"\bdirect\b", text, re.I) else "regular"


def classify_option(name: str, amfi_option: str | None = None) -> str | None:
    """'growth', 'idcw', or None when the name is out of scope or ambiguous."""
    if _EXCLUDE_RE.search(name):
        return None
    if amfi_option:
        if _IDCW_RE.search(amfi_option):
            return "idcw"
        if re.search(r"growth", amfi_option, re.I):
            return "growth"
    if _IDCW_RE.search(name):
        return "idcw"
    if re.search(r"growth", name, re.I):
        return "growth"
    return None


def base_scheme_key(fund_house: str, name: str) -> str:
    """Normalize a scheme name so the direct and regular plans of one fund share a key.

    'Aditya Birla Sun Life Large Cap Fund - Growth - Direct Plan' and
    'Aditya Birla Sun Life Large Cap Fund-Growth' both become
    'aditya birla sun life mutual fund|aditya birla sun life large cap fund'.
    """
    s = name.lower().replace("&", " and ")
    s = re.sub(r"\(.*?\)", " ", s)  # "(erstwhile ...)", "(formerly ...)"
    s = re.sub(r"\b(formerly|erstwhile)\b.*$", " ", s)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    s = re.sub(r"\bplan [a-c]\b", " ", s)  # 'Plan A' / 'Plan B (Direct)' style plan labels
    s = re.sub(r"\b(direct|regular|growth|option|plan)\b", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return f"{fund_house.lower().strip()}|{s}"


def pair_plans(schemes: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Make base_scheme_key unique per (key, plan) and log pairing problems.

    Expects columns scheme_code, scheme_name, base_scheme_key, plan_type, first_nav_date,
    last_nav_date. When several codes share a key and plan, the one labelled
    'Direct'/'Regular' with the latest last NAV keeps the key. Another code that ran at
    the same time (over a year of overlap) is a legacy share class of the same portfolio
    (e.g. 'Plan B') and is dropped; one that did not overlap has its own history, so it
    stays in the analysis, unpaired, with a '#code' suffix. Returns (schemes, pairing_log).
    """
    df = schemes.assign(labelled=schemes["scheme_name"].str.contains(r"\b(?:direct|regular)\b", case=False))
    df = df.sort_values(["labelled", "last_nav_date", "first_nav_date"], ascending=[False, False, True])
    issues, drop = [], []
    kept = df.drop_duplicates(["base_scheme_key", "plan_type"], keep="first").set_index(["base_scheme_key", "plan_type"])
    dup = df.duplicated(["base_scheme_key", "plan_type"], keep="first")
    for row in df[dup].itertuples():
        main = kept.loc[(row.base_scheme_key, row.plan_type)]
        overlap = min(row.last_nav_date, main.last_nav_date) - max(row.first_nav_date, main.first_nav_date)
        if overlap.days > 365:
            drop.append(row.Index)
            issues.append((row.base_scheme_key, row.scheme_code, row.plan_type, f"legacy_share_class_dropped: main={main.scheme_code}"))
        else:
            df.at[row.Index, "base_scheme_key"] = f"{row.base_scheme_key}#{row.scheme_code}"
            issues.append((row.base_scheme_key, row.scheme_code, row.plan_type, "duplicate_key_unpaired"))
    df = df.drop(index=drop).drop(columns="labelled")

    plans = df.groupby("base_scheme_key")["plan_type"].nunique()
    for row in df[df["base_scheme_key"].map(plans) < 2].itertuples():
        if "#" not in row.base_scheme_key:
            issues.append((row.base_scheme_key, row.scheme_code, row.plan_type, "no_matching_plan"))
    for key, code, plan, issue in issues:
        log.info("pairing: %s %s %s (%s)", issue, code, plan, key)
    pairing_log = pd.DataFrame(issues, columns=["base_scheme_key", "scheme_code", "plan_type", "issue"])
    return df.sort_values("scheme_code").reset_index(drop=True), pairing_log
