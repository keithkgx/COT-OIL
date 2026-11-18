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
OTHER_GROUPS = ["prod_merc", "swap", "other_rept", "nonrept"]
GROUP_NOTES = {
    "m_money": "speculative funds: CTAs, commodity pools, registered and unregistered funds",
    "prod_merc": "commercial hedgers: producers, merchants, processors and users of the physical commodity",
    "swap": "swap dealers: mostly banks hedging OTC swap books with clients",
    "other_rept": "other large traders not in the groups above",
    "nonrept": "small traders below the reporting threshold (derived: total open interest minus reportable positions)",
}


# ----------------------------------------------------------------------------- helpers
def fmt(x: float, signed: bool = False) -> str:
    if x is None or x != x:
        return "n/a"
    return f"{x:+,.0f}" if signed else f"{x:,.0f}"


def delta_cell(x: float) -> str:
    """Signed number with an arrow and colour class."""
    if x is None or x != x:
        return "<td class='na'>n/a</td>"
    cls = "up" if x > 0 else "dn" if x < 0 else ""
    arrow = "&#9650; " if x > 0 else "&#9660; " if x < 0 else ""
    return f"<td class='{cls}'>{arrow}{x:+,.0f}</td>"


def pct_cell(p: float) -> str:
    if p is None or p != p:
        return "<td class='na'>n/a</td>"
    if p >= 50:
        bg = f"rgba(217,72,15,{0.12 + 0.6 * (p - 50) / 50:.2f})"
    else:
        bg = f"rgba(28,126,214,{0.12 + 0.6 * (50 - p) / 50:.2f})"
    return f"<td style='background:{bg}'>{p:.0f}</td>"


def position_word(net: float) -> str:
    return "net long" if net >= 0 else "net short"


def esc(s) -> str:
    return html.escape(str(s))


# ----------------------------------------------------------------------------- charts
def contract_figure(g: pd.DataFrame, title: str) -> go.Figure:
    g = g.sort_values("date")
    fig = make_subplots(
        rows=2, cols=2, vertical_spacing=0.13, horizontal_spacing=0.06,
        subplot_titles=("Managed Money net position (contracts)", "Net position by trader group (contracts)",
                        "Open interest (left) and Managed Money net as % of OI (right)",
                        "Weekly change in Managed Money net: longs added vs shorts added"),
        specs=[[{}, {}], [{"secondary_y": True}, {}]],
    )
    fig.add_trace(go.Scatter(x=g["date"], y=g["m_money_net"], name="Managed Money net", line=dict(color=COLORS["m_money"], width=2)), 1, 1)
    fig.add_hline(y=0, line_width=1, line_color="#999", row=1, col=1)
    for c in metrics.COHORTS:
        fig.add_trace(go.Scatter(x=g["date"], y=g[f"{c}_net"], name=config.COHORT_LABELS[c],
                                 line=dict(color=COLORS[c], width=1.5), legendgroup=c), 1, 2)
    fig.add_hline(y=0, line_width=1, line_color="#999", row=1, col=2)
    fig.add_trace(go.Scatter(x=g["date"], y=g["oi"], name="Open interest", line=dict(color="#495057")), 2, 1, secondary_y=False)
    fig.add_trace(go.Scatter(x=g["date"], y=g["mm_net_pct_oi"], name="MM net % of OI", line=dict(color=COLORS["m_money"], dash="dot")), 2, 1, secondary_y=True)
    fig.add_trace(go.Bar(x=g["date"], y=g["m_money_long_chg_1w"], name="Change in longs", marker_color="#2f9e44"), 2, 2)
    fig.add_trace(go.Bar(x=g["date"], y=-g["m_money_short_chg_1w"], name="Change in shorts (flipped: covering = up)", marker_color="#e03131"), 2, 2)
    fig.update_layout(barmode="relative", height=780, template="plotly_white", autosize=True,
                      margin=dict(l=60, r=60, t=60, b=40), legend=dict(orientation="h", y=-0.08))
    end = g["date"].max()
    start = end - pd.DateOffset(years=LOOKBACK_YEARS_SHOWN)
    fig.update_xaxes(range=[start, end], matches="x")
    fig.update_xaxes(rangeselector=dict(buttons=[
        dict(count=1, label="1y", step="year", stepmode="backward"),
        dict(count=3, label="3y", step="year", stepmode="backward"),
        dict(count=5, label="5y", step="year", stepmode="backward"),
        dict(step="all", label="All")]), row=1, col=1)
    return fig


# ----------------------------------------------------------------------------- sections
def summary_cards(latest: pd.DataFrame) -> str:
    cards = []
    for _, r in latest.iterrows():
        net = r["m_money_net"]
        d_l, d_s = r["m_money_long_chg_1w"], r["m_money_short_chg_1w"]
        drv = metrics.driver(d_l, d_s)
        detail = "" if drv == "n/a" else f" <span class='muted'>(longs {d_l:+,.0f}, shorts {d_s:+,.0f})</span>"
        tr = ""
        if r.get("traders_mm_long") == r.get("traders_mm_long"):
            tr = f"<li><b>Managed Money traders:</b> {fmt(r['traders_mm_long'])} long &middot; {fmt(r['traders_mm_short'])} short</li>"
        cards.append(f"""
<div class=card>
  <h3>{esc(r['title'])}</h3>
  <div class=muted>{esc(r['name'])} &middot; report date {r['date']:%d %b %Y}</div>
  <ul>
    <li><b>Managed Money net position:</b> {abs(net):,.0f} contracts <b>{position_word(net)}</b>
        <span class='muted'>(long {fmt(r['m_money_long'])} &middot; short {fmt(r['m_money_short'])})</span></li>
    <li><b>Change vs last week:</b> {fmt(r['m_money_net_chg_1w'], True)} contracts</li>
    <li><b>Change vs 4 weeks ago:</b> {fmt(r['m_money_net_chg_4w'], True)} contracts</li>
    <li><b>Versus its own history:</b> {metrics._ord(r['m_money_net_pct_1y'])} percentile of the last year ({metrics.percentile_reading(r['m_money_net_pct_1y']).lower()}),
        {metrics._ord(r['m_money_net_pct_3y'])} percentile of the last three years</li>
    <li><b>What drove last week's move:</b> {esc(drv)}{detail}</li>
    <li><b>Open interest:</b> {fmt(r['oi'])} contracts ({fmt(r['oi_chg_1w'], True)} vs last week)</li>
    {tr}
  </ul>
</div>""")
    return "<div class=cards>" + "".join(cards) + "</div>"


def snapshot_table(latest: pd.DataFrame) -> str:
    head = ("<tr><th class=l>Contract</th><th>Report date</th><th>Long</th><th>Short</th><th>Net position</th>"
            "<th>Net change: 1 week</th><th>Net change: 4 weeks</th><th>Net as % of open interest</th>"
            "<th>Open interest</th><th>Open interest change: 1 week</th><th>MM traders long</th><th>MM traders short</th></tr>")
    rows = []
    for _, r in latest.iterrows():
        rows.append(
            f"<tr><td class=l>{esc(r['title'])}</td><td>{r['date']:%Y-%m-%d}</td><td>{fmt(r['m_money_long'])}</td><td>{fmt(r['m_money_short'])}</td>"
            f"<td><b>{fmt(r['m_money_net'], True)}</b></td>{delta_cell(r['m_money_net_chg_1w'])}{delta_cell(r['m_money_net_chg_4w'])}"
            f"<td>{r['mm_net_pct_oi']:.1f}%</td><td>{fmt(r['oi'])}</td>{delta_cell(r['oi_chg_1w'])}"
            f"<td>{fmt(r.get('traders_mm_long', float('nan')))}</td><td>{fmt(r.get('traders_mm_short', float('nan')))}</td></tr>")
    return f"<table>{head}{''.join(rows)}</table>"


def percentile_table(latest: pd.DataFrame) -> str:
    head = ("<tr><th class=l>Contract</th><th>Managed Money net position</th>"
            "<th>Percentile vs last 1 year</th><th>Percentile vs last 3 years</th><th class=l>Reading (vs last 1 year)</th></tr>")
    rows = []
    for _, r in latest.iterrows():
        p1 = r["m_money_net_pct_1y"]
        rows.append(f"<tr><td class=l>{esc(r['title'])}</td><td>{fmt(r['m_money_net'], True)}</td>{pct_cell(p1)}{pct_cell(r['m_money_net_pct_3y'])}"
                    f"<td class=l>{esc(metrics.percentile_reading(p1))}</td></tr>")
    return f"<table>{head}{''.join(rows)}</table>"


def percentile_explainer(latest: pd.DataFrame) -> str:
    r = latest.iloc[0]
    p = r["m_money_net_pct_1y"]
    if p != p:
        return ""
    return (f"<div class=note><b>How to read a percentile.</b> It ranks this week's net position against the weekly readings of the past year "
            f"(or three years). <b>0</b> = the lowest net position in that window (most short or least long), <b>100</b> = the highest (most long), "
            f"<b>50</b> = the median. Example from this page: {esc(r['title'])} has Managed Money {position_word(r['m_money_net'])} "
            f"{abs(r['m_money_net']):,.0f} contracts, which is the <b>{metrics._ord(p)} percentile</b>: funds held a net position at or below this level in "
            f"about {p:.0f}% of the past year's weeks, so it is "
            f"{'on the low side' if p < 50 else 'on the high side'} of its own range. "
            f"A fund can be net long and still sit at a low percentile if it is less long than usual. "
            f"Colours: blue = low, red = high.</div>")


def groups_table(latest: pd.DataFrame) -> str:
    head = ("<tr><th class=l>Contract</th><th class=l>Trader group</th><th>Net position</th><th>Change: 1 week</th><th>Change: 4 weeks</th>"
            "<th>Percentile 1 year</th><th>Percentile 3 years</th></tr>")
    rows = []
    for _, r in latest.iterrows():
        for i, c in enumerate(OTHER_GROUPS):
            first = f"<td class=l rowspan={len(OTHER_GROUPS)}>{esc(r['title'])}</td>" if i == 0 else ""
            rows.append(f"<tr class={'top' if i == 0 else ''}>{first}<td class=l>{esc(config.COHORT_LABELS[c])}</td><td>{fmt(r[f'{c}_net'], True)}</td>"
                        f"{delta_cell(r[f'{c}_net_chg_1w'])}{delta_cell(r[f'{c}_net_chg_4w'])}{pct_cell(r[f'{c}_net_pct_1y'])}{pct_cell(r[f'{c}_net_pct_3y'])}</tr>")
    return f"<table>{head}{''.join(rows)}</table>"


def group_legend() -> str:
    items = "".join(f"<li><b>{esc(config.COHORT_LABELS[c])}</b>: {esc(GROUP_NOTES[c])}</li>" for c in ["m_money"] + OTHER_GROUPS)
    return f"<ul class=legend>{items}</ul>"


PAGE = """<!doctype html><html lang=en><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>Oil COT positioning monitor</title>
<style>
*{{box-sizing:border-box}}
body{{font:15px/1.5 system-ui,-apple-system,Segoe UI,sans-serif;margin:0;color:#212529;background:#f8f9fa}}
main{{max-width:1800px;margin:0 auto;padding:0 28px 40px}}
header.top{{background:#fff;border-bottom:1px solid #dee2e6;position:sticky;top:0;z-index:10;padding:8px 28px}}
header.top a{{margin-right:16px;text-decoration:none;color:#1c7ed6;font-size:14px;white-space:nowrap}}
h1{{margin:.5em 0 .1em}} h2{{margin-top:1.8em;border-bottom:2px solid #dee2e6;padding-bottom:4px}} h3{{margin:0 0 2px}}
.meta,.muted{{color:#6c757d;font-size:13px}}
.cards{{display:grid;grid-template-columns:repeat(auto-fill,minmax(520px,1fr));gap:16px}}
.card{{background:#fff;border:1px solid #dee2e6;border-radius:8px;padding:14px 18px}}
.card ul{{margin:.6em 0 0;padding-left:20px}} .card li{{margin:.35em 0}}
.tablewrap{{overflow-x:auto;background:#fff;border:1px solid #dee2e6;border-radius:8px}}
table{{border-collapse:collapse;width:100%;font-size:14px}} th,td{{border-bottom:1px solid #eee;padding:7px 12px;text-align:right;white-space:nowrap}}
th{{background:#f1f3f5}} th.l,td.l{{text-align:left}} td.l{{font-weight:600}} td.na{{color:#adb5bd}}
tr.top td{{border-top:2px solid #ced4da}} .up{{color:#2b8a3e}} .dn{{color:#c92a2a}}
.note{{background:#fff9db;padding:10px 14px;border-radius:6px;font-size:14px;margin:12px 0}}
ul.legend{{font-size:13px;color:#495057}} .chartbox{{background:#fff;border:1px solid #dee2e6;border-radius:8px;padding:8px;margin-top:10px}}
</style></head><body>
<header class=top><nav>{nav}</nav></header>
<main>
<h1>Oil COT positioning monitor</h1>
<p class=meta>CFTC Disaggregated Commitments of Traders, futures only. Latest report date: <b>{latest}</b> (positions as of Tuesday; the CFTC normally publishes Friday ~15:30 US Eastern, later in holiday weeks).
Page built {built} UTC. Download: <a href="cot_oil.csv">raw data</a> &middot; <a href="metrics.csv">calculated metrics</a></p>

<h2 id=summary>This week at a glance</h2>
{cards}

<h2 id=snapshot>Managed Money snapshot</h2>
<p class=meta>Managed Money is the CFTC's speculative-fund category. Net position = long minus short, in contracts (spread positions excluded). Changes are in contracts.</p>
<div class=tablewrap>{snapshot}</div>

<h2 id=percentiles>How extreme is the positioning? (percentile ranks)</h2>
<div class=tablewrap>{percentiles}</div>
{explainer}

<h2 id=groups>Other trader groups</h2>
<p class=meta>Who is on the other side of the funds: hedgers, banks and others. Net position, change and percentile for each group.</p>
<div class=tablewrap>{groups}</div>
{legend}

<div class=note><b>Reading notes.</b> A group's net is a sum over firms running different strategies, so it is not a pure directional view. Positioning is shown beside, not as a predictor of, price.
Changes are in contracts, not percent, because net positions can change sign. Percentiles use only data up to each date (no look-ahead) and restart when a contract's units change or after a gap of more than a quarter.
A contract code can span product changes (NY Harbor ULSD was heating oil before late 2013). Brent here is the NYMEX Brent look-alike, not ICE Brent. Not investment advice.</div>

{charts}
<p class=meta>Source: U.S. Commodity Futures Trading Commission, public reporting environment. Auto-generated by GitHub Actions.</p>
</main></body></html>"""


def build(df: pd.DataFrame, out_dir: Path = Path("docs")) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    m = metrics.add_metrics(df)
    names = m.sort_values("date").groupby("code")["name"].last().to_dict()
    labels = {mk.key: mk.label for mk in config.MARKETS}
    m["title"] = m["market"].map(labels).fillna(m["code"].map(names))
    m.to_csv(out_dir / "metrics.csv", index=False, date_format="%Y-%m-%d")
    df.to_csv(out_dir / "cot_oil.csv", index=False, date_format="%Y-%m-%d")

    latest = m.sort_values("date").groupby("code").tail(1).copy()
    latest["name"] = latest["code"].map(names)
    order = {mk.key: i for i, mk in enumerate(config.MARKETS)}
    latest = latest.assign(_o=latest["market"].map(order)).sort_values("_o").drop(columns="_o")
    latest = latest[latest["date"] >= m["date"].max() - pd.Timedelta(days=21)]  # hide delisted contracts

    nav_links = ["<a href='#summary'>Summary</a>", "<a href='#snapshot'>Snapshot</a>", "<a href='#percentiles'>Percentiles</a>", "<a href='#groups'>Trader groups</a>"]
    charts, first = [], True
    for _, r in latest.iterrows():
        g = m[m["code"] == r["code"]]
        fig = contract_figure(g, r["title"])
        nav_links.append(f"<a href='#c{r['code']}'>{esc(r['market'].replace('_', ' '))}</a>")
        charts.append(f"<h2 id='c{r['code']}'>{esc(r['title'])} <span class=muted>&middot; {esc(r['name'])}</span></h2><div class=chartbox>"
                      + fig.to_html(full_html=False, include_plotlyjs="cdn" if first else False, default_width="100%", config={"responsive": True}) + "</div>")
        first = False

    page = PAGE.format(
        nav=" ".join(nav_links), latest=f"{m['date'].max():%Y-%m-%d}", built=pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%d %H:%M"),
        cards=summary_cards(latest), snapshot=snapshot_table(latest), percentiles=percentile_table(latest),
        explainer=percentile_explainer(latest), groups=groups_table(latest), legend=group_legend(), charts="".join(charts))
    p = out_dir / "index.html"
    p.write_text(page, encoding="utf-8")
    (out_dir / ".nojekyll").write_text("")
    return p
