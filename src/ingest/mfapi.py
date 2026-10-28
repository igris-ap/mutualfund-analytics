"""mfapi.in: the scheme list and per-scheme NAV history with metadata.

/mf returns [{schemeCode, schemeName, isinGrowth, isinDivReinvestment}] (no category).
/mf/{code} returns {meta: {fund_house, scheme_type, scheme_category, scheme_code,
scheme_name, ...}, data: [{date: 'dd-mm-yyyy', nav: '123.45600'}, ...] newest first,
status}. Closed schemes stay listed, with their last NAV and last category.
"""
import json

from src.config import RAW_DIR
from src.ingest.http import get

BASE_URL = "https://api.mfapi.in/mf"
MFAPI_DIR = RAW_DIR / "mfapi"


def fetch_scheme_list(refresh: bool = True) -> list[dict]:
    path = MFAPI_DIR / "scheme_list.json"
    if refresh or not path.exists():
        MFAPI_DIR.mkdir(parents=True, exist_ok=True)
        path.write_bytes(get(BASE_URL).content)
    return json.loads(path.read_text(encoding="utf-8"))


def scheme_path(code: int):
    return MFAPI_DIR / "schemes" / f"{code}.json"


def fetch_scheme(code: int, refresh: bool = False) -> dict:
    """Fetch one scheme's NAV history, caching the raw JSON. Cached files are reused
    unless refresh=True, which makes repeated runs resumable."""
    path = scheme_path(code)
    if refresh or not path.exists():
        payload = get(f"{BASE_URL}/{code}").json()
        if payload.get("status") != "SUCCESS" or "meta" not in payload:
            raise ValueError(f"mfapi returned no data for scheme {code}")
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload), encoding="utf-8")
        tmp.replace(path)  # atomic, so an interrupted run never leaves a half-written file
    return json.loads(path.read_text(encoding="utf-8"))
