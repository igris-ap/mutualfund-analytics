"""NAV cleaning: parse, sort, de-duplicate, drop non-positive values, flag large jumps.

The output keeps only real observations. Forward-filling to a common calendar happens
later, in the nav_filled view, and only feeds the return calculations.
"""
import pandas as pd

FLAG_COLUMNS = ["scheme_code", "nav_date", "flag_type", "nav", "prev_nav", "pct_change"]


def clean_nav(code: int, records: list[dict], start_date: str, jump_threshold: float):
    """records: mfapi 'data' list [{date: 'dd-mm-yyyy', nav: '12.3'}]. Returns (nav, flags)."""
    df = pd.DataFrame(records)
    if df.empty:
        return pd.DataFrame(columns=["scheme_code", "nav_date", "nav"]), pd.DataFrame(columns=FLAG_COLUMNS)
    df["nav_date"] = pd.to_datetime(df["date"], format="%d-%m-%Y", errors="coerce")
    df["nav"] = pd.to_numeric(df["nav"], errors="coerce")
    df = df.dropna(subset=["nav_date", "nav"])
    df = df[df["nav_date"] >= pd.Timestamp(start_date)]
    flags = []

    bad = df[df["nav"] <= 0]
    flags += [(code, r.nav_date, "nonpositive_nav", r.nav, None, None) for r in bad.itertuples()]
    df = df[df["nav"] > 0]

    # mfapi lists newest first; keep the first value seen for a repeated date.
    df = df.sort_values("nav_date", kind="stable")
    dup = df[df.duplicated("nav_date", keep="first")]
    first = df.drop_duplicates("nav_date", keep="first").set_index("nav_date")["nav"]
    flags += [(code, r.nav_date, "duplicate_date", r.nav, first[r.nav_date], None)
              for r in dup.itertuples() if r.nav != first[r.nav_date]]
    df = df.drop_duplicates("nav_date", keep="first").reset_index(drop=True)

    pct = df["nav"].pct_change()
    prev = df["nav"].shift()
    for i in df.index[pct.abs() > jump_threshold]:
        flags.append((code, df.at[i, "nav_date"], "jump_gt_threshold", df.at[i, "nav"], prev[i], pct[i]))

    df["scheme_code"] = code
    out_flags = pd.DataFrame(flags, columns=FLAG_COLUMNS)
    return df[["scheme_code", "nav_date", "nav"]], out_flags
