import numpy as np
import pandas as pd

from cot import config, fetch, metrics, store


def make_frame(n=200, code="067651", units="1,000 BARRELS", seed=0, start="2020-01-07"):
    rng = np.random.default_rng(seed)
    dates = pd.date_range(start, periods=n, freq="7D")
    df = pd.DataFrame({"date": dates, "code": code, "name": "WTI-PHYSICAL - NEW YORK MERCANTILE EXCHANGE",
                       "units": units, "market": "WTI"})
    df["oi"] = 1_500_000 + rng.integers(-50_000, 50_000, n)
    df["traders_total"] = 300
    for c in config.COHORT_COLUMNS:
        df[f"{c}_long"] = 100_000 + rng.integers(0, 50_000, n)
        df[f"{c}_short"] = 90_000 + rng.integers(0, 50_000, n)
        df[f"{c}_spread"] = 10_000
    return df


def test_net_and_changes():
    df = metrics.add_metrics(make_frame(30))
    r = df.iloc[10]
    assert r["m_money_net"] == r["m_money_long"] - r["m_money_short"]
    assert df["m_money_net_chg_1w"].iloc[10] == df["m_money_net"].iloc[10] - df["m_money_net"].iloc[9]
    assert df["m_money_net_chg_4w"].iloc[10] == df["m_money_net"].iloc[10] - df["m_money_net"].iloc[6]
    assert np.isnan(df["m_money_net_chg_1w"].iloc[0])


def test_driver_identity():
    df = metrics.add_metrics(make_frame(30))
    r = df.iloc[12]
    assert r["m_money_net_chg_1w"] == r["m_money_long_chg_1w"] - r["m_money_short_chg_1w"]


def test_percentile_has_no_lookahead():
    full = metrics.add_metrics(make_frame(260))
    for cut in (120, 200):
        trunc = metrics.add_metrics(make_frame(260).iloc[:cut])
        a = trunc["m_money_net_pct_1y"].to_numpy()
        b = full["m_money_net_pct_1y"].iloc[:cut].to_numpy()
        assert np.allclose(a, b, equal_nan=True)


def test_percentile_extremes():
    s = pd.Series(np.arange(60, dtype=float))
    p = metrics.rolling_percentile(s, 52)
    assert p.iloc[-1] == 100.0  # new high -> 100th
    s2 = pd.Series(np.arange(60, 0, -1, dtype=float))
    assert metrics.rolling_percentile(s2, 52).iloc[-1] < 3  # new low -> bottom


def test_unit_change_starts_new_segment():
    a = make_frame(80, units="1,000 BARRELS")
    b = make_frame(80, units="500 BARRELS", start=str((a["date"].max() + pd.Timedelta(days=7)).date()), seed=1)
    df = metrics.add_metrics(pd.concat([a, b], ignore_index=True))
    assert df["segment"].nunique() == 2
    first_new = df.index[df["segment"] == 1][0]
    assert np.isnan(df["m_money_net_chg_1w"].iloc[first_new])  # no change across the break
    assert np.isnan(df["m_money_net_pct_1y"].iloc[first_new])


def test_missing_week_is_not_a_one_week_change():
    df = make_frame(20).drop(index=10).reset_index(drop=True)
    out = metrics.add_metrics(df)
    assert np.isnan(out["m_money_net_chg_1w"].iloc[10])  # row after the gap


def test_driver_labels():
    assert metrics.driver(0, -10_000).startswith("short covering")
    assert metrics.driver(10_000, 0).startswith("new longs")
    assert metrics.driver(0, 10_000).startswith("new shorts")
    assert metrics.driver(-10_000, 0).startswith("long liquidation")
    assert metrics.driver(float("nan"), 1) == "n/a"


def test_upsert_replaces_revisions_and_sorts(tmp_path):
    old = make_frame(5)
    new = old.iloc[[3, 4]].copy()
    new["oi"] = 1
    out = store.upsert(old, new)
    assert len(out) == 5
    assert (out.loc[out["date"].isin(new["date"]), "oi"] == 1).all()
    p = tmp_path / "x.csv"
    store.save(out, p)
    back = store.load(p)
    assert len(back) == 5 and back["code"].iloc[0] == "067651"  # leading zeros survive


def test_where_clause_and_url_are_encoded():
    w = fetch.build_where("2024-01-01")
    assert "'067651'" in w and "'06765T'" in w and ">= '2024-01-01'" in w
    assert "'06765A'" in w and ">= '2019-03-26'" in w  # per-contract start floor
    url = fetch.build_url("2024-01-01")
    assert " " not in url and "%24select" in url


def test_rows_to_frame_handles_omitted_null_keys():
    rows = [{"report_date_as_yyyy_mm_dd": "2024-01-02T00:00:00.000", "cftc_contract_market_code": "067651",
             "market_and_exchange_names": "WTI-PHYSICAL - NEW YORK MERCANTILE EXCHANGE", "contract_units": "(CONTRACTS OF 1,000 BBLS)",
             "open_interest_all": "1500000", "m_money_positions_long_all": "200000", "m_money_positions_short_all": "50000"}]
    df = fetch.rows_to_frame(rows)
    assert df.loc[0, "market"] == "WTI" and df.loc[0, "m_money_long"] == 200000
    assert np.isnan(df.loc[0, "swap_long"])


def test_prune_drops_unconfigured_relabels_and_applies_start_floor():
    keep = make_frame(10, code="06765T"); keep["market"] = "WTI_FIN"  # stale label from an old config
    stale = make_frame(10, code="02141R"); stale["name"] = "USGC HSFO-PLATTS/BRENT 1ST LN - ICE FUTURES ENERGY DIV"
    swap_era = make_frame(20, code="06765A", start="2018-12-18")  # before the 2019-03-26 floor
    out = store.prune(pd.concat([keep, stale, swap_era], ignore_index=True))
    assert set(out["code"]) == {"06765T", "06765A"}
    assert (out.loc[out["code"] == "06765T", "market"] == "BRENT").all()
    assert out.loc[out["code"] == "06765A", "date"].min() >= pd.Timestamp("2019-03-26")


def test_driver_names_both_sides_when_both_push():
    assert metrics.driver(710, -3276) == "short covering + new longs"
    assert metrics.driver(-3935, 445) == "long liquidation + new shorts"


def test_percentile_reading_buckets():
    assert metrics.percentile_reading(95) == "Near the top of its range"
    assert metrics.percentile_reading(19) == "Low"
    assert metrics.percentile_reading(50) == "Mid-range"
    assert metrics.percentile_reading(float("nan")) == "Not enough history"


def test_dashboard_builds(tmp_path):
    from cot import report
    parts = []
    for i, (code, mk, nm) in enumerate([("067651", "WTI", "WTI-PHYSICAL - NYMEX"), ("06765T", "BRENT", "BRENT LAST DAY - NYMEX")]):
        f = make_frame(300, code=code, seed=i); f["market"] = mk; f["name"] = nm
        f["traders_mm_long"] = 80; f["traders_mm_short"] = 40
        parts.append(f)
    p = report.build(pd.concat(parts, ignore_index=True), tmp_path)
    page = p.read_text(encoding="utf-8")
    assert "Net change: 1 week" in page and "Percentile vs last 1 year" in page and "What drove last week" in page
    assert "WTI crude (NYMEX physical)" in page
