# clean_walmart_csv.py
import csv, sys, re
from urllib.parse import urlparse, parse_qs, unquote

IN = r".\data\walmart_milk.csv"
OUT = r".\data\walmart_milk_clean.csv"

BASE = "https://www.walmart.ca"

def tidy_url(u: str) -> str:
    if not u:
        return ""
    # Strip Walmart click-tracker and keep the real /en/ip/... path
    if "/wapcrs/track" in u:
        # 1) try rd=
        try:
            q = parse_qs(urlparse(u).query)
            rd = q.get("rd", [None])[0]
            if rd:
                u = unquote(rd)
        except Exception:
            pass
        # 2) some anchors include a literal "&/en/ip/..." after the query – keep that
        if "&/en/ip/" in u:
            u = BASE + u.split("&", 1)[1]   # keep from &/en/ip/...
    # Normalize to just scheme+host+path (drop query gunk)
    p = urlparse(u)
    return f"{p.scheme}://{p.netloc}{p.path}"

def good_price(row) -> bool:
    try:
        price = float(row.get("price") or 0)
    except:
        return False
    # Filter obvious mis-parses: “1.89”, “3.25”, “4.6” with no unit price
    if price < 2 and not (row.get("price_per_unit") or "").strip():
        return False
    return True

seen = {}
with open(IN, newline="", encoding="utf-8") as f:
    r = csv.DictReader(f)
    rows = []
    for row in r:
        row["url"] = tidy_url(row.get("url",""))
        rows.append(row)

# Drop rows that still aren’t product pages
rows = [r for r in rows if "/en/ip/" in (r.get("url") or "")]

# Drop rows with bad prices
rows = [r for r in rows if good_price(r)]

# Dedupe by SKU (fallback to URL), keep the most recently scraped row or the one with a non-empty brand
from datetime import datetime
def ts(s): 
    try: return datetime.fromisoformat((s or "").replace("Z",""))
    except: return datetime.min

rows_sorted = sorted(
    rows,
    key=lambda r: (r.get("brand","") != "", ts(r.get("scraped_at","")), r.get("price") or ""),
    reverse=True
)

out_rows = []
by_key = {}
for r in rows_sorted:
    key = (r.get("sku") or "").strip() or r.get("url")
    if key not in by_key:
        by_key[key] = True
        out_rows.append(r)

with open(OUT, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=[
        "title","brand","price","price_per_unit","image","url","sku","category","scraped_at"
    ])
    w.writeheader()
    for r in out_rows:
        w.writerow(r)

print(f"Cleaned {len(out_rows)} rows -> {OUT}")
