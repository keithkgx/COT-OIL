"""Historical database: one tidy CSV, keyed on (code, date).

CSV rather than SQLite so weekly commits are readable text diffs, the file opens
in Excel, and the repo holds no binary blobs. A handful of contracts x ~1,000
weeks is tiny.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

PATH = Path("data/cot_oil.csv")


def load(path: Path = PATH) -> pd.DataFrame:
    if not Path(path).exists():
        return pd.DataFrame()
    return pd.read_csv(path, dtype={"code": str}, parse_dates=["date"])


def upsert(existing: pd.DataFrame, new: pd.DataFrame) -> pd.DataFrame:
    """New rows replace existing rows with the same (code, date): CFTC revises weeks."""
    if existing.empty:
        out = new.copy()
    elif new.empty:
        out = existing.copy()
    else:
        out = pd.concat([existing, new], ignore_index=True)
        out = out.drop_duplicates(subset=["code", "date"], keep="last")
    return out.sort_values(["code", "date"]).reset_index(drop=True)


def save(df: pd.DataFrame, path: Path = PATH) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, date_format="%Y-%m-%d")


def latest_date(df: pd.DataFrame):
    return None if df.empty else df["date"].max()
