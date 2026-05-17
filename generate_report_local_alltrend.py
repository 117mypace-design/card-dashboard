#!/usr/bin/env python3
"""
generate_report_local.py - Pokemon Card Meta Analysis Report Generator (完全ローカル版)

Usage:
    python generate_report_local_alltrend.py

Reads event_results/, deck_lists/, deck_types.json, and meta_cards.json to generate a
comprehensive local meta report.

Outputs:
    reports/YYYY-MM-DD.md
    reports/YYYY-MM-DD_fullperiod.json

This version does NOT call Claude / OpenAI / any external API.
Environment summary, tier judgment, and dashboard companion JSON are generated
deterministically from the stats.

Expected directory structure (same directory as this script):
    event_results/
    deck_lists/
    deck_types.json
    meta_cards.json   # optional
    reports/
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from season_utils import load_current_season, season_date_from, season_date_to

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).parent
EVENT_DIR = BASE_DIR / "event_results"
DECK_DIR = BASE_DIR / "deck_lists"
REPORT_DIR = BASE_DIR / "reports"
DECK_TYPES_FILE = BASE_DIR / "deck_types.json"
META_CARDS_FILE = BASE_DIR / "meta_cards.json"
CARD_IMAGE_CACHE_FILE = BASE_DIR / "card_image_cache.json"
DECK_PUBLIC_URL_TEMPLATE = "https://www.pokemon-card.com/deck/confirm.html/deckID/{deck_code}"
DECK_IMAGE_URL_TEMPLATE = "https://www.pokemon-card.com/deck/deckView.php/deckID/{deck_image_ref}.png"
CARD_DETAIL_URL_TEMPLATE = "https://www.pokemon-card.com/card-search/details.php/card/{card_id}"


# ---------------------------------------------------------------------------
# Deck classification engine
# ---------------------------------------------------------------------------
class DeckClassifier:
    """
    Two-level deck classifier driven by deck_types.json.

    Classification flow:
      1. Try deck_types in descending order of required-condition count.
         First match -> (archetype, deck_type) from the matched entry.
      2. If no deck_type matched, try archetypes in the same order.
         First match -> (archetype_name, archetype_name).
      3. If nothing matched -> (fallback_archetype, fallback_deck_type).

    Card counts are aggregated by name before matching, so decks split across
    art variants still classify correctly.
    """

    def __init__(self, config_path: Path):
        cfg = json.loads(config_path.read_text(encoding="utf-8"))
        self.fallback_archetype = cfg["fallback_archetype"]
        self.fallback_deck_type = cfg["fallback_deck_type"]
        self.deck_types = sorted(cfg["deck_types"], key=lambda x: -len(x["required"]))
        self.archetypes = sorted(cfg["archetypes"], key=lambda x: -len(x["required"]))
        self.deck_type_main_card_lists = {
            deck_type["name"]: self._main_cards_from_entry(deck_type["name"], deck_type.get("required", []))
            for deck_type in cfg["deck_types"]
            if deck_type.get("required")
        }
        self.archetype_main_card_lists = {
            archetype["name"]: self._main_cards_from_entry(archetype["name"], archetype.get("required", []))
            for archetype in cfg["archetypes"]
            if archetype.get("required")
        }
        self.deck_type_main_cards = {
            name: cards[0]
            for name, cards in self.deck_type_main_card_lists.items()
            if cards
        }
        self.archetype_main_cards = {
            name: cards[0]
            for name, cards in self.archetype_main_card_lists.items()
            if cards
        }

    @staticmethod
    def _main_cards_from_entry(entry_name: str, required: list[dict[str, Any]]) -> list[str]:
        card_names: list[str] = []
        for rule in required:
            card_name = str(rule.get("card", "")).strip()
            if card_name and card_name not in card_names:
                card_names.append(card_name)
        if not card_names:
            return []
        if "/" not in entry_name and "／" not in entry_name:
            return card_names[:1]

        matched: list[str] = []
        parts = [part.strip() for part in re.split(r"[／/]", entry_name) if part.strip()]
        for part in parts:
            for card_name in card_names:
                if card_name in matched:
                    continue
                if part == card_name or part in card_name or card_name in part:
                    matched.append(card_name)
                    break
        for card_name in card_names:
            if card_name not in matched:
                matched.append(card_name)
        return matched[:2]

    @staticmethod
    def _card_totals(cards: list[dict[str, Any]]) -> dict[str, int]:
        totals: dict[str, int] = defaultdict(int)
        for card in cards:
            name = card.get("name", "")
            if name:
                totals[name] += int(card.get("count", 0))
        return totals

    @staticmethod
    def _matches(totals: dict[str, int], required: list[dict[str, Any]]) -> bool:
        return all(totals.get(r["card"], 0) >= int(r["min_count"]) for r in required)

    def classify(self, cards: list[dict[str, Any]]) -> tuple[str, str]:
        totals = self._card_totals(cards)
        for deck_type in self.deck_types:
            if self._matches(totals, deck_type["required"]):
                return deck_type["archetype"], deck_type["name"]
        for archetype in self.archetypes:
            if self._matches(totals, archetype["required"]):
                return archetype["name"], archetype["name"]
        return self.fallback_archetype, self.fallback_deck_type

    def main_card_for(self, deck_type: str, archetype: str) -> str:
        cards = self.main_cards_for(deck_type, archetype)
        return cards[0] if cards else ""

    def main_cards_for(self, deck_type: str, archetype: str) -> list[str]:
        deck_value = str(deck_type or "").strip()
        archetype_value = str(archetype or "").strip()
        if deck_value and deck_value in self.deck_type_main_card_lists:
            return list(self.deck_type_main_card_lists[deck_value])
        if archetype_value and archetype_value in self.archetype_main_card_lists:
            return list(self.archetype_main_card_lists[archetype_value])
        return []


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def load_deck(deck_id: str) -> list[dict[str, Any]]:
    path = DECK_DIR / f"{deck_id}.json"
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def week_start(d: date) -> date:
    """Return the Saturday that starts the week containing d."""
    return d - timedelta(days=(d.weekday() + 2) % 7)


def week_label(d: date) -> str:
    return f"{d.month}/{d.day}週"


def safe_pct(numerator: int | float, denominator: int | float) -> float:
    return (numerator / denominator * 100.0) if denominator else 0.0


def short(name: str, maxlen: int = 20) -> str:
    return name if len(name) <= maxlen else name[: maxlen - 1] + "…"


def format_signed_pt(value: float) -> str:
    return f"{value:+.1f}pt"


def take_existing(items: list[dict[str, Any]], start: int, end: int) -> list[dict[str, Any]]:
    return items[start:end] if start < len(items) else []


def is_strict_other(name: str) -> bool:
    value = (name or "").strip().lower()
    return value in {"other", "others", "\u305d\u306e\u4ed6"}


MIN_STABLE_WEEK_EVENTS = 12


def display_rankings(items: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    return [item for item in items if not is_strict_other(item.get(key, ""))]


def comparison_weeks(weeks_sorted: list[date], week_event_counts: dict[date, int]) -> list[date]:
    stable = [week for week in weeks_sorted if week_event_counts.get(week, 0) >= MIN_STABLE_WEEK_EVENTS]
    if len(stable) >= 2:
        return stable
    return weeks_sorted


def week_display_label(week: date, event_count: int) -> str:
    suffix = "・参考値" if event_count < MIN_STABLE_WEEK_EVENTS else ""
    return f"{week_label(week)}（{event_count}大会{suffix}）"


def normalize_deck_id(deck_id: str, event_file: Path, rank: int, result_index: int) -> str:
    value = (deck_id or "").strip()
    if value:
        return value
    return f"missing-{event_file.stem}-{rank:03d}-{result_index:03d}"


# ---------------------------------------------------------------------------
# Local analysis helpers
# ---------------------------------------------------------------------------
def compute_weekly_changes(
    week_counts: dict[str, dict[date, int]],
    week_top4: dict[str, dict[date, int]],
    week_wins: dict[str, dict[date, int]],
    week_totals: dict[date, int],
    week_t4_tot: dict[date, int],
    week_win_tot: dict[date, int],
    weeks_for_delta: list[date],
    top5_types: list[str],
) -> dict[str, dict[str, float]]:
    changes: dict[str, dict[str, float]] = {}
    if len(weeks_for_delta) < 2:
        return changes

    first_week = weeks_for_delta[0]
    last_week = weeks_for_delta[-1]

    for deck_type in top5_types:
        first_usage = safe_pct(week_counts[deck_type][first_week], week_totals[first_week])
        last_usage = safe_pct(week_counts[deck_type][last_week], week_totals[last_week])
        first_b4 = safe_pct(week_top4[deck_type][first_week], week_t4_tot[first_week])
        last_b4 = safe_pct(week_top4[deck_type][last_week], week_t4_tot[last_week])
        first_win = safe_pct(week_wins[deck_type][first_week], week_win_tot[first_week])
        last_win = safe_pct(week_wins[deck_type][last_week], week_win_tot[last_week])

        changes[deck_type] = {
            "usage_delta": last_usage - first_usage,
            "b4_delta": last_b4 - first_b4,
            "win_delta": last_win - first_win,
            "first_usage": first_usage,
            "last_usage": last_usage,
            "first_win": first_win,
            "last_win": last_win,
        }
    return changes


def build_local_summary(
    deck_ranking: list[dict[str, Any]],
    date_min: date,
    date_max: date,
    total_decks: int,
    total_events: int,
    weekly_changes: dict[str, dict[str, float]],
    meta_cards: list[tuple[str, int, float]],
    meta_week_counts: dict[str, dict[date, int]],
    week_totals: dict[date, int],
    weeks_sorted: list[date],
) -> str:
    top = deck_ranking[:10]
    leader = top[0]

    overperformers = sorted(
        top,
        key=lambda x: (x["win_share"] - x["usage_rate"], x["win_share"], x["count"]),
        reverse=True,
    )
    over = overperformers[0]

    underperformers = sorted(
        top,
        key=lambda x: (x["win_share"] - x["usage_rate"], -x["usage_rate"], -x["count"]),
    )
    under = underperformers[0]

    summary_parts: list[str] = []
    summary_parts.append(
        f"{date_min}〜{date_max}の{total_events}大会・{total_decks}デッキ集計では、"
        f"{leader['deck_type']}が使用率{leader['usage_rate']:.1f}%、B4シェア{leader['top4_share']:.1f}%、"
        f"優勝シェア{leader['win_share']:.1f}%で環境の中心です。"
    )

    if over["deck_type"] == leader["deck_type"] and len(overperformers) > 1:
        over = overperformers[1]
    summary_parts.append(
        f"使用率に対して勝ち切り性能が高いのは{over['deck_type']}で、"
        f"使用率{over['usage_rate']:.1f}%に対して優勝シェア{over['win_share']:.1f}%と、"
        f"差分は{format_signed_pt(over['win_share'] - over['usage_rate'])}です。"
    )

    if under["deck_type"] == leader["deck_type"] and len(underperformers) > 1:
        under = underperformers[1]
    summary_parts.append(
        f"一方で{under['deck_type']}は使用率{under['usage_rate']:.1f}%に対して優勝シェア{under['win_share']:.1f}%で、"
        f"母数の多さに対してはやや勝ち切りが伸びにくい傾向です。"
    )

    if weekly_changes:
        rising = max(weekly_changes.items(), key=lambda x: (x[1]["usage_delta"], x[1]["win_delta"]))
        falling = min(weekly_changes.items(), key=lambda x: (x[1]["usage_delta"], x[1]["win_delta"]))
        summary_parts.append(
            f"週次推移では、{rising[0]}が使用率{format_signed_pt(rising[1]['usage_delta'])}で相対的に上昇し、"
            f"{falling[0]}は使用率{format_signed_pt(falling[1]['usage_delta'])}で相対的に下降しています。"
        )

    if meta_cards and weeks_sorted:
        top_meta_name, _, top_meta_rate = max(meta_cards, key=lambda x: x[2])
        first_week = weeks_sorted[0]
        last_week = weeks_sorted[-1]
        deltas: list[tuple[float, str, float, float]] = []
        for name, _, _ in meta_cards:
            first_rate = safe_pct(meta_week_counts[name].get(first_week, 0), week_totals[first_week])
            last_rate = safe_pct(meta_week_counts[name].get(last_week, 0), week_totals[last_week])
            deltas.append((last_rate - first_rate, name, first_rate, last_rate))
        rising_meta = max(deltas, key=lambda x: x[0])
        summary_parts.append(
            f"メタカードでは{top_meta_name}が全期間採用率{top_meta_rate:.1f}%で最も広く使われています。"
            f"週次で見ると{rising_meta[1]}は{rising_meta[2]:.1f}%→{rising_meta[3]:.1f}%で、"
            f"{format_signed_pt(rising_meta[0])}の変化でした。"
        )

    return "\n\n".join(summary_parts)


def build_tier_table(deck_ranking: list[dict[str, Any]]) -> str:
    top = deck_ranking[:10]
    if not top:
        return "_Tier判定に必要なデータが不足しています。_"

    scored: list[dict[str, Any]] = []
    for d in top:
        # 使用率だけでなく、上位進出・優勝の実績を加味する
        score = d["usage_rate"] * 0.45 + d["top4_share"] * 0.25 + d["win_share"] * 0.30
        delta = d["win_share"] - d["usage_rate"]
        scored.append({**d, "score": score, "delta": delta})

    scored.sort(key=lambda x: (x["score"], x["win_share"], x["usage_rate"]), reverse=True)

    def assign_tiers(items: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
        n = len(items)
        if n >= 8:
            counts = [2, 3, 3, n - 8]
        elif n == 7:
            counts = [2, 2, 2, 1]
        elif n == 6:
            counts = [2, 2, 1, 1]
        elif n == 5:
            counts = [1, 2, 1, 1]
        elif n == 4:
            counts = [1, 1, 1, 1]
        elif n == 3:
            counts = [1, 1, 1, 0]
        elif n == 2:
            counts = [1, 1, 0, 0]
        else:
            counts = [1, 0, 0, 0]

        tiers: dict[str, list[dict[str, Any]]] = {"Tier1": [], "Tier2": [], "Tier3": [], "Tier4": []}
        idx = 0
        for tier_name, c in zip(["Tier1", "Tier2", "Tier3", "Tier4"], counts):
            tiers[tier_name] = items[idx : idx + c]
            idx += c
        return tiers

    tiers = assign_tiers(scored)
    descriptions = {
        "Tier1": "環境最上位：使用率・優勝率ともに高水準",
        "Tier2": "準環境級：安定した戦績",
        "Tier3": "ローカル活躍レベル：対策が必要な存在",
        "Tier4": "チャレンジャー：一定数存在するが結果は限定的",
    }

    blocks: list[str] = []
    for tier_name in ["Tier1", "Tier2", "Tier3", "Tier4"]:
        items = tiers[tier_name]
        if not items:
            continue
        lines = [f"**{tier_name}**（{descriptions[tier_name]}）"]
        for item in items:
            lines.append(
                f"- {item['deck_type']}  "
                f"  使用率 {item['usage_rate']:.1f}% / B4シェア {item['top4_share']:.1f}% / 優勝シェア {item['win_share']:.1f}%"
            )
        blocks.append("\n".join(lines).replace("\u0008", ""))

    return "\n\n".join(blocks)


TIER_DESCRIPTIONS = {
    "Tier1": "使用率12%以上の最上位帯",
    "Tier2": "使用率6%以上12%未満の上位帯",
    "Tier3": "使用率4%以上6%未満の注目帯",
    "Tier4": "使用率2%以上4%未満の監視帯",
}

FIXED_TIER_THRESHOLDS = [
    {"tier": "Tier1", "min_usage": 12.0, "max_usage": None, "description": TIER_DESCRIPTIONS["Tier1"]},
    {"tier": "Tier2", "min_usage": 6.0, "max_usage": 12.0, "description": TIER_DESCRIPTIONS["Tier2"]},
    {"tier": "Tier3", "min_usage": 4.0, "max_usage": 6.0, "description": TIER_DESCRIPTIONS["Tier3"]},
    {"tier": "Tier4", "min_usage": 2.0, "max_usage": 4.0, "description": TIER_DESCRIPTIONS["Tier4"]},
]


def fixed_tier_buckets(items: list[dict[str, Any]], usage_key: str = "usage_rate") -> list[dict[str, Any]]:
    buckets: list[dict[str, Any]] = []
    for spec in FIXED_TIER_THRESHOLDS:
        min_usage = float(spec["min_usage"])
        max_usage = spec["max_usage"]
        bucket_items = [
            item
            for item in items
            if float(item.get(usage_key, 0.0) or 0.0) >= min_usage
            and (max_usage is None or float(item.get(usage_key, 0.0) or 0.0) < float(max_usage))
        ]
        bucket_items.sort(
            key=lambda item: (
                float(item.get(usage_key, 0.0) or 0.0),
                float(item.get("win_share", 0.0) or 0.0),
                float(item.get("top4_share", 0.0) or 0.0),
                int(item.get("count", 0) or 0),
            ),
            reverse=True,
        )
        if bucket_items:
            buckets.append(
                {
                    "tier": spec["tier"],
                    "description": spec["description"],
                    "items": bucket_items,
                }
            )
    return buckets


def build_tier_buckets(deck_ranking: list[dict[str, Any]]) -> list[dict[str, Any]]:
    top = deck_ranking[:10]
    if not top:
        return []
    return fixed_tier_buckets(top)


def build_tier_thresholds(deck_ranking: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [dict(spec) for spec in FIXED_TIER_THRESHOLDS]


def build_fullperiod_payload(
    *,
    title: str,
    date_min: date,
    date_max: date,
    total_decks: int,
    total_events: int,
    weeks_sorted: list[date],
    week_event_counts: dict[date, int],
    records: list[dict[str, Any]],
    meta_card_names: list[str],
    deck_ranking: list[dict[str, Any]],
    deck_visuals: dict[str, dict[str, Any]],
    season: dict[str, Any] | None = None,
) -> dict[str, Any]:
    serialized_records: list[dict[str, Any]] = []
    for record in sorted(
        records,
        key=lambda r: (
            r["date"],
            int(r["rank"]),
            r.get("deck_type") or "",
            r.get("deck_id") or "",
        ),
    ):
        serialized_records.append(
            {
                "date": record["date"].isoformat(),
                "week": record["week"].isoformat(),
                "prefecture": record["prefecture"],
                "rank": int(record["rank"]),
                "deck_id": record["deck_id"],
                "archetype": record["archetype"],
                "deck_type": record["deck_type"],
                "cards": [
                    {
                        "category": card.get("category", ""),
                        "card_id": str(card.get("card_id", "")),
                        "name": card.get("name", ""),
                        "count": int(card.get("count", 0)),
                    }
                    for card in record["cards"]
                ],
            }
        )

    return {
        "title": title,
        "season": season or {},
        "period_start": date_min.isoformat(),
        "period_end": date_max.isoformat(),
        "total_decks": total_decks,
        "total_events": total_events,
        "week_labels": {week.isoformat(): week_label(week) for week in weeks_sorted},
        "week_event_counts": {week.isoformat(): int(week_event_counts[week]) for week in weeks_sorted},
        "meta_card_names": meta_card_names,
        "tier_thresholds": build_tier_thresholds(deck_ranking),
        "records": serialized_records,
    }


def build_tier_table(deck_ranking: list[dict[str, Any]]) -> str:
    tier_buckets = build_tier_buckets(deck_ranking)
    if not tier_buckets:
        return "_Tier判定に必要なデータが不足しています。_"

    blocks: list[str] = []
    for bucket in tier_buckets:
        lines = [f"**{bucket['tier']}**（{bucket['description']}）"]
        for item in bucket["items"]:
            lines.append(
                f"- {item['deck_type']}"
                f"    使用率 {item['usage_rate']:.1f}% / B4シェア {item['top4_share']:.1f}% / 優勝シェア {item['win_share']:.1f}%"
            )
        blocks.append("\n".join(lines))

    return "\n\n".join(blocks)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def compute_weekly_changes(
    week_counts: dict[str, dict[date, int]],
    week_top4: dict[str, dict[date, int]],
    week_wins: dict[str, dict[date, int]],
    week_totals: dict[date, int],
    week_t4_tot: dict[date, int],
    week_win_tot: dict[date, int],
    weeks_for_delta: list[date],
    top5_types: list[str],
) -> dict[str, dict[str, float]]:
    changes: dict[str, dict[str, float]] = {}
    if len(weeks_for_delta) < 2:
        return changes

    first_week = weeks_for_delta[0]
    last_week = weeks_for_delta[-1]
    for deck_type in top5_types:
        first_usage = safe_pct(week_counts[deck_type][first_week], week_totals[first_week])
        last_usage = safe_pct(week_counts[deck_type][last_week], week_totals[last_week])
        first_b4 = safe_pct(week_top4[deck_type][first_week], week_t4_tot[first_week])
        last_b4 = safe_pct(week_top4[deck_type][last_week], week_t4_tot[last_week])
        first_win = safe_pct(week_wins[deck_type][first_week], week_win_tot[first_week])
        last_win = safe_pct(week_wins[deck_type][last_week], week_win_tot[last_week])
        changes[deck_type] = {
            "usage_delta": last_usage - first_usage,
            "b4_delta": last_b4 - first_b4,
            "win_delta": last_win - first_win,
            "first_usage": first_usage,
            "last_usage": last_usage,
            "first_win": first_win,
            "last_win": last_win,
        }
    return changes


def build_local_summary(
    deck_ranking: list[dict[str, Any]],
    date_min: date,
    date_max: date,
    total_decks: int,
    total_events: int,
    weekly_changes: dict[str, dict[str, float]],
    meta_cards: list[tuple[str, int, float]],
    meta_week_counts: dict[str, dict[date, int]],
    week_totals: dict[date, int],
    weeks_sorted: list[date],
    week_event_counts: dict[date, int],
    weeks_for_delta: list[date],
) -> str:
    top = display_rankings(deck_ranking, "deck_type")[:10]
    if not top:
        return "集計対象はありますが、表示用ランキングに使えるデッキ分類がありません。"

    leader = top[0]
    overperformers = sorted(
        top,
        key=lambda x: (x["win_share"] - x["usage_rate"], x["win_share"], x["count"]),
        reverse=True,
    )
    underperformers = sorted(
        top,
        key=lambda x: (x["win_share"] - x["usage_rate"], -x["usage_rate"], -x["count"]),
    )
    over = overperformers[1] if len(overperformers) > 1 and overperformers[0]["deck_type"] == leader["deck_type"] else overperformers[0]
    under = underperformers[1] if len(underperformers) > 1 and underperformers[0]["deck_type"] == leader["deck_type"] else underperformers[0]

    summary_parts = [
        (
            f"{date_min}～{date_max}の{total_events}大会・{total_decks}デッキ集計では、"
            f"{leader['deck_type']}が使用率{leader['usage_rate']:.1f}%、"
            f"B4シェア{leader['top4_share']:.1f}%、優勝シェア{leader['win_share']:.1f}%で環境の中心です。"
        ),
        (
            f"使用率に対して勝ち切り性能が高いのは{over['deck_type']}で、"
            f"使用率{over['usage_rate']:.1f}%に対して優勝シェア{over['win_share']:.1f}%、"
            f"差分は{format_signed_pt(over['win_share'] - over['usage_rate'])}です。"
        ),
        (
            f"一方で{under['deck_type']}は使用率{under['usage_rate']:.1f}%に対して"
            f"優勝シェア{under['win_share']:.1f}%で、母数の多さに対してはやや勝ち切りが伸びにくい傾向です。"
        ),
    ]

    if len(weeks_for_delta) >= 2 and weekly_changes:
        rising = max(weekly_changes.items(), key=lambda x: (x[1]["usage_delta"], x[1]["win_delta"]))
        falling = min(weekly_changes.items(), key=lambda x: (x[1]["usage_delta"], x[1]["win_delta"]))
        summary_parts.append(
            f"週次推移では、{rising[0]}が使用率{format_signed_pt(rising[1]['usage_delta'])}で相対的に上昇し、"
            f"{falling[0]}は使用率{format_signed_pt(falling[1]['usage_delta'])}で相対的に下降しています。"
        )

    if meta_cards and len(weeks_for_delta) >= 2:
        top_meta_name, _, top_meta_rate = max(meta_cards, key=lambda x: x[2])
        first_week = weeks_for_delta[0]
        last_week = weeks_for_delta[-1]
        deltas: list[tuple[float, str, float, float]] = []
        for name, _, _ in meta_cards:
            first_rate = safe_pct(meta_week_counts[name].get(first_week, 0), week_totals[first_week])
            last_rate = safe_pct(meta_week_counts[name].get(last_week, 0), week_totals[last_week])
            deltas.append((last_rate - first_rate, name, first_rate, last_rate))
        rising_meta = max(deltas, key=lambda x: x[0])
        summary_parts.append(
            f"メタカードでは{top_meta_name}が全期間採用率{top_meta_rate:.1f}%で最も広く使われています。"
            f"週次で見ると{rising_meta[1]}は{rising_meta[2]:.1f}%→{rising_meta[3]:.1f}%で、"
            f"{format_signed_pt(rising_meta[0])}の変化でした。"
        )

    unstable_weeks = [week for week in weeks_sorted if week_event_counts.get(week, 0) < MIN_STABLE_WEEK_EVENTS]
    if unstable_weeks:
        summary_parts.append(
            f"なお、{MIN_STABLE_WEEK_EVENTS}大会未満の週は参考値扱いとし、増減比較は安定週ベースで見ています。"
        )

    return "\n\n".join(summary_parts)


def build_tier_buckets(deck_ranking: list[dict[str, Any]]) -> list[dict[str, Any]]:
    top = display_rankings(deck_ranking, "deck_type")[:10]
    if not top:
        return []
    return fixed_tier_buckets(top)


def build_tier_thresholds(deck_ranking: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [dict(spec) for spec in FIXED_TIER_THRESHOLDS]


def build_tier_table(deck_ranking: list[dict[str, Any]]) -> str:
    tier_buckets = build_tier_buckets(deck_ranking)
    if not tier_buckets:
        return "_Tier表に使える表示対象デッキがありません。_"

    blocks: list[str] = []
    for bucket in tier_buckets:
        lines = [f"**{bucket['tier']}**（{bucket['description']}）"]
        for item in bucket["items"]:
            lines.append(
                f"- {item['deck_type']}    使用率 {item['usage_rate']:.1f}% / "
                f"B4シェア {item['top4_share']:.1f}% / 優勝シェア {item['win_share']:.1f}%"
            )
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def normalize_placing_score(rank: int, point: Any) -> float:
    try:
        point_num = float(point)
    except (TypeError, ValueError):
        return float(rank)
    return round(float(rank) + max(0.0, 100.0 - point_num) / 1000.0, 3)


def build_deck_public_url(deck_code: str) -> str:
    value = str(deck_code or "").strip()
    if not value or value.startswith("missing-"):
        return ""
    return DECK_PUBLIC_URL_TEMPLATE.format(deck_code=value)


def build_deck_image_url(deck_code: str) -> str:
    value = str(deck_code or "").strip()
    if not value or value.startswith("missing-"):
        return ""
    return DECK_IMAGE_URL_TEMPLATE.format(deck_image_ref=value)


def build_card_detail_url(card_id: str) -> str:
    value = str(card_id or "").strip()
    if not value:
        return ""
    return CARD_DETAIL_URL_TEMPLATE.format(card_id=value)


def load_card_image_cache() -> dict[str, dict[str, Any]]:
    if not CARD_IMAGE_CACHE_FILE.exists():
        return {}
    try:
        raw = json.loads(CARD_IMAGE_CACHE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if isinstance(raw, dict) and isinstance(raw.get("cards"), dict):
        raw_cards = raw["cards"]
    elif isinstance(raw, dict):
        raw_cards = raw
    else:
        return {}
    cache: dict[str, dict[str, Any]] = {}
    for card_id, value in raw_cards.items():
        key = str(card_id or "").strip()
        if not key:
            continue
        if isinstance(value, str):
            cache[key] = {"image_url": value}
            continue
        if isinstance(value, dict):
            cache[key] = value
    return cache


def build_deck_visual_payload(
    records: list[dict[str, Any]],
    classifier: DeckClassifier,
    card_image_cache: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    card_id_votes_by_deck_and_main: dict[str, dict[str, Counter[str]]] = defaultdict(lambda: defaultdict(Counter))
    card_id_votes_by_main_name: dict[str, Counter[str]] = defaultdict(Counter)
    archetype_names: dict[str, str] = {}

    for record in records:
        deck_name = str(record.get("deck_type", "")).strip()
        archetype_name = str(record.get("archetype", "")).strip()
        if not deck_name:
            continue
        archetype_names[deck_name] = archetype_name
        main_card_names = classifier.main_cards_for(deck_name, archetype_name)
        if not main_card_names:
            continue
        for card in record.get("cards", []):
            card_name = str(card.get("name", "")).strip()
            if card_name not in main_card_names:
                continue
            card_id = str(card.get("card_id", "")).strip()
            if card_id:
                weight = int(card.get("count", 0) or 1)
                card_id_votes_by_deck_and_main[deck_name][card_name][card_id] += weight
                card_id_votes_by_main_name[card_name][card_id] += weight

    payload: dict[str, dict[str, Any]] = {}
    for deck_name in sorted({str(record.get("deck_type", "")).strip() for record in records if record.get("deck_type")}):
        archetype_name = archetype_names.get(deck_name, "")
        main_card_names = classifier.main_cards_for(deck_name, archetype_name)
        main_cards_payload: list[dict[str, str]] = []
        for main_card_name in main_card_names:
            main_card_id = ""
            deck_counter = card_id_votes_by_deck_and_main.get(deck_name, {}).get(main_card_name, Counter())
            name_counter = card_id_votes_by_main_name.get(main_card_name, Counter())
            for candidate_id, _count in deck_counter.most_common():
                if str(card_image_cache.get(candidate_id, {}).get("image_url", "")).strip():
                    main_card_id = candidate_id
                    break
            if not main_card_id:
                for candidate_id, _count in name_counter.most_common():
                    if str(card_image_cache.get(candidate_id, {}).get("image_url", "")).strip():
                        main_card_id = candidate_id
                        break
            if not main_card_id and deck_counter:
                main_card_id = deck_counter.most_common(1)[0][0]
            if not main_card_id and name_counter:
                main_card_id = name_counter.most_common(1)[0][0]
            cache_entry = card_image_cache.get(main_card_id, {}) if main_card_id else {}
            main_card_image = str(cache_entry.get("image_url", "")).strip()
            main_cards_payload.append(
                {
                    "main_card_name": main_card_name,
                    "main_card_id": main_card_id,
                    "main_card_image": main_card_image,
                    "main_card_image_status": "available" if main_card_image else "missing",
                    "main_card_detail_url": build_card_detail_url(main_card_id),
                }
            )

        primary_card = next(
            (item for item in main_cards_payload if str(item.get("main_card_image", "")).strip()),
            main_cards_payload[0] if main_cards_payload else {},
        )
        payload[deck_name] = {
            "main_cards": main_cards_payload,
            "main_card_name": str(primary_card.get("main_card_name", "")).strip(),
            "main_card_id": str(primary_card.get("main_card_id", "")).strip(),
            "main_card_image": str(primary_card.get("main_card_image", "")).strip(),
            "main_card_image_status": str(primary_card.get("main_card_image_status", "missing")).strip() or "missing",
            "main_card_detail_url": str(primary_card.get("main_card_detail_url", "")).strip(),
        }
    return payload


def build_decklist_search_payload(records: list[dict[str, Any]]) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    deck_names_by_archetype: dict[str, set[str]] = defaultdict(set)
    archetype_names: set[str] = set()
    deck_names: set[str] = set()
    placing_values: set[int] = set()
    card_names: set[str] = set()
    event_names: set[str] = set()
    missing_deck_code_count = 0
    missing_deck_image_count = 0
    missing_placing_score_count = 0
    synthetic_deck_list_id_count = 0
    available_deck_code_count = 0
    available_public_url_count = 0

    ordered_records = sorted(
        records,
        key=lambda record: (
            -record["date"].toordinal(),
            float(record.get("placing_score", record["rank"])),
            int(record["rank"]),
            str(record["deck_type"]),
        ),
    )

    for index, record in enumerate(ordered_records, 1):
        cards = [
            {
                "card_name": str(card.get("name", "")),
                "card_id": str(card.get("card_id", "")).strip(),
                "count": int(card.get("count", 0)),
            }
            for card in record.get("cards", [])
            if card.get("name")
        ]
        deck_list_id = str(record.get("deck_id", "")).strip() or f"decklist-{index}"
        deck_code = str(record.get("deck_code", "")).strip()
        deck_public_url = str(record.get("deck_public_url", "")).strip()
        deck_image = str(record.get("deck_image", "")).strip()
        deck_image_ref = str(record.get("deck_image_ref", "")).strip()
        deck_code_status = str(record.get("deck_code_status", "missing")).strip() or "missing"
        deck_image_status = str(record.get("deck_image_status", "missing")).strip() or "missing"
        placing_score = record.get("placing_score")
        if placing_score in (None, ""):
            missing_placing_score_count += 1
            placing_score = float(record["rank"])
        if deck_list_id.startswith("missing-"):
            synthetic_deck_list_id_count += 1
        if not deck_code:
            missing_deck_code_count += 1
        else:
            available_deck_code_count += 1
        if deck_public_url:
            available_public_url_count += 1
        if not deck_image:
            missing_deck_image_count += 1

        item = {
            "deck_list_id": deck_list_id,
            "deck_name": str(record["deck_type"]),
            "archetype_name": str(record["archetype"]),
            "event_date": record["date"].isoformat(),
            "placing": int(record["rank"]),
            "placing_score": float(placing_score),
            "point": int(record.get("point", 0) or 0),
            "event_id": str(record.get("event_id", "")),
            "event_name": str(record.get("event_name", "")),
            "event_type": str(record.get("event_type", "")),
            "event_league": str(record.get("event_league", "")),
            "event_regulation": str(record.get("event_regulation", "")),
            "shop_name": str(record.get("shop_name", "")),
            "deck_code": deck_code,
            "deck_code_status": deck_code_status,
            "deck_public_url": deck_public_url,
            "deck_image": deck_image,
            "deck_image_status": deck_image_status,
            "deck_image_ref": deck_image_ref,
            "cards": cards,
        }
        items.append(item)

        archetype_name = item["archetype_name"]
        deck_name = item["deck_name"]
        archetype_names.add(archetype_name)
        deck_names.add(deck_name)
        deck_names_by_archetype[archetype_name].add(deck_name)
        placing_values.add(int(item["placing"]))
        if item["event_name"]:
            event_names.add(item["event_name"])
        for card in cards:
            card_name = str(card["card_name"]).strip()
            if card_name:
                card_names.add(card_name)

    return {
        "schema_version": 2,
        "sort": {
            "primary": "event_date",
            "primary_direction": "desc",
            "secondary": "placing_score",
            "secondary_direction": "asc",
        },
        "templates": {
            "deck_public_url_template": DECK_PUBLIC_URL_TEMPLATE,
            "deck_image_url_template": DECK_IMAGE_URL_TEMPLATE,
            "deck_image_ref_field": "deck_image_ref",
        },
        "filter_options": {
            "archetype_names": sorted(archetype_names),
            "deck_names": sorted(deck_names),
            "deck_names_by_archetype": {
                archetype_name: sorted(names)
                for archetype_name, names in sorted(deck_names_by_archetype.items())
            },
            "placing_values": sorted(placing_values),
            "card_names": sorted(card_names),
            "event_names": sorted(event_names),
        },
        "data_quality": {
            "item_count": len(items),
            "synthetic_deck_list_id_count": synthetic_deck_list_id_count,
            "available_deck_code_count": available_deck_code_count,
            "missing_deck_code_count": missing_deck_code_count,
            "available_public_url_count": available_public_url_count,
            "missing_deck_image_count": missing_deck_image_count,
            "missing_placing_score_count": missing_placing_score_count,
            "deck_code_strategy": "deck_id_as_code_when_available",
            "deck_public_url_strategy": "official_confirm_url_from_deck_code",
            "deck_image_strategy": "official_deck_view_png_from_deck_code",
            "placing_score_strategy": "rank_plus_inverse_point",
        },
        "items": items,
    }


def build_card_category_lookup(records: list[dict[str, Any]]) -> dict[str, str]:
    category_counts: dict[str, Counter[str]] = defaultdict(Counter)
    for record in records:
        for card in record.get("cards", []):
            name = str(card.get("name", "")).strip()
            category = str(card.get("category", "")).strip()
            if not name or not category:
                continue
            category_counts[name][category] += 1

    return {
        name: counts.most_common(1)[0][0]
        for name, counts in sorted(category_counts.items())
        if counts
    }


def build_fullperiod_payload(
    *,
    title: str,
    date_min: date,
    date_max: date,
    total_decks: int,
    total_events: int,
    weeks_sorted: list[date],
    week_event_counts: dict[date, int],
    records: list[dict[str, Any]],
    meta_card_names: list[str],
    deck_ranking: list[dict[str, Any]],
    deck_visuals: dict[str, dict[str, Any]],
    season: dict[str, Any] | None = None,
) -> dict[str, Any]:
    weeks_data: dict[str, Any] = {}
    synthetic_deck_ids = 0
    records_without_cards = 0

    for week in weeks_sorted:
        week_rows = [record for record in records if record["week"] == week]
        deck_stats: dict[str, list[Any]] = {}
        archetype_stats: dict[str, list[int]] = {}
        card_stats: dict[str, list[int]] = {}
        deck_card_stats: dict[str, dict[str, list[int]]] = {}
        archetype_card_stats: dict[str, dict[str, list[int]]] = {}
        total_top4 = 0
        total_wins = 0

        for record in week_rows:
            deck_type = record["deck_type"]
            archetype = record["archetype"]
            rank = int(record["rank"])
            cards = record["cards"]
            if str(record.get("deck_id", "")).startswith("missing-"):
                synthetic_deck_ids += 1
            if not cards:
                records_without_cards += 1

            deck_entry = deck_stats.setdefault(deck_type, [0, 0, 0, archetype])
            arch_entry = archetype_stats.setdefault(archetype, [0, 0, 0])
            deck_entry[0] += 1
            arch_entry[0] += 1

            if rank <= 4:
                total_top4 += 1
                deck_entry[1] += 1
                arch_entry[1] += 1
            if rank == 1:
                total_wins += 1
                deck_entry[2] += 1
                arch_entry[2] += 1

            card_totals: dict[str, int] = defaultdict(int)
            for card in cards:
                name = card.get("name", "")
                if not name:
                    continue
                card_totals[name] += int(card.get("count", 0))

            if not card_totals:
                continue

            deck_card_bucket = deck_card_stats.setdefault(deck_type, {})
            archetype_card_bucket = archetype_card_stats.setdefault(archetype, {})
            for name, count in card_totals.items():
                card_entry = card_stats.setdefault(name, [0, 0])
                card_entry[0] += 1
                card_entry[1] += count
                deck_card_entry = deck_card_bucket.setdefault(name, [0, 0])
                deck_card_entry[0] += 1
                deck_card_entry[1] += count
                archetype_card_entry = archetype_card_bucket.setdefault(name, [0, 0])
                archetype_card_entry[0] += 1
                archetype_card_entry[1] += count

        weeks_data[week.isoformat()] = {
            "totals": {
                "decks": len(week_rows),
                "top4": total_top4,
                "wins": total_wins,
                "stable": week_event_counts[week] >= MIN_STABLE_WEEK_EVENTS,
            },
            "decks": deck_stats,
            "archetypes": archetype_stats,
            "cards": card_stats,
            "deck_cards": deck_card_stats,
            "archetype_cards": archetype_card_stats,
        }

    return {
        "title": title,
        "season": season or {},
        "period_start": date_min.isoformat(),
        "period_end": date_max.isoformat(),
        "total_decks": total_decks,
        "total_events": total_events,
        "week_labels": {week.isoformat(): week_label(week) for week in weeks_sorted},
        "week_event_counts": {week.isoformat(): int(week_event_counts[week]) for week in weeks_sorted},
        "stable_week_min_events": MIN_STABLE_WEEK_EVENTS,
        "display_exclusions": ["その他"],
        "meta_card_names": meta_card_names,
        "tier_thresholds": build_tier_thresholds(deck_ranking),
        "deck_visuals": deck_visuals,
        "card_categories": build_card_category_lookup(records),
        "data_quality": {
            "synthetic_deck_ids": synthetic_deck_ids,
            "records_without_cards": records_without_cards,
        },
        "decklist_search": build_decklist_search_payload(records),
        "weeks_data": weeks_data,
    }


def main() -> None:
    REPORT_DIR.mkdir(exist_ok=True)

    if not DECK_TYPES_FILE.exists():
        print(f"ERROR: {DECK_TYPES_FILE} not found.", flush=True)
        sys.exit(1)

    classifier = DeckClassifier(DECK_TYPES_FILE)
    print(
        f"Loaded {len(classifier.deck_types)} deck types, {len(classifier.archetypes)} archetypes from {DECK_TYPES_FILE.name}",
        flush=True,
    )

    print("Loading event results ...", flush=True)
    season = load_current_season()
    season_start = season_date_from(season)
    season_end = season_date_to(season)
    print(
        f"Season: {season['name']} ({season_start.isoformat()} - {season_end.isoformat()})",
        flush=True,
    )
    records: list[dict[str, Any]] = []
    included_event_ids: set[str] = set()
    event_files = sorted(EVENT_DIR.glob("*.json"))

    for event_file in event_files:
        try:
            event_data = json.loads(event_file.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"  Skip {event_file.name}: {e}", flush=True)
            continue

        event = event_data.get("event", {})
        date_str = event.get("eventDate", {}).get("date", "")
        if not date_str:
            continue

        try:
            event_date = datetime.strptime(date_str[:10], "%Y-%m-%d").date()
        except Exception:
            continue
        if event_date < season_start or event_date > season_end:
            continue

        prefecture = event.get("prefecture_name", "不明")
        event_id = event_file.stem
        included_event_ids.add(event_id)
        event_name = event.get("event_title", "")
        event_type = event.get("event_type_title", "")
        shop_name = event.get("shopName", "")
        event_league = event.get("league") or event.get("event_kbn") or ""
        event_regulation = event.get("regulation", "")
        for result_index, result in enumerate(event_data.get("results", []), 1):
            rank = int(result.get("rank", 999))
            deck_id = normalize_deck_id(result.get("deck_id", ""), event_file, rank, result_index)
            point = int(result.get("point", 0) or 0)
            placing_score = normalize_placing_score(rank, result.get("point"))
            deck_code = "" if deck_id.startswith("missing-") else deck_id
            cards = load_deck(deck_id)
            archetype, deck_type = classifier.classify(cards)
            records.append(
                {
                    "event_id": event_id,
                    "event_name": event_name,
                    "event_type": event_type,
                    "event_league": event_league,
                    "event_regulation": event_regulation,
                    "date": event_date,
                    "week": week_start(event_date),
                    "prefecture": prefecture,
                    "shop_name": shop_name,
                    "rank": rank,
                    "point": point,
                    "placing_score": placing_score,
                    "deck_id": deck_id,
                    "deck_code": deck_code,
                    "deck_public_url": build_deck_public_url(deck_code),
                    "deck_image": build_deck_image_url(deck_code),
                    "deck_image_ref": deck_code,
                    "deck_code_status": "available" if deck_code else "synthetic_missing",
                    "deck_image_status": "available" if deck_code else "missing",
                    "archetype": archetype,
                    "deck_type": deck_type,
                    "cards": cards,
                }
            )

    total_decks = len(records)
    total_events = len(included_event_ids)
    print(f"  {total_decks} records from {total_events} events", flush=True)
    if total_decks == 0:
        print("No records found. Exiting.", flush=True)
        sys.exit(1)

    card_image_cache = load_card_image_cache()
    deck_visuals = build_deck_visual_payload(records, classifier, card_image_cache)
    available_main_card_images = sum(
        1 for item in deck_visuals.values() if str(item.get("main_card_image", "")).strip()
    )
    print(
        f"Loaded {available_main_card_images}/{len(deck_visuals)} main-card images from {CARD_IMAGE_CACHE_FILE.name}",
        flush=True,
    )

    date_min = min(r["date"] for r in records)
    date_max = max(r["date"] for r in records)
    total_top4 = sum(1 for r in records if r["rank"] <= 4)
    total_wins = sum(1 for r in records if r["rank"] == 1)

    print("Aggregating archetype / deck type statistics ...", flush=True)
    arch_stats: dict[str, dict[str, int]] = defaultdict(lambda: {"count": 0, "top4": 0, "wins": 0})
    for r in records:
        arch_stats[r["archetype"]]["count"] += 1
        if r["rank"] <= 4:
            arch_stats[r["archetype"]]["top4"] += 1
        if r["rank"] == 1:
            arch_stats[r["archetype"]]["wins"] += 1

    archetype_ranking = sorted(
        [
            {
                "archetype": arch,
                "count": s["count"],
                "usage_rate": safe_pct(s["count"], total_decks),
                "top4": s["top4"],
                "top4_share": safe_pct(s["top4"], total_top4),
                "wins": s["wins"],
                "win_share": safe_pct(s["wins"], total_wins),
            }
            for arch, s in arch_stats.items()
        ],
        key=lambda x: (-x["count"], -x["wins"]),
    )

    type_stats: dict[str, dict[str, Any]] = defaultdict(lambda: {"count": 0, "top4": 0, "wins": 0, "archetype": ""})
    for r in records:
        dt = r["deck_type"]
        type_stats[dt]["count"] += 1
        type_stats[dt]["archetype"] = r["archetype"]
        if r["rank"] <= 4:
            type_stats[dt]["top4"] += 1
        if r["rank"] == 1:
            type_stats[dt]["wins"] += 1

    deck_ranking = sorted(
        [
            {
                "deck_type": dt,
                "archetype": s["archetype"],
                "count": s["count"],
                "usage_rate": safe_pct(s["count"], total_decks),
                "top4": s["top4"],
                "top4_share": safe_pct(s["top4"], total_top4),
                "wins": s["wins"],
                "win_share": safe_pct(s["wins"], total_wins),
            }
            for dt, s in type_stats.items()
        ],
        key=lambda x: (-x["count"], -x["wins"]),
    )
    archetype_display_ranking = display_rankings(archetype_ranking, "archetype")
    deck_display_ranking = display_rankings(deck_ranking, "deck_type")

    print("Computing weekly trends ...", flush=True)
    top5_types = [d["deck_type"] for d in deck_display_ranking[:5]]
    week_counts: dict[str, dict[date, int]] = defaultdict(lambda: defaultdict(int))
    week_top4: dict[str, dict[date, int]] = defaultdict(lambda: defaultdict(int))
    week_wins: dict[str, dict[date, int]] = defaultdict(lambda: defaultdict(int))
    week_totals: dict[date, int] = defaultdict(int)
    week_t4_tot: dict[date, int] = defaultdict(int)
    week_win_tot: dict[date, int] = defaultdict(int)
    week_event_counts: dict[date, int] = defaultdict(int)

    for r in records:
        w = r["week"]
        dt = r["deck_type"]
        week_counts[dt][w] += 1
        week_totals[w] += 1
        if r["rank"] <= 4:
            week_top4[dt][w] += 1
            week_t4_tot[w] += 1
        if r["rank"] == 1:
            week_wins[dt][w] += 1
            week_win_tot[w] += 1
            week_event_counts[w] += 1

    weeks_sorted = sorted(week_totals.keys())
    weeks_for_delta = comparison_weeks(weeks_sorted, week_event_counts)
    weekly_changes = compute_weekly_changes(
        week_counts=week_counts,
        week_top4=week_top4,
        week_wins=week_wins,
        week_totals=week_totals,
        week_t4_tot=week_t4_tot,
        week_win_tot=week_win_tot,
        weeks_for_delta=weeks_for_delta,
        top5_types=top5_types,
    )

    print("Computing meta card adoption rates ...", flush=True)
    meta_card_names: list[str] = []
    meta_cards: list[tuple[str, int, float]] = []
    meta_week_counts: dict[str, dict[date, int]] = {}
    if META_CARDS_FILE.exists():
        meta_card_names = json.loads(META_CARDS_FILE.read_text(encoding="utf-8")).get("meta_cards", [])
        card_deck_count: dict[str, int] = defaultdict(int)
        for r in records:
            seen: set[str] = set()
            for card in r["cards"]:
                name = card.get("name", "")
                if name and name not in seen:
                    card_deck_count[name] += 1
                    seen.add(name)

        meta_cards = [(name, card_deck_count[name], safe_pct(card_deck_count[name], total_decks)) for name in meta_card_names]
        meta_week_counts = {name: defaultdict(int) for name in meta_card_names}
        for r in records:
            seen: set[str] = set()
            for card in r["cards"]:
                name = card.get("name", "")
                if name and name not in seen and name in meta_week_counts:
                    meta_week_counts[name][r["week"]] += 1
                    seen.add(name)
    else:
        print("  meta_cards.json not found - skipping section 5", flush=True)

    print("Analysing top deck compositions ...", flush=True)
    top3_types = [d["deck_type"] for d in deck_display_ranking[:3]]
    top3_analysis: dict[str, dict[str, Any]] = {}
    for dt in top3_types:
        dt_records = [r for r in records if r["deck_type"] == dt]
        dt_total = len(dt_records)
        card_cnt: dict[str, int] = defaultdict(int)
        for r in dt_records:
            seen: set[str] = set()
            for card in r["cards"]:
                name = card.get("name", "")
                if name and name not in seen:
                    card_cnt[name] += 1
                    seen.add(name)
        top3_analysis[dt] = {
            "total": dt_total,
            "archetype": type_stats[dt]["archetype"],
            "cards": sorted(
                [(n, c, safe_pct(c, dt_total)) for n, c in card_cnt.items()],
                key=lambda x: -x[2],
            )[:15],
        }

    print("Generating local summary / tier table ...", flush=True)
    summary = build_local_summary(
        deck_ranking=deck_ranking,
        date_min=date_min,
        date_max=date_max,
        total_decks=total_decks,
        total_events=total_events,
        weekly_changes=weekly_changes,
        meta_cards=meta_cards,
        meta_week_counts=meta_week_counts,
        week_totals=week_totals,
        weeks_sorted=weeks_sorted,
        week_event_counts=week_event_counts,
        weeks_for_delta=weeks_for_delta,
    )
    tier_body = build_tier_table(deck_ranking)
    summary = (
        "_このレポートの『環境サマリー』『Tier表』は、外部AIではなくローカルのルールベース判定で生成しています。_\n\n"
        + summary
    )

    print("Building Markdown report ...", flush=True)
    today = date.today()
    report_path = REPORT_DIR / f"{today}.md"
    fullperiod_path = REPORT_DIR / f"{today}_fullperiod.json"
    report_title = f"ポケモンカード メタレポート {today}"

    lines: list[str] = []
    lines += [
        f"# {report_title}",
        "",
        f"> 環境区分: {season['name']}  ",
        f"> 集計期間: {date_min} 〜 {date_max}  ",
        f"> 総エントリー数: {total_decks} デッキ / {total_events} 大会",
        "",
        "---",
        "",
    ]

    lines += ["## 1. 環境サマリー", "", summary, ""]
    lines += ["## 2. Tier表", "", tier_body, ""]

    lines += [
        "## 3a. アーキタイプ別 使用率・優勝率 TOP10（レベル1）",
        "",
        "| 順位 | アーキタイプ | 使用数 | 使用率 | B4シェア | 優勝シェア |",
        "|:----:|------------|------:|------:|-------:|--------:|",
    ]
    for i, a in enumerate(archetype_display_ranking[:10], 1):
        lines.append(
            f"| {i} | {a['archetype']} | {a['count']} | {a['usage_rate']:.1f}% | {a['top4_share']:.1f}% | {a['win_share']:.1f}% |"
        )
    lines.append("")

    lines += [
        "## 3b. デッキタイプ別 使用率・優勝率 TOP10（レベル2）",
        "",
        "| 順位 | デッキタイプ | アーキタイプ | 使用数 | 使用率 | B4シェア | 優勝シェア |",
        "|:----:|------------|------------|------:|------:|-------:|--------:|",
    ]
    for i, d in enumerate(deck_display_ranking[:10], 1):
        lines.append(
            f"| {i} | {d['deck_type']} | {d['archetype']} | {d['count']} | {d['usage_rate']:.1f}% | {d['top4_share']:.1f}% | {d['win_share']:.1f}% |"
        )
    lines.append("")

    def weekly_table(header: str, value_fn) -> list[str]:
        cols = ["週"] + [short(t) for t in top5_types]
        sep = [":---:"] + ["---:"] * len(top5_types)
        out = [header, "", "| " + " | ".join(cols) + " |", "| " + " | ".join(sep) + " |"]
        for week in weeks_sorted:
            row = [week_display_label(week, week_event_counts[week])] + [value_fn(dt, week) for dt in top5_types]
            out.append("| " + " | ".join(row) + " |")
        out.append("")
        return out

    lines += ["## 4. 週別推移 TOP5", "", f"> {MIN_STABLE_WEEK_EVENTS}大会未満の週は参考値扱いです。", ""]
    lines += weekly_table(
        "### 4a. 週別 使用率推移",
        lambda dt, w: f"{safe_pct(week_counts[dt][w], week_totals[w]):.1f}%" if week_totals[w] else "—",
    )
    lines += weekly_table(
        "### 4b. 週別 B4シェア推移",
        lambda dt, w: f"{safe_pct(week_top4[dt][w], week_t4_tot[w]):.1f}%" if week_t4_tot[w] else "—",
    )
    lines += weekly_table(
        "### 4c. 週別 優勝シェア推移",
        lambda dt, w: f"{safe_pct(week_wins[dt][w], week_win_tot[w]):.1f}%" if week_win_tot[w] else "—",
    )

    if meta_card_names:
        lines += [
            "## 5. メタカード採用率",
            "",
            "### 5a. 全期間採用率",
            "",
            "| カード名 | 採用デッキ数 | 採用率 |",
            "|---------|----------:|------:|",
        ]
        for name, cnt, rate in meta_cards:
            lines.append(f"| {name} | {cnt} | {rate:.1f}% |")
        lines.append("")

        lines += ["### 5b. 週別採用率推移", ""]
        header_cols = ["週"] + meta_card_names
        sep_cols = [":---:"] + ["---:"] * len(meta_card_names)
        lines.append("| " + " | ".join(header_cols) + " |")
        lines.append("| " + " | ".join(sep_cols) + " |")
        for week in weeks_sorted:
            wt = week_totals[week]
            row = [week_display_label(week, week_event_counts[week])]
            for name in meta_card_names:
                rate = safe_pct(meta_week_counts[name].get(week, 0), wt)
                row.append(f"{rate:.1f}%")
            lines.append("| " + " | ".join(row) + " |")
        lines.append("")

    lines += ["## 6. 注目デッキのカード採用傾向（TOP3デッキ）", ""]
    for rank_idx, dt in enumerate(top3_types, 1):
        info = top3_analysis[dt]
        lines += [
            f"### {rank_idx}位: {dt}（{info['archetype']} / {info['total']} デッキ）",
            "",
            "| カード名 | 採用数 | 採用率 |",
            "|---------|------:|------:|",
        ]
        for name, cnt, rate in info["cards"]:
            lines.append(f"| {name} | {cnt} | {rate:.1f}% |")
        lines.append("")

    report_content = "\n".join(lines)
    report_path.write_text(report_content, encoding="utf-8")
    print(f"\nReport saved -> {report_path}", flush=True)

    fullperiod_payload = build_fullperiod_payload(
        title=report_title,
        date_min=date_min,
        date_max=date_max,
        total_decks=total_decks,
        total_events=total_events,
        weeks_sorted=weeks_sorted,
        week_event_counts=week_event_counts,
        records=records,
        meta_card_names=meta_card_names,
        deck_ranking=deck_ranking,
        deck_visuals=deck_visuals,
        season=season,
    )
    fullperiod_path.write_text(
        json.dumps(fullperiod_payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    print(f"Full-period data saved -> {fullperiod_path}", flush=True)


if __name__ == "__main__":
    main()
