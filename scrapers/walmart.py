# scrapers/walmart.py
from urllib.parse import quote_plus, urljoin
from typing import List, Dict, Optional
from bs4 import BeautifulSoup
from .base import BaseScraper
import time

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "KHTML, like Gecko) Chrome/124.0 Safari/537.36")

class WalmartScraper(BaseScraper):
    name = "Walmart"

    def __init__(self):
        super().__init__(chain="Walmart", base_url="https://www.walmart.ca", ttl_seconds=60*60)

    def _render_page(self, url: str, timeout: int) -> Optional[str]:
        try:
            from playwright.sync_api import sync_playwright
        except Exception as e:
            print("[SCRAPE ERROR] Playwright not installed:", e)
            return None

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                ctx = browser.new_context(user_agent=UA, locale="en-CA")
                page = ctx.new_page()
                page.set_default_timeout(timeout * 1000)

                print(f"[WALMART] Visiting {url}")
                page.goto(url, wait_until="domcontentloaded")
                page.wait_for_timeout(3000)  # let JS load

                # Try to close cookie/consent modals
                for sel in [
                    "button:has-text('Accept')",
                    "button:has-text('Accept All')",
                    "button:has-text('Got it')",
                    "button[aria-label='Close']",
                ]:
                    try:
                        page.locator(sel).first.click(timeout=1000)
                        print(f"[WALMART] Clicked consent button: {sel}")
                        time.sleep(0.5)
                    except Exception:
                        pass

                # Wait for product grid
                try:
                    page.wait_for_selector("a[href*='/ip/']", timeout=8000)
                except Exception:
                    print("[WALMART] No product anchors found after wait.")

                # Scroll down gradually
                for _ in range(6):
                    page.evaluate("window.scrollBy(0, document.body.scrollHeight)")
                    page.wait_for_timeout(1000)

                html = page.content()
                browser.close()
                return html

        except Exception as e:
            print("[WALMART PLAYWRIGHT ERROR]", e)
            return None

    def fetch_html(self, query: str, province: str, timeout: int) -> str:
        url = f"{self.base_url}/search?q={quote_plus(query)}"
        html = self._render_page(url, timeout)
        if html:
            return html
        from .generic import http_get
        resp = http_get(url, timeout=timeout)
        return resp.text if (resp and getattr(resp, "status_code", 500) < 400) else ""

    def parse(self, html: str, limit: int) -> List[Dict]:
        soup = BeautifulSoup(html or "", "html.parser")
        items = []
        seen = set()

        for el in soup.select("a[href*='/ip/']"):
            title = el.get("aria-label") or el.get_text(" ", strip=True)
            if not title:
                continue
            parent = el.find_parent(["div", "li"])
            text = parent.get_text(" ", strip=True) if parent else ""
            import re
            m = re.search(r"\$?\s*(\d{1,3}(?:,\d{3})*\.\d{2})", text)
            if not m:
                continue
            price = float(m.group(1))
            img = el.find("img")
            img_url = urljoin(self.base_url, img["src"]) if img and img.get("src") else None
            url = urljoin(self.base_url, el["href"])
            key = (title.lower(), url)
            if key in seen:
                continue
            seen.add(key)
            items.append({"title": title, "price": price, "image": img_url, "url": url})
            if len(items) >= limit:
                break

        print(f"[WALMART] Parsed {len(items)} items.")
        if not items:
            with open("debug_walmart.html", "w", encoding="utf-8") as f:
                f.write(html)
            print("[WALMART] Saved debug_walmart.html for inspection.")
        return items
