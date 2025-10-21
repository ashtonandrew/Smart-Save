# app.py
from flask import Flask, render_template, jsonify, request
from pathlib import Path
import csv

app = Flask(__name__)

# Paths
ROOT = Path(__file__).parent
DATA_PATH = ROOT / "data" / "walmart_milk_clean.csv"

def try_float(x):
    try:
        return float(x)
    except:
        return None

def load_walmart_rows():
    """Load cleaned Walmart rows from CSV and normalize a bit."""
    rows = []
    if not DATA_PATH.exists():
        return rows
    with DATA_PATH.open(newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            title = (row.get("title") or "").strip()
            url = (row.get("url") or "").strip()
            if not title or not url:
                continue
            rows.append({
                "store": "Walmart",
                "title": title,
                "brand": (row.get("brand") or "").strip(),
                "price": try_float(row.get("price")),
                "price_per_unit": (row.get("price_per_unit") or "").strip(),
                "image": (row.get("image") or "").strip(),
                "url": url,
                "sku": (row.get("sku") or "").strip(),
                "scraped_at": (row.get("scraped_at") or "").strip(),
            })
    return rows

@app.route("/")
def home():
    # templates/index.html references static/style.css and static/script.js via url_for
    return render_template("index.html")

@app.route("/api/health")
def health():
    return jsonify({
        "status": "ok",
        "csv_found": DATA_PATH.exists(),
        "csv_path": str(DATA_PATH)
    })

@app.route("/api/search")
def api_search():
    """
    Example:
      /api/search?q=milk&province=AB&refresh=true

    - q:        search term (required-ish; if empty we return everything)
    - province: currently not used for Walmart, but accepted for future stores
    - refresh:  accepted but ignored here (we just read the cleaned CSV)
    """
    q = (request.args.get("q") or "").strip().lower()
    _province = (request.args.get("province") or "").strip().upper()
    # refresh flag is accepted but not used in this minimal server
    # refresh = request.args.get("refresh") in ("1", "true", "True")

    rows = load_walmart_rows()

    # Filter by query if provided
    if q:
        rows = [r for r in rows if q in r["title"].lower()]

    # Basic sort: by price (unknowns last), then title
    def sort_key(r):
        p = r["price"]
        return (p is None, p if p is not None else 0, r["title"].lower())

    rows.sort(key=sort_key)

    # Send back only what your frontend expects (it currently uses store,title,price,url)
    payload = [
        {
            "store": r["store"],
            "title": r["title"],
            "price": r["price"],
            "url": r["url"],
            "image": r["image"],
            "brand": r["brand"],
            "sku": r["sku"],
            "price_per_unit": r["price_per_unit"],
            "scraped_at": r["scraped_at"],
        }
        for r in rows
    ]
    return jsonify(payload)

if __name__ == "__main__":
    # Run the dev server:  http://127.0.0.1:5000
    app.run(debug=True, host="127.0.0.1", port=5000)
