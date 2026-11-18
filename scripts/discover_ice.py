"""Inspect ICE Futures Europe's own COT file (Brent / WTI / Gasoil) before we ingest it.

Run on your own machine:   python scripts/discover_ice.py
Paste the output back so the ICE loader can be written against the real column names.
Report Center page: https://www.ice.com/report/122  (Commitments of Traders)
"""
import csv
import io
import sys
import urllib.request

YEAR = int(sys.argv[1]) if len(sys.argv) > 1 else 2026
URL = f"https://www.ice.com/publicdocs/futures/COTHist{YEAR}.csv"
req = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0 (cot-oil-monitor research)"})
raw = urllib.request.urlopen(req, timeout=60).read().decode("utf-8-sig", errors="replace")
rows = list(csv.reader(io.StringIO(raw)))
print("URL:", URL, "| rows:", len(rows))
print("\nHEADER (", len(rows[0]), "columns ):")
for i, c in enumerate(rows[0]):
    print(f"  {i:3d} {c}")
name_col = next((i for i, c in enumerate(rows[0]) if "market" in c.lower() and "name" in c.lower()), 0)
print("\nDistinct market names:")
for n in sorted({r[name_col] for r in rows[1:] if len(r) > name_col}):
    print("  ", n)
print("\nFirst 3 data rows:")
for r in rows[1:4]:
    print("  ", r[:12], "...")
