# app.py
import csv, os, math, io
from urllib.parse import urlparse
from flask import Flask, jsonify, request, send_from_directory, render_template, abort, Response
import requests

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(APP_DIR, "data")

app = Flask(__name__, static_folder="static", template_folder="templates")


# ---------- Data loading ----------
def _pick_data_file():
    """Prefer the aggregated catalog if present; otherwise the Walmart clean CSV."""
    c1 = os.path.join(DATA_DIR, "catalog_latest.csv")
    c2 = os.path.join(DATA_DIR, "walmart_milk_clean.csv")
    if os.path.exists(c1): return c1
    if os.path.exists(c2): return c2
    return None

def _load_rows():
    csv_path = _pick_data_file()
    if not csv_path:
        return []
    rows = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            # normalize fields used by the API
            r["price"] = _safe_price(r.get("price"))
            r["title"] = (r.get("title") or "").strip()
            r["brand"] = (r.get("brand") or "").strip()
            r["image"] = (r.get("image") or "").strip()
            r["url"] = (r.get("url") or "").strip()
            r["sku"] = (r.get("sku") or "").strip()
            r["category"] = (r.get("category") or "").strip()
            r["scraped_at"] = (r.get("scraped_at") or "").strip()
            # annotate store for the UI (this csv is Walmart)
            if not r.get("store"):
                r["store"] = "Walmart"
            rows.append(r)
    return rows

def _safe_price(val):
    if val is None: return None
    try:
        s = str(val).strip().replace("$", "")
        return float(s) if s != "" else None
    except Exception:
        return None


# Cache the CSV into memory for quick API responses
ROWS = _load_rows()


# ---------- Routes ----------
@app.get("/")
def home():
    return render_template("index.html")


@app.get("/api/search")
def api_search():
    q = (request.args.get("q") or "").strip().lower()
    sort_key = request.args.get("sort") or "price-asc"  # price-asc | price-desc
    page = max(int(request.args.get("page", 1)), 1)
    size = min(max(int(request.args.get("size", 25)), 1), 100)

    # Filter
    filtered = []
    for r in ROWS:
        text = f"{r.get('title','')} {r.get('brand','')}".lower()
        if q and q not in text:
            continue
        filtered.append(r)

    # Sort
    def price_or_default(x, default):
        p = x.get("price")
        return p if isinstance(p, (int, float)) else default

    if sort_key == "price-desc":
        filtered.sort(key=lambda x: price_or_default(x, -1_000_000), reverse=True)
    else:
        filtered.sort(key=lambda x: price_or_default(x, 1_000_000))

    total = len(filtered)
    start = (page - 1) * size
    end = start + size
    page_rows = filtered[start:end]

    items = [
        {
            "store": r.get("store") or "Walmart",
            "title": r.get("title"),
            "url": r.get("url"),
            "image": r.get("image"),
            "price": r.get("price"),
            "price_per_unit": r.get("price_per_unit"),
            "brand": r.get("brand"),
            "sku": r.get("sku"),
            "size_text": r.get("size_text") or None,
            "scraped_at": r.get("scraped_at"),
        }
        for r in page_rows
    ]
    return jsonify({"total": total, "page": page, "size": size, "items": items})



@app.get("/health")
def health():
    csv_path = _pick_data_file()
    return jsonify({
        "ok": True,
        "csv": os.path.basename(csv_path) if csv_path else None,
        "rows_cached": len(ROWS)
    })


# Serve files from ./data for quick inspection (read-only)
@app.get("/static/data/<path:filename>")
def static_data(filename):
    # security: only allow paths under DATA_DIR
    safe_path = os.path.normpath(os.path.join(DATA_DIR, filename))
    if not safe_path.startswith(DATA_DIR):
        return abort(403)
    if not os.path.exists(safe_path):
        return abort(404)
    return send_from_directory(DATA_DIR, filename, as_attachment=False)


# ---------- Image proxy (fixes Walmart hotlinking) ----------
ALLOWED_IMAGE_HOSTS = {"i5.walmartimages.com", "i5.walmartimages.ca", "i5.walmartimages.com.mx", "images.walmart.ca"}

@app.get("/img")
def proxy_image():
    """
    Proxies remote product images to bypass CDN hotlink restrictions.
    Usage: /img?u=<encoded URL>
    Only allows Walmart image hosts & https scheme.
    """
    src = request.args.get("u", "").strip()
    if not src:
        return abort(400, "missing u")

    try:
        parsed = urlparse(src)
    except Exception:
        return abort(400, "bad url")

    if parsed.scheme != "https" or parsed.netloc.lower() not in ALLOWED_IMAGE_HOSTS:
        return abort(403, "host not allowed")

    try:
        r = requests.get(src, timeout=10, stream=True, headers={"User-Agent": "Mozilla/5.0"})
        content = r.content
        ct = r.headers.get("Content-Type", "image/jpeg")
        resp = Response(content, status=r.status_code, mimetype=ct)
        resp.headers["Cache-Control"] = "public, max-age=86400"
        return resp
    except requests.RequestException:
        return abort(504, "image fetch timeout")


if __name__ == "__main__":
    # run dev server
    app.run(debug=True, host="127.0.0.1", port=5000)
