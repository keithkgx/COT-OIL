"""Build a single static HTML dashboard (docs/index.html) for GitHub Pages."""
from __future__ import annotations

import html
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from . import config, metrics

COLORS = {"m_money": "#d9480f", "prod_merc": "#1c7ed6", "swap": "#2f9e44", "other_rept": "#862e9c", "nonrept": "#868e96"}
LOOKBACK_YEARS_SHOWN = 5


def _pct_color(p: float) -> str:
    if p != p:
        return "#eee"
    # blue (low) -> white -> red (high)
    if p >= 50:
        a = (p - 50) / 50
        return f"rgba(217,72,15,{0.15 + 0.6 * a:.2f})"
    a = (50 - p) / 50
    return f"rgba(28,126,214,{0.15 + 0.6 * a:.2f})"


def _fmt(x: float, signed=False) -> str:
    if x != x:
        return "n/a"
    return f"{x:+,.0f}" if signed else f"{x:,.0f}"


def contract_figure(g: pd.DataFrame, title: str) -> go.Figure:
    g = g.sort_values("date")
    fig = make_subplots(
        rows=4, cols=1, shared_xaxes=True, vertical_spacing=0.05,
        row_heights=[0.3, 0.25, 0.2, 0.25],
        subplot_titles=("Managed Money net position (contracts)", "Net position by trader group",
                        "Open interest and Managed Money net as % of OI", "Weekly Managed Money net change: where it came from"),
        specs=[[{}], [{}], [{"secondary_y": True}], [{}]],
    )
    fig.add_trace(go.Scatter(x=g["date"], y=g["m_money_net"], name="MM net", line=dict(color=COLORS["m_money"], width=2)), 1, 1)
    fig.add_hline(y=0, line_width=1, line_color="#999", row=1, col=1)
    for c in metrics.COHORTS:
        fig.add_trace(go.Scatter(x=g["date"], y=g[f"{c}_net"], name=config.COHORT_LABELS[c],
                                 line=dict(color=COLORS[c], width=1.5), legendgroup=c), 2, 1)
    fig.add_trace(go.Scatter(x=g["date"], y=g["oi"], name="Open interest", line=dict(color="#495057")), 3, 1, secondary_y=False)
    fig.add_trace(go.Scatter(x=g["date"], y=g["mm_net_pct_oi"], name="MM net % OI", line=dict(color=COLORS["m_money"], dash="dot")), 3, 1, secondary_y=True)
    fig.add_trace(go.Bar(x=g["date"], y=g["m_money_long_chg_1w"], name="Δ longs", marker_color="#2f9e44"), 4, 1)
    fig.add_trace(go.Bar(x=g["date"], y=-g["m_money_short_chg_1w"], name="Δ shorts (sign flipped: covering = +)", marker_color="#e03131"), 4, 1)
    fig.update_layout(barmode="relative", height=900, template="plotly_white", title=title,
                      margin=dict(l=60, r=60, t=90, b=40), legend=dict(orientation="h", y=-0.05))
    end = g["date"].max()
    start = end - pd.DateOffset(years=LOOKBACK_YEARS_SHOWN)
    fig.update_xaxes(range=[start, end], rangeslider_visible=False)
    fig.update_xaxes(rangeselector=dict(buttons=[
        dict(count=1, label="1y", step="year", stepmode="backward"),
        dict(count=3, label="3y", step="year", stepmode="backward"),
        dict(count=5, label="5y", step="year", stepmode="backward"),
        dict(step="all", label="All")]), row=1, col=1)
    return fig


def heat_table(latest: pd.DataFrame) -> str:
    cols = ["m_money", "prod_merc", "swap", "other_rept"]
    head = "<tr><th rowspan=2>Contract</th><th rowspan=2>Report date</th><th rowspan=2>MM net</th><th rowspan=2>Δ 1w</th><th rowspan=2>Δ 4w</th><th rowspan=2>OI</th>" + \
        "".join(f"<th colspan=2>{html.escape(config.COHORT_LABELS[c])} net pctile</th>" for c in cols) + "</tr>" + \
        "<tr>" + "".join("<th>1y</th><th>3y</th>" for _ in cols) + "</tr>"
    body = []
    for _, r in latest.iterrows():
        cells = "".join(
            f"<td style='background:{_pct_color(r[f'{c}_net_pct_1y'])}'>{_fmt(r[f'{c}_net_pct_1y'])}</td>"
            f"<td style='background:{_pct_color(r[f'{c}_net_pct_3y'])}'>{_fmt(r[f'{c}_net_pct_3y'])}</td>" for c in cols)
        body.append(f"<tr><td class=l>{html.escape(r['label'])}</td><td>{r['date']:%Y-%m-%d}</td><td>{_fmt(r['m_money_net'])}</td>"
                    f"<td>{_fmt(r['m_money_net_chg_1w'], True)}</td><td>{_fmt(r['m_money_net_chg_4w'], True)}</td><td>{_fmt(r['oi'])}</td>{cells}</tr>")
    return f"<table>{head}{''.join(body)}</table>"


PAGE = """<!doctype html><html lang=en><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>Oil COT positioning monitor</title>
<style>
body{{font:15px/1.5 system-ui,sans-serif;max-width:1150px;margin:0 auto;padding:16px;color:#212529}}
h1{{margin:.2em 0}} h2{{margin-top:1.6em;border-bottom:1px solid #ddd;padding-bottom:4px}}
table{{border-collapse:collapse;font-size:13px;display:block;overflow-x:auto}} th,td{{border:1px solid #ddd;padding:4px 8px;text-align:right}}
td.l{{text-align:left;font-weight:600}} th{{background:#f1f3f5}} .note{{background:#fff9db;padding:10px 14px;border-radius:6px;font-size:13px}}
li{{margin:.4em 0}} nav a{{margin-right:12px}} .meta{{color:#666;font-size:13px}}
</style></head><body>
<h1>Oil COT positioning monitor</h1>
<p class=meta>CFTC Disaggregated Commitments of Traders, futures only. Latest report date: <b>{latest}</b> (positions as of Tuesday, published Friday ~15:30 ET). Page built {built} UTC.
Data: <a href="cot_oil.csv">cot_oil.csv</a> · <a href="metrics.csv">metrics.csv</a></p>
<h2>This week</h2><ul>{summaries}</ul>
<h2>Positioning snapshot</h2>
<p class=meta>Percentile = where today's net position ranks within the trailing 1-year / 3-year window (0 = most short, 100 = most long), no look-ahead. Red = crowded long, blue = crowded short.</p>
{table}
<div class=note><b>Reading notes.</b> Managed Money is the CFTC's speculative-fund category. A cohort's net is a sum over firms with different strategies, so it is not a pure directional view.
Positioning is shown beside, not as a predictor of, price. Changes are in contracts, not percent, because net positions can change sign.
Percentiles restart when a contract's units change or after a gap of more than a quarter. Not investment advice.</div>
<nav>{nav}</nav>
{charts}
<p class=meta>Source: U.S. Commodity Futures Trading Commission, public reporting environment. This page is auto-generated by GitHub Actions.</p>
</body></html>"""


def build(df: pd.DataFrame, out_dir: Path = Path("docs")) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    m = metrics.add_metrics(df)
    labels = m.sort_values("date").groupby("code")["name"].last().to_dict()
    m["label"] = m["code"].map(labels)
    # Tidy exports
    m.to_csv(out_dir / "metrics.csv", index=False, date_format="%Y-%m-%d")
    df.to_csv(out_dir / "cot_oil.csv", index=False, date_format="%Y-%m-%d")

    latest = m.sort_values("date").groupby("code").tail(1)
    order = {mk.key: i for i, mk in enumerate(config.MARKETS)}
    latest = latest.assign(_o=latest["market"].map(order)).sort_values(["_o", "label"]).drop(columns="_o")
    # Only show contracts that reported recently (hide delisted ones from the snapshot)
    cutoff = m["date"].max() - pd.Timedelta(days=21)
    latest = latest[latest["date"] >= cutoff]

    summaries = "".join(f"<li>{html.escape(metrics.summary_sentence(r['label'], r))}</li>" for _, r in latest.iterrows())
    nav, charts, first = [], [], True
    for _, r in latest.iterrows():
        g = m[m["code"] == r["code"]]
        fig = contract_figure(g, r["label"])
        nav.append(f"<a href='#c{r['code']}'>{html.escape(r['market'])}: {html.escape(r['label'][:40])}</a>")
        charts.append(f"<h2 id='c{r['code']}'>{html.escape(r['label'])}</h2>" + fig.to_html(full_html=False, include_plotlyjs="cdn" if first else False))
        first = False

    page = PAGE.format(latest=f"{m['date'].max():%Y-%m-%d}", built=pd.Timestamp.utcnow().strftime("%Y-%m-%d %H:%M"),
                       summaries=summaries, table=heat_table(latest), nav=" ".join(nav), charts="".join(charts))
    p = out_dir / "index.html"
    p.write_text(page, encoding="utf-8")
    (out_dir / ".nojekyll").write_text("")
    return p
