import json
import os
import time
from datetime import datetime, timedelta
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from season_utils import (
    load_current_season,
    season_end_yyyymmdd,
    season_output_name,
    season_start_yyyymmdd,
)

# ============================================================
# 設定
# ============================================================

EVENT_TYPES      = ["3:1", "3:2", "3:7"]  # 全種別指定（Python側でオープンのみフィルタ）
PER_PAGE         = 20
REQUEST_INTERVAL = 1.0
EVENT_SEARCH_API = "https://players.pokemon-card.com/event_search"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
    "Referer": "https://players.pokemon-card.com/",
}

def get_output_filename(season):
    return f"event_ids_{season_output_name(season)}.json"


def get_date_range(existing, season):
    season_end = season_end_yyyymmdd(season, cap_today=True)

    if not existing:
        return season_start_yyyymmdd(season), season_end

    latest = max(str(v.get("date", "")) for v in existing.values())
    if latest >= season_end:
        return None, None

    next_day = (datetime.strptime(latest, "%Y%m%d") + timedelta(days=1)).strftime("%Y%m%d")
    return next_day, season_end


def make_session():
    session = requests.Session()
    retry = Retry(total=3, backoff_factor=2, status_forcelist=[500, 502, 503, 504])
    session.mount("https://", HTTPAdapter(max_retries=retry))
    return session


def fetch_events(session, date_from, date_to):
    """
    result_resist=1で新しい順に取得。
    取得バッチの最大日付がdate_fromより古くなったら打ち切る。
    """
    all_events = []
    offset = 0
    total = None

    while True:
        params = [
            ("offset", offset),
            ("order", 4),        # 新しい順
            ("result_resist", 1), # 結果公開済みのみ
        ]
        for et in EVENT_TYPES:
            params.append(("event_type[]", et))

        print(f"  取得中: offset={offset} ...", end=" ", flush=True)
        try:
            resp = session.get(EVENT_SEARCH_API, params=params, headers=HEADERS, timeout=30)
            resp.raise_for_status()
            data = resp.json()
        except requests.exceptions.Timeout:
            print("タイムアウト。30秒待って再試行...")
            time.sleep(30)
            continue
        except Exception as e:
            print(f"エラー: {e}。10秒待って再試行...")
            time.sleep(10)
            continue

        events = data.get("event", [])
        if total is None:
            total = data.get("eventCount", 0)
            print(f"全{total}件 → {len(events)}件取得")
        else:
            print(f"{len(events)}件取得")

        if not events:
            break

        dates = [str(e.get("event_date_params", "")) for e in events if e.get("event_date_params")]

        # 新しい順なので、このバッチの最大日付がシーズン開始より古ければ以降は全部対象外
        if dates and max(dates) < date_from:
            print(f"  シーズン開始日({date_from})より古いデータのみ → 取得終了")
            break

        # オープンリーグ・対象期間のみフィルタ
        for e in events:
            d = str(e.get("event_date_params", ""))
            league = str(e.get("leagueName", ""))
            if date_from <= d <= date_to and league == "オープン":
                all_events.append(e)

        offset += len(events)
        if total and offset >= total:
            break

        time.sleep(REQUEST_INTERVAL)

    return all_events


def main():
    season = load_current_season()
    output_json = get_output_filename(season)

    existing = {}
    if os.path.exists(output_json):
        with open(output_json, encoding="utf-8") as f:
            existing = json.load(f)

    date_from, date_to = get_date_range(existing, season)

    print("=" * 55)
    print(f"ポケモンカード 大会ID差分取得")
    print(f"シーズン: {season['name']}  ({season['date_from']}〜{season['date_to']})")
    print(f"既存データ: {len(existing)}件")

    if date_from is None:
        print("すでに最新です。取得をスキップします。")
        return

    print(f"取得期間: {date_from} 〜 {date_to}")
    print("=" * 55)

    session = make_session()
    events = fetch_events(session, date_from, date_to)

    found = 0
    for e in events:
        eid = str(e.get("event_holding_id"))
        if eid and eid not in existing:
            existing[eid] = {
                "event_id": e["event_holding_id"],
                "event_title": e.get("event_title", ""),
                "event_kbn": e.get("leagueName", ""),
                "date": e.get("event_date_params", ""),
                "prefecture": e.get("prefecture_name", ""),
                "regulation": e.get("regulation", ""),
                "capacity": e.get("capacity", 0),
                "shop_name": e.get("shop_name", ""),
            }
            found += 1

    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)

    print(f"\n完了！ 新規追加: {found}件 / 合計: {len(existing)}件")
    print(f"保存: {output_json}")

    by_date = {}
    for v in existing.values():
        d = str(v.get("date", ""))[:6]
        by_date[d] = by_date.get(d, 0) + 1
    print("\n月別件数:")
    for d, n in sorted(by_date.items()):
        print(f"  {d[:4]}/{d[4:6]}: {n}件")


if __name__ == "__main__":
    main()
