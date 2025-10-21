# walmart_scrape.py
import argparse
import csv
import os
import re
import sys
from datetime import datetime
from typing import List, Dict, Optional
from urllib.parse import urljoin, urlencode, urlparse, parse_qs

from slugify import slugify
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "KHTML, like Gecko) Chrome/124.0 Safari/537.36")
BASE = "https://www.walmart.ca"

CSV_FIELDS = [
    "title", "brand", "price", "price_per_unit", "image",
    "url", "sku", "category", "scraped_at"
]

PRICE_RE = re.compile(r"\$?\s*(\d{1,3}(?:,\d{3})*\.\d{2})")
UNIT_RE  = re.compile(r"(\$?\s*\d+(?:\.\d+)?\s*/\s*(?:100\s*g|kg|g|L|mL|ea|each|ct))", re.I)
SKU_RE   = re.compile(r"/ip/([^/?#]+)")

# ---------------------------- helpers ----------------------------

def norm_price(text: str) -> Optional[float]:
    if not text:
        return None
    m = PRICE_RE.search(text.replace(",", ""))
    if not m:
        return None
    try:
        return float(m.group(1))
    except Exception:
        return None

def find_unit_price(text: str) -> Optional[str]:
    if not text:
        return None
    m = UNIT_RE.search(text)
    return m.group(1).strip() if m else None

def guess_brand(container_text: str, aria_label: Optional[str]) -> Optional[str]:
    if aria_label:
        t = aria_label.strip()
        head = re.split(r"[–\-|]", t)[0].strip()
        if head and head[0].isupper():
            return head.split(" ")[0] if " " in head else head
    return None

def ensure_dir(path: str):
    d = os.path.dirname(os.path.abspath(path))
    if d and not os.path.exists(d):
        os.makedirs(d, exist_ok=True)

def write_rows(path: str, rows: List[Dict]):
    ensure_dir(path)
    file_exists = os.path.exists(path)
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        if not file_exists:
            w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in CSV_FIELDS})

def handle_bot_wall(page):
    """
    If Walmart shows the 'We like real shoppers, not robots!' page (/blocked),
    pause in headful mode so the user can press & hold once.
    With a persistent context, the solved session sticks for future runs.
    """
    try:
        # quick checks
        is_blocked = ("walmart.ca/blocked" in page.url)
        if not is_blocked:
            try:
                is_blocked = page.get_by_text("We like real shoppers, not robots!", exact=False).count() > 0
            except Exception:
                is_blocked = False

        if not is_blocked:
            return

        print("[BOT WALL] Walmart anti-bot screen detected.")
        headless = page.context._options.get("headless", True)
        if headless:
            print("[BOT WALL] Headless cannot solve this. Re-run with --headful once, press & hold, then re-run headless.")
            raise SystemExit(2)

        print(">>> ACTION: In the opened browser, press & hold the button to verify. Waiting up to 120s...")
        page.wait_for_function("!window.location.href.includes('/blocked')", timeout=120_000)
        print("[BOT WALL] Passed. Continuing.")
        page.wait_for_timeout(1200)
    except Exception as e:
        print("[BOT WALL] Error/timeout while waiting:", e)
        raise

# ---------------------------- navigation ----------------------------

def set_location(page, postal_code: str):
    page.goto(BASE, wait_until="domcontentloaded")
    handle_bot_wall(page)
    page.wait_for_timeout(2000)

    # Dismiss consent / banners
    for sel in (
        "button:has-text('Accept')",
        "button:has-text('Accept All')",
        "button:has-text('Got it')",
        "button[aria-label='Close']",
    ):
        try:
            page.locator(sel).first.click(timeout=1200)
            page.wait_for_timeout(300)
        except Exception:
            pass

    # Try opening store chooser; sometimes geolocation is automatic
    opened = False
    for sel in (
        "button:has-text('Choose pickup store')",
        "button:has-text('Choose your store')",
        "button:has-text('Pickup')",
        "button:has-text('Delivery')",
        "button[aria-label*='location']",
    ):
        try:
            page.locator(sel).first.click(timeout=2000)
            opened = True
            break
        except Exception:
            continue

    if opened:
        for inp_sel in ("input[placeholder*='postal']", "input[name*='postal']", "input[type='search']", "input[type='text']"):
            try:
                inp = page.locator(inp_sel).first
                if inp and inp.count() > 0:
                    inp.fill(postal_code, timeout=1500)
                    page.wait_for_timeout(700)
                    for choose in ("button:has-text('Choose store')", "button:has-text('Select')"):
                        try:
                            page.locator(choose).first.click(timeout=2000)
                            page.wait_for_timeout(700)
                            break
                        except Exception:
                            pass
                    break
            except Exception:
                pass

def build_search_url(query: str, page_num: int) -> str:
    return f"{BASE}/search?{urlencode({'q': query, 'page': page_num})}"

# ---------------------------- extraction ----------------------------

def auto_paginate(page, per_page_goal: int = 60, min_wait_ms: int = 2000):
    """
    Scrolls, waits for network idle, and clicks 'Load more' until we see enough tiles
    or the page stops growing.
    """
    try:
        page.wait_for_load_state("networkidle", timeout=15_000)
    except Exception:
        pass
    try:
        page.wait_for_selector("a[href*='/ip/'], [data-automation-id='product-title'], [data-testid*='product']", timeout=12_000)
    except Exception:
        pass

    last_count = 0
    stable = 0
    for _ in range(30):
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(min_wait_ms)

        for sel in ("button:has-text('Load more')", "button:has-text('Show more')"):
            try:
                if page.locator(sel).first.is_visible():
                    page.locator(sel).first.click(timeout=2000)
                    page.wait_for_timeout(min_wait_ms)
            except Exception:
                pass

        try:
            page.wait_for_load_state("networkidle", timeout=5_000)
        except Exception:
            pass

        count = page.locator("a[href*='/ip/']").count()
        if count >= per_page_goal:
            break

        if count <= last_count:
            stable += 1
        else:
            stable = 0
            last_count = count

        if stable >= 3:
            break

def extract_tiles_from_html(html: str) -> List[Dict]:
    soup = BeautifulSoup(html, "html.parser")
    items: List[Dict] = []
    seen = set()

    anchors = soup.select("a[href*='/ip/']")
    if not anchors:
        anchors = soup.select("[data-testid*='product'] a[href], [data-automation-id*='product'] a[href]")

    for a in anchors:
        href = a.get("href")
        if not href:
            continue
        url = urljoin(BASE, href)
        if "/ip/" not in url:
            continue

        title = a.get("aria-label") or a.get_text(" ", strip=True)
        if not title:
            head = None
            for sel in ("[data-automation-id='product-title']", "h2", "h3", "span"):
                head = a.find_next(sel)
                if head:
                    title = head.get_text(" ", strip=True)
                    break

        # Walk up for price/unit
        tile = a
        price = None
        unit = None
        for _ in range(6):
            if not tile:
                break
            text = tile.get_text(" ", strip=True) or ""
            if price is None:
                price = norm_price(text)
            if unit is None:
                unit = find_unit_price(text)
            if price is not None and title:
                break
            tile = tile.parent

        if price is None or not title:
            continue

        # Image near the tile
        img_el = None
        node = a
        for _ in range(6):
            if not node:
                break
            img_el = node.find("img")
            if img_el and img_el.get("src"):
                break
            node = node.parent
        img = urljoin(BASE, img_el["src"]) if img_el and img_el.get("src") else ""

        # Brand guess
        brand = None
        branded = tile.find(attrs={"data-brand": True}) if tile else None
        if branded and branded.has_attr("data-brand"):
            brand = branded["data-brand"]
        if not brand:
            brand = guess_brand(tile.get_text(" ", strip=True) if tile else "", a.get("aria-label"))

        m = SKU_RE.search(url)
        sku = m.group(1) if m else ""

        key = (url,)
        if key in seen:
            continue
        seen.add(key)

        items.append({
            "title": (title or "").strip()[:250],
            "brand": brand or "",
            "price": price,
            "price_per_unit": unit or "",
            "image": img,
            "url": url,
            "sku": sku,
            "category": "",
            "scraped_at": datetime.utcnow().isoformat(timespec="seconds") + "Z"
        })
    return items

# ---------------------------- crawlers ----------------------------

def crawl_search(page, query: str, out_csv: str, max_pages: int, per_page_goal: int):
    total = 0
    for page_num in range(1, max_pages + 1):
        url = build_search_url(query, page_num)
        print(f"[SEARCH] {query} page={page_num} -> {url}")
        page.goto(url, wait_until="domcontentloaded")
        handle_bot_wall(page)
        page.wait_for_timeout(2500)

        for sel in (
            "button:has-text('Accept')",
            "button:has-text('Accept All')",
            "button:has-text('Got it')",
            "button[aria-label='Close']",
        ):
            try:
                page.locator(sel).first.click(timeout=1200)
                page.wait_for_timeout(300)
            except Exception:
                pass

        auto_paginate(page, per_page_goal=per_page_goal)

        html = page.content()
        rows = extract_tiles_from_html(html)
        for r in rows:
            r["category"] = f"search:{query}"
        write_rows(out_csv, rows)
        total += len(rows)
        print(f"[SEARCH] got {len(rows)} rows (total {total})")

        if len(rows) == 0:
            try:
                html_path = f"debug_walmart_search_{slugify(query)}_p{page_num}.html"
                png_path = f"debug_walmart_search_{slugify(query)}_p{page_num}.png"
                with open(html_path, "w", encoding="utf-8") as f:
                    f.write(html)
                page.screenshot(path=png_path, full_page=True)
                print(f"[SEARCH DEBUG] Saved {html_path} and {png_path}")
            except Exception as e:
                print("[SEARCH DEBUG] Failed to save debug artifacts:", e)
            break

def crawl_category(page, category_url: str, out_csv: str, max_pages: int, per_page_goal: int):
    total = 0
    for page_num in range(1, max_pages + 1):
        parsed = urlparse(category_url)
        q = parse_qs(parsed.query)
        q["page"] = [str(page_num)]
        new_q = urlencode({k: v[0] if isinstance(v, list) else v for k, v in q.items()})
        url = parsed._replace(query=new_q).geturl()
        if "page=" not in url:
            sep = "?" if "?" not in url else "&"
            url = f"{category_url}{sep}page={page_num}"

        print(f"[CATEGORY] page {page_num} -> {url}")
        page.goto(url, wait_until="domcontentloaded")
        handle_bot_wall(page)
        page.wait_for_timeout(2000)

        auto_paginate(page, per_page_goal=per_page_goal)

        html = page.content()
        rows = extract_tiles_from_html(html)
        for r in rows:
            r["category"] = category_url
        write_rows(out_csv, rows)
        total += len(rows)
        print(f"[CATEGORY] got {len(rows)} rows (total {total})")

        if len(rows) == 0:
            try:
                html_path = f"debug_walmart_category_p{page_num}.html"
                png_path = f"debug_walmart_category_p{page_num}.png"
                with open(html_path, "w", encoding="utf-8") as f:
                    f.write(html)
                page.screenshot(path=png_path, full_page=True)
                print(f"[CATEGORY DEBUG] Saved {html_path} and {png_path}")
            except Exception as e:
                print("[CATEGORY DEBUG] Failed to save debug artifacts:", e)
            break

# ---------------------------- main ----------------------------

def main():
    ap = argparse.ArgumentParser(description="Walmart.ca scraper (Playwright)")
    ap.add_argument("--postal", required=True, help="Postal Code (e.g., T5J 0N3)")
    ap.add_argument("--out", required=True, help="Output CSV path")
    ap.add_argument("--query", action="append", help="Search query (repeatable)")
    ap.add_argument("--category", action="append", help="Category URL (repeatable)")
    ap.add_argument("--max-pages", type=int, default=10)
    ap.add_argument("--per-page-goal", type=int, default=60)
    ap.add_argument("--headful", action="store_true", help="Visible browser for first run / debugging")
    args = ap.parse_args()

    if not args.query and not args.category:
        print("You must specify at least one --query or --category")
        sys.exit(1)

    # Ensure output exists & header is written once
    ensure_dir(args.out)
    if not os.path.exists(args.out):
        with open(args.out, "w", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=CSV_FIELDS).writeheader()

    with sync_playwright() as p:
        # Persistent context to keep cookies + bot-check state across runs
        user_data_dir = os.path.abspath(".pw_walmart")
        os.makedirs(user_data_dir, exist_ok=True)

        browser_ctx = p.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            headless=(not args.headful),
            args=["--disable-blink-features=AutomationControlled"],
            locale="en-CA",
            user_agent=UA,
        )
        page = browser_ctx.new_page()
        page.set_default_timeout(30_000)

        print(f"[INIT] Setting location for postal: {args.postal}")
        set_location(page, args.postal)

        if args.query:
            for q in args.query:
                crawl_search(page, q, args.out, max_pages=args.max_pages, per_page_goal=args.per_page_goal)

        if args.category:
            for cat in args.category:
                crawl_category(page, cat, args.out, max_pages=args.max_pages, per_page_goal=args.per_page_goal)

        browser_ctx.close()
        print(f"[DONE] CSV saved -> {os.path.abspath(args.out)}")

if __name__ == "__main__":
    main()
