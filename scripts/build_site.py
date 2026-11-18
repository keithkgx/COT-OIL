"""Build docs/index.html (+ CSV exports) from data/cot_oil.csv."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cot import report, store  # noqa: E402

df = store.load()
if df.empty:
    raise SystemExit("data/cot_oil.csv is empty - run scripts/update.py first")
print("Wrote", report.build(df))
