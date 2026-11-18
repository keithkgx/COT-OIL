"""Derived measures. Deliberately plain and individually testable.

Conventions (borrowed from the offchart project, where each was a real bug first):

1. NO LOOK-AHEAD. A percentile at week t ranks the value against the trailing
   window ending at t, never against data that did not exist yet.
2. SIGNED QUANTITIES ARE NEVER PERCENT-CHANGED. Net positions change sign, so
   changes are reported in contracts ("+3,913 contracts, less short").
3. HISTORY IS SEGMENTED. A change in contract units, or a gap of more than a
   quarter, starts a new segment; percentiles and changes never straddle one.
4. WEEKLY CHANGES ARE DATE-CHECKED. A "1-week" change across a missing week is NaN
   rather than silently a 2-week change.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import config

COHORTS = list(config.COHORT_COLUMNS)
WINDOWS = {"1y": 52, "3y": 156}


def rolling_percentile(s: pd.Series, window: int, min_periods: int | None = None) -> pd.Series:
    """Percent (0-100) of the trailing `window` observations (including today) that are <= today."""
    mp = min_periods if min_periods is not None else max(window // 2, 8)
    return s.rolling(window, min_periods=mp).apply(lambda w: float((w <= w[-1]).mean() * 100), raw=True)


def add_segments(g: pd.DataFrame) -> pd.Series:
    gap = g["date"].diff().dt.days > 91
    prev_units = g["units"].shift()
    unit_change = prev_units.notna() & (g["units"] != prev_units)
    return (gap | unit_change).cumsum()


def _shift_ok(g: pd.DataFrame, weeks: int) -> pd.Series:
    """True where the row `weeks` earlier is genuinely ~`weeks` weeks before."""
    d = (g["date"] - g["date"].shift(weeks)).dt.days
    return d.between(7 * weeks - 3, 7 * weeks + 3)


def _add_one(g: pd.DataFrame) -> pd.DataFrame:
    g = g.sort_values("date").copy()
    g["segment"] = add_segments(g)
    seg = g["segment"]

    for c in COHORTS:
        g[f"{c}_net"] = g[f"{c}_long"] - g[f"{c}_short"]
        g[f"{c}_gross"] = g[f"{c}_long"] + g[f"{c}_short"]
    g["mm_net_pct_oi"] = g["m_money_net"] / g["oi"] * 100  # a ratio of a non-negative base; fine to express as %

    ok1, ok4 = _shift_ok(g, 1), _shift_ok(g, 4)
    in1 = seg == seg.shift(1)
    in4 = seg == seg.shift(4)

    def chg(col: str, weeks: int) -> pd.Series:
        ok = (ok1 & in1) if weeks == 1 else (ok4 & in4)
        return (g[col] - g[col].shift(weeks)).where(ok)

    for c in COHORTS:
        for col in (f"{c}_net", f"{c}_long", f"{c}_short"):
            g[f"{col}_chg_1w"] = chg(col, 1)
            g[f"{col}_chg_4w"] = chg(col, 4)  # ~ monthly
    g["oi_chg_1w"] = chg("oi", 1)
    g["oi_chg_4w"] = chg("oi", 4)

    # Percentiles within segment (no look-ahead: trailing window only).
    for c in COHORTS:
        for label, w in WINDOWS.items():
            g[f"{c}_net_pct_{label}"] = g.groupby("segment")[f"{c}_net"].transform(lambda s, w=w: rolling_percentile(s, w))
    for label, w in WINDOWS.items():
        g[f"mm_net_pct_oi_pct_{label}"] = g.groupby("segment")["mm_net_pct_oi"].transform(lambda s, w=w: rolling_percentile(s, w))
    return g


def add_metrics(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    parts = [_add_one(g) for _, g in df.sort_values(["code", "date"]).groupby("code", sort=False)]
    return pd.concat(parts, ignore_index=True)


def driver(d_long: float, d_short: float) -> str:
    """Explain a weekly net change as new longs / long liquidation / new shorts / short covering.

    Net change = d_long - d_short. Long contribution = d_long; short contribution = -d_short.
    """
    if d_long is None or d_short is None or np.isnan(d_long) or np.isnan(d_short):
        return "n/a"
    long_c, short_c = d_long, -d_short
    net = long_c + short_c
    if net == 0:
        return "no net change"
    if net > 0:
        main = "new longs" if long_c >= short_c else "short covering"
        both = long_c > 0 and short_c > 0
    else:
        main = "new shorts" if short_c <= long_c else "long liquidation"
        both = long_c < 0 and short_c < 0
    detail = f"longs {d_long:+,.0f}, shorts {d_short:+,.0f}"
    return f"{main}{' + ' + _second(long_c, short_c, net) if both else ''} ({detail})"


def _second(long_c: float, short_c: float, net: float) -> str:
    if net > 0:
        return "short covering" if long_c >= short_c else "new longs"
    return "long liquidation" if short_c <= long_c else "new shorts"


def _ord(x: float) -> str:
    if x != x:
        return "n/a"
    n = int(round(x))
    suf = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suf}"


def summary_sentence(label: str, row: pd.Series) -> str:
    net = row["m_money_net"]
    side = "net long" if net >= 0 else "net short"
    return (
        f"{label}: Managed Money {side} {abs(net):,.0f} contracts "
        f"({row['m_money_net_chg_1w']:+,.0f} w/w, {row['m_money_net_chg_4w']:+,.0f} over 4 weeks), "
        f"{_ord(row['m_money_net_pct_1y'])} percentile of the last year, {_ord(row['m_money_net_pct_3y'])} of three years. "
        f"Weekly move: {driver(row['m_money_long_chg_1w'], row['m_money_short_chg_1w'])}. "
        f"Open interest {row['oi']:,.0f} ({row['oi_chg_1w']:+,.0f} w/w)."
    )
