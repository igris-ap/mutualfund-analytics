"""Polite HTTP: one shared session, a minimum gap between requests, retries with backoff."""
import logging
import time

import requests
import truststore

truststore.inject_into_ssl()

log = logging.getLogger(__name__)

MIN_INTERVAL = 0.3  # seconds between requests
_session = requests.Session()
_session.headers["User-Agent"] = "mf-analytics (portfolio research project)"
_last = 0.0


def get(url: str, timeout: int = 60, retries: int = 4) -> requests.Response:
    global _last
    for attempt in range(retries):
        wait = MIN_INTERVAL - (time.monotonic() - _last)
        if wait > 0:
            time.sleep(wait)
        _last = time.monotonic()
        try:
            resp = _session.get(url, timeout=timeout)
            if resp.status_code == 200:
                return resp
            if resp.status_code not in (429, 500, 502, 503, 504):
                resp.raise_for_status()
            log.warning("GET %s -> %s", url, resp.status_code)
        except (requests.ConnectionError, requests.Timeout) as exc:
            log.warning("GET %s failed: %s", url, exc)
        time.sleep(2 ** attempt * 2)
    raise RuntimeError(f"GET {url} failed after {retries} attempts")
