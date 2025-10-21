# enrich_walmart_csv.py
import re
import math
import pandas as pd
from pathlib import Path

IN = Path("data/walmart_milk_clean.csv")
OUT = Path("data/walmart_milk_enriched.csv")

PACK_RE = re.compile(r'(\d+)\s*[x×]\s*(\d+(?:\.\d+)?)\s*(mL|ml|L|l)\b')
VOL_RE  = re.compile(r'(\d+(?:\.\d+)?)\s*(mL|ml|L|l)\b')

def to_ml(qty, unit):
    qty = float(qty)
    unit = unit.lower()
    return qty * (1000 if unit == "l" else 1)

def parse_volume(title: str):
    """
    Returns (pack_count, single_ml, net_ml) or (1, single_ml, single_ml)
    If nothing found, returns (None, None, None)
    """
    if not isinstance(title, str):
        return (None, None, None)

    # Try pack pattern first (e.g., "6 x 200 mL", "3×1 L")
    m = PACK_RE.search(title)
    if m:
        count = int(m.group(1))
        single_ml = to_ml(m.group(2), m.group(3))
        return (count, single_ml, count * single_ml)

    # Otherwise, take the last single volume match (often the actual size)
    vols = list(VOL_RE.finditer(title))
    if vols:
        qty, unit = vols[-1].groups()
        single_ml = to_ml(qty, unit)
        return (1, single_ml, single_ml)

    return (None, None, None)

def normalize_brand(brand):
    if not isinstance(brand, str) or not brand.strip():
        return None
    return brand.strip().title()

def classify(title: str):
    """Simple tags for quick filtering."""
    t = (title or "").lower()
    tags = []
    if "lactose free" in t:
        tags.append("lactose-free")
    if "ultrafiltered" in t or "joyya" in t:
        tags.append("ultrafiltered")
    if "chocolate" in t or "strawberry" in t:
        tags.append("flavoured")
    if "organic" in t:
        tags.append("organic")
    return ",".join(tags) or None

def size_label(net_ml):
    if not isinstance(net_ml, (int, float)) or math.isnan(net_ml):
        return None
    # Common sizes bucketed nicely
    buckets = {
        1000: "1 L",
        1890: "1.89 L",
        2000: "2 L",
        3780: "3.78 L",
        4000: "4 L",
        946:  "946 mL",
        750:  "750 mL",
        600:  "600 mL",
        1200: "6×200 mL",
    }
    # Snap to nearest common bucket within 3%
    for ml, lab in buckets.items():
        if abs(net_ml - ml) / ml <= 0.03:
            return lab
    # Fallback
    if net_ml >= 1000:
        return f"{net_ml/1000:.2f} L"
    else:
        return f"{int(round(net_ml))} mL"

def coerce_price(x):
    try:
        # Some rows might already be numeric; some could be strings
        return float(str(x).replace("$","").strip())
    except Exception:
        return float("nan")

def main():
    if not IN.exists():
        raise SystemExit(f"Input not found: {IN}")

    df = pd.read_csv(IN)

    # Parse volumes
    parsed = df["title"].apply(parse_volume)
    df["pack_count"]  = parsed.apply(lambda t: t[0])
    df["single_ml"]   = parsed.apply(lambda t: t[1])
    df["net_ml"]      = parsed.apply(lambda t: t[2])

    # Prices & per-liter
    df["price"] = df["price"].apply(coerce_price)
    df.loc(df["price"] <= 0, "price")  # leave as is; NaN handled later
    df["price_per_liter"] = df.apply(
        lambda r: r["price"] / (r["net_ml"] / 1000.0)
        if pd.notna(r["price"]) and pd.notna(r["net_ml"]) and r["net_ml"] > 0
        else float("nan"),
        axis=1,
    )

    # Normalized helpers
    df["brand_norm"] = df["brand"].apply(normalize_brand)
    df["tags"]       = df["title"].apply(classify)
    df["size_label"] = df["net_ml"].apply(size_label)

    # Drop rows with no usable price/volume
    before = len(df)
    df = df[pd.notna(df["price_per_liter"])]
    dropped = before - len(df)

    # Sort nice: cheapest per liter first
    df = df.sort_values(["size_label", "price_per_liter", "price"], ascending=[True, True, True])

    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT, index=False)
    print(f"Enriched {len(df)} rows (dropped {dropped}) -> {OUT}")

    # Show quick cheapest summary in console
    topk = (
        df.sort_values("price_per_liter")
          .groupby("size_label", as_index=False)
          .first()[["size_label", "title", "brand_norm", "price", "price_per_liter", "url"]]
    )
    with pd.option_context("display.max_colwidth", 120):
        print("\nCheapest by size_label:\n", topk.to_string(index=False))

if __name__ == "__main__":
    main()
