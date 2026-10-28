"""AMFI NAV files: the current NAVAll.txt and the NAV history report.

Both are semicolon-delimited text with section headers such as
'Open Ended Schemes ( Equity Scheme - Large Cap Fund )' followed by a fund house
line, then one row per scheme. AMFI labels every scheme with its *current* (or
last) category, even in old history files, so a history snapshot from 2019 lists
schemes that have since merged or closed, under post-2018 category names.
"""
import logging
import re
from datetime import date

import pandas as pd

from src.config import RAW_DIR
from src.ingest.http import get

log = logging.getLogger(__name__)

NAVALL_URL = "https://www.amfiindia.com/spages/NAVAll.txt"
HISTORY_URL = "https://portal.amfiindia.com/DownloadNAVHistoryReport_Po.aspx?frmdt={frm}&todt={to}"
AMFI_DIR = RAW_DIR / "amfi"

_SECTION_RE = re.compile(r"^(Open Ended|Close Ended|Interval Fund)\s+Schemes?\s*\(\s*(.*?)\s*\)\s*$", re.I)
_COLUMNS = {
    "scheme code": "scheme_code",
    "scheme name": "name",
    "nav name": "name",
    "plan": "plan",
    "option": "option",
    "net asset value": "nav",
    "date": "date",
}


def parse(text: str) -> pd.DataFrame:
    """Parse an AMFI NAV file into rows with their section's scheme type, category and fund house.
    Columns are mapped from the header line because the layout differs across files and years."""
    lines = text.splitlines()
    header = [h.strip().lower() for h in lines[0].split(";")]
    idx = {_COLUMNS[h]: i for i, h in enumerate(header) if h in _COLUMNS}
    scheme_type = category = fund_house = None
    rows = []
    for line in lines[1:]:
        line = line.strip()
        if not line:
            continue
        m = _SECTION_RE.match(line)
        if m:
            scheme_type, category = m.group(1), m.group(2)
            continue
        parts = line.split(";")
        if len(parts) < len(header) or not parts[0].strip().isdigit():
            fund_house = line
            continue
        rec = {k: parts[i].strip() for k, i in idx.items()}
        rec.update(scheme_type=scheme_type, category=category, fund_house=fund_house)
        rows.append(rec)
    df = pd.DataFrame(rows)
    df["scheme_code"] = df["scheme_code"].astype(int)
    return df


def fetch_navall(refresh: bool = True) -> pd.DataFrame:
    path = AMFI_DIR / "NAVAll.txt"
    if refresh or not path.exists():
        AMFI_DIR.mkdir(parents=True, exist_ok=True)
        path.write_bytes(get(NAVALL_URL).content)
    return parse(path.read_text(encoding="utf-8", errors="replace"))


def fetch_history_snapshot(start: date, days: int = 5) -> pd.DataFrame:
    """NAV history for a short window starting at `start` (several days so holidays don't
    leave it empty). Cached, since past windows never change."""
    end = start + pd.Timedelta(days=days - 1)
    path = AMFI_DIR / f"history_{start:%Y%m%d}.txt"
    if not path.exists():
        AMFI_DIR.mkdir(parents=True, exist_ok=True)
        url = HISTORY_URL.format(frm=f"{start:%d-%b-%Y}", to=f"{end:%d-%b-%Y}")
        path.write_bytes(get(url, timeout=180).content)
    text = path.read_text(encoding="utf-8", errors="replace")
    if not text.lower().startswith("scheme code"):
        log.warning("AMFI history %s: unexpected response, skipping", path.name)
        return pd.DataFrame()
    return parse(text)
