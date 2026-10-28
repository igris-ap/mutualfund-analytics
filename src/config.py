"""Project paths and settings. Settings come from config/settings.yaml, with env overrides."""
import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
SQL_DIR = ROOT / "sql"

load_dotenv(ROOT / ".env")

CATEGORIES = ("Large Cap", "Flexi Cap", "Mid Cap")


def settings() -> dict:
    with open(CONFIG_DIR / "settings.yaml", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    for key, value in cfg.items():
        env = os.getenv(key.upper())
        if env is not None:
            cfg[key] = type(value)(env)
    return cfg


def benchmarks() -> dict:
    with open(CONFIG_DIR / "benchmarks.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)
