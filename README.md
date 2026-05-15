# card-tracker README

## このプロジェクトの目的

このプロジェクトは、ポケモンカード公式サイトの大会結果と公開デッキリストを収集し、
シティリーグ環境の分析レポートと固定分析ダッシュボードを作るためのローカル運用ツールです。

現行の本線は、次の流れで動いています。

1. 拡張パック発売日にもとづく環境区分を更新
2. 大会IDを取得
3. 大会結果とデッキリストを取得
4. レポートと分析用JSONを生成
5. 5ページ構成のダッシュボードを再生成

## ふだん使う入口

- `run_fetch_report_dashboard.bat`
  大会データ取得から、レポート生成・ダッシュボード再生成までをまとめて実行します。
- `run_report_dashboard.bat`
  既存データを使って、レポート生成・ダッシュボード再生成だけを実行します。
- `publish_source_changes.bat`
  よくある設定・コード変更を GitHub に反映するための公開用バッチです。  
  `deck_types.json` などを編集したあと、ダブルクリックで `commit / pull --rebase / push` まで進めます。
- `publish_deck_types.bat`
  `deck_types.json` を直したあとに使う専用バッチです。
- `publish_meta_cards.bat`
  `meta_cards.json` を直したあとに使う専用バッチです。
- `publish_seasons.bat`
  `seasons.json` を直したあとに使う専用バッチです。  
  push 後は GitHub 側で `fetch_data = true` の手動実行が必要です。
- `work_shortcuts`
  編集ファイルを開くバッチと、GitHub 反映バッチを順番に置いた作業用フォルダです。  
  エクスプローラーでこのフォルダを開いたままにしておくと、PowerShell を使わずに更新できます。

## トップレベルのフォルダ

### `.venv`

このプロジェクト用の Python 仮想環境です。  
通常は中身を手で触りません。

### `_vendor_lib`

実行時に参照する依存ライブラリの置き場です。  
収集バッチが `requests` などを読むために使います。

### `_vendor_wheels`

依存パッケージの wheel バックアップです。  
再展開や再構築用の保険なので、通常は残しておきます。

### `deck_lists`

取得した個別デッキリスト JSON の保存先です。  
分析の元データです。

### `event_results`

大会ごとの順位・ポイント・デッキIDなどの結果 JSON を保存する場所です。  
分析の元データです。

### `reports`

生成した Markdown レポートと `*_fullperiod.json` を置く場所です。

- 最新の Markdown レポート
- 最新の分析用 JSON
- 過去の Markdown レポート

が入ります。

### `site_fullperiod`

現行の固定分析ダッシュボードの出力先です。  
ブラウザで開くのは基本的にこの中の HTML です。

## トップレベルのファイル

### `find_events_v2.py`

対象シーズンの大会 ID を探すスクリプトです。

### `fetch_results_s4.py`

大会結果とデッキリストを取得して、`event_results` と `deck_lists` に保存するスクリプトです。

### `generate_report_local_alltrend.py`

現行の集計本体です。  
データを読み込み、分類・集計し、Markdown レポートと `*_fullperiod.json` を生成します。

### `build_dashboard_multipage_fullperiod_styled.py`

現行のダッシュボード生成スクリプトです。  
`reports/*_fullperiod.json` を読み、`site_fullperiod` の HTML を作ります。

### `deck_types.json`

デッキ分類ルールです。  
新しいデッキタイプの追加・名称変更・条件変更は、主にこのファイルを手で更新します。

### `meta_cards.json`

重要メタカードの定義です。  
追いかけたいカードを手で更新します。

### `seasons.json`

どの環境区分を取得・集計対象にするかの設定です。  
現在は公式シティリーグのシーズン番号ではなく、拡張パックの発売日を新しい環境の開始日として区切ります。  
`current_season` が `auto` の場合は、今日の日付が含まれる環境区分を自動で選びます。

### `season_utils.py`

`seasons.json` を読み込み、現在の環境区分を選ぶ共通ヘルパーです。  
大会ID取得、結果取得、レポート生成で同じ環境区分を使うために参照します。

### `update_expansion_seasons.py`

ポケカ公式の商品情報 API から拡張パックの発売日を取得し、`seasons.json` を発売日ベースで再生成するスクリプトです。  
新しい拡張パック情報が公式に公開された場合、日次更新または一括取得時に次の環境区分が自動で追加されます。

### `card_image_cache.json`

カード画像 URL のキャッシュです。  
Tier表、カード分析、メタカード表示などで使います。

### `event_ids_シティリーグ2026_シーズン4.json`

大会 ID 一覧の保存ファイルです。  
取得処理の中間生成物です。

### `events.csv`

大会一覧の CSV です。  
収集済みイベントの一覧確認に使います。

### `run_fetch_report_dashboard.bat`

収集から再生成までを一括実行する運用用バッチです。

### `run_report_dashboard.bat`

再集計・再生成だけを実行する運用用バッチです。

## `site_fullperiod` の中身

- `index.html`
  環境全体ページ
- `archetypes.html`
  アーキタイプ分析ページ
- `decks.html`
  デッキ分析ページ
- `cards.html`
  カード分析ページ
- `decklists.html`
  デッキリスト検索ページ
- `data.js`
  各ページが共通で読むデータ本体

## `reports` の中身

- `YYYY-MM-DD.md`
  日付付きの分析レポート
- `YYYY-MM-DD_fullperiod.json`
  ダッシュボード用の集計済み JSON

現時点では、最新の本線成果物は次の2つです。

- `reports/2026-05-02.md`
- `reports/2026-05-02_fullperiod.json`

## 手で編集することが多いファイル

- `deck_types.json`
- `meta_cards.json`
- `seasons.json`

この3つは運用上、手で更新する前提の設定ファイルです。

## 原則として手で編集しないもの

- `deck_lists/`
- `event_results/`
- `reports/*_fullperiod.json`
- `site_fullperiod/*`
- `events.csv`
- `event_ids_*.json`

これらは取得・集計・生成によって自動更新されるため、通常は手で編集しません。

## 日々の基本運用

### 1. データ取得から全部やるとき

`run_fetch_report_dashboard.bat` を実行します。

### 2. 設定だけ変えて再生成したいとき

1. `deck_types.json` や `meta_cards.json` を手で更新
2. `run_report_dashboard.bat` を実行

## GitHub 自動更新

このプロジェクトには、GitHub Actions 用の自動更新 workflow を追加しています。

- `.github/workflows/update-dashboard.yml`
  GitHub 上で
  1. 拡張パック発売日にもとづく環境区分更新
  2. 大会データ取得
  3. レポート生成
  4. ダッシュボード再生成
  5. 更新差分の自動 commit / push
  6. `site_fullperiod` の GitHub Pages 自動公開

  を行います。

- `requirements.txt`
  GitHub Actions が入れる Python 依存です。

- `.gitignore`
  ローカル専用の `.venv` や `_vendor_lib` などを Git に載せないための設定です。

- `connect_github_remote.bat`
  GitHub のリポジトリ URL を設定し、`main` ブランチを push するための補助バッチです。

### GitHub で使い始める手順

この作業フォルダは、すでに Git 初期化と初回コミットが済んでいます。  
そのため、GitHub 自動更新を有効にするには次の作業が必要です。

1. GitHub 上に空のリポジトリを作る
2. `connect_github_remote.bat` を実行して、そのリポジトリ URL を設定する
3. `main` ブランチを GitHub に push する
4. GitHub の `Settings > Pages` で `Source = GitHub Actions` を有効化する
5. GitHub の `Actions` を有効化する

### 自動更新の内容

- 毎日 09:15 JST に自動実行
- GitHub の Actions 画面から手動実行も可能
- 手動実行時は「大会データ取得あり / なし」を選べます
- 更新後の `site_fullperiod` は GitHub Pages に自動デプロイされます
- 次のファイルを `push` したときも自動実行されます
  - `deck_types.json`
  - `meta_cards.json`
  - `card_image_cache.json`
  - `seasons.json`
  - `season_utils.py`
  - `update_expansion_seasons.py`
  - `find_events_v2.py`
  - `fetch_results_s4.py`
  - `generate_report_local_alltrend.py`
  - `build_dashboard_multipage_fullperiod_styled.py`

### いちばん楽な運用

#### `deck_types.json` や `meta_cards.json` を直したとき

1. ファイルを編集して保存
2. `deck_types.json` なら `publish_deck_types.bat`、`meta_cards.json` なら `publish_meta_cards.bat` をダブルクリック
3. 何も追加操作しなくても、GitHub 側で自動再生成と自動公開が走る

もっと楽にやるなら、`work_shortcuts` フォルダを開いて次の順で押します。

- `01_edit_deck_types.bat` → 編集
- `02_publish_deck_types.bat` → GitHub 反映

`meta_cards.json` も同じで、

- `03_edit_meta_cards.bat` → 編集
- `04_publish_meta_cards.bat` → GitHub 反映

#### `seasons.json` や取得スクリプトを直したとき

1. ファイルを編集して保存
2. `seasons.json` なら `publish_seasons.bat`、それ以外の取得スクリプトは `publish_source_changes.bat` をダブルクリック
3. GitHub の `Actions > Update Dashboard` を開く
4. `Run workflow` で `fetch_data = true` を選んで実行

`seasons.json` は `work_shortcuts` の

- `05_edit_seasons.bat` → 編集
- `06_publish_seasons.bat` → GitHub 反映

でも同じです。

理由:
- `deck_types.json` などは再分類・再描画だけで反映できる
- `seasons.json` や取得スクリプト変更は、大会データの再取得が必要になることがある

### GitHub に commit されるもの

- `deck_lists/`
- `event_results/`
- `reports/`
- `site_fullperiod/`
- `events.csv`
- `event_ids_*.json`

これは、毎回の取得を差分更新に寄せて、GitHub Actions の実行時間を短くするためです。

## 補足

- 古い Markdown レポートは履歴として残しています。
- `site_fullperiod` が現行の公開用出力です。
- `reports` の古い `*_fullperiod.json` や旧ダッシュボード生成物は、容量整理のため適宜削除していく運用です。
