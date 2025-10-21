import re
from typing import List, Dict, Optional
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
import requests
import net_prefs

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "KHTML, like Gecko) Chrome/124.0 Safari/537.36")
HEADERS = {
    "User-Agent": UA,
    "Accept-Language": "en-CA,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Connection": "keep-alive",
}

PRICE_RE = re.compile(r"\$?\s*(\d{1,3}(?:,\d{3})*\.\d{2})")
BLOCKLIST = {
    "we respect your privacy", "cookie settings", "customer service", "about us",
    "our company", "join our team", "retail careers", "pharmacy careers",
    "connect with us", "the content you are looking for is no longer available.",
    "hi guest", "inspiration", "deals", "canadian products", "list review",
}

def http_get(url: str, timeout: int = 25) -> Optional[requests.Response]:
    with net_prefs.prefer_ipv4():
        try:
            return requests.get(url, headers=HEADERS, timeout=timeout)
        except Exception:
            return None

def extract_price(text: str) -> Optional[float]:
    if not text: return None
    m = PRICE_RE.search(text.replace(",", ""))
    if not m: return None
    try: return float(m.group(1))
    except: return None

def looks_like_product_url(base_host: str, url: str) -> bool:
    host = urlparse(url).netloc
    if base_host and host and base_host not in host:
        return False
    u = url.lower()
    return any(k in u for k in ("/product/","/products/","/ip/","/en/ip/","/p/","/pd/","/item/","/sku/","/shop/p"))

def parse_products(html: str, base_url: str, limit: int = 12) -> List[Dict]:
    soup = BeautifulSoup(html or "", "html.parser")
    items: List[Dict] = []
    seen = set()
    base_host = urlparse(base_url).netloc

    # cast a wide net for potential tiles
    candidates = soup.select(
        "[data-testid*='product'], [data-automation*='product'], [data-test*='product'], "
        "[class*='product'], li, article, div"
    )

    for el in candidates:
        a = el.find("a", href=True)
        if not a: continue
        url = urljoin(base_url, a["href"])
        if not looks_like_product_url(base_host, url):
            continue

        # title: prefer headings or explicit title attributes
        t_el = (el.find(attrs={"data-testid": re.compile("title", re.I)}) or
                el.find(attrs={"aria-label": True}) or
                el.find(["h1","h2","h3"]) or
                el.find("span"))
        title = (t_el.get("aria-label") if t_el and t_el.has_attr("aria-label")
                 else (t_el.get_text(" ", strip=True) if t_el else None))
        if not title: continue
        tnorm = title.lower().strip()
        if tnorm in BLOCKLIST or tnorm.startswith("results for"):
            continue

        # price: check explicit price nodes, fallback to any text in the element
        p_el = (el.find(attrs={"data-testid": re.compile("price", re.I)}) or
                el.find("span", string=PRICE_RE) or
                el.find("div", string=PRICE_RE))
        price_text = (p_el.get_text(" ", strip=True) if p_el else el.get_text(" ", strip=True))
        price = extract_price(price_text)
        if price is None:
            continue

        img = el.find("img")
        img_url = urljoin(base_url, img["src"]) if img and img.get("src") else None

        key = (tnorm, url)
        if key in seen: continue
        seen.add(key)

        items.append({"title": title[:200], "price": price, "image": img_url, "url": url})
        if len(items) >= limit:
            break

    return items

def playwright_render(url: str, timeout: int = 25, before: Optional[callable] = None) -> Optional[str]:
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return None
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            ctx = browser.new_context(user_agent=UA, locale="en-CA")
            page = ctx.new_page()
            page.set_default_timeout(timeout * 1000)
            if before:
                before(page)
            page.goto(url, wait_until="load")
            page.wait_for_timeout(1200)
            html = page.content()
            browser.close()
            return html
    except Exception:
        return None
