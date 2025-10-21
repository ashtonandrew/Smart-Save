# app.py
import os
import csv
from flask import Flask, jsonify, render_template, request, send_from_directory, abort

# ------------------------------------------------------------------------------
# Flask setup
# ------------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")

# Prefer a unified catalog if present; otherwise fall back to the cleaned Walmart file
DEFAULT_DATA_FILES = [
    os.path.join(DATA_DIR, "catalog_latest.csv"),
    os.path.join(DATA_DIR, "walmart_milk_clean.csv"),
    os.path.join(DATA_DIR, "walmart_milk.csv"),
]

app = Flask(
    __name__,
    static_folder="static",
    template_folder="templates",
)

# ------------------------------------------------------------------------------
# Small in-memory cache of rows to avoid re-reading the CSV on every request
# ------------------------------------------------------------------------------

_rows_cache = []
_rows_src_path = None
_rows_src_mtime = None


def _pick_data_file() -> str:
    """Return the first existing CSV path from DEFAULT_DATA_FILES."""
    for p in DEFAULT_DATA_FILES:
        if os.path.exists(p):
            return p
    return ""


def _load_rows(force: bool = False):
    """Load rows from CSV if needed; return the cached list of dicts."""
    global _rows_cache, _rows_src_path, _rows_src_mtime

    csv_path = _pick_data_file()
    if not csv_path:
        _rows_cache = []
        _rows_src_path = None
        _rows_src_mtime = None
        return _rows_cache

    mtime = os.path.getmtime(csv_path)
    need_load = (
        force
        or _rows_src_path != csv_path
        or _rows_src_mtime is None
        or mtime != _rows_src_mtime
        or not _rows_cache
    )

    if not need_load:
        return _rows_cache

    rows = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            # Normalize a few common fields so frontend can rely on them
            r["store"] = (r.get("store") or "Walmart").strip()
            r["title"] = (r.get("title") or "").strip()
            r["brand"] = (r.get("brand") or "").strip()
            r["url"] = (r.get("url") or "").strip()
            r["image"] = (r.get("image") or "").strip()
            r["sku"] = (r.get("sku") or "").strip()
            r["province"] = (r.get("province") or "").strip().upper()
            r["price"] = (r.get("price") or "").strip()
            r["price_per_unit"] = (r.get("price_per_unit") or "").strip()
            r["size_text"] = (r.get("size_text") or "").strip()
            r["scraped_at"] = (r.get("scraped_at") or "").strip()
            rows.append(r)

    _rows_cache = rows
    _rows_src_path = csv_path
    _rows_src_mtime = mtime
    return _rows_cache


# ------------------------------------------------------------------------------
# Routes
# ------------------------------------------------------------------------------

@app.get("/")
def home():
    # Renders templates/index.html which loads /static/style.css and /static/script.js
    return render_template("index.html")


@app.get("/api/search")
def api_search():
    """
    Query params:
      q          : search string (title/brand)
      province   : province code to filter (optional; if empty returns all)
      page       : 1-based page number
      size       : page size (default 50, max 200)
      refresh    : 'true' to force a CSV reload
    """
    q = (request.args.get("q") or "").strip().lower()
    province = (request.args.get("province") or "").strip().upper()
    page = max(int(request.args.get("page", 1)), 1)
    size = max(min(int(request.args.get("size", 50)), 200), 1)
    refresh = (request.args.get("refresh") or "").lower() in ("1", "true", "yes")

    rows = _load_rows(force=refresh)

    # simple full-text filter on title + brand
    if q:
        rows = [r for r in rows if q in (r["title"] + " " + r["brand"]).lower()]

    # optional province filter (will pass everything if rows lack that column)
    if province:
        rows = [r for r in rows if (r.get("province") or "").upper() in ("", province)]

    total = len(rows)
    start = (page - 1) * size
    end = start + size
    page_rows = rows[start:end]

    # IMPORTANT: include "image" so the frontend can render thumbnails
    return jsonify({
        "total": total,
        "page": page,
        "size": size,
        "items": [
            {
                "store": r.get("store", ""),
                "title": r.get("title", ""),
                "price": _safe_price(r.get("price", "")),
                "url": r.get("url", ""),
                "image": r.get("image", ""),
                "brand": r.get("brand", ""),
                "sku": r.get("sku", ""),
                "province": r.get("province", ""),
                "price_per_unit": r.get("price_per_unit", ""),
                "size_text": r.get("size_text", ""),
                "scraped_at": r.get("scraped_at", ""),
            }
            for r in page_rows
        ],
    })


@app.get("/static/data/<path:filename>")
def static_data(filename: str):
    """
    Serve CSVs from ./data so you can download them, e.g.:
      /static/data/catalog_latest.csv
      /static/data/walmart_milk_clean.csv
    """
    safe_path = os.path.normpath(os.path.join(DATA_DIR, filename))
    if not safe_path.startswith(DATA_DIR):
        return abort(403)
    if not os.path.exists(safe_path):
        return abort(404)
    return send_from_directory(DATA_DIR, filename, as_attachment=False)


@app.get("/health")
def health():
    csv_path = _pick_data_file()
    exists = bool(csv_path)
    total = len(_load_rows())
    return jsonify({
        "ok": exists,
        "csv": os.path.basename(csv_path) if csv_path else None,
        "rows_cached": total,
    })


# ------------------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------------------
def _safe_price(val):
    """Convert price to float if possible; otherwise return None."""
    try:
        s = str(val).strip().replace("$", "")
        return float(s) if s else None
    except Exception:
        return None


# ------------------------------------------------------------------------------
# Entrypoint
# ------------------------------------------------------------------------------
if __name__ == "__main__":
    # Run with debug so code changes auto-reload while developing.
    app.run(debug=True, host="127.0.0.1", port=5000)
