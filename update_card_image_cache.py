#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

BASE_DIR = Path(__file__).resolve().parent
DECK_DIR = BASE_DIR / "deck_lists"
CACHE_FILE = BASE_DIR / "card_image_cache.json"
CARD_DETAIL_URL_TEMPLATE = "https://www.pokemon-card.com/card-search/details.php/card/{card_id}"
IMAGE_RE = re.compile(r'<img[^>]+class=["\'][^"\']*\bfit\b[^"\']*["\'][^>]+src=["\']([^"\']+)["\'][^>]*>', re.I)
ALT_RE = re.compile(r'alt=["\']([^"\']*)["\']', re.I)
CARD_IMAGE_RE = re.compile(r'["\']([^"\']*/assets/images/card_images/large/[^"\']+\.(?:jpg|png))["\']', re.I)


def load_json(path: Path, fallback: Any) -> Any:
    if not path.exists():
        return fallback
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return fallback


def iter_deck_cards() -> dict[str, str]:
    cards: dict[str, str] = {}
    for path in sorted(DECK_DIR.glob("*.json")):
        rows = load_json(path, [])
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            card_id = str(row.get("card_id") or "").strip()
            name = str(row.get("name") or "").strip()
            if card_id and name and card_id not in cards:
                cards[card_id] = name
    return cards


def load_cache() -> dict[str, Any]:
    payload = load_json(CACHE_FILE, {})
    if not isinstance(payload, dict):
        payload = {}
    cards = payload.get("cards")
    if not isinstance(cards, dict):
        payload["cards"] = {}
    return payload


def fetch_card_image(card_id: str, timeout: float = 15.0) -> tuple[str, str]:
    detail_url = CARD_DETAIL_URL_TEMPLATE.format(card_id=card_id)
    req = Request(
        detail_url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; card-dashboard-image-cache/1.0)",
            "Accept-Language": "ja,en-US;q=0.8,en;q=0.6",
        },
    )
    with urlopen(req, timeout=timeout) as res:
        body = res.read().decode("utf-8", errors="replace")

    image_url = ""
    card_name = ""
    image_match = IMAGE_RE.search(body)
    if image_match:
        image_url = urljoin(detail_url, html.unescape(image_match.group(1)))
        alt_match = ALT_RE.search(image_match.group(0))
        if alt_match:
            card_name = html.unescape(alt_match.group(1)).strip()
    if not image_url:
        fallback_match = CARD_IMAGE_RE.search(body)
        if fallback_match:
            image_url = urljoin(detail_url, html.unescape(fallback_match.group(1)))
    return image_url, card_name


def update_cache(limit: int | None, force: bool, sleep_seconds: float, stop_after_forbidden: int) -> int:
    source_cards = iter_deck_cards()
    payload = load_cache()
    payload["schema_version"] = 1
    cache_cards: dict[str, dict[str, Any]] = payload.setdefault("cards", {})
    now = datetime.now(timezone.utc).date().isoformat()
    changed = False

    for card_id, name in source_cards.items():
        entry = cache_cards.get(card_id)
        if not isinstance(entry, dict):
            continue
        if name and entry.get("card_name") != name:
            entry["card_name"] = name
            changed = True
        detail_url = CARD_DETAIL_URL_TEMPLATE.format(card_id=card_id)
        if entry.get("detail_url") != detail_url:
            entry["detail_url"] = detail_url
            changed = True

    targets = [
        card_id
        for card_id in sorted(source_cards, key=lambda value: int(value) if value.isdigit() else value)
        if force or not str(cache_cards.get(card_id, {}).get("image_url") or "").strip()
    ]
    if limit is not None:
        targets = targets[:limit]

    updated = 0
    failed = 0
    consecutive_forbidden = 0
    total = len(targets)
    for index, card_id in enumerate(targets, 1):
        name = source_cards.get(card_id, "")
        try:
            image_url, official_name = fetch_card_image(card_id)
            consecutive_forbidden = 0
        except HTTPError as exc:
            failed += 1
            print(f"[{index}/{total}] skip {card_id} {name}: {exc}", flush=True)
            if exc.code == 403:
                consecutive_forbidden += 1
                if stop_after_forbidden and consecutive_forbidden >= stop_after_forbidden:
                    print(
                        f"Stopping early after {consecutive_forbidden} consecutive 403 responses; remaining cards will be retried next run.",
                        flush=True,
                    )
                    break
            else:
                consecutive_forbidden = 0
            continue
        except (URLError, TimeoutError, OSError) as exc:
            failed += 1
            consecutive_forbidden = 0
            print(f"[{index}/{total}] skip {card_id} {name}: {exc}", flush=True)
            continue
        if not image_url:
            failed += 1
            print(f"[{index}/{total}] skip {card_id} {name}: image not found", flush=True)
            continue

        entry = cache_cards.setdefault(card_id, {})
        entry["card_name"] = official_name or name
        entry["detail_url"] = CARD_DETAIL_URL_TEMPLATE.format(card_id=card_id)
        entry["image_url"] = image_url
        entry["fetched_at"] = now
        updated += 1
        changed = True
        if index == 1 or index % 50 == 0 or index == total:
            print(f"[{index}/{total}] cached {updated} images", flush=True)
        if sleep_seconds > 0 and index < total:
            time.sleep(sleep_seconds)

    if changed:
        payload["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        CACHE_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        f"Card image cache updated: source={len(source_cards)} cached={sum(1 for item in cache_cards.values() if str(item.get('image_url') or '').strip())} fetched={updated} failed={failed}",
        flush=True,
    )
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Update card_image_cache.json from official Pokemon card detail pages.")
    parser.add_argument("--limit", type=int, default=None, help="Fetch at most this many missing images.")
    parser.add_argument("--force", action="store_true", help="Refresh images even when already cached.")
    parser.add_argument("--sleep", type=float, default=0.03, help="Delay between requests in seconds.")
    parser.add_argument("--stop-after-forbidden", type=int, default=25, help="Stop after this many consecutive HTTP 403 responses.")
    args = parser.parse_args()
    raise SystemExit(update_cache(args.limit, args.force, args.sleep, args.stop_after_forbidden))


if __name__ == "__main__":
    main()
