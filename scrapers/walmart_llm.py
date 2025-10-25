 # scrapers/walmart_llm.py
"""
Loads Walmart category pages with Playwright, grabs the HTML,
sends it to OpenAI for extraction, and appends results to a CSV.

Usage (Windows PowerShell):
.\.venv\Scripts\python.exe .\scrapers\walmart_llm.py `
  --categories-file .\data\walmart_categories.txt `
  --out .\data\walmart_all.csv `
  --province AB `
  --max-pages 6 `
  --headful
"""
from __future__ import annotations

import argparse
import csv
import os
from datetime import datetime
from urllib.parse import urlparse, parse_qs, urlencode

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright
from slugify import slugify

from .llm_extract import extract_products_from_html

CSV_FIELDS = ["title","brand","price","price_per_unit","image","url","sku","category","scraped_at"]

def _ensure_out(out_csv: str) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(out_csv)), exist_ok=True)
    if not os.path.exists(out_csv):
        with open(out_csv, "w", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=CSV_FIELDS).writeheader()

def _append_rows(out_csv: str, rows: list[dict], category_url: str) -> int:
    if not rows:
        return 0
    count = 0
    with open(out_csv, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        for r in rows:
            w.writerow({
                "title": r.get("title") or "",
                "brand": r.get("brand") or "",
                "price": r.get("price"),
                "price_per_unit": r.get("price_per_unit") or "",
                "image": r.get("image") or "",
                "url": r.get("url") or "",
                "sku": (r.get("sku") or "").strip(),
                "category": category_url,
                "scraped_at": datetime.utcnow().isoformat(timespec="seconds") + "Z"
            })
            count += 1
    return count

def _add_or_replace_page(url: str, page_num: int) -> str:
    p = urlparse(url)
    q = parse_qs(p.query)
    q["page"] = [str(page_num)]
    new_query = urlencode({k: v[0] if isinstance(v, list) else v for k, v in q.items()})
    return p._replace(query=new_query).geturl()

def _try_close_cookie_modals(page) -> None:
    for sel in (
        "button:has-text('Accept')",
        "button:has-text('Accept All')",
        "button:has-text('Close')",
        "button[aria-label='Close']",
        "button:has-text('Manage cookie settings')", # sometimes needed first
    ):
        try:
            page.locator(sel).first.click(timeout=1200)
            page.wait_for_timeout(200)
        except Exception:
            pass

def _fetch_html(page, url: str) -> str:
    page.goto(url, wait_until="domcontentloaded")
    page.wait_for_timeout(600)
    _try_close_cookie_modals(page)

    # Try to let dynamic tiles load:
    try:
        page.wait_for_load_state("networkidle", timeout=6000)
    except Exception:
        pass

    # gentle scroll
    for _ in range(4):
        page.evaluate("window.scrollBy(0, document.body.scrollHeight)")
        page.wait_for_timeout(600)

    try:
        page.wait_for_load_state("networkidle", timeout=3000)
    except Exception:
        pass

    return page.content()

def _read_category_list(path: str) -> list[str]:
    with open(path, "r", encoding="utf-8") as f:
        urls = [ln.strip() for ln in f if ln.strip() and not ln.strip().startswith("#")]
    return urls

def main():
    load_dotenv()
    ap = argparse.ArgumentParser(description="Walmart crawler via OpenAI LLM")
    ap.add_argument("--categories-file", required=True, help="Text file with category URLs (one per line).")
    ap.add_argument("--out", required=True, help="Output CSV path")
    ap.add_argument("--province", default=os.getenv("PROVINCE_DEFAULT", "AB"), help="Province tag (e.g., AB)")
    ap.add_argument("--max-pages", type=int, default=6)
    ap.add_argument("--headful", action="store_true")
    args = ap.parse_args()

    urls = _read_category_list(args.categories_file)
    if not urls:
        print(f"No URLs found in {args.categories_file}")
        return

    _ensure_out(args.out)
    total_written = 0

    with sync_playwright() as p:
        user_data = os.path.abspath(".pw_walmart_llm")
        os.makedirs(user_data, exist_ok=True)
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=user_data,
            headless=(not args.headful),
            args=["--disable-blink-features=AutomationControlled"],
            locale="en-CA",
        )
        page = ctx.new_page()
        page.set_default_timeout(25_000)

        print(f"[START] {len(urls)} category URLs, writing -> {os.path.abspath(args.out)}")

        for i, base_url in enumerate(urls, start=1):
            print(f"\n==== [{i}/{len(urls)}] {base_url} ====")
            for page_num in range(1, args.max_pages + 1):
                url = _add_or_replace_page(base_url, page_num)
                print(f"[CATEGORY] page={page_num} -> {url}")

                html = _fetch_html(page, url)
                items = extract_products_from_html(url, html, province=args.province)
                wrote = _append_rows(args.out, items, category_url=base_url)
                total_written += wrote
                print(f"[CATEGORY] extracted {len(items)} -> wrote {wrote} (running total {total_written})")

                # Heuristic stop: if we got few/no items, likely end
                if len(items) == 0 or wrote == 0:
                    # Save a debug HTML so you can inspect what the LLM saw
                    dbg = f"debug_walmart_llm_{slugify(base_url)}_p{page_num}.html"
                    with open(dbg, "w", encoding="utf-8") as f:
                        f.write(html)
                    print(f"[DEBUG] Saved {dbg}")
                    break

        ctx.close()

    print(f"\n[DONE] wrote rows: {total_written} -> {os.path.abspath(args.out)}")

if __name__ == "__main__":
    main()
