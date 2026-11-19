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
    name_like: tuple[str, ...] = ()  # upper-case substrings of market_and_exchange_names (avoid: too broad)
    start: str | None = None  # ignore rows before this date (the CFTC re-used the code for a different product)
    barrels: int = 1000  # barrels (or barrel-equivalents) per contract
    size_text: str = "1 contract = 1,000 barrels"
    note: str = ""  # shown on the dashboard when the contract needs a caveat

    def matches(self, code: str, name: str) -> bool:
        return code in self.codes or any(s in name.upper() for s in self.name_like)


# Verified against the live API with scripts/discover.py (2026-11-18). The CFTC keeps one
# code per contract through renames (e.g. 067651 was "CRUDE OIL, LIGHT SWEET" until 2022-02,
# then "WTI-PHYSICAL"), so we key on codes, never names.
GALLON_SIZE = "1 contract = 42,000 US gallons = 1,000 barrels"
MARKETS: tuple[Market, ...] = (
    Market("WTI", "WTI crude (NYMEX physical)", codes=("067651",)),
    Market("WTI_ICE", "WTI crude (ICE Futures Europe)", codes=("067411",)),
    Market("BRENT", "Brent crude last day (NYMEX)", codes=("06765T",),
           note="Small contract. This is the NYMEX look-alike of Brent, not ICE Brent (the main Brent benchmark), "
                "which is not in the CFTC report. Treat it as a sample of Brent positioning, not the whole market."),
    Market("ULSD", "NY Harbor ULSD (diesel)", codes=("022651",), size_text=GALLON_SIZE,
           note="Before late 2013 the same CFTC code covers NY Harbor heating oil."),
    Market("RBOB", "RBOB gasoline", codes=("111659",), size_text=GALLON_SIZE),
)

# Dropped: 06765A "WTI financial crude" reports zero Managed Money positions (all funds sit in other
# groups), so every Managed Money statistic for it is meaningless. A `start` date was also needed
# because the CFTC re-used that code for a calendar swap before 2019-03-26.
# Optional watchlist (active contracts you could add later):
#   0676A5  WTI Houston Argus/WTI trade month (basis)   067A71  WTI Midland Argus vs WTI (basis)
#   06742T/06742G/06739C  Canadian crude differentials (ICE)   02141R  USGC HSFO Platts/Brent (fuel oil)
#   111A34  Gulf Coast CBOB vs RBOB (spread)   06665R  Mt Belvieu natural gasoline (NGL)


def market_for(code: str, name: str) -> str | None:
    for m in MARKETS:
        if m.matches(code, name):
            return m.key
    return None
