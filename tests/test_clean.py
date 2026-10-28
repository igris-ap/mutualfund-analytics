"""Scheme classification, plan pairing, NAV cleaning and AMFI parsing."""
from datetime import date

import pandas as pd
import pytest

from src.clean.nav import clean_nav
from src.clean.schemes import base_scheme_key, classify_option, classify_plan, map_category, pair_plans
from src.ingest.amfi import parse


@pytest.mark.parametrize("direct, regular", [
    ("Aditya Birla Sun Life Large Cap Fund - Growth - Direct Plan", "Aditya Birla Sun Life Large Cap Fund-Growth"),
    ("Baroda Mid-cap Fund- Plan B (Direct) - Growth Option", "Baroda Mid-cap Fund- Plan A - Growth Option"),
    ("HDFC Flexi Cap Fund (Erstwhile HDFC Equity Fund) - Direct Plan - Growth", "HDFC Flexi Cap Fund - Growth Plan"),
    ("Motilal Oswal Midcap Fund-Direct Plan-Growth Option", "Motilal Oswal Midcap Fund-Regular Plan-Growth Option"),
    ("Kotak Bluechip Fund - Direct Plan - Growth", "Kotak Bluechip Fund - Growth"),
])
def test_direct_and_regular_share_a_key(direct, regular):
    assert base_scheme_key("AMC", direct) == base_scheme_key("AMC", regular)
    assert classify_plan(direct) == "direct"
    assert classify_plan(regular) == "regular"


def test_different_funds_get_different_keys():
    assert base_scheme_key("AMC", "Axis Midcap Fund - Growth") != base_scheme_key("AMC", "Axis Small Cap Fund - Growth")
    assert base_scheme_key("AMC A", "X Fund - Growth") != base_scheme_key("AMC B", "X Fund - Growth")


@pytest.mark.parametrize("name, amfi_option, expected", [
    ("Axis Midcap Fund - Regular Plan - Growth Option", None, "growth"),
    ("Axis Midcap Fund - Regular Plan - IDCW", None, "idcw"),
    ("Some Fund - Dividend Payout", None, "idcw"),
    ("DHFL Pramerica Large Cap Fund - BONUS OPTION", None, "idcw"),
    ("ICICI Prudential Bluechip Fund - Institutional Option - I - Growth", None, None),
    ("PGIM India Large Cap Fund Wealth Plan - Growth Option", None, None),
    ("Edelweiss Large Cap Fund", None, None),
    ("Edelweiss Large Cap Fund", "Direct Growth", "growth"),
    ("ABSL Large Cap Fund", "IDCW", "idcw"),
])
def test_classify_option(name, amfi_option, expected):
    assert classify_option(name, amfi_option) == expected


@pytest.mark.parametrize("raw, expected", [
    ("Equity Scheme - Large Cap Fund", "Large Cap"),
    ("Equity Schemes - Flexi Cap Fund", "Flexi Cap"),
    ("Equity Scheme - Mid Cap Fund", "Mid Cap"),
    ("Equity Scheme - Large & Mid Cap Fund", None),
    ("Other Scheme - Index Funds", None),
    (None, None),
])
def test_map_category(raw, expected):
    assert map_category(raw) == expected


def test_clean_nav_flags_and_keeps_jumps():
    records = [  # mfapi order: newest first
        {"date": "05-01-2021", "nav": "130.0"},   # +30% jump: flagged, kept
        {"date": "04-01-2021", "nav": "100.0"},
        {"date": "04-01-2021", "nav": "101.0"},   # duplicate with a different value
        {"date": "01-01-2021", "nav": "0.0"},     # non-positive: dropped
        {"date": "31-12-2020", "nav": "99.0"},
        {"date": "31-12-2012", "nav": "50.0"},    # before start_date
    ]
    nav, flags = clean_nav(7, records, "2013-01-01", 0.20)
    assert list(nav["nav"]) == [99.0, 100.0, 130.0]
    assert nav["nav_date"].is_monotonic_increasing
    assert sorted(flags["flag_type"]) == ["duplicate_date", "jump_gt_threshold", "nonpositive_nav"]
    jump = flags.set_index("flag_type").loc["jump_gt_threshold"]
    assert jump["pct_change"] == pytest.approx(0.30)


def test_pair_plans_drops_legacy_share_class_and_logs_unmatched():
    d = date
    schemes = pd.DataFrame([
        (1, "Edelweiss Large Cap Fund - Direct Plan - Growth", "k|edel", "direct", d(2013, 1, 1), d(2026, 10, 1)),
        (2, "Edelweiss Large Cap Fund - Regular Plan - Growth", "k|edel", "regular", d(2013, 1, 1), d(2026, 10, 1)),
        (3, "Edelweiss Large Cap Fund -Plan B - Growth option", "k|edel", "regular", d(2013, 1, 1), d(2026, 10, 1)),
        (4, "Old Fund - Growth", "k|old", "regular", d(2013, 1, 1), d(2015, 1, 1)),
        (5, "Old Fund - Regular Plan - Growth", "k|old", "regular", d(2016, 1, 1), d(2026, 10, 1)),
    ], columns=["scheme_code", "scheme_name", "base_scheme_key", "plan_type", "first_nav_date", "last_nav_date"])
    out, log = pair_plans(schemes)
    assert set(out["scheme_code"]) == {1, 2, 4, 5}  # 3 overlaps 2 for years: dropped
    assert out.set_index("scheme_code").loc[4, "base_scheme_key"] == "k|old#4"  # own history, unpaired
    issues = log.set_index("scheme_code")["issue"]
    assert issues[3].startswith("legacy_share_class_dropped")
    assert issues[4] == "duplicate_key_unpaired"
    assert issues[5] == "no_matching_plan"


def test_parse_amfi_both_layouts():
    navall = (
        "Scheme Code;ISIN Div Payout/ ISIN Growth;ISIN Div Reinvestment;Scheme Name;Plan;Option;Net Asset Value;Date\n"
        " \nOpen Ended Schemes(Equity Scheme - Large Cap Fund)\n \nAxis Mutual Fund\n \n"
        "120465;INF846K01DP8;-;Axis Large Cap Fund;Direct Plan;Growth;60.1;26-Oct-2026\n"
    )
    history = (
        "Scheme Code;NAV Name;Plan;Option;ISIN Div Payout/ISIN Growth;ISIN Div Reinvestment;Net Asset Value;Date\n\n"
        "Open Ended Schemes ( Equity Scheme - Mid Cap Fund )\n\n\nAxis Mutual Fund\n"
        "120505;Axis Midcap Fund - Direct Plan - Growth;Direct Plan;Growth;INF846K01CH7;;40.2;02-Jan-2019\n"
    )
    a, b = parse(navall).iloc[0], parse(history).iloc[0]
    assert (a["scheme_code"], a["category"], a["fund_house"], a["plan"]) == (120465, "Equity Scheme - Large Cap Fund", "Axis Mutual Fund", "Direct Plan")
    assert (b["scheme_code"], b["category"], b["name"]) == (120505, "Equity Scheme - Mid Cap Fund", "Axis Midcap Fund - Direct Plan - Growth")
    assert a["scheme_type"] == b["scheme_type"] == "Open Ended"
