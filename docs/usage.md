# 競馬予想システム ユーザーガイド

> 本ドキュメントは、keiba-prediction の使い方を総合的に解説するガイドです。
> 設計の技術的詳細については [docs/design.md](design.md) を参照してください。

---

## 目次

1. [はじめに](#1-はじめに)
2. [セットアップ](#2-セットアップ)
3. [基本的な使い方](#3-基本的な使い方)
4. [パイプラインの全体像](#4-パイプラインの全体像)
5. [各エージェントの詳細](#5-各エージェントの詳細)
6. [出力物の読み方](#6-出力物の読み方)
7. [設定のカスタマイズ](#7-設定のカスタマイズ)
8. [データソースの差し替え](#8-データソースの差し替え)
9. [よくある使い方パターン](#9-よくある使い方パターン)
10. [トラブルシューティング](#10-トラブルシューティング)
11. [テストと開発](#11-テストと開発)

---

## 1. はじめに

### システム概要

keiba-prediction は、中央競馬の重賞レース（GI/GII/GIII）を対象とした予想システムです。16のエージェントがパイプライン構成で連携し、データ取得 → 特徴量生成 → 統計分析+ML予測 → Web調査 → 根拠統合 → オッズ評価 → 予想生成 → バックテスト → 可視化 → Note記事生成 → 品質保証までを一貫して自動実行します。

### 対象レース

- 中央競馬の重賞レース（GI / GII / GIII）
- 土日のメインレース（11R）など

### 動作モード

3つのデータソースに対応しています:

| モード | データソース | 内容 |
|-------|------------|------|
| `sample` | SampleDataSource | 架空のGIレース・10頭立て（動作確認用） |
| `production` | ProductionDataSource | netkeiba/JRAのWebスクレイピング（キャッシュ付き） |
| `jrvan` | JrVanDataSource | JRA-VAN DataLabの27年分SQLiteデータ（推奨） |

JRA-VANデータソースでは、**LightGBM + Optuna** によるML予測が有効になります（検証AUC=0.8332、テストAUC=0.7707、214Kサンプル）。

### 免責事項

> ⚠️ 本システムはデータ分析に基づく参考情報を提供するものです。馬券の購入を保証するものではありません。投資は自己責任でお願いします。

---

## 2. セットアップ

### 前提

- Python 3.11 以上

### インストール手順

```bash
# リポジトリをクローン
git clone https://github.com/Foo53/keiba.git
cd keiba

# 仮想環境の作成と有効化
python3 -m venv .venv
source .venv/bin/activate

# パッケージのインストール（開発用ツール含む）
pip install -e ".[dev]"
```

### 動作確認

```bash
keiba --help
```

以下のようなヘルプメッセージが表示されればインストール成功です：

```
usage: keiba [-h] [--config CONFIG] [--source {sample,production}]
             [--output-dir OUTPUT_DIR] [--verbose]
             [race_id]

競馬予想システム - 16エージェントパイプライン
```

### 主要パッケージ

| パッケージ | 用途 |
|-----------|------|
| pydantic >= 2.0 | データモデル・バリデーション |
| pyyaml >= 6.0 | 設定ファイル（YAML）の読込 |
| rich >= 13.0 | コンソール出力のフォーマット |
| lightgbm >= 4.0 | ML予測（LightGBMモデル） |
| optuna | ハイパーパラメータ最適化 |
| matplotlib / seaborn | EDA可視化チャート生成 |
| pytest >= 7.0 | テストフレームワーク（開発用） |
| ruff >= 0.1 | リンター（開発用） |
| mypy >= 1.0 | 型チェック（開発用） |

---

## 3. 基本的な使い方

### CLI コマンド一覧

#### 予想パイプライン

| オプション | 説明 | デフォルト |
|-----------|------|-----------|
| `race_id` | 対象レースID（位置引数） | `20260607-Tokyo-11` |
| `--config` | 設定ファイルのパス | `config/default.yaml` |
| `--source` | データソース（`sample` / `production`） | 設定ファイルに従う |
| `--output-dir` | 出力ディレクトリ | `output` |
| `--verbose, -v` | 詳細ログ出力（DEBUG レベル） | オフ |

#### モデル学習（`keiba train`）

| オプション | 説明 | デフォルト |
|-----------|------|-----------|
| `--source` | データソース（`sample` / `production` / `jrvan`） | `production` |
| `--months` | 学習データの期間（月） | `12` |
| `--max-races` | 最大レース数 | `500` |
| `--optuna-trials` | Optuna最適化試行数 | `100` |

#### 対話型リーダー（`keiba lead`）

| オプション | 説明 | デフォルト |
|-----------|------|-----------|
| `race_id` | 対象レースID（位置引数） | `20260607-Tokyo-11` |
| `--source` | データソース（`sample` / `production`） | 設定ファイルに従う |
| `--verbose, -v` | 詳細ログ出力 | オフ |

### 実行例

```bash
# サンプルデータで実行（デフォルト）
keiba

# レースIDを指定
keiba 20260607-Tokyo-11

# 詳細ログ付きで実行
keiba -v

# カスタム設定ファイルを使用
keiba --config config/my-config.yaml

# 出力先を変更
keiba --output-dir /path/to/output

# JRA-VANデータでモデル学習
keiba train --source jrvan --optuna-trials 50

# サンプルデータで学習（動作確認用）
keiba train --source sample --optuna-trials 10

# 対話型リーダーを起動
keiba lead

# レースID指定でリーダー起動
keiba lead 20260607-Tokyo-11
```

### 画面出力の構成

`keiba` コマンドを実行すると、以下の順でコンソールに出力されます：

```
============================================================
🏇 競馬予想システム - 16エージェントパイプライン
============================================================
対象レース: 20260607-Tokyo-11
データソース: sample
------------------------------------------------------------
```

1. **ヘッダ**: レースIDとデータソースの表示
2. **エージェント実行ログ**: 16エージェントの実行結果（✅/❌ と所要時間）
3. **QA採点**: 10項目・120点満点での採点結果
4. **予想サマリ**: 券種別買い目（リスクアイコン付き）
5. **Note記事情報**: タイトル・文字数・禁止表現チェック
6. **バックテスト**: 的中率とROI
7. **免責事項**: フッター

### 出力ファイル

実行後、以下のファイルが生成されます：

| ファイル | パス | 形式 | 内容 |
|---------|------|------|------|
| 全分析結果 | `output/json/{race_id}.json` | JSON | PipelineContext の完全なダンプ |
| Note記事案 | `output/markdown/{race_id}.md` | Markdown | Note投稿用の記事 |
| 実行ログ | `output/logs/pipeline.jsonl` | JSONL | エージェントごとの構造化ログ |
| EDAチャート | `output/eda/{race_id}/*.png` | PNG | 可視化チャート群（最大5枚） |
| 学習済みモデル | `data/store/models/lgbm_latest.txt` | TXT | LightGBMモデル |
| モデルメタデータ | `data/store/models/lgbm_metadata.json` | JSON | モデルの学習情報・特徴量リスト |

---

## 4. パイプラインの全体像

### データフロー図

```
[1.過去データ管理] → [2.当日データ取得] → [3.品質チェック] → [4.特徴量生成]
       ↑                                                       ↓
       │                                         ┌──────────────┼──────────────┐
       │                                         ↓              ↓              ↓
       │                                  [5.Python分析] [6.ML予測]  [7.Web調査]  ← 並列実行
       │                                         └──────────────┼──────────────┘
       │                                                        ↓
       │                                              [8.根拠統合]
       │                                                        ↓
       │                                       [9.予想オッズ評価]（暫定）
       │                                                        ↓
       │                                       [10.実オッズ評価]（最終）
       │                                                        ↓
       │                                            [11.予想生成]
       │                                                        ↓
       │                                            [12.バックテスト]
       │                                                        ↓
       │                                          [13.EDA可視化]
       │                                               ↓           ↓
       │                                       [14.Note構成調査]   │
       │                                               ↓           ↓
       │                                          [15.Note作成] ←──┘
       │                                                        ↓
       └──────────────── 差し戻し（リトライ） ←──── [16.品質保証]
```

### 16ステージ一覧

| # | ステージ名 | エージェントクラス | 依存関係 | 並列グループ |
|---|-----------|-------------------|---------|-------------|
| 1 | `historical_data` | HistoricalDataManager | — | — |
| 2 | `current_data` | CurrentDataFetcher | `historical_data` | — |
| 3 | `quality_check` | DataQualityChecker | `current_data` | — |
| 4 | `feature_gen` | FeatureGenerator | `quality_check` | — |
| 5 | `python_analysis` | PythonAnalyzer | `feature_gen` | `parallel_1` |
| 6 | `ml_analysis` | MLPredictor | `feature_gen` | `parallel_1` |
| 7 | `web_research` | WebResearcher | `current_data` | `parallel_1` |
| 8 | `evidence` | EvidenceIntegrator | `python_analysis`, `ml_analysis`, `web_research` | — |
| 9 | `predicted_odds` | PredictedOddsEvaluator | `evidence` | — |
| 10 | `actual_odds` | ActualOddsEvaluator | `predicted_odds` | — |
| 11 | `prediction` | PredictionGenerator | `actual_odds` | — |
| 12 | `backtest` | Backtester | `prediction` | — |
| 13 | `visualization` | VisualizerAgent | `backtest` | — |
| 14 | `note_research` | NoteStructureResearcher | `prediction` | — |
| 15 | `note_write` | NoteWriter | `note_research`, `visualization` | — |
| 16 | `qa` | QualityAssurance | `note_write` | — |

### PipelineContext（共有状態）

全16エージェントは `PipelineContext` オブジェクトを共有します。各エージェントは前段の出力を読み取り、自身の結果を書き込みます。

```python
PipelineContext:
  pipeline_id: str        # パイプライン実行ID（UUID）
  race_id: str            # 対象レースID
  started_at: datetime    # 開始時刻
  current_stage: str      # 現在のステージ名
  status: str             # "running" | "completed" | "failed"

  # 各エージェントの出力（Optional、実行時に書き込まれる）
  historical_data         # Agent 1
  current_race_data       # Agent 2
  quality_check           # Agent 3
  features                # Agent 4
  analysis                # Agent 5（統計分析）
  ml_analysis             # Agent 6（LightGBM ML予測）
  web_research            # Agent 7
  evidence                # Agent 8（統計+ML+Web を統合）
  predicted_odds_eval     # Agent 9
  actual_odds_eval        # Agent 10
  prediction_predicted    # Agent 11
  prediction_actual       # Agent 11
  backtest                # Agent 12
  eda_images              # Agent 13（EDA可視化チャート）
  note_suggestion         # Agent 14
  note_article            # Agent 15
  qa_report               # Agent 16

  agent_results: list     # 全エージェントの実行ログ
```

### 並列実行

Agent 5（PythonAnalyzer）、Agent 6（MLPredictor）、Agent 7（WebResearcher）は互いに依存しないため、`ThreadPoolExecutor` で並列実行されます。各スレッドには `PipelineContext` のコピー（`deepcopy`）が渡され、実行後に結果がメインの Context にマージされます。

### QAゲートとリトライ

Agent 16（QualityAssurance）が品質をチェックし、**100点未満**の場合は該当するエージェントに差し戻されます：

1. 最もスコアの低かった評価項目を特定
2. その項目に対応するエージェントを `route_back_to` に設定
3. 当該エージェント以降の実行記録をリセット
4. 当該エージェントから再実行
5. 最大 **3回** までリトライ（`config/default.yaml` の `pipeline.max_qa_retries`）

差し戻し先の対応表：

| QA評価項目 | 差し戻し先エージェント |
|-----------|---------------------|
| データ鮮度 | `historical_data_manager`（Agent 1） |
| データ欠損チェック | `data_quality_checker`（Agent 3） |
| 分析根拠の明確さ | `python_analyzer`（Agent 5） |
| Web調査の信頼性 | `web_researcher`（Agent 7） |
| オッズ期待値 | `actual_odds_evaluator`（Agent 10） |
| バックテスト結果 | `backtester`（Agent 12） |
| 券種別予想の妥当性 | `prediction_generator`（Agent 11） |
| Noteの読みやすさ | `note_writer`（Agent 15） |
| 誇大表現の排除 | `note_writer`（Agent 15） |
| リスク説明・出典表記 | `note_writer`（Agent 15） |

---

## 5. 各エージェントの詳細

各エージェントは `BaseAgent` 抽象クラスを継承し、以下のテンプレートメソッドパターンで実行されます：

```
execute(context)
  ├── validate_input(context)  → 入力チェック（失敗ならエラー）
  ├── process(context)          → メイン処理
  ├── 結果を AgentResult にラップ
  └── ログ出力（成功/失敗・所要時間）
```

---

### 5.1 HistoricalDataManager（過去データ管理）

**役割:** 過去レースデータを取得・管理するエージェント

**入力:**
- `context.race_id`

**出力:**
- `context.historical_data` — 過去レース・出走馬・過去成績・騎手成績・厩舎成績を含む辞書

**処理内容:**
1. `DataSource.get_historical_data(race_id)` を呼び出し
2. 取得データのサマリーをログ出力（馬数・過去成績数）

**データソース:** あり（`DataSource` 経由）

---

### 5.2 CurrentDataFetcher（当日データ取得）

**役割:** 対象レースの最新情報を取得するエージェント

**入力:**
- `context.race_id`
- `context.historical_data`（前提条件）

**出力:**
- `context.current_race_data` — レース情報と出馬表（entries リスト）を含む辞書

**処理内容:**
1. `DataSource.get_current_race_card(race_id)` を呼び出し
2. 出走頭数をログ出力

**データソース:** あり（`DataSource` 経由）

---

### 5.3 DataQualityChecker（データ品質チェック）

**役割:** 取得データの欠損・異常を検出するエージェント

**入力:**
- `context.historical_data`
- `context.current_race_data`

**出力:**
- `context.quality_check` — 品質レポート辞書：
  - `passed` (bool) — critical問題がなければ True
  - `issues` (list) — 検出された問題
  - `anomalies` (list) — 異常値
  - `completeness_score` (float) — データ完成度（0.0〜1.0）
  - `total_entries` (int) — 出走頭数

**処理内容:**
1. 出走馬ごとに以下をチェック：
   - 過去成績が3走未満 → `warning`
   - 馬体重変動 ±10kg 以上 → `warning`
   - 騎手情報なし → `critical`
2. レース基本情報（馬場状態など）をチェック
3. 完成度スコアを算出 = 通過チェック数 / 総チェック数

**データソース:** なし

---

### 5.4 FeatureGenerator（特徴量生成）

**役割:** 各馬の特徴量を生成するエージェント

**入力:**
- `context.current_race_data`
- `context.historical_data`
- `context.quality_check`（critical問題がないこと）

**出力:**
- `context.features` — 馬ごとの特徴量セット：
  - `horse_features` (list) — 各馬の特徴量辞書
  - `field_size` (int) — 出走頭数

**処理内容:**

各出走馬について以下の特徴量を計算します：

| 特徴量 | キー | 説明 |
|-------|------|------|
| 距離適性 | `distance_aptitude_score` | 過去成績の距離と目標距離の差 × 着順で評価（0〜100） |
| 芝適性 | `track_turf_score` | 芝レースでの平均着順から算出（0〜100） |
| ダート適性 | `track_dirt_score` | ダートレースでの平均着順から算出（0〜100） |
| コース適性 | `course_specific_score` | コースごとの着順ベースのスコア |
| 脚質 | `primary_style` | 過去レースの最多脚質（逃げ/先行/差し/追込） |
| 脚質一貫性 | `style_consistency` | 最多脚質の比率（0.0〜1.0） |
| 上がり性能 | `average_last_3f` / `best_last_3f` | 上がり3ハロンの平均・最良タイム |
| 上がり順位 | `closing_speed_rank` | 全馬中の上がり順位 |
| 近走成績 | `recent_3_runs` / `recent_5_runs` | 直近3走・5走の着順リスト |
| 近走スコア | `form_score` | 直近3走の平均着順から算出（0〜100） |
| クラス変更 | `class_change` | クラス昇降（`up` / `down` / `same`） |
| 距離変更 | `distance_change` | 前走との距離差 ±200m（`up` / `down` / `same`） |
| 馬体重傾向 | `horse_weight_trend` | 馬体重の変動傾向（`increasing` / `stable` / `decreasing`） |
| 騎手勝率 | `jockey_trainer_win_rate` | 騎手の全体勝率 |
| 騎手コース勝率 | `jockey_course_win_rate` | 騎手のコース別勝率 |

**データソース:** なし

---

### 5.5 PythonAnalyzer（統計分析）

**役割:** 特徴量から複合スコアを算出し、勝率・複勝率を推定するエージェント

**入力:**
- `context.features`

**出力:**
- `context.analysis` — 分析結果辞書：
  - `method` (str) — 分析手法（現在は `"statistical"`）
  - `probabilities` (list) — 各馬の確率推定（勝率・複勝率・モデル信頼度・順位）
  - `key_factors` (list) — 主要ファクター
  - `caveats` (list) — 注意事項
  - `data_sufficiency` (str) — `"sufficient"` / `"limited"` / `"minimal"`

**処理内容:**

1. **複合スコア計算** — 特徴量の加重和（9種のウェイトを使用）：

   | 特徴量 | ウェイト | 説明 |
   |-------|---------|------|
   | 近走成績 (`recent_form`) | **0.20** | 最も重視 |
   | 距離適性 (`distance_aptitude`) | 0.15 | |
   | 上がり性能 (`closing_speed`) | 0.15 | 34秒=100点、36秒=0点 |
   | 馬場適性 (`track_aptitude`) | 0.12 | |
   | 騎手成績 (`jockey_stats`) | 0.12 | |
   | 脚質 (`running_style`) | 0.08 | 東京2400mでは先行・差しが有利 |
   | 厩舎成績 (`trainer_stats`) | 0.08 | |
   | 血統 (`pedigree`) | 0.05 | |
   | 馬体重 (`weight_factors`) | 0.05 | |

2. **ソフトマックスによる勝率推定** — スコアを平均中心に正規化（±5.0スケール）し、温度パラメータ 1.0 のソフトマックス関数で確率化

3. **複勝率の近似** — Harville公式の簡易版：`place_prob = min(1.0, win_prob × 2.5)`

4. **データ十分性評価** — 出走頭数に基づく：≥8頭=`sufficient`、≥5頭=`limited`、<5頭=`minimal`

**データソース:** なし

---

### 5.6 MLPredictor（ML予測）

**役割:** 学習済みLightGBMモデルで各馬の勝率を推定するエージェント

**入力:**
- `context.features`

**出力:**
- `context.ml_analysis` — ML分析結果辞書：
  - `method` (str) — `"lightgbm"`
  - `model_version` (str) — モデルの学習日時
  - `model_confidence` (float) — 検証AUC値
  - `probabilities` (list) — 各馬の確率推定（勝率・複勝率・モデル信頼度・順位・composite_score）
  - `feature_importance` (list) — 上位10特徴量の重要度（gainベース）
  - `caveats` (list) — 注意事項

**処理内容:**

1. **モデルロード** — `data/store/models/lgbm_latest.txt` からLightGBMモデルを読み込み。モデルが存在しない場合はgracefulにスキップ（`ml_analysis = None`）

2. **特徴量ベクトル化** — `feature_vectorizer.py` の `vectorize_race()` で各馬の特徴量を25次元の数値ベクトルに変換

3. **予測実行** — LightGBMモデルでスコアを算出し、softmax正規化でレース内相対確率に変換

4. **特徴量重要度** — gain ベースの特徴量重要度を上位10件取得

**特徴量ベクトル（25次元）:**

| # | 特徴量 | 説明 |
|---|-------|------|
| 1-3 | `distance_aptitude_score`, `track_turf_score`, `track_dirt_score` | 距離・芝・ダート適性スコア |
| 4 | `course_specific_best` | コース適性最高値 |
| 5-9 | `style_consistency`, `style_front_runner`, `style_stalker`, `style_midpack`, `style_closer` | 脚質一貫性 + one-hot符号化 |
| 10-12 | `avg_last_3f`, `best_last_3f`, `closing_speed_rank` | 上がり3F関連 |
| 13 | `form_score` | 近走フォームスコア |
| 14-17 | `class_change_up/down`, `distance_change_up/down` | クラス・距離変更（0/1） |
| 18 | `jockey_trainer_win_rate` | 騎手厩舎勝率 |
| 19-25 | `recent_win_rate`, `recent_place_rate`, `avg_recent_position`, `last_run_position`, `field_size`, `jockey_course_win_rate`, `best_3f_gap` | 高効果特徴量（文献調査由来） |

**データソース:** なし（学習済みモデルファイルを使用）

> **注意:** モデル未学習時はスキップされます。`keiba train --source jrvan` で事前に学習してください。

---

### 5.7 WebResearcher（Web調査）

**役割:** Web検索で調教情報・ニュース等の補足情報を集めるエージェント

**入力:**
- `context.current_race_data`

**出力:**
- `context.web_research` — Web調査結果辞書：
  - `track_tendencies` (list) — トラック傾向
  - `weather_forecast` — 天気予報
  - `horse_intel` (list) — 各馬の調査結果（信頼度・影響度付き）
  - `data_source` (str) — データソース名
  - `note` (str) — 補足情報

**処理内容:**

1. `DataSource.get_web_content(race_id, horse_ids)` を呼び出し
2. 各馬の情報に**信頼度**を付与：
   - ニュース関連性の平均 ≥ 0.8 → `high`
   - ≥ 0.5 → `medium`
   - < 0.5 → `low`
3. 各馬の**予想への影響度**を評価：
   - ポジティブキーワード（好調/好時計/勢い 等）があれば `positive`
   - ネガティブキーワード（不安/注意/減少 等）があれば `negative`
   - 両方あれば `mixed`
   - どちらもなければ `neutral`

**データソース:** あり（`DataSource` 経由）

> **MVP注意:** 現在はサンプルデータを返します。本番ではWeb検索API等を使用しますが、対象サイトの利用規約・robots.txt・アクセス頻度制限を必ず確認してください。

---

### 5.8 EvidenceIntegrator（根拠統合）

**役割:** 統計分析結果とWeb調査結果を統合し、最終的な確率と評価を生成するエージェント

**入力:**
- `context.analysis`（統計分析）
- `context.ml_analysis`（ML予測）
- `context.web_research`（Web調査）

**出力:**
- `context.evidence` — 統合根拠プロファイル：
  - `horses` (list) — 各馬の根拠情報（強み/弱み/懸念/統合確率/グレード）
  - `race_narrative` (str) — レース概観テキスト

**処理内容:**

1. **根拠の抽出** — 統計データ・ML予測・Web情報から以下を分類：
   - `strengths`（強み）— モデル上位、好調キーワード、好調教 等
   - `weaknesses`（弱み）— 軽めの調教 等
   - `concerns`（懸念）— 不安/注意/減少キーワード 等

2. **Web証拠による確率調整** — Web影響度と信頼度に基づく調整（最大 ±15%）：
   - 影響度 `positive` → `+0.15 × 信頼度係数`
   - 影響度 `negative` → `-0.15 × 信頼度係数`
   - 信頼度係数: `high`=1.0, `medium`=0.6, `low`=0.3

3. **信頼度グレードの割当** — 統合確率と根拠数から判定：

   | グレード | 条件 |
   |---------|------|
   | 🔴 S | 勝率 > 20% & 強み ≥ 3 & 懸念 = 0 |
   | 🟠 A | 勝率 > 10% & 強み ≥ 2 & 懸念 ≤ 1 |
   | 🟡 B | 勝率 > 5% & 懸念 ≤ 2 |
   | ⚪ C | その他 |

**データソース:** なし

---

### 5.9 PredictedOddsEvaluator（予想オッズ評価）

**役割:** 予想オッズベースの暫定的な価値評価を行うエージェント

**入力:**
- `context.evidence`
- `context.current_race_data`

**出力:**
- `context.predicted_odds_eval` — 暫定評価辞書：
  - `is_provisional` (bool) — 常に `True`
  - `evaluations` (list) — 各馬の評価（オッズ、モデル確率、バリューギャップ）
  - `value_candidates` (list) — 妙味ありの馬（ギャップ > +5%）
  - `skip_candidates` (list) — 見送り候補（ギャップ < -10%）

**処理内容:**

1. モデル確率と市場インプライド確率（1 / オッズ）を比較
2. **バリューギャップ** = モデル確率 − 市場確率 を計算
3. ギャップに基づく判定：
   - `> +0.05` → 「妙味あり」
   - `> -0.05` → 「妙味薄」
   - `≤ -0.05` → 「見送り」

> ⚠️ **重要:** この評価は常に `is_provisional: true` です。実オッズ取得後に Agent 9 で再評価が必要です。

**データソース:** なし（context 内のオッズデータを使用）

---

### 5.10 ActualOddsEvaluator（実オッズ評価）

**役割:** 実オッズで期待値（EV）を計算し、最終的な推奨グレードを付与するエージェント

**入力:**
- `context.evidence`
- `context.predicted_odds_eval`（比較用）

**出力:**
- `context.actual_odds_eval` — 最終評価辞書：
  - `is_provisional` (bool) — `False`（最終評価）
  - `evaluations` (list) — 各馬の評価（実オッズ、EV、推奨グレード、予想オッズからの変動）
  - `market_sentiment` (str) — 市場センチメント
  - `s_grade_horses` / `a_grade_horses` / `skip_candidates`

**処理内容:**

1. **期待値計算:** `EV = モデル確率 × オッズ − 1`
2. **推奨グレードの付与:**

   | グレード | 条件 |
   |---------|------|
   | S | EV > 0.3 & ギャップ > 0.10 & 懸念 0件 |
   | A | EV > 0.1 & ギャップ > 0.05 & 懸念 ≤ 1件 |
   | B | EV > -0.1 |
   | C | その他 |

3. **市場センチメント評価:** EV > 0 の馬の数に基づく：
   - 0頭 → `no_value_found`
   - 1-2頭 → `few_opportunities`
   - 3-4頭 → `moderate_opportunities`
   - 5頭以上 → `many_opportunities`

4. **予想オッズとの比較:** オッズ変動（`odds_change_from_predicted`）を記録

**データソース:** なし（context 内のオッズデータを使用）

---

### 5.11 PredictionGenerator（予想生成）

**役割:** 券種別の買い目を生成、または見送りを推奨するエージェント

**入力:**
- `context.evidence`
- `context.actual_odds_eval`
- `context.predicted_odds_eval`

**出力:**
- `context.prediction_predicted` — 予想オッズベースの予想
- `context.prediction_actual` — 実オッズベースの予想（メイン出力）

各予想辞書の内容：
- `top_pick` — 本命の entry_id
- `second_pick` — 対抗の entry_id
- `dark_horse` — 穴馬候補（順位4-7位で最高EVの馬）の entry_id
- `skip_recommended` (bool) — 見送り推奨フラグ
- `skip_reason` (str) — 見送り理由
- `win_prediction` — 単勝買い目
- `place_prediction` — 複勝買い目
- `quinella_prediction` — 馬連買い目
- `trifecta_prediction` — 3連単買い目
- `disclaimer` (str) — 免責事項

**処理内容:**

1. **順位付け** — 統合確率の高い順にランク付け
2. **見送り判定** — 全馬のEVの最大値が **-0.3 未満**なら見送り推奨
3. **買い目生成**（見送りでない場合）：
   - **単勝**: 本命（1位馬）。EV > 0 なら `1unit`、否则は「見送り検討」
   - **複勝**: 複勝率 > 30% の上位馬。リスク `low`
   - **馬連**: 本命×対抗。リスク `medium`
   - **3連単**: 本命の勝率 > 15% の場合のみ生成（本命-対抗-穴馬）。リスク `high`
4. 各買い目にリスクレベル（🟢low / 🟡medium / 🔴high）を付与

**データソース:** なし

---

### 5.12 Backtester（バックテスト）

**役割:** 過去データで予想ロジックを検証するエージェント

**入力:**
- `context.prediction_actual` または `context.prediction_predicted`

**出力:**
- `context.backtest` — バックテスト結果辞書：
  - `total_races` (int) — 対象レース数
  - `hit_rate` (float) — 単勝的中率
  - `roi` (float) — 総合ROI
  - `profit_loss_total` (float) — 損益合計
  - `breakdown_by_bet_type` — 券種別内訳
  - `breakdown_by_course` — コース別内訳
  - `breakdown_by_distance` — 距離別内訳
  - `breakdown_by_condition` — 馬場別内訳
  - `improvement_suggestions` (list) — 改善提案

**処理内容:**

1. `DataSource.get_backtest_data()` で過去データを取得
2. 各レースで予想1位馬が実際に1着になったかを判定
3. 単勝・複勝それぞれで的中率と回収率を計算
4. コース・距離・馬場状態別にブレークダウン
5. 閾値に基づき改善提案を生成：
   - 単勝的中率 < 25% → 「上位予想の精度向上が必要」
   - 単勝ROI < 80% → 「期待値評価の閾値見直しを検討」
   - 複勝的中率 < 40% → 「複勝圏内予測の改善を検討」

**データソース:** あり（`DataSource` 経由。MVPでは20レースのサンプルデータ）

---

### 5.13 NoteStructureResearcher（Note構成調査）

**役割:** 人気競馬Note記事の共通パターンに基づき、無料/有料境界付きの構成を提案するエージェント

**入力:**
- `context.current_race_data`

**出力:**
- `context.note_suggestion` — 記事構成提案：
  - `suggested_title` — タイトル案（例: `【安田記念2026】機械学習モデルが導いた期待値◎｜危険な人気馬と勝負買い目`）
  - `structure` — 無料5セクション＋有料13セクションの構成案
  - `tone` — 記事のトーン（`reader_friendly_actionable`）
  - `successful_patterns` — 成功パターンのヒント
  - `ng_expressions` — 使用禁止表現（17種）
  - `recommended_expressions` — 推奨表現
  - `jravan_disclaimer` — JRA-VAN DataLab準拠の免責文

**記事構成（無料5＋有料13＝18セクション）:**

**無料部分:**

| # | セクション | 内容 |
|---|-----------|------|
| 1 | ヘッダー | タイトル |
| 2 | この記事で分かること | ティザー（具体馬名は出さない） |
| 3 | レース概要 | レース情報・JRA-VAN免責文 |
| 4 | 今年のレースの見立て | 展開予想（脚質構成はぼかす） |
| 5 | モデルの考え方 | モデル説明（特徴量は一般化） |
| 6 | 有料部分で公開する内容 | 購入導線ティザー |

**有料部分:**

| # | セクション | 内容 |
|---|-----------|------|
| 7 | 最終結論 | ◎○▲☆△の印一覧 |
| 8 | モデル評価ランキング | S/A/B評価＋妙味ランク＋馬券判断の表 |
| 9 | ◎本命 | 強み・懸念・買い条件 |
| 10 | ○対抗 | 強み・懸念・買い条件 |
| 11 | ▲単穴 | 強み・懸念・買い条件 |
| 12 | ☆評価馬 | 強み・懸念・買い条件・人気注意 |
| 13 | 危険な人気馬 | 人気過熱リスクの警告 |
| 14 | 消し馬 | 今回見送り馬（最大4頭） |
| 15 | 当日オッズ別の買い条件 | 馬ごとの買い/見送り閾値 |
| 16 | 推奨買い目 | 本線・保険・高配当狙いの3段階 |
| 17 | 資金配分 | 合計10,000円想定の具体配分 |
| 18 | 見送り条件 | レース全体を見送る条件 |
| 19 | 免責事項 | リスク説明・JRA-VAN出典 |

**データソース:** なし

---

### 5.14 NoteWriter（Note作成）

**役割:** 予想結果をもとにNote投稿用のMarkdown記事案を作成するエージェント。無料/有料境界付きの構成で、 monetizationを意識した記事を生成する。

**入力:**
- `context.note_suggestion`
- `context.prediction_actual`
- `context.evidence`
- `context.current_race_data`
- `context.backtest`

**出力:**
- `context.note_article` — 記事データ：
  - `title` (str) — 記事タイトル
  - `body_markdown` (str) — 記事本文（Markdown）
  - `summary_box` (str) — サマリー（本命/対抗/単穴/評価馬/見送り）
  - `key_prediction` (str) — 主要予想
  - `risk_warning` (str) — JRA-VAN免責文
  - `word_count` (int) — 文字数
  - `prohibited_word_violations` (list) — 禁止表現の検出結果
  - `data_sources` (str) — JRA-VAN DataLab出典表記

**処理内容:**

1. **無料部分**（5セクション）のMarkdown本文を構築：
   - **ヘッダー**: タイトル
   - **この記事で分かること**: ティザー（具体馬名は出さない）
   - **レース概要**: レース名・グレード・条件・JRA-VAN免責文
   - **今年のレースの見立て**: 展開予想（脚質構成はぼかす）
   - **モデルの考え方**: LightGBMの説明（特徴量は一般化、「独自の評価スコアを算出」）
   - **有料部分で公開する内容**: 購入導線ティザー

2. **有料部分**（13セクション）のMarkdown本文を構築：
   - **最終結論**: ◎○▲☆△の印一覧（騎手名付き）
   - **モデル評価ランキング**: S/A/B評価＋妙味ランク＋馬券判断の表
   - **◎本命**: 強み・懸念・買い条件
   - **○対抗**: 強み・懸念・買い条件
   - **▲単穴**: 強み・懸念・買い条件
   - **☆評価馬**: 強み・懸念・買い条件＋人気過熱注意
   - **危険な人気馬**: 人気過熱リスクの警告
   - **消し馬**: 今回見送り馬（最大4頭）
   - **当日オッズ別の買い条件**: 馬ごとの買い/見送り閾値
   - **推奨買い目**: 本線・保険・高配当狙いの3段階
   - **資金配分**: 合計10,000円想定の具体配分
   - **見送り条件**: レース全体を見送る条件
   - **免責事項**: 6項目＋JRA-VAN出典表記

3. **禁止表現チェック**: 17種の禁止語をスキャンし、検出結果を記録

**禁止表現（17種）:**

| 禁止語 | 理由 |
|-------|------|
| 絶対 | 確実性を装う表現 |
| 確定 | レース結果は確定前 |
| 鉄板 | 過度な自信を示唆 |
| 確実 | 確実性を装う表現 |
| 必勝 | 投資保証の誤認 |
| 必ず儲かる | 投資保証の誤認 |
| 回収保証 | 実績の保証なし |
| 100% | 絶対的表現 |
| 稼げる | 投資誘引 |
| 儲かる | 投資誘引 |
| 必ず当たる | 確実性を装う |
| 間違いなく | 確実性を装う |
| 間違いない | 確実性を装う |
| これだけ買えば勝てる | 責任ある表現ではない |
| 負けない | 確実性を装う |
| ノーリスク | リスクの隠蔽 |
| 安全 | リスクの隠蔽 |

**データソース:** なし

---

### 5.15 VisualizerAgent（EDA可視化）

**役割:** 分析結果のEDAチャートを画像ファイルとして生成するエージェント

**入力:**
- `context.features`
- `context.evidence`
- `context.actual_odds_eval`
- `context.backtest`

**出力:**
- `context.eda_images` — 生成されたチャートのファイルパス辞書

**処理内容:**

以下の5種類のチャートを `output/eda/{race_id}/` に生成します：

| チャート名 | ファイル名 | 内容 |
|-----------|-----------|------|
| `horse_comparison` | horse_comparison.png | 出走馬の勝率推定ランキング（横棒グラフ、グレード別カラー） |
| `feature_comparison` | feature_comparison.png | 上位5頭の特徴量比較（距離適性/調子/上がり/騎手厩舎） |
| `expected_value` | expected_value.png | オッズ vs モデル勝率の散布図（色=期待値EV） |
| `backtest_summary` | backtest_summary.png | 券種別の回収率・的中率 |
| `recent_form_heatmap` | recent_form_heatmap.png | 全馬の近5走着順ヒートマップ |

各チャートは個別にtry/exceptで保護されており、1つのチャート生成に失敗しても他のチャートは生成されます。日本語フォント（Noto Sans CJK JP）がインストールされていない場合は警告が出力されます。

**データソース:** なし

---

### 5.16 QualityAssurance（品質保証）

**役割:** 全成果物を120点満点で採点し、品質ゲートを管理するエージェント

**入力:**
- `context.prediction_actual`
- `context.note_article`
- （その他全コンテキストフィールドを参照）

**出力:**
- `context.qa_report` — QAレポート：
  - `total_score` (int) — 総合スコア（0〜120）
  - `passed` (bool) — 100点以上で True
  - `criteria` (list) — 10項目の採点結果
  - `overall_feedback` (str) — 総合フィードバック
  - `route_back_to` (str) — 差し戻し先（不合格時）
  - `retry_count` (int) — リトライ回数

**10項目の採点基準:**

| # | 評価項目 | 満点 | 主な判定基準 |
|---|---------|------|------------|
| 1 | データ鮮度 | 15 | 完成度スコア ≥ 95% → 15点、≥ 80% → 10点 |
| 2 | データ欠損チェック | 10 | critical問題0件 → 10点、あり → 4点 |
| 3 | 分析根拠の明確さ | 15 | 確率エントリ ≥ 8 & ファクタ ≥ 1 → 15点 |
| 4 | Web調査の信頼性 | 10 | カバレッジ ≥ 80% → 10点 |
| 5 | オッズ期待値 | 15 | 予想+実オッズ双方評価あり → 15点 |
| 6 | バックテスト結果 | 15 | 対象 ≥ 15レース → 15点 |
| 7 | 券種別予想の妥当性 | 10 | 1-4券種の予想 または 見送り → 10点 |
| 8 | Noteの読みやすさ | 10 | 文字数 > 500 & セクション ≥ 5 → 10点 |
| 9 | 誇大表現の排除 | 10 | 禁止語0件 → 10点、検出 → 0点 |
| 10 | リスク説明・出典表記 | 10 | リスク表記 ≥ 3箇所 & JRA-VAN出典あり → 10点 |

**合否ライン:** **100点 / 120点** 以上で通過

**データソース:** なし

---

## 6. 出力物の読み方

### 出力ファイル一覧

| ファイル | 形式 | 内容 |
|---------|------|------|
| `output/json/{race_id}.json` | JSON | PipelineContext の完全なJSONダンプ。全エージェントの出力と実行ログを含む |
| `output/markdown/{race_id}.md` | Markdown | Note投稿用の記事案。9セクション構成 |
| `output/logs/pipeline.jsonl` | JSONL | 各エージェントの実行ログ（JSON1行ずつ） |

### JSON出力の主要キー

`output/json/{race_id}.json` のトップレベルキー：

| キー | 内容 |
|-----|------|
| `race_id` / `pipeline_id` / `status` | パイプライン実行のメタ情報 |
| `historical_data` | 過去レース・出走馬・騎手・厩舎データ |
| `current_race_data` | レース情報と出馬表 |
| `quality_check` | データ品質レポート |
| `features` | 各馬の特徴量（25項目/頭） |
| `analysis` | 統計分析結果（確率・順位・ファクタ） |
| `ml_analysis` | LightGBM ML予測結果（確率・特徴量重要度） |
| `web_research` | Web調査結果 |
| `evidence` | 統合根拠プロファイル（強み/弱み/懸念/グレード） |
| `predicted_odds_eval` | 暫定オッズ評価 |
| `actual_odds_eval` | 最終オッズ評価（EV・推奨グレード） |
| `prediction_predicted` | 予想オッズベースの予想 |
| `prediction_actual` | 実オッズベースの予想（メイン） |
| `backtest` | バックテスト結果 |
| `eda_images` | EDA可視化チャートのファイルパス |
| `note_suggestion` | 記事構成案 |
| `note_article` | 生成されたNote記事 |
| `qa_report` | 品質保証スコアカード |
| `agent_results` | 16エージェントの実行ログ（成功/失敗・所要時間） |

### 信頼度グレードの読み方

2種類のグレードが存在します：

**根拠グレード（`evidence.horses[].evidence_grade`）**
統計分析とWeb調査を統合した総合評価：

| グレード | アイコン | 意味 |
|---------|---------|------|
| S | 🔴 | 強気 — 勝率が高く、根拠が強固で懸念なし |
| A | 🟠 | 買い — 勝率が高く、根拠が十分 |
| B | 🟡 | 中立 — 一定の勝率があるが懸念もあり |
| C | ⚪ | 様子見 — 根拠が弱いか懸念が多い |

**推奨グレード（`actual_odds_eval.evaluations[].recommendation_grade`）**
期待値（EV）に基づく購入推奨度：

| グレード | 意味 | EV条件 |
|---------|------|--------|
| S | 強く推奨 | EV > 0.3 & ギャップ > 0.10 |
| A | 推奨 | EV > 0.1 & ギャップ > 0.05 |
| B | 中立 | EV > -0.1 |
| C | 非推奨 | EV ≤ -0.1 |

### 予想オッズと実オッズの使い分け

| 段階 | タイミング | マーク | 特徴 |
|-----|-----------|--------|------|
| 予想オッズ評価 | レース前日〜当日午前 | `is_provisional: true` | 暫定的な価値評価。実オッズで再評価必須 |
| 実オッズ評価 | レース直前 | `is_provisional: false` | 最終的なEV計算と推奨グレード |

### 見送り判定

`prediction_actual.skip_recommended` が `true` の場合、システムは**馬券購入を見送る**ことを推奨しています。

条件: 全馬の期待値の最大値が **-0.3 未満**（どの馬に賭けても期待値が負で、損失の可能性が高い）

---

## 7. 設定のカスタマイズ

設定は `config/default.yaml` で管理されています。コピーを作成して変更し、`--config` オプションで指定できます。

```bash
cp config/default.yaml config/my-config.yaml
# my-config.yaml を編集
keiba --config config/my-config.yaml
```

### 設定ファイルの全セクション

#### `pipeline` — パイプライン実行設定

```yaml
pipeline:
  max_qa_retries: 3              # QA不合格時の最大リトライ回数
  fail_on_critical_quality: true # critical品質問題でパイプライン停止
  parallel_execution: true       # Agent 5 & 6 の並列実行を有効化
```

#### `data_source` — データソース設定

```yaml
data_source:
  active: "sample"               # "sample" / "production" / "jrvan"
  sample:
    race_id: "20260607-Tokyo-11" # サンプルレースID
  production:
    http:
      user_agent: "keiba-prediction/0.1.0 (educational research)"
      min_interval_seconds: 7
      daily_request_budget: 500
      timeout_seconds: 30
      max_retries: 2
    cache:
      directory: "data/store/cache"
      default_ttl_seconds: 3600
    netkeiba:
      enabled: true
      base_url: "https://db.netkeiba.com"
    jra:
      enabled: true
      base_url: "https://www.jra.go.jp"
    backtest:
      max_months: 2
      max_races: 5
```

#### `logging` — ログ設定

```yaml
logging:
  level: "INFO"                  # "INFO" / "DEBUG"（-v オプションで上書き）
  format: "structured"           # 構造化ログフォーマット
  log_dir: "output/logs"         # ログ出力先
  per_agent_files: true          # エージェント別ログファイル生成
```

#### `analysis` — 分析設定

```yaml
analysis:
  method: "statistical"          # "statistical"（現在）または "ml"（将来）
  feature_weights:               # 複合スコアの特徴量ウェイト（合計 1.0）
    distance_aptitude: 0.15      # 距離適性
    track_aptitude: 0.12         # 馬場適性
    recent_form: 0.20            # 近走成績（最大ウェイト）
    closing_speed: 0.15          # 上がり性能
    running_style: 0.08          # 脚質
    jockey_stats: 0.12           # 騎手成績
    trainer_stats: 0.08          # 厩舎成績
    pedigree: 0.05               # 血統
    weight_factors: 0.05         # 馬体重
```

> **ヒント:** ウェイトを調整することで、分析の傾向を変えられます。例えば騎手を重視するなら `jockey_stats` を上げ、血統を軽視するなら `pedigree` を下げます。合計は必ず **1.0** にしてください。

#### `odds` — オッズ評価設定

```yaml
odds:
  max_web_evidence_adjustment: 0.15  # Web証拠による確率調整の上限（±15%）
  value_threshold: 0.10              # バリュー判定の閾値
  skip_if_no_value: true             # 全EVが負なら見送り推奨
```

#### `quality` — 品質保証設定

```yaml
quality:
  passing_score: 100              # 合格ライン（/120点）
  total_score: 120                # 満点
  prohibited_words:               # 自動検出する禁止語
    - "絶対"
    - "確定"
    - "鉄板"
    - "必ず儲かる"
    - "回収保証"
    - "100%"
    - "間違いなく"
```

#### `note` — Note記事設定

```yaml
note:
  disclaimer: |                   # 記事末尾に付与する免責事項
    ※本予想は個人的な分析に基づくものであり、
    馬券の購入を保証するものではありません。
    競馬にはリスクがあり、投資額以上の損失が生じる可能性があります。
    自己責任でご判断ください。
```

---

## 8. データソースの差し替え

### DataSource ABC のインターフェース

全データ取得は `DataSource` 抽象基底クラス（`src/keiba/data/base_source.py`）を経由します。6つの抽象メソッドを定義：

| メソッド | 戻り値 | 使用エージェント |
|---------|-------|----------------|
| `get_historical_data(race_id)` | 過去レース・馬・騎手・厩舎データ | Agent 1 |
| `get_current_race_card(race_id)` | レース情報 + 出馬表 | Agent 2 |
| `get_predicted_odds(race_id)` | 予想オッズ | Agent 9 |
| `get_actual_odds(race_id)` | 実オッズ | Agent 10 |
| `get_web_content(race_id, horse_ids)` | Web調査結果 | Agent 7 |
| `get_backtest_data(config)` | バックテスト用過去データ | Agent 12 |

### サンプルデータの内容（SampleDataSource）

MVPでは `src/keiba/data/sample/` 以下の架空データを使用します：

- **レース**: 第93回東京優駿（架空GI） / 東京2400m芝
- **出走馬**: 10頭（逃げ1 / 先行2 / 差し4 / 追込3）
  - 3連勝中の実力馬、休み明け、距離初体験、牝馬、増減 etc.
- **過去成績**: 各馬5-8走（着順・タイム・上がり・脚質・通過順位）
- **オッズ**: 予想オッズ（1.8x〜98.3x）+ 実オッズ（市場変動あり）
- **Web調査**: 調教レポート、陣営コメント、ニュース（ relevance / impact 付き）
- **バックテスト**: 20レース（`random.seed(42)` で再現可能）

### 新しいデータソースの追加手順

1. `src/keiba/data/` に新しいモジュールを作成（例: `production/netkeiba_source.py`）
2. `DataSource` を継承し、6つの抽象メソッドを実装
3. `config/default.yaml` の `data_source.active` を変更、または `--source` オプションで指定

```python
from keiba.data.base_source import DataSource

class NetkeibaSource(DataSource):
    def get_historical_data(self, race_id: str) -> dict:
        # 実装
        ...
```

### JrVanDataSource（JRA-VAN DataLab）

JRA-VAN DataLab のCSVデータをSQLiteに変換して使用するデータソースです。ML学習の推奨データソース。

**構成:**

| ファイル | 役割 |
|---------|------|
| `src/keiba/data/jrvan/loader.py` | CSV→SQLite変換・DBコネクション管理 |
| `src/keiba/data/jrvan/data_source.py` | DataSourceインターフェース実装 |
| `data/store/jrvan.db` | SQLiteデータベース（27年分・約49万頭） |

**データ規模:**

| 項目 | 値 |
|------|-----|
| 期間 | 1999〜2026年（27年分） |
| レース数 | 214,988 |
| カラム数 | 92（RA + SE 結合済み） |
| 学習済みモデル | 検証AUC=0.8332、テストAUC=0.7707 |

**使用方法:**

```bash
# JRA-VANデータでモデル学習
keiba train --source jrvan --optuna-trials 50
```

### 外部アクセスに関する方針

> ⚠️ **必須事項**: 本番実装時は、対象サイトの利用規約・robots.txt・アクセス頻度制限を必ず確認し、過剰アクセスを避けてください。MVPでは外部サイトへの実アクセスは行いません。

---

## 9. よくある使い方パターン

### パターン1: サンプルデータで手軽に試す

```bash
# デフォルト設定で実行
keiba

# 生成されたNote記事を確認
cat output/markdown/20260607-Tokyo-11.md

# JSON結果から上位3頭の確率を確認
python3 -c "
import json
data = json.load(open('output/json/20260607-Tokyo-11.json'))
for h in data['evidence']['horses'][:3]:
    print(f\"{h['horse_name']}: 勝率{h['integrated_probability']:.1%} グレード{h['evidence_grade']}\")
"
```

### パターン2: 特徴量ウェイトを調整する

```bash
# 設定ファイルをコピー
cp config/default.yaml config/attack-config.yaml
```

`attack-config.yaml` の `analysis.feature_weights` を変更：

```yaml
analysis:
  feature_weights:
    recent_form: 0.30          # 近走成績を重視（0.20 → 0.30）
    closing_speed: 0.20        # 上がり性能を重視（0.15 → 0.20）
    distance_aptitude: 0.10    # 距離適性をやや下げ（0.15 → 0.10）
    track_aptitude: 0.10
    jockey_stats: 0.10
    running_style: 0.05
    trainer_stats: 0.05
    pedigree: 0.05
    weight_factors: 0.05
```

```bash
keiba --config config/attack-config.yaml
```

### パターン3: 詳細ログでエージェントの動きを確認

```bash
# DEBUG レベルで実行
keiba -v

# 特定エージェントのログを抽出
cat output/logs/pipeline.jsonl | grep "PythonAnalyzer"

# JSON結果から特定エージェントの実行情報を確認
python3 -c "
import json
data = json.load(open('output/json/20260607-Tokyo-11.json'))
for r in data['agent_results']:
    print(f\"{r['agent_name']}: {r['duration_seconds']:.2f}s {'✅' if r['success'] else '❌'}\")
"
```

### パターン4: QAスコアを詳しく確認する

```bash
keiba
# 画面出力のQA採点セクションを確認
# またはJSONから取得:
python3 -c "
import json
data = json.load(open('output/json/20260607-Tokyo-11.json'))
qa = data['qa_report']
print(f'総合スコア: {qa[\"total_score\"]}/120')
print(f'合否: {\"通過\" if qa[\"passed\"] else \"不合格\"}')
for c in qa['criteria']:
    mark = '✓' if c['passed'] else '✗'
    print(f'  {mark} {c[\"criterion_name\"]}: {c[\"actual_score\"]}/{c[\"max_score\"]} - {c[\"notes\"]}')
"
```

### パターン5: テストスイートを実行する

```bash
# 全テスト
pytest

# エージェント別テスト
pytest tests/test_agents/ -v

# 統合テストのみ
pytest tests/test_integration/ -v

# カバレッジレポート
pytest --cov=keiba --cov-report=term-missing
```

### パターン6: MLモデルを学習する

```bash
# JRA-VANデータでフル学習（推奨）
keiba train --source jrvan --optuna-trials 50

# 学習結果の確認
# val AUC / test AUC / 上位特徴量が表示される

# サンプルデータで学習（動作確認用）
keiba train --source sample --optuna-trials 10

# 学習スクリプトを直接実行（詳細制御用）
.venv/bin/python scripts/train_full.py
```

### パターン7: 出馬表を取得する（個別レース）

```bash
# netkeiba出馬表を取得（netkeiba形式のrace_id指定）
.venv/bin/python scripts/fetch_racecard.py 202605030211

# DB照合なしで取得（軽量）
.venv/bin/python scripts/fetch_racecard.py 202605030211 --no-db

# 出力先を指定
.venv/bin/python scripts/fetch_racecard.py 202605030211 -o output/racecard.json
```

### パターン8: 個別レース予測スクリプト

特定レース向けの予測スクリプトを使用する場合:

```bash
# 予測実行（レース固有のHORSESデータを内蔵）
.venv/bin/python scripts/predict_yasuda.py

# 出力:
#   output/yasuda_kinen_2026.json — 予測結果JSON
#   output/note_yasuda_kinen_2026.md — Note記事
```

### パターン9: 対話型リーダーで段階的に作業する

```bash
# リーダーを起動
keiba lead

# メニューが表示されるので番号を選択:
#   [1] 完全予想パイプライン  — 全16エージェント一括実行
#   [2] データ取得            — Agent 1-3（過去データ＋出馬表＋品質確認）
#   [3] 特徴量生成            — Agent 4（18項目の特徴量生成）
#   [4] 分析                  — Agent 5-8（統計/ML/Web→根拠統合）
#   [5] オッズ評価            — Agent 9-10（予想/実オッズで期待値計算）
#   [6] 予想生成              — Agent 11-12（買い目生成＋バックテスト）
#   [7] 記事生成              — Agent 13-16（チャート→記事→品質確認）
#   [8] ML学習                — LightGBMモデルの学習
#   [s] 現在の状況確認        — 進捗テーブル表示
#   [r] レース変更            — レースID変更・状態リセット
#   [q] 終了

# 例: 段階的に実行
# 1. まず [2] でデータを取得
# 2. [s] で状況確認
# 3. [4] で分析
# 4. [5] でオッズ評価
# 5. [6] で予想生成
# 6. [s] で最終確認

# 前提チェック機能:
# 未完了の前提ステージがある場合、自動的に検出して確認プロンプトを表示:
#   ⚠️ 「分析」には以下のステージが未完了です:
#     • historical_data
#     • current_data
#     • quality_check
#     • feature_gen
#   先に実行しますか？ [y/n]:
```

---

## 10. トラブルシューティング

### よくあるエラーと対処法

| エラー・症状 | 原因 | 対処法 |
|-------------|------|--------|
| エラー・症状 | 原因 | 対処法 |
|-------------|------|--------|
| `Data source 'production' not implemented, falling back to sample` | `--source production` を指定したが本番ソース未実装 | `--source sample` またはオプション省略 |
| `lightgbmがインストールされていません` | venvにlightgbmが未インストール | `pip install lightgbm` をvenv内で実行 |
| `学習済みモデルが存在しません` | ML予測時にモデルファイルがない | `keiba train --source jrvan` でモデルを学習 |
| `ModuleNotFoundError: No module named 'lightgbm'` | system pythonでvenv外実行 | `.venv/bin/python` で実行 |
| `Input validation failed for {AgentName}` | 前段エージェントの出力が `None`（依存データなし） | `-v` で詳細ログを確認。最初に失敗したエージェントを特定 |
| QAスコア < 100 / リトライループ | 品質基準を満たさない。最大3回リトライ後も改善しない場合あり | `qa_report.criteria` で不合格項目を確認。該当エージェントの入力データを見直し |
| `Pipeline failed at {stage_name}` | エージェントの `process()` で例外発生 | `-v` でフルトレースバックを確認。`output/logs/pipeline.jsonl` も参照 |
| 出力ファイルが生成されない | パイプラインが `completed` に達していない | コンソール出力で最後に実行されたエージェントを確認。`context.status` が `failed` でないか |
| 文字化け（日本語表示） | ターミナルのエンコーディングがUTF-8でない | `export PYTHONIOENCODING=utf-8` を設定、またはUTF-8対応ターミナルを使用 |
| `pip` / `pip3` が見つからない | venv を有効化していない | `source .venv/bin/activate` を実行 |

### ログの確認方法

```bash
# JSONLログの全件表示
cat output/logs/pipeline.jsonl

# 失敗したエージェントのみ抽出
cat output/logs/pipeline.jsonl | python3 -c "
import sys, json
for line in sys.stdin:
    entry = json.loads(line)
    if not entry.get('success', True):
        print(json.dumps(entry, ensure_ascii=False, indent=2))
"
```

---

## 11. テストと開発

### テスト実行コマンド

```bash
# 全テスト実行
pytest

# 詳細表示
pytest tests/ -v

# エージェント別テスト
pytest tests/test_agents/ -v

# 統合テスト
pytest tests/test_integration/ -v

# カバレッジ付き
pytest --cov=keiba --cov-report=term-missing

# HTMLカバレッジレポート
pytest --cov=keiba --cov-report=html
```

### 型チェック・Lint

```bash
mypy src/keiba
ruff check src/ tests/ --fix
```

### テストフィクスチャ一覧

`tests/conftest.py` で定義されている共通フィクスチャ：

| フィクスチャ | 内容 | 対象エージェント |
|-------------|------|----------------|
| `sample_race_id` | `"20260607-Tokyo-11"` | 共通 |
| `sample_data_source` | `SampleDataSource()` インスタンス | 共通 |
| `fresh_context` | 空の `PipelineContext` | Agent 1 |
| `context_with_historical` | Agent 1 実行済み | Agent 2 |
| `context_with_current` | Agent 1-2 実行済み | Agent 3 |
| `context_with_quality` | Agent 1-3 実行済み | Agent 4 |
| `context_with_features` | Agent 1-4 実行済み | Agent 5-6 |
| `full_context` | Agent 1-14 全実行済み | 統合テスト |

### 新エージェントの追加手順

1. `src/keiba/agents/new_agent.py` に `BaseAgent` を継承したクラスを作成
2. `validate_input(context)` と `process(context)` を実装
3. `src/keiba/models/pipeline.py` の `PipelineContext` に出力フィールドを追加
4. `src/keiba/orchestration/pipeline.py` の `build_pipeline()` に `PipelineStage` を追加
5. `tests/test_agents/` にテストを追加
6. `tests/test_integration/test_full_pipeline.py` の期待値を更新

### 個別スクリプト

パイプラインとは独立して実行可能なスクリプト群です:

| スクリプト | 用途 | 使用例 |
|-----------|------|--------|
| `scripts/train_full.py` | フルデータでのモデル学習 | `.venv/bin/python scripts/train_full.py` |
| `scripts/fetch_racecard.py` | netkeiba出馬表取得 | `.venv/bin/python scripts/fetch_racecard.py <race_id>` |
| `scripts/predict_yasuda.py` | 個別レース予測（レース固有データ内蔵） | `.venv/bin/python scripts/predict_yasuda.py` |

> **注意:** lightgbmが必要なスクリプトは `.venv/bin/python` で実行してください。system python3にはlightgbmがインストールされていません。

### 参考リンク

- 技術的詳細: [docs/design.md](design.md)
- 設定ファイル: [config/default.yaml](../config/default.yaml)
- プロジェクト構成: [README.md](../README.md)
