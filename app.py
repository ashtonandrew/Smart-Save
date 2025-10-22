from __future__ import annotations

import os
from typing import Optional, Tuple

from flask import Flask, jsonify, render_template, request, send_from_directory
import pandas as pd

# ---------------------------------
# Config
# ---------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
DATA_FILE = os.path.join(DATA_DIR, "catalog_latest.csv")

DEFAULT_PAGE = 1
DEFAULT_SIZE = 50

app = Flask(
    __name__,
    static_folder="static",
    template_folder="templates",
)

# ---------------------------------
# CSV cache
# ---------------------------------
_df_cache: Optional[pd.DataFrame] = None
_df_mtime: Optional[float] = None

REQUIRED_COLUMNS = [
    "store",
    "title",
    "brand",
    "price",
    "price_per_unit",
    "image",
    "url",
    "sku",
    "category",
    "scraped_at",
    "province",
]

def _to_float(x):
    try:
        if x is None or (isinstance(x, float) and pd.isna(x)):
            return None
        s = str(x).strip().replace("$", "").replace(",", "")
        return float(s)
    except Exception:
        return None

def _ensure_columns(df: pd.DataFrame) -> pd.DataFrame:
    for col in REQUIRED_COLUMNS:
        if col not in df.columns:
            df[col] = pd.NA

    df["price"] = df["price"].map(_to_float)

    for c in ["store", "brand", "title", "category", "province", "url", "image", "sku", "price_per_unit", "scraped_at"]:
        df[c] = df[c].astype("string")

    if df["store"].isna().all():
        df["store"] = "Walmart"

    return df

def _load_df() -> Tuple[pd.DataFrame, str]:
    global _df_cache, _df_mtime
    if not os.path.exists(DATA_FILE):
        empty = pd.DataFrame(columns=REQUIRED_COLUMNS)
        return _ensure_columns(empty), DATA_FILE

    mtime = os.path.getmtime(DATA_FILE)
    if _df_cache is None or _df_mtime != mtime:
        df = pd.read_csv(DATA_FILE)
        df = _ensure_columns(df)
        _df_cache = df
        _df_mtime = mtime

    return _df_cache.copy(), DATA_FILE

# Helper: convert pandas NA → None (and leave other values intact)
def _py(v):
    return None if pd.isna(v) else v

@app.get("/")
def home():
    return render_template("index.html")

@app.get("/api/health")
def api_health():
    df, path = _load_df()
    return jsonify({"ok": True, "path": path, "rows": int(len(df)), "source": "csv"})

@app.get("/static/data/<path:filename>")
def static_data(filename: str):
    safe = os.path.normpath(os.path.join(DATA_DIR, filename))
    if not safe.startswith(DATA_DIR):
        return ("Forbidden", 403)
    if not os.path.exists(safe):
        return ("Not found", 404)
    return send_from_directory(DATA_DIR, filename)

@app.get("/api/search")
def api_search():
    df, _ = _load_df()

    q = (request.args.get("q") or "").strip()
    prov = (request.args.get("province") or "").strip()
    sort_key = (request.args.get("sort") or "price-asc").strip().lower()

    try:
        page = max(1, int(request.args.get("page", DEFAULT_PAGE)))
    except Exception:
        page = DEFAULT_PAGE
    try:
        size = max(1, min(200, int(request.args.get("size", DEFAULT_SIZE))))
    except Exception:
        size = DEFAULT_SIZE

    # ---- filtering
    filtered = df

    if q:
        q_lower = q.lower()
        title_match = filtered["title"].fillna("").str.lower().str.contains(q_lower, na=False)
        brand_match = filtered["brand"].fillna("").str.lower().str.contains(q_lower, na=False)
        filtered = filtered[title_match | brand_match]

    has_province_data = "province" in filtered.columns and filtered["province"].dropna().ne("").any()
    if prov and has_province_data:
        filtered = filtered[filtered["province"].fillna("").str.upper() == prov.upper()]

    # ---- sorting
    if sort_key == "price-desc":
        filtered = filtered.sort_values(by=["price"], ascending=[False], na_position="last")
    elif sort_key == "brand":
        filtered = filtered.sort_values(by=["brand", "price"], ascending=[True, True], na_position="last")
    elif sort_key == "store":
        filtered = filtered.sort_values(by=["store", "price"], ascending=[True, True], na_position="last")
    else:
        filtered = filtered.sort_values(by=["price"], ascending=[True], na_position="last")

    # ---- pagination
    total = int(len(filtered))
    start = (page - 1) * size
    end = start + size
    page_rows = filtered.iloc[start:end]

    # ---- payload
    items = []
    for _, r in page_rows.iterrows():
        items.append({
            "store": _py(r.get("store")),
            "title": _py(r.get("title")),
            "price": float(r["price"]) if pd.notna(r.get("price")) else None,
            "price_per_unit": _py(r.get("price_per_unit")),
            "image": _py(r.get("image")),
            "url": _py(r.get("url")),
            "brand": _py(r.get("brand")),
            "sku": _py(r.get("sku")),
            "category": _py(r.get("category")),
            "province": _py(r.get("province")),
            "scraped_at": _py(r.get("scraped_at")),
        })

    return jsonify({"total": total, "page": page, "size": size, "items": items})

if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=True)
