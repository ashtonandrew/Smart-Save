import os, csv, time, re
from typing import List, Dict, Optional
from abc import ABC, abstractmethod

DATA_DIR = os.environ.get("SMARTSAVE_DATA_DIR") or os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
os.makedirs(DATA_DIR, exist_ok=True)

def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")

class BaseScraper(ABC):
    name: str = "Base"

    def __init__(self, chain: str, base_url: str, ttl_seconds: int = 3*60*60):
        self.chain = chain
        self.base_url = base_url.rstrip("/")
        self.ttl = ttl_seconds

    # cache helpers
    def _csv_name(self, query: str, province: str) -> str:
        return f"{_slug(query)}_{(province or 'NA').upper()}_{_slug(self.chain)}.csv"

    def _cache_path(self, query: str, province: str) -> str:
        return os.path.join(DATA_DIR, self._csv_name(query, province))

    def _read_cache(self, query: str, province: str) -> List[Dict]:
        path = self._cache_path(query, province)
        if not os.path.exists(path):
            return []
        age = time.time() - os.path.getmtime(path)
        if age > self.ttl:
            return []
        out = []
        with open(path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                try:
                    price = float(row["price"]) if row.get("price") else None
                except Exception:
                    price = None
                out.append({
                    "store": row.get("store"),
                    "title": row.get("title"),
                    "price": price,
                    "image": row.get("image"),
                    "url": row.get("url"),
                    "province": row.get("province"),
                    "queried_at": row.get("queried_at"),
                })
        return out

    def _write_cache(self, query: str, province: str, rows: List[Dict]):
        path = self._cache_path(query, province)
        keys = ["store", "title", "price", "image", "url", "province", "queried_at"]
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=keys)
            w.writeheader()
            for r in rows:
                w.writerow({k: r.get(k) for k in keys})

    @abstractmethod
    def fetch_html(self, query: str, province: str, timeout: int) -> Optional[str]:
        pass

    @abstractmethod
    def parse(self, html: str, limit: int) -> List[Dict]:
        pass

    def search(self, query: str, province: str = "", force_refresh: bool = False, limit: int = 12) -> List[Dict]:
        print(f"[SCRAPE] {self.chain}: q='{query}' prov='{province}' force_refresh={force_refresh}")
        if not force_refresh:
            cached = self._read_cache(query, province)
            if cached:
                print(f"[SCRAPE] {self.chain}: using cache rows={len(cached)}")
                return cached

        html = self.fetch_html(query, province, timeout=25) or ""
        items = self.parse(html, limit=limit)
        print(f"[SCRAPE] {self.chain}: parsed items={len(items)}")

        ts = str(int(time.time()))
        out = []
        for it in items:
            if it.get("price") is None:
                continue
            out.append({
                "store": self.chain,
                "title": it.get("title"),
                "price": it.get("price"),
                "image": it.get("image"),
                "url": it.get("url"),
                "province": (province or "").upper(),
                "queried_at": ts,
            })
        self._write_cache(query, province, out)
        print(f"[SCRAPE] {self.chain}: saved rows={len(out)} -> {self._csv_name(query, province)}")
        return out
