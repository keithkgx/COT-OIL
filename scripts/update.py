"""Fetch the latest COT data and upsert it into data/cot_oil.csv.

    python scripts/update.py          # incremental (re-pulls last 8 weeks to catch revisions)
    python scripts/update.py --full   # full backfill from 2006
"""
import argparse
import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cot import config, fetch, store  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", action="store_true")
    args = ap.parse_args()

    existing = store.prune(store.load())
    have = set(existing["code"]) if not existing.empty else set()
    new_codes = store.configured_codes() - have  # e.g. a contract just added to config
    last = store.latest_date(existing)
    if args.full or last is None or new_codes:
        if new_codes and not args.full:
            print(f"New contracts in config {sorted(new_codes)} -> backfilling full history")
        since = config.FIRST_DATE
    else:
        since = (last - dt.timedelta(days=config.INCREMENTAL_OVERLAP_DAYS)).strftime("%Y-%m-%d")
    print(f"Fetching since {since} ...")
    new = fetch.fetch(since)
    if new.empty:
        print("ERROR: CFTC returned no rows for the configured contracts. Run scripts/discover.py.")
        return 1

    # Fail loudly if a configured market vanished (wrong code / renamed contract).
    got = set(new["market"])
    missing = [m.key for m in config.MARKETS if m.key not in got]
    if missing:
        print(f"WARNING: no rows for markets {missing}. Check codes with scripts/discover.py.")
        if since == config.FIRST_DATE:
            print("ERROR: refusing to save a backfill that is missing configured markets.")
            return 1

    out = store.upsert(existing, new)
    store.save(out)
    print(f"Stored {len(out):,} rows; latest report date {out['date'].max():%Y-%m-%d}; "
          f"{new['date'].nunique()} weeks fetched.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
