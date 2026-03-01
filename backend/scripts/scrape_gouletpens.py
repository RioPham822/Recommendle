"""Scrape Goulet Pens catalog and export normalized JSON/CSV datasets."""

import csv
import json
import time
from pathlib import Path
from urllib import robotparser

import requests

BASE_URL = "https://www.gouletpens.com"
COLLECTION_URL = f"{BASE_URL}/collections/fountain-pens/products.json"

OUTPUT_DIR = Path(__file__).resolve().parents[1] / "data"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def check_robots() -> bool:
    """Return whether scraping target endpoint is allowed by robots.txt."""
    robots_url = f"{BASE_URL}/robots.txt"
    rp = robotparser.RobotFileParser()
    rp.set_url(robots_url)
    rp.read()
    return rp.can_fetch("*", COLLECTION_URL)


def fetch_products(limit: int = 250, delay: float = 0.5) -> list[dict]:
    """Fetch all paginated products from the Goulet collection endpoint."""
    products = []
    page = 1
    while True:
        params = {"limit": limit, "page": page}
        resp = requests.get(COLLECTION_URL, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        batch = data.get("products", [])
        if not batch:
            break
        products.extend(batch)
        page += 1
        time.sleep(delay)
    return products


def normalize_product(raw: dict) -> dict:
    """Normalize raw Shopify product into project dataset shape."""
    variants = raw.get("variants", [])
    prices = [float(v.get("price", 0)) for v in variants if v.get("price")]
    price_min = min(prices) if prices else None
    price_max = max(prices) if prices else None
    options = {opt.get("name"): opt.get("values", []) for opt in raw.get("options", [])}
    raw_tags = raw.get("tags") or []
    if isinstance(raw_tags, str):
        tags = [t.strip() for t in raw_tags.split(",") if t.strip()]
    else:
        tags = [str(t).strip() for t in raw_tags if str(t).strip()]
    images = raw.get("images", [])

    return {
        "category": "fountain_pens",
        "schema_version": 2,
        "source_id": str(raw.get("id")),
        "title": raw.get("title"),
        "handle": raw.get("handle"),
        "vendor": raw.get("vendor"),
        "product_type": raw.get("product_type"),
        "price_min": price_min,
        "price_max": price_max,
        "currency": "USD",
        "tags": tags,
        "options": options,
        "description": raw.get("body_html"),
        "url": f"{BASE_URL}/products/{raw.get('handle')}",
        "images": [
            {
                "url": img.get("src"),
                "alt": img.get("alt"),
                "position": img.get("position"),
            }
            for img in images
            if img.get("src")
        ],
    }


def main():
    """CLI/script entrypoint for scraping and exporting fountain-pen data."""
    if not check_robots():
        raise SystemExit("Robots.txt disallows scraping the fountain-pens collection.")

    raw_products = fetch_products()
    normalized = [normalize_product(p) for p in raw_products]

    json_path = OUTPUT_DIR / "products.json"
    csv_path = OUTPUT_DIR / "fountain_pens.csv"

    json_path.write_text(json.dumps(normalized, indent=2), encoding="utf-8")

    fieldnames = [
        "source_id",
        "title",
        "handle",
        "vendor",
        "product_type",
        "price_min",
        "price_max",
        "currency",
        "tags",
        "options",
        "description",
        "url",
        "image_url",
    ]

    with csv_path.open("w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for item in normalized:
            image_url = item["images"][0]["url"] if item["images"] else ""
            writer.writerow(
                {
                    "source_id": item["source_id"],
                    "title": item["title"],
                    "handle": item["handle"],
                    "vendor": item["vendor"],
                    "product_type": item["product_type"],
                    "price_min": item["price_min"],
                    "price_max": item["price_max"],
                    "currency": item["currency"],
                    "tags": json.dumps(item["tags"]),
                    "options": json.dumps(item["options"]),
                    "description": item["description"],
                    "url": item["url"],
                    "image_url": image_url,
                }
            )

    print(f"Saved {len(normalized)} products to {json_path} and {csv_path}")


if __name__ == "__main__":
    main()
