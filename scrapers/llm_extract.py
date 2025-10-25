# scrapers/llm_extract.py
from __future__ import annotations

import os
import re
import json
from typing import List, Dict, Any
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# OpenAI SDK (>= 1.51.0)
try:
    from openai import OpenAI
except Exception as e:
    raise RuntimeError("openai>=1.51.0 is required. Did you 'pip install -r requirements.txt'?") from e

load_dotenv()

_PRICE_RE = re.compile(r"\$\s*(\d+(?:\.\d{2})?)")
_SKU_RE = re.compile(r"/ip/([^/?#]+)")

def _strip_html_for_llm(html: str) -> str:
    """
    Make the HTML smaller: drop scripts/styles, collapse whitespace.
    """
    soup = BeautifulSoup(html or "", "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    txt = soup.get_text(" ", strip=True)
    # keep it reasonably sized
    return txt[:350_000]  # ~350k chars cap to avoid huge prompts

def _chunk(text: str, size: int = 18_000, overlap: int = 1_000) -> List[str]:
    """Split text into overlapping chunks for safer LLM calls."""
    if len(text) <= size:
        return [text]
    out = []
    i = 0
    while i < len(text):
        out.append(text[i:i + size])
        i += (size - overlap)
    return out

def _model_and_client():
    model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
    base_url = os.getenv("OPENAI_BASE_URL")
    client = OpenAI(base_url=base_url) if base_url else OpenAI()
    return model, client

def _schema() -> Dict[str, Any]:
    """
    JSON schema for structured extraction.
    """
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "ProductList",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "title": {"type": "string"},
                                "brand": {"type": "string"},
                                "price": {"type": "number"},
                                "price_per_unit": {"type": "string"},
                                "image": {"type": "string"},
                                "url": {"type": "string"},
                                "sku": {"type": "string"},
                                "category_hint": {"type": "string"}
                            },
                            "required": ["title", "price", "url"]
                        }
                    }
                },
                "required": ["items"],
                "additionalProperties": False
            }
        }
    }

def _post_clean(item: Dict[str, Any], page_url: str, province: str | None) -> Dict[str, Any]:
    # try to coerce brand from title if missing
    if not item.get("brand"):
        title = (item.get("title") or "").strip()
        if title:
            head = re.split(r"[\s,/]+", title)[0:3]
            item["brand"] = " ".join(head)

    # normalize price (ensure float)
    p = item.get("price")
    if isinstance(p, str):
        m = _PRICE_RE.search(p.replace(",", ""))
        item["price"] = float(m.group(1)) if m else None

    # sku from url if missing
    if not item.get("sku") and item.get("url"):
        m = _SKU_RE.search(item["url"])
        if m:
            item["sku"] = m.group(1)

    # stamp province into category_hint if provided
    if province:
        item["category_hint"] = (item.get("category_hint") or "").strip()
        # no overwrite, just append tag context (your later pipeline can consume this)
        item["category_hint"] = (item["category_hint"] + f" [prov={province}]").strip()

    # keep only known keys
    keep = ["title", "brand", "price", "price_per_unit", "image", "url", "sku", "category_hint"]
    return {k: item.get(k) for k in keep}

def extract_products_from_html(page_url: str, html: str, *, province: str | None = None) -> List[Dict[str, Any]]:
    """
    Call OpenAI with structured output to extract product tiles from Walmart HTML.
    Returns a list of dicts.
    """
    if not html:
        return []

    model, client = _model_and_client()
    cleaned = _strip_html_for_llm(html)
    chunks = _chunk(cleaned, size=18_000, overlap=1_000)

    system = (
        "You extract product tiles from retail HTML. Only return items actually on the page.\n"
        "If a value does not exist, omit it or leave it empty. Price must be a number in CAD.\n"
        "Prefer a product card's title, price, unit-price (like $/100 g), main image URL, and product page URL (/ip/..).\n"
        "If multiple variants exist, return one per product tile on the current page only."
    )

    merged: Dict[str, Dict[str, Any]] = {}

    for idx, chunk in enumerate(chunks, start=1):
        prompt = (
            f"PAGE URL: {page_url}\n"
            f"HTML (text-only chunk {idx}/{len(chunks)}):\n"
            f"{chunk}"
        )

        resp = client.responses.create(
            model=model,
            input=[{"role": "system", "content": system},
                   {"role": "user", "content": prompt}],
            response_format=_schema(),
            temperature=0.0,
        )

        try:
            data = json.loads(resp.output[0].content[0].text)  # type: ignore
        except Exception:
            # best-effort fallback if the SDK shape changes
            text = resp.output_text  # type: ignore
            data = json.loads(text)

        for it in (data.get("items") or []):
            it = _post_clean(it, page_url, province)
            key = (it.get("sku") or it.get("url") or "").strip()
            if not key:
                continue
            # prefer the one that has price/brand/image
            prev = merged.get(key)
            score = int(bool(it.get("price"))) + int(bool(it.get("image"))) + int(bool(it.get("brand")))
            prev_score = int(bool(prev and prev.get("price"))) + int(bool(prev and prev.get("image"))) + int(bool(prev and prev.get("brand")))
            if (prev is None) or (score >= prev_score):
                merged[key] = it

    # filter only items with a numeric price
    out = [v for v in merged.values() if isinstance(v.get("price"), (int, float))]
    return out
