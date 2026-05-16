import json
import os
import time
import re
import csv
import requests

from season_utils import (
    load_current_season,
    season_end_yyyymmdd,
    season_output_name,
    season_start_yyyymmdd,
)

# ============================================================
# 設定
# ============================================================

RESULTS_DIR = "event_results"
DECKS_DIR   = "deck_lists"
EVENTS_CSV  = "events.csv"

RESULT_API = "https://players.pokemon-card.com/event_result_detail_search"
DECK_URL   = "https://www.pokemon-card.com/deck/confirm.html/deckID/{deck_id}"

PER_PAGE = 100
REQUEST_INTERVAL = 1.0

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
    "Referer": "https://players.pokemon-card.com/",
}

DECK_CATEGORY = {
    "deck_pke": "ポケモン",
    "deck_gds": "グッズ",
    "deck_tool": "ポケモンのどうぐ",
    "deck_tech": "テクニカルマシン",
    "deck_sup": "サポート",
    "deck_sta": "スタジアム",
    "deck_ene": "エネルギー",
}


# ============================================================
# シーズン設定の読み込み
# ============================================================

def get_event_ids_file(season):
    return f"event_ids_{season_output_name(season)}.json"


def load_event_ids(season):
    """seasons.jsonの期間に合致する大会IDリストを返す"""
    ids_file = get_event_ids_file(season)
    if not os.path.exists(ids_file):
        print(f"エラー: {ids_file} が見つかりません。先に find_events_v2.py を実行してください。")
        return []

    date_from = season_start_yyyymmdd(season)
    date_to = season_end_yyyymmdd(season, cap_today=True)

    with open(ids_file, encoding="utf-8") as f:
        data = json.load(f)

    def should_include_event(row):
        league = str(row.get("event_kbn", "")).strip()
        title = str(row.get("event_title", "")).strip()
        if league in ("オープン", ""):
            return True
        if "チャンピオンズリーグ" in title:
            if league in {"シニア", "ジュニア"}:
                return True
            if league == "マスター" and ("Day2" in title or "2日目" in title):
                return True
        return False

    ids = [
        v["event_id"] for v in data.values()
        if date_from <= str(v.get("date", "")) <= date_to
        and should_include_event(v)
    ]
    return sorted(ids)


# ============================================================
# 大会結果の取得
# ============================================================

def fetch_event_results(event_id):
    all_results = []
    event_info = None
    offset = 0
    while True:
        params = {"event_holding_id": event_id, "offset": offset, "per_page": PER_PAGE}
        resp = requests.get(RESULT_API, params=params, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        if event_info is None:
            event_info = data.get("event", {})
        results = data.get("results", [])
        all_results.extend(results)
        total = data.get("count", 0)
        offset += len(results)
        if offset >= total or not results:
            break
        time.sleep(REQUEST_INTERVAL)
    return {"event": event_info, "results": all_results, "total": len(all_results)}


def save_event_results(event_id, data):
    os.makedirs(RESULTS_DIR, exist_ok=True)
    path = os.path.join(RESULTS_DIR, f"{event_id}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return path


# ============================================================
# デッキリストの取得
# ============================================================

def parse_deck_html(html):
    name_map = {}
    for m in re.finditer(r"PCGDECK\.searchItemNameAlt\[(\d+)\]='([^']+)'", html):
        name_map[m.group(1)] = m.group(2)
    for m in re.finditer(r"PCGDECK\.searchItemName\[(\d+)\]='([^']+)'", html):
        if m.group(1) not in name_map:
            name_map[m.group(1)] = m.group(2)
    cards = []
    for field, category in DECK_CATEGORY.items():
        m = re.search(rf'name="{field}"\s+id="{field}"\s+value="([^"]*)"', html)
        if not m or not m.group(1):
            continue
        for entry in m.group(1).split("-"):
            if not entry:
                continue
            parts = entry.split("_")
            if len(parts) < 2:
                continue
            card_id, count = parts[0], parts[1]
            cards.append({
                "category": category,
                "card_id": card_id,
                "name": name_map.get(card_id, f"ID:{card_id}"),
                "count": int(count),
            })
    return cards


def fetch_deck_list(deck_id):
    url = DECK_URL.format(deck_id=deck_id)
    resp = requests.get(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://players.pokemon-card.com/",
    }, timeout=20)
    resp.raise_for_status()
    return parse_deck_html(resp.text)


def save_deck_list(deck_id, cards):
    os.makedirs(DECKS_DIR, exist_ok=True)
    path = os.path.join(DECKS_DIR, f"{deck_id}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cards, f, ensure_ascii=False, indent=2)
    return path


# ============================================================
# CSVサマリー更新
# ============================================================

def update_events_csv(event_id, data):
    event = data["event"]
    rows = []
    fieldnames = ["event_id", "event_title", "event_type", "date",
                  "prefecture", "regulation", "capacity", "total_results"]
    if os.path.exists(EVENTS_CSV):
        with open(EVENTS_CSV, encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))
    new_row = {
        "event_id": event_id,
        "event_title": event.get("event_title", ""),
        "event_type": event.get("event_type_title", ""),
        "date": event.get("eventDate", {}).get("date", "")[:10],
        "prefecture": event.get("prefecture_name", ""),
        "regulation": event.get("regulation", ""),
        "capacity": event.get("capacity", ""),
        "total_results": data["total"],
    }
    updated = False
    for i, row in enumerate(rows):
        if str(row.get("event_id")) == str(event_id):
            rows[i] = new_row
            updated = True
            break
    if not updated:
        rows.append(new_row)
    with open(EVENTS_CSV, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


# ============================================================
# メイン処理
# ============================================================

def main():
    season = load_current_season()
    event_ids = load_event_ids(season)

    if not event_ids:
        return

    print("=" * 55)
    print(f"ポケモンカード 大会データ一括収集")
    print(f"シーズン: {season['name']}")
    print(f"対象大会: {len(event_ids)}件")
    print("=" * 55)

    total_new_decks = 0
    total_skip = 0

    for i, event_id in enumerate(event_ids, 1):
        print(f"\n[{i}/{len(event_ids)}] 大会ID: {event_id}")

        result_path = os.path.join(RESULTS_DIR, f"{event_id}.json")
        if os.path.exists(result_path):
            with open(result_path, encoding="utf-8") as f:
                data = json.load(f)
            # 結果が0件のまま保存されている場合は再取得を試みる
            if data["total"] == 0:
                print(f"  大会結果: 0件（再取得を試みます）")
                try:
                    data = fetch_event_results(event_id)
                    if data["total"] == 0:
                        print(f"  大会結果: まだ0件（スキップ）")
                        continue
                    save_event_results(event_id, data)
                    print(f"  大会結果: {data['event'].get('event_title','')} ({data['total']}件) 再取得・保存")
                except Exception as e:
                    print(f"  大会結果再取得エラー: {e}")
                    continue
                time.sleep(REQUEST_INTERVAL)
            else:
                print(f"  大会結果: 取得済み ({data['total']}件)")
        else:
            try:
                data = fetch_event_results(event_id)
                if data["total"] == 0:
                    # 当日開催の可能性あり → 0件でも保存して次回再取得
                    save_event_results(event_id, data)
                    print(f"  大会結果: 0件（次回再取得予定）")
                    continue
                save_event_results(event_id, data)
                print(f"  大会結果: {data['event'].get('event_title','')} ({data['total']}件) 保存")
            except Exception as e:
                print(f"  大会結果取得エラー: {e}")
                continue
            time.sleep(REQUEST_INTERVAL)

        update_events_csv(event_id, data)

        success = skip = fail = 0
        for result in data["results"]:
            deck_id = result.get("deck_id")
            if not deck_id:
                continue
            deck_path = os.path.join(DECKS_DIR, f"{deck_id}.json")
            if os.path.exists(deck_path):
                skip += 1
                continue
            try:
                cards = fetch_deck_list(deck_id)
                if cards:
                    save_deck_list(deck_id, cards)
                    success += 1
                else:
                    fail += 1
            except Exception as e:
                print(f"    デッキエラー: {deck_id} ({e})")
                fail += 1
            time.sleep(REQUEST_INTERVAL)

        print(f"  デッキ: {success}件取得 / {skip}件スキップ / {fail}件失敗")
        total_new_decks += success
        total_skip += skip

    print(f"\n{'='*55}")
    print(f"完了！ 新規取得: {total_new_decks}件 / スキップ: {total_skip}件")


if __name__ == "__main__":
    main()
