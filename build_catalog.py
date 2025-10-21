# build_catalog.py
import csv, glob, os, re
from datetime import datetime

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
OUT = os.path.join(DATA_DIR, "catalog_latest.csv")

# Detect store name from filename like "walmart_milk_clean.csv" -> "Walmart"
def guess_store_from_filename(path: str) -> str:
    base = os.path.basename(path).lower()
    if "walmart" in base: return "Walmart"
    if "nofrills" in base or "no-frills" in base: return "No Frills"
    if "real-canadian" in base or "superstore" in base: return "Real Canadian Superstore"
    if "safeway" in base: return "Safeway"
    if "saveon" in base or "save-on" in base: return "Save-On-Foods"
    return "Store"

def parse_size_text(title: str) -> str:
    if not title: return ""
    # Simple grab like "1.89L", "2 L", "946 mL", "750ml", "4 x 200 mL"
    m = re.findall(r'(\d+(?:\.\d+)?\s?(?:ml|l|g|kg)|\d+\s?[x×]\s?\d+(?:\.\d+)?\s?(?:ml|g))', title, flags=re.I)
    return ", ".join(dict.fromkeys([s.strip() for s in m]))  # de-dup keep order

in_files = sorted(glob.glob(os.path.join(DATA_DIR, "*_clean.csv")))
if not in_files:
    raise SystemExit("No *_clean.csv files found in ./data. Run your cleaners first.")

rows_out = []
for path in in_files:
    store = guess_store_from_filename(path)
    with open(path, newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            # normalize fields (keep image + price_per_unit!)
            rows_out.append({
                "store": store,
                "title": row.get("title","").strip(),
                "brand": row.get("brand","").strip(),
                "price": row.get("price","").strip(),
                "price_per_unit": row.get("price_per_unit","").strip(),
                "image": row.get("image","").strip(),
                "url": row.get("url","").strip(),
                "sku": row.get("sku","").strip(),
                "category": row.get("category","").strip(),
                "scraped_at": row.get("scraped_at","").strip(),
                "size_text": parse_size_text(row.get("title","") or ""),
            })

# (Optional) light dedupe by (store, url OR sku); keep the lowest price
def price_num(p):
    try: return float(p)
    except: return 1e12

dedup = {}
ordered = []
for r in rows_out:
    key = (r["store"], r["sku"] or r["url"])
    prev = dedup.get(key)
    if prev is None or price_num(r["price"]) < price_num(prev["price"]):
        dedup[key] = r

ordered = list(dedup.values())

# write out
fieldnames = [
    "store","title","brand","price","price_per_unit","image","url",
    "sku","category","scraped_at","size_text"
]
os.makedirs(DATA_DIR, exist_ok=True)
with open(OUT, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=fieldnames)
    w.writeheader()
    w.writerows(ordered)

print(f"Wrote {OUT} with {len(ordered)} rows at {datetime.now().isoformat(timespec='seconds')}")
