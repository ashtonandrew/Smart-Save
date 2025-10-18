from flask import Flask, render_template, request, jsonify
from scrapers.walmart import WalmartScraper
from scrapers.saveonfoods import SaveOnFoodsScraper
from scrapers.pcx import PCExpressScraper
import os

app = Flask(__name__, template_folder="templates", static_folder="static")

# Instantiate scrapers (share Playwright where needed per request)
SCRAPERS = [
    WalmartScraper(),
    SaveOnFoodsScraper(),
    # PC Express (Real Canadian Superstore). You can add "nofrills" or "loblaws" later.
    PCExpressScraper(chain="Real Canadian Superstore", base_url="https://www.realcanadiansuperstore.ca"),
]

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/api/search")
def api_search():
    q = (request.args.get("q") or "").strip()
    province = (request.args.get("province") or "").strip().upper()
    refresh = (request.args.get("refresh") or "false").lower() == "true"
    max_items = int(request.args.get("limit") or 12)

    if not q:
        return jsonify([])

    # Run scrapers, merge, filter, sort
    results = []
    for s in SCRAPERS:
        try:
            rows = s.search(q, province=province, force_refresh=refresh, limit=max_items)
            results.extend(rows)
        except Exception as e:
            print(f"[SCRAPER ERROR] {s.name}: {e!r}")

    # Dedup + only priced + sort ascending
    seen = set()
    out = []
    for r in results:
        if r.get("price") is None:
            continue
        key = (r.get("store"), r.get("title"), r.get("url"))
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    out.sort(key=lambda x: x["price"])

    return jsonify(out)

if __name__ == "__main__":
    # Let the cache directory be configurable, but default to ./data
    os.environ.setdefault("SMARTSAVE_DATA_DIR", os.path.join(os.path.dirname(__file__), "data"))
    app.run(debug=True)
