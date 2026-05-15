from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

SEASONS_FILE = Path("seasons.json")
AUTO_CURRENT_SEASON = "auto"
JST = timezone(timedelta(hours=9))


def today_jst() -> date:
    return datetime.now(JST).date()


def parse_yyyymmdd(value: str) -> date:
    return datetime.strptime(str(value), "%Y%m%d").date()


def yyyymmdd(value: date) -> str:
    return value.strftime("%Y%m%d")


def load_seasons(path: str | Path = SEASONS_FILE) -> dict[str, Any]:
    with Path(path).open(encoding="utf-8") as f:
        return json.load(f)


def select_current_season(data: dict[str, Any], today: date | None = None) -> dict[str, Any]:
    seasons = data.get("seasons", [])
    if not seasons:
        raise ValueError("seasons.json に seasons が定義されていません")

    current_name = data.get("current_season", AUTO_CURRENT_SEASON)
    if current_name != AUTO_CURRENT_SEASON:
        for season in seasons:
            if season.get("name") == current_name:
                return season
        raise ValueError(f"seasons.json に '{current_name}' が見つかりません")

    today = today or today_jst()
    selected = None
    for season in sorted(seasons, key=lambda item: str(item.get("date_from", ""))):
        start = parse_yyyymmdd(season["date_from"])
        end = parse_yyyymmdd(season["date_to"])
        if start <= today <= end:
            return season
        if start <= today:
            selected = season

    if selected is not None:
        return selected
    return min(seasons, key=lambda item: str(item.get("date_from", "")))


def load_current_season(path: str | Path = SEASONS_FILE) -> dict[str, Any]:
    return select_current_season(load_seasons(path))


def season_date_from(season: dict[str, Any]) -> date:
    return parse_yyyymmdd(season["date_from"])


def season_date_to(season: dict[str, Any]) -> date:
    return parse_yyyymmdd(season["date_to"])


def season_start_yyyymmdd(season: dict[str, Any]) -> str:
    return yyyymmdd(season_date_from(season))


def season_end_yyyymmdd(season: dict[str, Any], cap_today: bool = False) -> str:
    end = season_date_to(season)
    if cap_today:
        end = min(end, today_jst())
    return yyyymmdd(end)


def season_output_name(season: dict[str, Any]) -> str:
    return str(season["name"]).replace(" ", "_").replace("/", "-")
