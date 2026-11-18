"""Configuration: which CFTC dataset, which columns, which oil contracts.

Column names were taken from the IngTian/offchart project, which verified them
against live CFTC payloads. The API misspells some of its own columns
("swap__positions_short_all" has TWO underscores, the spread column for managed
money has no "_all" suffix, etc.), so do not "tidy" them.
"""
from __future__ import annotations

from dataclasses import dataclass

# Disaggregated COT, futures-only (CFTC Public Reporting Environment, Socrata).
DATASET = "72hh-3qpy"
BASE_URL = f"https://publicreporting.cftc.gov/resource/{DATASET}.json"
USER_AGENT = "cot-oil-monitor (research; low volume)"

# CFTC revises already-published weeks, so every update re-pulls an overlap window.
INCREMENTAL_OVERLAP_DAYS = 56
FIRST_DATE = "2006-06-01"  # disaggregated report history starts 2006-06-13

# Meta columns: API name -> our name
META = {
    "report_date_as_yyyy_mm_dd": "date",
    "cftc_contract_market_code": "code",
    "market_and_exchange_names": "name",
    "contract_units": "units",
    "open_interest_all": "oi",
    "traders_tot_all": "traders_total",
    "traders_m_money_long_all": "traders_mm_long",
    "traders_m_money_short_all": "traders_mm_short",
}

TEXT_COLUMNS = ("date", "code", "name", "units")

# Cohort -> API column names (long / short / spread). None = not published.
COHORT_COLUMNS = {
    "prod_merc": dict(long="prod_merc_positions_long", short="prod_merc_positions_short", spread=None),
    "swap": dict(long="swap_positions_long_all", short="swap__positions_short_all", spread="swap__positions_spread_all"),
    "m_money": dict(long="m_money_positions_long_all", short="m_money_positions_short_all", spread="m_money_positions_spread"),
    "other_rept": dict(long="other_rept_positions_long", short="other_rept_positions_short", spread="other_rept_positions_spread"),
    "nonrept": dict(long="nonrept_positions_long_all", short="nonrept_positions_short_all", spread=None),
}

COHORT_LABELS = {
    "m_money": "Managed Money",
    "prod_merc": "Producers/Merchants",
    "swap": "Swap Dealers",
    "other_rept": "Other Reportables",
    "nonrept": "Non-reportable (small)",
}


def api_to_internal() -> dict[str, str]:
    """Rename map for every API column we select."""
    m = dict(META)
    for c, cols in COHORT_COLUMNS.items():
        for side, api in cols.items():
            if api:
                m[api] = f"{c}_{side}"
    return m


@dataclass(frozen=True)
class Market:
    key: str
    label: str
    codes: tuple[str, ...] = ()
    name_like: tuple[str, ...] = ()  # upper-case substrings of market_and_exchange_names

    def matches(self, code: str, name: str) -> bool:
        return code in self.codes or any(s in name.upper() for s in self.name_like)


# !! VERIFY with `python scripts/discover.py` on first run. Codes below are from
# memory (not checked against the live API); Brent is matched by name because
# several Brent contracts exist.
MARKETS: tuple[Market, ...] = (
    Market("WTI", "WTI crude (NYMEX physical)", codes=("067651",)),
    Market("WTI_FIN", "WTI financial crude", codes=("06765T",)),
    Market("BRENT", "Brent crude", name_like=("BRENT",)),
    Market("ULSD", "NY Harbor ULSD (diesel)", codes=("022651",)),
    Market("RBOB", "RBOB gasoline", codes=("111659",)),
)


def market_for(code: str, name: str) -> str | None:
    for m in MARKETS:
        if m.matches(code, name):
            return m.key
    return None
