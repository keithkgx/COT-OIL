# Oil COT positioning monitor

Auto-updating dashboard of speculative positioning in oil futures, built from the CFTC
**Disaggregated Commitments of Traders** (futures only). Runs entirely on GitHub Actions and
publishes to GitHub Pages — no machine of yours has to stay on.

**What it shows** (pick any past week with the selector; every figure is explained in the on-page guide):
per-contract summary cards for Managed Money, one table of every trader group (week vs previous week and
vs four weeks ago), percentile range bars that show what 0th/100th percentile mean in contracts, and four
history charts per contract. Raw data and calculated metrics are downloadable as CSV.

## Setup (once)
1. Create a GitHub repo and push this folder.
2. **Settings → Pages → Source: GitHub Actions.**
3. **Settings → Actions → General → Workflow permissions: Read and write.**
4. Optional: `python scripts/discover.py` lists every oil-related contract the CFTC publishes if you want to add more (see the watchlist in `cot/config.py`).
5. **Actions → "Update COT data and publish dashboard" → Run workflow → tick "full".**

After that it refreshes itself Friday evening (plus Saturday and Monday catch-ups).

## Layout
- `cot/fetch.py` Socrata client (no API key) · `cot/store.py` CSV database, upsert on (code, date)
- `cot/metrics.py` net, changes, percentiles, driver decomposition · `cot/report.py` Plotly dashboard
- `scripts/` update, build_site, discover · `tests/` · `.github/workflows/update.yml`

## Methodology notes
Positions are as of Tuesday, published Friday. CFTC revises past weeks, so each run re-pulls an
8-week window. Changes are in contracts (never % of a signed number). Percentiles use only the
trailing window and restart at contract-unit changes or gaps over a quarter. Positioning is shown
beside price context, not as a trading signal. Design borrows from IngTian/offchart.

## Contracts covered
WTI (NYMEX physical and ICE), Brent last-day (NYMEX), NY Harbor ULSD, RBOB. (WTI financial was dropped: it reports no Managed Money positions.)
Note: the CFTC keeps one code per contract across renames, but history can span product changes
(ULSD was heating oil before late 2013). ICE Brent futures are not in the CFTC report; ICE publishes its own COT.

## Development
`python -m pytest -q` runs the unit tests. The dashboard is `cot/dashboard_template.html` (layout and the script that
renders the selected week) filled by `cot/report.py`. Library versions are pinned in `requirements.txt` so local and
GitHub builds match.
