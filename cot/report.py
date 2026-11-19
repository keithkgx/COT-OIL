"""Build the static dashboard (docs/index.html) for GitHub Pages.

All numbers are computed once in Python (cot.metrics) and embedded in the page as JSON; a small
script in cot/dashboard_template.html renders the cards, tables and range bars for whichever week
the reader picks. Charts are drawn by Plotly from plain lists (ISO date strings, numbers/None), with no
numpy/datetime serialisation, so the output does not depend on the pandas/plotly version used to build it.
"""
from __future__ import annotations

import html
import json
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
from plotly.offline import get_plotlyjs_version

from . import config, metrics

TEMPLATE = Path(__file__).with_name("dashboard_template.html")
COLORS = {"m_money": "#d9480f", "prod_merc": "#1c7ed6", "swap": "#2f9e44", "other_rept": "#862e9c", "nonrept": "#868e96"}
DEFAULT_SPAN_YEARS = 5


def esc(s) -> str:
    return html.escape(str(s))


# ----------------------------------------------------------------------------- data payload
def _col(g: pd.DataFrame, name: str, nd: int | None):
    """Column as a JSON-safe list: NaN -> None, rounded; integers for nd == 0."""
    if name not in g:
        return [None] * len(g)
    out = []
    for v in g[name].tolist():
        if v is None or v != v:
            out.append(None)
        elif nd == 0:
            out.append(int(round(v)))
        else:
            out.append(round(float(v), nd))
    return out


def contract_payload(g: pd.DataFrame, mk: config.Market, official_name: str) -> dict:
    g = g.sort_values("date")
    f: dict[str, list] = {}
    for c in metrics.COHORTS:
        for suffix, nd in (("long", 0), ("short", 0), ("net", 0), ("net_chg_1w", 0), ("net_chg_4w", 0), ("net_pct_1y", 1), ("net_pct_3y", 1)):
            f[f"{c}_{suffix}"] = _col(g, f"{c}_{suffix}", nd)
    for name, nd in (("m_money_long_chg_1w", 0), ("m_money_short_chg_1w", 0), ("oi", 0), ("oi_chg_1w", 0), ("mm_net_pct_oi", 2),
                     ("traders_mm_long", 0), ("traders_mm_short", 0)):
        f[name] = _col(g, name, nd)
    for w in metrics.WINDOWS:
        for stat in ("min", "p25", "med", "p75", "max"):
            f[f"m_money_net_{stat}_{w}"] = _col(g, f"m_money_net_{stat}_{w}", 0)
    f["driver"] = [metrics.driver(a, b) for a, b in zip(g["m_money_long_chg_1w"].tolist(), g["m_money_short_chg_1w"].tolist())]
    return {"code": g["code"].iloc[0], "key": mk.key, "title": mk.label, "name": official_name, "size": mk.size_text,
            "bpc": mk.barrels, "note": mk.note, "dates": g["date"].dt.strftime("%Y-%m-%d").tolist(), "f": f}


def to_json(obj) -> str:
    # allow_nan=False makes a stray NaN fail the build instead of producing invalid JSON in the page.
    return json.dumps(obj, separators=(",", ":"), allow_nan=False).replace("</", "<\\/")


# ----------------------------------------------------------------------------- charts
def _ylim(series: list[list], x: list[str], x0: str, pad: float = 0.06):
    """Explicit y-range for the visible window. Plotly's autorange ignores the x-window and would
    stretch the axis to the whole history, squashing the lines we actually show."""
    vals = [v for ys in series for d, v in zip(x, ys) if d >= x0 and v is not None]
    if not vals:
        return None
    lo, hi = min(vals), max(vals)
    p = (hi - lo or abs(hi) or 1) * pad
    return [lo - p, hi + p]


def _layout(x0: str, x1: str, last: str, ytitle: str, ylim=None, height: int = 340) -> dict:
    return dict(
        template="plotly_white", height=height, autosize=True, margin=dict(l=64, r=16, t=8, b=70),
        legend=dict(orientation="h", y=-0.2, x=0, font=dict(size=11)), hovermode="x unified",
        xaxis=dict(range=[x0, x1], type="date"), yaxis=dict(title=dict(text=ytitle, font=dict(size=11)), zeroline=False, range=ylim),
        shapes=[dict(type="line", xref="x", yref="paper", x0=last, x1=last, y0=0, y1=1, line=dict(color="#495057", width=1.5, dash="dot"))],
    )


def chart_net(x, g, x0, x1, last):
    y = _col(g, "m_money_net", 0)
    fig = go.Figure([go.Scatter(x=x, y=y, name="Managed Money net position", line=dict(color=COLORS["m_money"], width=2)),
                     go.Scatter(x=[x[-1]], y=[y[-1]], mode="markers+text", text=[f"{y[-1]:,}" if y[-1] is not None else ""], textposition="top left",
                                marker=dict(size=8, color=COLORS["m_money"]), showlegend=False, hoverinfo="skip")])
    fig.add_hline(y=0, line_width=1, line_color="#999")
    fig.update_layout(**_layout(x0, x1, last, "contracts", _ylim([y], x, x0)))
    return fig


def chart_groups(x, g, x0, x1, last):
    fig = go.Figure()
    allv = []
    for c in metrics.COHORTS:
        y = _col(g, f"{c}_net", 0)
        allv.append(y)
        fig.add_trace(go.Scatter(x=x, y=y, name=config.COHORT_LABELS[c], line=dict(color=COLORS[c], width=2.5 if c == "m_money" else 1.4)))
    fig.add_hline(y=0, line_width=1, line_color="#999")
    fig.update_layout(**_layout(x0, x1, last, "net position, contracts", _ylim(allv, x, x0)))
    return fig


def chart_oi(x, g, x0, x1, last):
    y = _col(g, "oi", 0)
    fig = go.Figure([go.Scatter(x=x, y=y, name="Open interest", line=dict(color="#495057", width=2))])
    fig.update_layout(**_layout(x0, x1, last, "contracts", _ylim([y], x, x0)))
    return fig


def chart_changes(x, g, x0, x1, last):
    dl = _col(g, "m_money_long_chg_1w", 0)
    ds = _col(g, "m_money_short_chg_1w", 0)
    sc = [None if v is None else -v for v in ds]  # contribution of the short side to the change in net
    net = _col(g, "m_money_net_chg_1w", 0)
    fig = go.Figure([
        go.Bar(x=x, y=dl, name="Long side: new longs (up) / long liquidation (down)", marker_color="#2f9e44",
               hovertemplate="Change in longs: %{y:+,.0f}<extra></extra>"),
        go.Bar(x=x, y=sc, name="Short side: short covering (up) / new shorts (down)", marker_color="#e03131", customdata=ds,
               hovertemplate="Short-side effect: %{y:+,.0f} (raw change in shorts %{customdata:+,.0f})<extra></extra>"),
        go.Scatter(x=x, y=net, name="Net change (total of both bars)", mode="lines+markers", line=dict(color="#212529", width=1.5), marker=dict(size=4),
                   hovertemplate="Net change: %{y:+,.0f}<extra></extra>"),
    ])
    fig.add_hline(y=0, line_width=1, line_color="#999")
    pos = [None if (a is None) else max(a, 0) + (0 if b is None else max(b, 0)) for a, b in zip(dl, sc)]
    neg = [None if (a is None) else min(a, 0) + (0 if b is None else min(b, 0)) for a, b in zip(dl, sc)]
    lay = _layout(x0, x1, last, "contracts per week", _ylim([pos, neg, net], x, x0), height=380)
    lay["barmode"] = "relative"
    fig.update_layout(**lay)
    return fig


CHARTS = [
    ("net", "Managed Money net position", "Long minus short for the speculative funds. Above zero = net long, below zero = net short. The labelled dot is the latest reading.", chart_net),
    ("groups", "Net position by trader group", "Managed Money (thick orange) against hedgers, banks and others. The groups always add up to zero, so the lines show who is on the other side of the funds.", chart_groups),
    ("oi", "Open interest", "Total contracts outstanding. Rising = new positions are being opened (money entering); falling = positions are being closed.", chart_oi),
    ("chg", "Weekly change in Managed Money net position", "Bars above zero are buying (new longs or short covering); bars below zero are selling (long liquidation or new shorts). The black line is the net result for the week.", chart_changes),
]


def charts_html(m: pd.DataFrame, latest: pd.DataFrame) -> tuple[str, list[str]]:
    blocks, ids = [], []
    last_all = m["date"].max()
    x1 = last_all.strftime("%Y-%m-%d")
    x0 = (last_all - pd.DateOffset(years=DEFAULT_SPAN_YEARS)).strftime("%Y-%m-%d")
    for _, r in latest.iterrows():
        g = m[m["code"] == r["code"]].sort_values("date")
        x = g["date"].dt.strftime("%Y-%m-%d").tolist()
        cells = []
        for key, title, cap, fn in CHARTS:
            fig = fn(x, g, x0, x1, x1)
            div_id = f"ch-{r['code']}-{key}"
            ids.append(div_id)
            cells.append(f"<div class=chart><h4>{esc(title)}</h4><p class=cap>{esc(cap)}</p>"
                         + fig.to_html(full_html=False, include_plotlyjs=False, div_id=div_id, default_width="100%", default_height=f"{fig.layout.height}px",
                                       config={"responsive": True, "displaylogo": False}) + "</div>")
        blocks.append(f"<h3 id='c{esc(r['code'])}' style='margin-top:1.6em'>{esc(r['title'])} <span class=muted>&middot; {esc(r['name'])} &middot; data through "
                      f"{g['date'].max():%d %b %Y} ({len(g)} weeks)</span></h3><div class=chartsgrid>{''.join(cells)}</div>")
    return "".join(blocks), ids


# ----------------------------------------------------------------------------- guide
GUIDE = """
<p class=intro>New to the Commitments of Traders report? Start here. Each item opens to a short explanation.</p>
<details open><summary>What is this report, and when does it update?</summary>
<p>Every Tuesday, large traders in US-regulated futures markets must report their open positions to the CFTC (the US Commodity Futures Trading Commission). The CFTC publishes the totals, split by type of trader, the following Friday at 15:30 US Eastern time (a day or more later in holiday weeks).
This page uses the <b>Disaggregated</b> version for <b>futures only</b> (options are excluded). It checks for new data every day and rebuilds itself, and the CFTC revises past weeks occasionally, so the last eight weeks are re-downloaded on every run.</p>
<p>The report is a snapshot of <i>positions on a Tuesday</i>. It does not show trades during the week, prices, or why anyone traded.</p></details>
<details><summary>Contracts, long, short and net: what do the numbers mean?</summary>
<ul><li><b>Contract.</b> One futures contract. Its size is fixed by the exchange. Every contract on this page is 1,000 barrels (NY Harbor ULSD and RBOB are 42,000 US gallons, which is also 1,000 barrels). So <b>1,000 contracts = 1 million barrels</b> of oil exposure.</li>
<li><b>Long</b> = contracts bought and held (a bet on higher prices). <b>Short</b> = contracts sold and held (a bet on lower prices). <b>Net position</b> = long minus short. Positive = net long; negative = net short.</li>
<li><b>A change of +3,986 contracts</b> means the group's net position rose by 3,986 contracts (about 4.0 million barrels) versus the week before: it became more net long or less net short. It is a number of contracts, not a contract size.</li>
<li><b>Spreading</b> is a position that is long and short in different months of the same contract. It is balanced, so it is left out of net position.</li>
<li><b>Gross vs net.</b> The same net position can hide very different long and short books, so the cards also show the long and short totals.</li></ul></details>
<details><summary>The trader groups</summary>
<ul><li><b>Managed Money</b>: speculative funds: registered commodity trading advisors, commodity pool operators and unregistered funds. This is the group most watched for speculative positioning and crowding, which is why this page leads with it. It is wider than "hedge funds".</li>
<li><b>Producers / Merchants</b>: businesses that produce, process, trade or use the physical commodity and hedge that exposure.</li>
<li><b>Swap Dealers</b>: mostly banks that sell customised swaps to clients and hedge them in futures.</li>
<li><b>Other Reportables</b>: large traders that fit none of the above.</li>
<li><b>Non-reportable (small)</b>: everyone below the reporting threshold. The CFTC does not report them directly; they are what is left of open interest.</li></ul>
<p>The five groups' net positions add up to exactly zero in every contract, because every long has a short on the other side. When funds are net long, the other groups are net short in total.</p></details>
<details><summary>Open interest</summary><p>The total number of contracts that are open (long and short sides count once). Rising open interest means new positions are being opened; falling means positions are being closed. It says how big the market is, not which way anyone leans.
"Net as % of open interest" divides a group's net position by open interest, which makes positioning comparable across contracts and across years as the market grows.</p></details>
<details><summary>What drove the week's move? (new longs, short covering, new shorts, long liquidation)</summary>
<p>A change in net position comes from changes on the long side, the short side, or both. Looking at each side shows whether funds were opening or closing positions.</p>
<table><tr><th>Label</th><th>What happened</th><th>Effect on net</th></tr>
<tr><td>New longs</td><td>Funds' long positions rose: they bought to open</td><td>Up (buying)</td></tr>
<tr><td>Short covering</td><td>Funds' short positions fell: they bought to close</td><td>Up (buying)</td></tr>
<tr><td>Long liquidation</td><td>Funds' long positions fell: they sold to close</td><td>Down (selling)</td></tr>
<tr><td>New shorts</td><td>Funds' short positions rose: they sold to open</td><td>Down (selling)</td></tr></table>
<p>In the weekly-change chart, bars above zero are buying and bars below zero are selling. The green bar is the long side and the red bar the short side, with the red bar flipped so that "up" always means buying. Two reasons can appear together, for example "short covering + new longs" means both sides pushed net up. The black line adds them: it is the week's total change in net position.</p></details>
<details><summary>Percentiles and the range bars</summary>
<p>A percentile ranks this week's value against the weekly values over a trailing window: 52 weeks (1 year) or 156 weeks (3 years). <b>0</b> is the lowest value in the window, <b>100</b> the highest, <b>50</b> the median. A 19th percentile means funds held a net position at or below today's level in 19% of those weeks, so today is toward the low end of its recent range, even if the position is still net long.</p>
<p>The range bars show the actual values behind the ranking: the left end is the lowest net position in the window, the right end the highest, the grey band the middle half of weeks, and the orange dot this week.
The reading labels are: 90 and above "near the top of its range", 75 to 90 "high", 25 to 75 "mid-range", 10 to 25 "low", 10 and below "near the bottom of its range".</p>
<p>Percentiles use only the data that existed at each date (no look-ahead), restart when a contract's units change or after a gap of more than a quarter, and show "n/a" when there is too little history or the group never changes. They describe where positioning is relative to its own past. They are not a forecast.</p></details>
<details><summary>The charts</summary>
<ul><li><b>Managed Money net position</b>: the funds' net long/short over time.</li><li><b>Net position by trader group</b>: all groups together, to see who is on the other side.</li>
<li><b>Open interest</b>: market size over time.</li><li><b>Weekly change</b>: what funds did each week, split into the long and short sides, with a line for the net total.</li></ul>
<p>The dotted vertical line marks the selected week. The labelled dot on the first chart is the latest reading in the data.</p></details>
<details><summary>Contracts covered and data coverage</summary>
%%COVERAGE%%
<p class=meta>"Missing weeks" counts gaps of more than ten days between consecutive reports. Contract codes are kept by the CFTC through renames, so history can span product changes (noted above).</p></details>
<details><summary>Method and limitations</summary>
<ul><li><b>Source:</b> CFTC Public Reporting Environment, Disaggregated COT futures-only dataset. Contracts are matched on CFTC contract codes.</li>
<li><b>Changes</b> are in contracts, never in percent, because net positions can change sign. "4 weeks ago" is a rough monthly comparison.</li>
<li><b>Futures only.</b> Options are excluded. Some analysts quote futures-and-options-combined figures, which differ.</li>
<li><b>Brent:</b> the CFTC report only has the small NYMEX Brent look-alike. ICE Brent, the main benchmark, is reported separately by ICE and is not on this page yet.</li>
<li><b>Managed Money</b> is a regulatory category. A group's net position sums firms with different strategies, so it is not a single view.</li>
<li><b>Positioning is not a price forecast.</b> Extreme readings show crowding, not timing. Not investment advice.</li></ul></details>
"""


def coverage_table(m: pd.DataFrame, latest: pd.DataFrame) -> str:
    cov = metrics.coverage(m).set_index("code")
    rows = []
    for _, r in latest.iterrows():
        c = cov.loc[r["code"]]
        rows.append(f"<tr><td>{esc(r['title'])}</td><td>{esc(r['code'])}</td><td>{esc(r['name'])}</td><td>{esc(r['size'])}</td>"
                    f"<td>{c['first']:%d %b %Y}</td><td>{c['last']:%d %b %Y}</td><td>{int(c['weeks'])}</td><td>{int(c['gaps'])}</td></tr>")
    head = "<tr><th>Contract</th><th>CFTC code</th><th>CFTC name</th><th>Size</th><th>First week</th><th>Last week</th><th>Weeks</th><th>Missing weeks</th></tr>"
    return f"<table>{head}{''.join(rows)}</table>"


# ----------------------------------------------------------------------------- build
def build(df: pd.DataFrame, out_dir: Path = Path("docs")) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    m = metrics.add_metrics(df)
    names = m.sort_values("date").groupby("code")["name"].last().to_dict()
    by_key = {mk.key: mk for mk in config.MARKETS}
    m["title"] = m["market"].map({k: v.label for k, v in by_key.items()}).fillna(m["code"].map(names))
    m.to_csv(out_dir / "metrics.csv", index=False, date_format="%Y-%m-%d")
    df.to_csv(out_dir / "cot_oil.csv", index=False, date_format="%Y-%m-%d")

    latest = m.sort_values("date").groupby("code").tail(1).copy()
    latest["name"] = latest["code"].map(names)
    latest["size"] = latest["market"].map({k: v.size_text for k, v in by_key.items()})
    order = {mk.key: i for i, mk in enumerate(config.MARKETS)}
    latest = latest.assign(_o=latest["market"].map(order)).sort_values("_o").drop(columns="_o")
    latest = latest[latest["date"] >= m["date"].max() - pd.Timedelta(days=21)]  # hide delisted contracts

    contracts = [contract_payload(m[m["code"] == r["code"]], by_key[r["market"]], names[r["code"]]) for _, r in latest.iterrows()]
    charts, chart_ids = charts_html(m, latest)
    payload = {"contracts": contracts, "charts": chart_ids}

    nav = ["<a href='#summary'>Summary</a>", "<a href='#table'>Trader groups</a>", "<a href='#percentiles'>Percentiles</a>", "<a href='#charts'>Charts</a>"]
    nav += [f"<a href='#c{esc(r['code'])}'>{esc(r['market'].replace('_', ' '))}</a>" for _, r in latest.iterrows()]
    nav.append("<a href='#guide'>Guide</a>")

    page = (TEMPLATE.read_text(encoding="utf-8")
            .replace("%%PLOTLY_SRC%%", f"https://cdn.plot.ly/plotly-{get_plotlyjs_version()}.min.js")
            .replace("%%NAV%%", " ".join(nav))
            .replace("%%CHARTS%%", charts)
            .replace("%%GUIDE%%", GUIDE.replace("%%COVERAGE%%", coverage_table(m, latest)))
            .replace("%%BUILT%%", pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%d %H:%M"))
            .replace("%%DATA%%", to_json(payload)))
    p = out_dir / "index.html"
    p.write_text(page, encoding="utf-8")
    (out_dir / ".nojekyll").write_text("")
    return p
