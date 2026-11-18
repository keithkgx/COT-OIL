"""List candidate oil contracts in the CFTC disaggregated futures dataset.

Run this ONCE to confirm/adjust the contract codes in cot/config.py.
"""
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cot import config, fetch  # noqa: E402

KEYWORDS = ["CRUDE", "BRENT", "WTI", "ULSD", "HEATING OIL", "GASOLINE", "RBOB", "GASOIL", "DIESEL"]
where = " OR ".join(f"upper(market_and_exchange_names) like '%{k}%'" for k in KEYWORDS)
q = {
    "$select": "cftc_contract_market_code,market_and_exchange_names,max(contract_units) as units,"
               "min(report_date_as_yyyy_mm_dd) as first_date,max(report_date_as_yyyy_mm_dd) as last_date,count(*) as weeks",
    "$where": where,
    "$group": "cftc_contract_market_code,market_and_exchange_names",
    "$order": "last_date DESC",
    "$limit": "500",
}
rows = fetch.get_json(config.BASE_URL + "?" + urllib.parse.urlencode(q))
print(f"{'code':8} {'last':10} {'first':10} {'weeks':>5}  name  [units]")
for r in rows:
    print(f"{r['cftc_contract_market_code']:8} {r['last_date'][:10]} {r['first_date'][:10]} {r['weeks']:>5}  "
          f"{r['market_and_exchange_names']}  [{r.get('units','')}]")
print("\nCurrently configured:")
for m in config.MARKETS:
    print(" ", m.key, m.codes, m.name_like)
