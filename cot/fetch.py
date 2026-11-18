"""Socrata client for publicreporting.cftc.gov (no API key needed)."""
from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request

import pandas as pd

from . import config

NUMERIC = [v for v in config.api_to_internal().values() if v not in config.TEXT_COLUMNS]


def _esc(s: str) -> str:
    return s.replace("'", "''")


def build_where(since: str | None) -> str:
    clauses = []
    for m in config.MARKETS:
        if m.codes:
            c = "cftc_contract_market_code in (" + ",".join(f"'{_esc(x)}'" for x in m.codes) + ")"
            if m.start:
                c = f"({c} AND report_date_as_yyyy_mm_dd >= '{_esc(m.start)}')"
            clauses.append(c)
        for s in m.name_like:
            clauses.append(f"upper(market_and_exchange_names) like '%{_esc(s)}%'")
    where = "(" + " OR ".join(clauses) + ")"
    if since:
        where += f" AND report_date_as_yyyy_mm_dd >= '{_esc(since)}'"
    return where


def build_url(since: str | None, limit: int = 100_000) -> str:
    # $select projects to known columns: if CFTC renames one, Socrata answers HTTP 400
    # naming it -> the job fails loudly instead of silently producing nulls.
    q = {
        "$select": ",".join(config.api_to_internal().keys()),
        "$where": build_where(since),
        "$order": "report_date_as_yyyy_mm_dd",
        "$limit": str(limit),
    }
    # urlencode (never f-strings): spaces and '%' must be percent-encoded.
    return config.BASE_URL + "?" + urllib.parse.urlencode(q)


def get_json(url: str, retries: int = 3):
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": config.USER_AGENT})
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.load(r)
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(2 * (i + 1))
    raise RuntimeError(f"CFTC request failed after {retries} tries: {last}")


def rows_to_frame(rows: list[dict]) -> pd.DataFrame:
    """Socrata omits keys whose value is null, so an absent key means NaN, not schema drift."""
    df = pd.DataFrame(rows).rename(columns=config.api_to_internal())
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["date"]).dt.normalize()
    for c in NUMERIC:
        df[c] = pd.to_numeric(df[c], errors="coerce") if c in df else float("nan")
    df["code"] = df["code"].astype(str).str.strip()
    df["name"] = df["name"].astype(str).str.strip()
    df["units"] = df["units"].astype(str).str.strip()
    df["market"] = [config.market_for(c, n) for c, n in zip(df["code"], df["name"])]
    return df[df["market"].notna()].reset_index(drop=True)


def fetch(since: str | None = None) -> pd.DataFrame:
    limit = 100_000
    rows = get_json(build_url(since, limit))
    if len(rows) >= limit:
        raise RuntimeError("Hit $limit; result may be truncated")
    return rows_to_frame(rows)
