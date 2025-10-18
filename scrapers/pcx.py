from urllib.parse import quote_plus
from typing import List, Dict
import os
from .base import BaseScraper
from .generic import parse_products, playwright_render

# Postal code used to select a store. Override with env POSTAL_CODE.
POSTAL_CODE = os.environ.get("POSTAL_CODE", "T5J 0N3")

class PCExpressScraper(BaseScraper):
    """
    PC Express brands need a store selection before prices show.
    We use Playwright to:
      1) open home
      2) accept cookies if present
      3) open store picker, enter postal, choose first store
      4) navigate to search results and parse
    """
    name = "PC Express"

    def __init__(self, chain: str, base_url: str):
        super().__init__(chain=chain, base_url=base_url, ttl_seconds=6*60*60)

    def _preload(self, page):
        # Home
        page.goto(self.base_url, wait_until="load")
        # Cookies / consent
        for sel in ("button:has-text('Accept')", "button:has-text('Accept All')", "button:has-text('Got it')"):
            try:
                page.locator(sel).first.click(timeout=1500)
            except Exception:
                pass
        # Store picker
        try:
            page.locator("button:has-text('Choose your store')").first.click(timeout=3000)
        except Exception:
            # Fallback: sometimes picker text differs
            for alt in ("button:has-text('Pick up')", "button:has-text('Delivery')"):
                try:
                    page.locator(alt).first.click(timeout=2000)
                    break
                except Exception:
                    pass
        # Postal input (try a few likely selectors)
        typed = False
        for sel in ("input[name='postalCode']", "input[placeholder*='postal']", "input[type='text']"):
            try:
                inp = page.locator(sel).first
                if inp.count() > 0:
                    inp.fill(POSTAL_CODE)
                    typed = True
                    break
            except Exception:
                pass
        if typed:
            page.wait_for_timeout(1200)
            # Choose first available store
            for btn in ("button:has-text('Choose store')", "button:has-text('Choose Store')", "button:has-text('Select')"):
                try:
                    page.locator(btn).first.click(timeout=2500)
                    break
                except Exception:
                    pass

    def fetch_html(self, query: str, province: str, timeout: int) -> str:
        url = f"{self.base_url}/search?search={quote_plus(query)}"
        html = playwright_render(url, timeout=timeout, before=self._preload)
        return html or ""

    def parse(self, html: str, limit: int) -> List[Dict]:
        items = parse_products(html, self.base_url, limit=limit)
        # PCX product URLs usually contain /product/ or /products/
        items = [it for it in items if any(k in it.get("url","").lower() for k in ("/product/","/products/"))]
        return items
