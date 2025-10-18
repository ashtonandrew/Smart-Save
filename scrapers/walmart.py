from urllib.parse import quote_plus
from typing import List, Dict
from .base import BaseScraper
from .generic import http_get, parse_products

class WalmartScraper(BaseScraper):
    name = "Walmart"

    def __init__(self):
        super().__init__(chain="Walmart", base_url="https://www.walmart.ca", ttl_seconds=60*60)

    def fetch_html(self, query: str, province: str, timeout: int) -> str:
        url = f"{self.base_url}/search?q={quote_plus(query)}"
        resp = http_get(url, timeout=timeout)
        return resp.text if (resp and getattr(resp, "status_code", 500) < 400) else ""

    def parse(self, html: str, limit: int) -> List[Dict]:
        items = parse_products(html, self.base_url, limit=limit)
        # Walmart product pages usually have "/ip/" in the path:
        items = [it for it in items if "/ip/" in (it.get("url","").lower())]
        return items
