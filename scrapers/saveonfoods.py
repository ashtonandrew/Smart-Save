# scrapers/saveonfoods.py
from urllib.parse import quote_plus, urljoin
from typing import List, Dict, Optional
from bs4 import BeautifulSoup
import os
import re
from .base import BaseScraper

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "KHTML, like Gecko) Chrome/124.0 Safari/537.36")

# Set your store once in the terminal before running app.py:
#   $env:SAVEON_RSID = "1982"   # (example: Edmonton DT)
DEFAULT_RSID = os.environ.get("SAVEON_RSID", "1982")


class SaveOnFoodsScraper(BaseScraper):
    name = "Save-On-Foods"

    def __init__(self):
        super().__init__(
            chain="Save-On-Foods",
            base_url="https://www.saveonfoods.com",
            ttl_seconds=2 * 60 * 60,
        )

    # ------------ Playwright render ------------
    def _render(self, url: str, timeout: int) -> Optional[str]:
        try:
            from playwright.sync_api import sync_playwright
        except Exception as e:
            print("[SAVEON] Playwright not available:", e)
            return None

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                ctx = browser.new_context(user_agent=UA, locale="en-CA")
                page = ctx.new_page()
                page.set_default_timeout(timeout * 1000)

                print(f"[SAVEON] Visiting {url}")
                page.goto(url, wait_until="domcontentloaded")
                page.wait_for_timeout(2500)  # let framework boot

                # Close consent / banners if present
                for sel in (
                    "button:has-text('Accept')",
                    "button:has-text('Accept All')",
                    "button:has-text('Got it')",
                    "button[aria-label='Close']",
                ):
                    try:
                        page.locator(sel).first.click(timeout=1200)
                        print(f"[SAVEON] Clicked consent: {sel}")
                        page.wait_for_timeout(500)
                    except Exception:
                        pass

                # Wait for typical product anchors to appear
                try:
                    page.wait_for_selector("a[href*='/product/'], a[href*='/products/']", timeout=9000)
                except Exception:
                    print("[SAVEON] No product anchors after wait; continuing with current DOM.")

                # Small scroll to trigger lazy tiles
                for _ in range(4):
                    page.evaluate("window.scrollBy(0, document.body.scrollHeight)")
                    page.wait_for_timeout(800)

                html = page.content()
                browser.close()
                return html
        except Exception as e:
            print("[SAVEON PLAYWRIGHT ERROR]", e)
            return None

    # ------------ Scraper contract ------------
    def fetch_html(self, query: str, province: str, timeout: int) -> str:
        # RSID is required to see prices
        url = f"{self.base_url}/sm/pickup/rsid/{DEFAULT_RSID}/search?q={quote_plus(query)}"
        html = self._render(url, timeout=timeout)
        return html or ""

    def parse(self, html: str, limit: int) -> List[Dict]:
        soup = BeautifulSoup(html or "", "html.parser")
        items: List[Dict] = []
        seen = set()

        PRICE_RE = re.compile(r"\$?\s*(\d{1,3}(?:,\d{3})*\.\d{2})")

        # Save-On product links typically include /product/ or /products/
        anchors = soup.select("a[href*='/product/'], a[href*='/products/']")
        for a in anchors:
            href = a.get("href")
            if not href:
                continue
            url = urljoin(self.base_url, href)

            # Title: aria-label preferred; fallback to text
            title = a.get("aria-label") or a.get_text(" ", strip=True)
            if not title:
                continue

            # Price: walk up a couple of containers to find a price string
            price = None
            node = a
            for _ in range(4):
                node = node.parent
                if not node:
                    break
                text = node.get_text(" ", strip=True) or ""
                m = PRICE_RE.search(text.replace(",", ""))
                if m:
                    try:
                        price = float(m.group(1))
                        break
                    except Exception:
                        pass
            if price is None:
                continue

            # Image: look nearby for an <img>
            img = None
            node = a
            for _ in range(4):
                node = node.parent
                if not node:
                    break
                img = node.find("img")
                if img:
                    break
            img_url = urljoin(self.base_url, img["src"]) if img and img.get("src") else None

            key = (title.lower().strip(), url)
            if key in seen:
                continue
            seen.add(key)

            items.append({"title": title[:200], "price": price, "image": img_url, "url": url})
            if len(items) >= limit:
                break

        print(f"[SAVEON] Parsed {len(items)} items.")
        if not items:
            # Write what Playwright actually saw so we can fine-tune selectors if needed
            try:
                with open("debug_saveon.html", "w", encoding="utf-8") as f:
                    f.write(html or "")
                print("[SAVEON] Saved debug_saveon.html for inspection.")
            except Exception:
                pass
        return items
