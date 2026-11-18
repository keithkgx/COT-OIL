# Oil COT positioning monitor

Auto-updating dashboard of speculative positioning in oil futures, built from the CFTC
**Disaggregated Commitments of Traders** (futures only). Runs entirely on GitHub Actions and
publishes to GitHub Pages — no machine of yours has to stay on.

**What it shows:** Managed Money long/short/net, weekly and 4-week changes, what drove the
weekly change (new longs vs short covering vs new shorts vs long liquidation), 1-year and 3-year
net-position percentiles (no look-ahead) for every trader group, open interest, and a
cross-contract percentile heatmap. Raw data and computed metrics are downloadable as CSV.

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
WTI (NYMEX physical, ICE, NYMEX financial since 2019), Brent last-day (NYMEX), NY Harbor ULSD, RBOB.
Note: the CFTC keeps one code per contract across renames, but history can span product changes
(ULSD was heating oil before late 2013). ICE Brent futures are not in the CFTC report; ICE publishes its own COT.
