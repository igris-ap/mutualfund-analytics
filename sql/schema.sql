-- Base tables. Loading truncates and refills them, so this file is safe to rerun.

CREATE TABLE IF NOT EXISTS schemes (
    scheme_code      INTEGER PRIMARY KEY,
    scheme_name      TEXT    NOT NULL,
    fund_house       TEXT    NOT NULL,
    category         TEXT    NOT NULL,  -- Large Cap | Flexi Cap | Mid Cap | Index Fund
    plan_type        TEXT    NOT NULL CHECK (plan_type IN ('direct', 'regular')),
    option_type      TEXT    NOT NULL CHECK (option_type IN ('growth', 'idcw')),
    base_scheme_key  TEXT    NOT NULL,  -- shared by the direct and regular plan of one fund
    is_benchmark     BOOLEAN NOT NULL DEFAULT FALSE,
    first_nav_date   DATE,
    last_nav_date    DATE
);
CREATE INDEX IF NOT EXISTS schemes_base_key_idx ON schemes (base_scheme_key);

CREATE TABLE IF NOT EXISTS nav_daily (
    scheme_code INTEGER       NOT NULL REFERENCES schemes (scheme_code),
    nav_date    DATE          NOT NULL,
    nav         NUMERIC(18,6) NOT NULL CHECK (nav > 0),
    PRIMARY KEY (scheme_code, nav_date)
);

CREATE TABLE IF NOT EXISTS benchmarks (
    category    TEXT    PRIMARY KEY,
    scheme_code INTEGER NOT NULL REFERENCES schemes (scheme_code),
    index_name  TEXT    NOT NULL
);

-- Data-quality log: nothing is dropped or kept silently.
--   jump_gt_threshold: single-day move above jump_threshold (kept in the data)
--   nonpositive_nav:   zero or negative NAV (dropped)
--   duplicate_date:    repeated date with a different NAV (first value kept)
CREATE TABLE IF NOT EXISTS nav_flags (
    scheme_code INTEGER NOT NULL,
    nav_date    DATE    NOT NULL,
    flag_type   TEXT    NOT NULL,
    nav         NUMERIC,
    prev_nav    NUMERIC,
    pct_change  DOUBLE PRECISION
);

-- Schemes left out of the analysis, and plans that could not be paired.
CREATE TABLE IF NOT EXISTS scheme_log (
    scheme_code     INTEGER NOT NULL,
    scheme_name     TEXT,
    base_scheme_key TEXT,
    plan_type       TEXT,
    issue           TEXT    NOT NULL
);

-- Analysis parameters from config/settings.yaml, read by the metric views.
CREATE TABLE IF NOT EXISTS params (
    key   TEXT PRIMARY KEY,
    value DOUBLE PRECISION NOT NULL
);
