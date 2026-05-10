# card-tracker README

## このプロジェクトの目的

このプロジェクトは、ポケモンカード公式サイトの大会結果と公開デッキリストを収集し、
シティリーグ環境の分析レポートと固定分析ダッシュボードを作るためのローカル運用ツールです。

現行の本線は、次の流れで動いています。

1. 大会IDを取得
2. 大会結果とデッキリストを取得
3. レポートと分析用JSONを生成
4. 5ページ構成のダッシュボードを再生成

## ふだん使う入口

- `run_fetch_report_dashboard.bat`
  大会データ取得から、レポート生成・ダッシュボード再生成までをまとめて実行します。
- `run_report_dashboard.bat`
  既存データを使って、レポート生成・ダッシュボード再生成だけを実行します。

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

どのシーズンを取得対象にするかの設定です。

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
  1. 大会データ取得
  2. レポート生成
  3. ダッシュボード再生成
  4. 更新差分の自動 commit / push

  を行います。

- `requirements.txt`
  GitHub Actions が入れる Python 依存です。

- `.gitignore`
  ローカル専用の `.venv` や `_vendor_lib` などを Git に載せないための設定です。

### GitHub で使い始める手順

この作業フォルダは、現時点ではまだ Git 管理されていません。  
そのため、GitHub 自動更新を有効にするには次の作業が必要です。

1. このフォルダを Git リポジトリとして初期化する
2. GitHub 上にリポジトリを作る
3. このフォルダを GitHub に push する
4. GitHub の Actions を有効化する

### 自動更新の内容

- 毎日 09:15 JST に自動実行
- GitHub の Actions 画面から手動実行も可能
- 手動実行時は「大会データ取得あり / なし」を選べます

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
