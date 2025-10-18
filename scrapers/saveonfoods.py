from urllib.parse import quote_plus
from typing import List, Dict
import os
from .base import BaseScraper
from .generic import http_get, parse_products

# Default RSID (Edmonton). You can set a different store via env SAVEON_RSID.
DEFAULT_RSID = os.environ.get("SAVEON_RSID", "1982")

class SaveOnFoodsScraper(BaseScraper):
    name = "Save-On-Foods"

    def __init__(self):
        super().__init__(chain="Save-On-Foods", base_url="https://www.saveonfoods.com", ttl_seconds=2*60*60)

    def fetch_html(self, query: str, province: str, timeout: int) -> str:
        url = f"{self.base_url}/sm/pickup/rsid/{DEFAULT_RSID}/search?q={quote_plus(query)}"
        resp = http_get(url, timeout=timeout)
        return resp.text if (resp and getattr(resp, "status_code", 500) < 400) else ""

    def parse(self, html: str, limit: int) -> List[Dict]:
        items = parse_products(html, self.base_url, limit=limit)
        # Looser URL patterns (/product/, /p/, /pd/)
        items = [it for it in items if any(k in it.get("url","").lower() for k in ("/product/", "/products/", "/p/", "/pd/"))]
        return items
