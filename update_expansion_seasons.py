#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests

SEASONS_FILE = Path("seasons.json")
PRODUCT_API = "https://www.pokemon-card.com/products/resultAPI.php"
DATE_LOWER = "20250101"
LOOKAHEAD_DAYS = 420
REQUEST_INTERVAL = 0.5
JST = timezone(timedelta(hours=9))

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
    "Referer": "https://www.pokemon-card.com/products/index.html?productType=expansion",
}


def split_yyyymmdd(value: str) -> tuple[int, int, int]:
    return int(value[:4]), int(value[4:6]), int(value[6:8])


def yyyymmdd(dt: datetime) -> str:
    return dt.strftime("%Y%m%d")


def parse_release_date(value: str) -> str:
    match = re.search(r"(\d{4})年\s*(\d{1,2})月\s*(\d{1,2})日", value)
    if not match:
        raise ValueError(f"発売日を解析できません: {value}")
    y, m, d = (int(part) for part in match.groups())
    return f"{y:04d}{m:02d}{d:02d}"


def normalize_title(value: str) -> str:
    return re.sub(r"\s+", "", value.replace("\u3000", " ")).strip()


def short_product_name(title: str) -> str:
    normalized = normalize_title(title)
    short = re.sub(r"^(強化拡張パック|ハイクラスパック|拡張パックデラックス|拡張パック)", "", normalized)
    short = short.strip("「」")
    return short or normalized


def season_name(products: list[str]) -> str:
    names: list[str] = []
    for product in products:
        short = short_product_name(product)
        if short and short not in names:
            names.append(short)
    return "・".join(names) + "環境"


def fetch_products(date_lower: str, date_upper: str) -> list[dict[str, Any]]:
    ly, lm, ld = split_yyyymmdd(date_lower)
    uy, um, ud = split_yyyymmdd(date_upper)
    base_params = {
        "productType": "expansion",
        "dateLowerY": ly,
        "dateLowerM": lm,
        "dateLowerD": ld,
        "dateUpperY": uy,
        "dateUpperM": um,
        "dateUpperD": ud,
    }

    products: list[dict[str, Any]] = []
    page = 1
    max_page = 1
    with requests.Session() as session:
        while page <= max_page:
            params = dict(base_params)
            if page > 1:
                params["page"] = page
            resp = session.get(PRODUCT_API, params=params, headers=HEADERS, timeout=30)
            resp.raise_for_status()
            payload = resp.json()
            if int(payload.get("result", 0)) != 1:
                raise RuntimeError(payload.get("errMsg") or "商品APIの取得に失敗しました")
            products.extend(payload.get("products", []))
            max_page = int(payload.get("maxPage", 1) or 1)
            page += 1
            if page <= max_page:
                time.sleep(REQUEST_INTERVAL)
    return products


def build_seasons(products: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_release: dict[str, list[str]] = defaultdict(list)
    for product in products:
        title = normalize_title(str(product.get("productTitle", "")))
        release = parse_release_date(str(product.get("releaseDate", "")))
        if title and title not in by_release[release]:
            by_release[release].append(title)

    seasons: list[dict[str, Any]] = []
    releases = sorted(by_release)
    for index, release in enumerate(releases):
        products_on_date = by_release[release]
        if index + 1 < len(releases):
            next_start = datetime.strptime(releases[index + 1], "%Y%m%d") - timedelta(days=1)
            date_to = yyyymmdd(next_start)
        else:
            date_to = "20991231"
        seasons.append(
            {
                "name": season_name(products_on_date),
                "release_date": release,
                "products": products_on_date,
                "date_from": release,
                "date_to": date_to,
            }
        )
    return seasons


def main() -> None:
    existing: dict[str, Any] = {}
    if SEASONS_FILE.exists():
        existing = json.loads(SEASONS_FILE.read_text(encoding="utf-8"))

    date_upper = yyyymmdd(datetime.now(JST) + timedelta(days=LOOKAHEAD_DAYS))
    products = fetch_products(DATE_LOWER, date_upper)
    seasons = build_seasons(products)
    if not seasons:
        raise RuntimeError("拡張パック商品が見つかりませんでした")

    updated = {
        "season_policy": "expansion_release",
        "season_source": {
            "type": "pokemon-card-products-api",
            "product_type": "expansion",
            "date_lower": DATE_LOWER,
            "lookahead_days": LOOKAHEAD_DAYS,
        },
        "current_season": existing.get("current_season", "auto"),
        "seasons": seasons,
    }

    old_text = SEASONS_FILE.read_text(encoding="utf-8") if SEASONS_FILE.exists() else ""
    new_text = json.dumps(updated, ensure_ascii=False, indent=2) + "\n"
    if old_text == new_text:
        print(f"No season changes. {len(seasons)} expansion-release seasons.")
        return

    SEASONS_FILE.write_text(new_text, encoding="utf-8")
    print(f"Updated {SEASONS_FILE}: {len(seasons)} expansion-release seasons.")
    print(f"Latest known season: {seasons[-1]['name']} ({seasons[-1]['date_from']} - {seasons[-1]['date_to']})")


if __name__ == "__main__":
    main()
