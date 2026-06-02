# 競馬予想システム — 全体設計・実装計画

> 中央競馬の重賞・メインレース（G1/G2/G3、土日11R）向けの予想システムを、14のエージェントで構成するパイプラインとして実装する。
> まずはサンプルデータで動くMVPを作り、後から本番データ取得に差し替えられる設計にする。

---

## 目次

1. [全体設計方針](#1-全体設計方針)
2. [フォルダ構成](#2-フォルダ構成)
3. [データフロー](#3-データフロー)
4. [各エージェントの責務・入出力](#4-各エージェントの責務入出力)
5. [主要データモデル](#5-主要データモデル)
6. [BaseAgent 設計](#6-baseagent-設計)
7. [オーケストレーション設計](#7-オーケストレーション設計)
8. [設定・ログ](#8-設定ログ)
9. [実行方法](#9-実行方法)
10. [MVP対象範囲](#10-mvp対象範囲)
11. [差し替え設計（将来拡張）](#11-差し替え設計将来拡張)
12. [実装順序](#12-実装順序)
13. [テスト戦略](#13-テスト戦略)
14. [検証方法](#14-検証方法)

---

## 1. 全体設計方針

| 方針 | 内容 |
|------|------|
| **言語・FW** | Python 3.11+ / Pydantic v2 で型安全なデータモデル |
| **パイプラインパターン** | 14エージェントが `PipelineContext`（共有状態）を読み書きしながら直列・並列実行 |
| **データソース抽象化** | `DataSource` ABC を挟み、MVPは `SampleDataSource`、本番は `NetkeibaSource` 等に差し替え |
| **外部アクセス制約** | **MVPでは外部サイトへの実アクセス禁止。SampleDataSourceのみで動作確認。** 本番実装時は対象サイトの利用規約・robots.txt・アクセス頻度制限を必ず確認し、過剰アクセスを避けること。 |
| **QAゲート付きリトライ** | 品質保証エージェントが100点未満なら該当エージェントへ差し戻し（最大3回） |
| **誇大表現禁止** | QAエージェントが禁止語（絶対/確定/鉄板/必ず儲かる/回収保証 等）を自動検出 |
| **見送り推奨** | 期待値が閾値未満なら無理に買い目を出さず「見送り」判定 |
| **オッズ段階区分** | 予想オッズ（暫定）→ 実オッズ（最終）で明確に分けて評価 |
| **過去データ蓄積** | 初回全量取得 → 以後差分更新。学習・統計分析・バックテスト用に蓄積 |
| **データ不足時の態度** | 機械学習を過信せず、ルールベース + 統計スコア + バックテストを中心に |

---

## 2. フォルダ構成

```
keiba/
├── pyproject.toml                          # プロジェクト設定・依存関係
├── README.md                               # 使い方説明
├── .gitignore
├── CLAUDE.md                               # Claude Code 用プロジェクト指示
│
├── config/
│   ├── default.yaml                        # デフォルト設定
│   └── logging.yaml                        # ログ設定
│
├── docs/
│   └── design.md                           # 本ドキュメント
│
├── src/
│   └── keiba/
│       ├── __init__.py
│       ├── cli.py                          # CLI エントリポイント
│       │
│       ├── models/                         # Pydantic データモデル
│       │   ├── __init__.py
│       │   ├── base.py                     # 共通Enum, KeibaBaseModel
│       │   ├── race.py                     # Race, RaceCard
│       │   ├── horse.py                    # Horse, PastPerformance, Entry
│       │   ├── jockey.py                   # Jockey, JockeyStats
│       │   ├── trainer.py                  # Trainer, TrainerStats
│       │   ├── odds.py                     # OddsEntry, PredictedOdds, ActualOdds
│       │   ├── features.py                 # HorseFeatures, FeatureSet
│       │   ├── analysis.py                 # AnalysisResult, ProbabilityEstimate
│       │   ├── web_research.py             # WebResearchResult, NewsItem
│       │   ├── evidence.py                 # EvidenceProfile, StrengthWeakness
│       │   ├── prediction.py               # RacePrediction, BetRecommendation
│       │   ├── backtest.py                 # BacktestSummary
│       │   ├── note.py                     # NoteArticle, NoteSuggestion
│       │   ├── quality.py                  # QAReport, QACriterion
│       │   └── pipeline.py                 # PipelineContext, AgentResult
│       │
│       ├── agents/                         # 14エージェント
│       │   ├── __init__.py
│       │   ├── base.py                     # BaseAgent 抽象クラス
│       │   ├── historical_data_manager.py  # 1.  過去データ管理
│       │   ├── current_data_fetcher.py     # 2.  当日・前日データ取得
│       │   ├── data_quality_checker.py     # 3.  データ品質チェック
│       │   ├── feature_generator.py        # 4.  特徴量生成
│       │   ├── python_analyzer.py          # 5.  Python分析
│       │   ├── web_researcher.py           # 6.  Web調査
│       │   ├── evidence_integrator.py      # 7.  根拠統合
│       │   ├── predicted_odds_evaluator.py # 8.  予想オッズ評価
│       │   ├── actual_odds_evaluator.py    # 9.  実オッズ評価
│       │   ├── prediction_generator.py     # 10. 予想生成
│       │   ├── backtester.py               # 11. バックテスト
│       │   ├── note_structure_researcher.py# 12. Note構成調査
│       │   ├── note_writer.py              # 13. Note作成
│       │   └── quality_assurance.py        # 14. 品質保証
│       │
│       ├── data/                           # データソース（差し替え可能）
│       │   ├── __init__.py
│       │   ├── base_source.py              # DataSource ABC
│       │   ├── sample/                     # MVP用サンプルデータ
│       │   │   ├── __init__.py
│       │   │   ├── sample_source.py        # SampleDataSource 実装
│       │   │   ├── races.py                # サンプルレース定義
│       │   │   ├── horses.py               # サンプル出走馬（10頭）
│       │   │   ├── past_performances.py    # サンプル過去成績
│       │   │   ├── odds.py                 # 予想オッズ + 実オッズ
│       │   │   └── web_content.py          # サンプルWeb調査内容
│       │   └── production/                 # 将来用（スタブ）
│       │       ├── __init__.py
│       │       ├── netkeiba_source.py      # netkeiba スクレイパー（スタブ）
│       │       └── jra_source.py           # JRA公式データ（スタブ）
│       │
│       ├── orchestration/                  # パイプライン管理
│       │   ├── __init__.py
│       │   ├── orchestrator.py             # メインオーケストレータ
│       │   └── pipeline.py                 # ステージ定義・依存関係
│       │
│       └── utils/
│           ├── __init__.py
│           ├── config.py                   # 設定ローダー
│           └── logging.py                  # 構造化ログ
│
├── tests/
│   ├── __init__.py
│   ├── conftest.py                         # 共通フィクスチャ
│   ├── test_agents/                        # エージェント別テスト
│   │   ├── __init__.py
│   │   ├── test_base_agent.py
│   │   ├── test_historical_data_manager.py
│   │   ├── test_current_data_fetcher.py
│   │   ├── test_data_quality_checker.py
│   │   ├── test_feature_generator.py
│   │   ├── test_python_analyzer.py
│   │   ├── test_web_researcher.py
│   │   ├── test_evidence_integrator.py
│   │   ├── test_predicted_odds_evaluator.py
│   │   ├── test_actual_odds_evaluator.py
│   │   ├── test_prediction_generator.py
│   │   ├── test_backtester.py
│   │   ├── test_note_structure_researcher.py
│   │   ├── test_note_writer.py
│   │   └── test_quality_assurance.py
│   ├── test_orchestration/
│   │   ├── __init__.py
│   │   └── test_orchestrator.py
│   └── test_integration/
│       ├── __init__.py
│       └── test_full_pipeline.py
│
├── output/                                 # 成果物出力（gitignore）
│   ├── json/
│   ├── markdown/
│   └── logs/
│
└── data/                                   # ローカルデータ蓄積（gitignore）
    └── store/
```

---

## 3. データフロー

```
[1. 過去データ管理] ─────────────────────┐
       ↓                                  │
[2. 当日・前日データ取得] ←──────────────┘
       ↓
[3. データ品質チェック] → 問題あれば [1]/[2] へ差し戻し
       ↓
[4. 特徴量生成]
       ↓
  ┌────┴────┐
  ↓         ↓
[5. Python分析]  [6. Web調査]     ← 並列実行
  └────┬────┘
       ↓
[7. 根拠統合]
       ↓
[8. 予想オッズ評価] ← 暫定評価として出力
       ↓
[9. 実オッズ評価]   ← 実オッズで再評価
       ↓
[10. 予想生成] → 買い目 or 見送り
       ↓
[11. バックテスト]
       ↓
[12. Note構成調査]
       ↓
[13. Note作成]
       ↓
[14. 品質保証] → 100点以上なら完了 / 未満なら該当エージェントへ差し戻し
```

### 差し戻しルール

| 品質保証での問題 | 差し戻し先 |
|---|---|
| データ品質に問題 | [1] 過去データ管理 / [2] 当日データ取得 / [3] 品質チェック |
| 特徴量に問題 | [4] 特徴量生成 |
| 分析根拠が弱い | [5] Python分析 |
| Web調査が弱い | [6] Web調査 |
| 根拠整理が弱い | [7] 根拠統合 |
| オッズ評価が弱い | [8] 予想オッズ評価 / [9] 実オッズ評価 |
| 買い目が多すぎる | [10] 予想生成 |
| バックテスト結果が弱い | [11] バックテスト |
| Noteの説得力が弱い | [13] Note作成 |
| 誇大表現がある | [13] Note作成 |

---

## 4. 各エージェントの責務・入出力

### 1. 過去データ管理エージェント (HistoricalDataManager)

| 項目 | 内容 |
|------|------|
| **役割** | 過去レースデータを取得・保存・管理する。初回取得と差分更新を分ける。学習・統計分析・バックテスト用のデータを整備する。 |
| **入力** | race_id, 対象期間, 競馬場, レース種別, グレード条件 |
| **出力** | races, horses, past_performances, jockey_stats, trainer_stats, 更新ログ |
| **書込フィールド** | `context.historical_data` |

### 2. 当日・前日データ取得エージェント (CurrentDataFetcher)

| 項目 | 内容 |
|------|------|
| **役割** | 対象レースの最新情報を取得する。出馬表・枠順・騎手・斤量・天気・馬場状態・出走取消・オッズ等。 |
| **入力** | race_id, historical_data |
| **出力** | RaceCard（レース基本情報・出走馬情報・枠順・騎手・斤量・天気・馬場状態・取消情報・オッズ） |
| **書込フィールド** | `context.current_race_data` |

### 3. データ品質チェックエージェント (DataQualityChecker)

| 項目 | 内容 |
|------|------|
| **役割** | 取得したデータに欠損や異常がないか確認する。分析に使ってよいか判定する。問題があれば警告を出す。 |
| **確認項目** | 出走取消, 騎手変更, 枠順未確定, 馬場状態未確定, オッズ未取得, 過去成績の欠損, 不自然な数値, 古い情報の混入 |
| **入力** | historical_data, current_race_data |
| **出力** | 品質レポート（passed/issues/completeness_score/anomalies） |
| **書込フィールド** | `context.quality_check` |

### 4. 特徴量生成エージェント (FeatureGenerator)

| 項目 | 内容 |
|------|------|
| **役割** | 予想に使う特徴量を作成する。各馬を比較しやすい数値に変換する。 |
| **特徴量** | 距離適性, 馬場適性, コース適性, 脚質, 上がり性能, 近走成績, ローテーション, 騎手成績, 厩舎成績, 枠順傾向, 人気と成績の関係, 重賞実績, 同条件実績 |
| **入力** | historical_data, current_race_data, quality_check |
| **出力** | FeatureSet（馬ごとの特徴量テーブル、レースごとの特徴量、分析用データセット） |
| **書込フィールド** | `context.features` |

### 5. Python分析エージェント (PythonAnalyzer)

| 項目 | 内容 |
|------|------|
| **役割** | Pythonで統計分析・スコアリング・必要に応じて機械学習を行う。データ量が少ない場合は統計スコア中心にする。 |
| **分析内容** | 各馬の能力スコア, 勝率推定, 複勝率推定, 順位期待値, 条件別の強み・弱み, レース傾向, 馬ごとの比較 |
| **入力** | features, historical_data |
| **出力** | AnalysisResult（分析スコア・勝率推定・複勝率推定・順位予測・分析レポート） |
| **書込フィールド** | `context.analysis` |
| **備考** | MVPでは純統計手法。データ蓄積後にML切替可能。 |

### 6. Web調査エージェント (WebResearcher)

| 項目 | 内容 |
|------|------|
| **役割** | 各レースと出走馬についてWeb検索で補足情報を集める。データだけでは分からない情報を補助的に扱う。 |
| **調査対象** | ニュース, 調教情報, 陣営コメント, 騎手コメント, コース傾向, 馬場傾向, レース傾向, 注目馬の状態 |
| **入力** | current_race_data |
| **出力** | WebResearchResult（馬ごとの調査レポート・レース傾向・情報源一覧・信頼度・影響度） |
| **書込フィールド** | `context.web_research` |
| **注意** | Web情報は補助情報。データ分析結果より過度に優先しない。SNS・個人予想は信頼度低め。 |

### 7. 根拠統合エージェント (EvidenceIntegrator)

| 項目 | 内容 |
|------|------|
| **役割** | Python分析結果とWeb調査結果を統合する。各馬の強み・弱み・不安要素を整理する。データ根拠と調査根拠を分けて記録する。 |
| **入力** | analysis + web_research |
| **出力** | EvidenceProfile（馬ごとの総合評価・強み・弱み・不安要素・買える理由・消し材料・根拠一覧） |
| **書込フィールド** | `context.evidence` |
| **調整幅** | Web証拠は確率を最大 ±15% まで調整可能 |

### 8. 予想オッズ評価エージェント (PredictedOddsEvaluator)

| 項目 | 内容 |
|------|------|
| **役割** | 数日前・前日発売前の予想オッズを使って暫定評価を行う。実オッズがない段階では期待値を断定しない。 |
| **入力** | evidence, current_race_data |
| **出力** | 暫定期待値評価（is_provisional=True, 予想オッズベースの暫定妙味・買い候補・見送り候補） |
| **書込フィールド** | `context.predicted_odds_eval` |
| **注意** | 必ず「暫定評価」「実オッズ取得後に再評価が必要」と明記する。 |

### 9. 実オッズ評価エージェント (ActualOddsEvaluator)

| 項目 | 内容 |
|------|------|
| **役割** | 実オッズ取得後に期待値を再計算する。市場評価とモデル評価のズレを見る。 |
| **入力** | evidence, predicted_odds_eval, current_race_data |
| **出力** | 実オッズ評価（期待値・市場確率・モデル推定確率・妙味判定・推奨度 S/A/B/C・見送り判定・予想オッズからの変更点） |
| **書込フィールド** | `context.actual_odds_eval` |

### 10. 予想生成エージェント (PredictionGenerator)

| 項目 | 内容 |
|------|------|
| **役割** | 各レースの最終予想を作成する。券種別に買い目を出す。信頼度が低い券種は無理に出さず見送りにする。 |
| **対象券種** | 単勝, 複勝, ワイド, 馬連, 馬単, 3連複, 3連単 |
| **入力** | evidence, predicted_odds_eval, actual_odds_eval, analysis |
| **出力** | RacePrediction（本命・対抗・単穴・連下・穴馬・券種別買い目・信頼度・期待値・見送り理由） |
| **書込フィールド** | `context.prediction_predicted`, `context.prediction_actual` |
| **注意** | 買い目を出しすぎない。3連単は根拠が弱ければ見送り。信頼度低なら「買わない」判断。 |

### 11. バックテストエージェント (Backtester)

| 項目 | 内容 |
|------|------|
| **役割** | 過去データを使って予想ロジックを検証する。的中率と回収率を確認する。 |
| **入力** | historical_data, prediction |
| **出力** | BacktestSummary（的中率・回収率・単勝/複勝/ワイド/馬連回収率・券種別/競馬場別/距離別/馬場別/人気別成績・改善提案） |
| **書込フィールド** | `context.backtest` |

### 12. Note構成調査エージェント (NoteStructureResearcher)

| 項目 | 内容 |
|------|------|
| **役割** | 売れている競馬予想Noteの構成を調査する。タイトル・見出し・導入・根拠提示・買い目提示・注意書きの流れを分析する。 |
| **入力** | race_name, grade |
| **出力** | NoteSuggestion（売れている構成パターン・タイトル案・見出し案・読者導線・NG表現一覧・採用/回避すべき表現） |
| **書込フィールド** | `context.note_suggestion` |

### 13. Note作成エージェント (NoteWriter)

| 項目 | 内容 |
|------|------|
| **役割** | 予想結果をもとにNote記事案を作成する。データ分析・Web調査・期待値・リスクを交えて説明する。 |
| **入力** | note_suggestion, evidence, prediction, backtest, current_race_data |
| **出力** | NoteArticle（タイトル・導入文・レース見解・各馬評価・本命/対抗/穴馬・買い目・根拠・リスク説明・注意喚起・まとめ・当日更新項目） |
| **書込フィールド** | `context.note_article` |
| **禁止表現** | 絶対当たる, 確定, 鉄板, 必ず儲かる, 回収保証, これだけ買えば勝てる |

### 14. 品質保証エージェント (QualityAssurance)

| 項目 | 内容 |
|------|------|
| **役割** | 生成された予想・レポート・Note記事を評価する。独自の採点基準で100点以上なら通過。100点未満なら差し戻す。 |
| **入力** | 全前段出力 |
| **出力** | QAReport（120点満点・100点以上で通過・差し戻し先・再試行回数） |
| **書込フィールド** | `context.qa_report` |

#### 採点基準（120点満点）

| 基準 | 配点 |
|------|------|
| データ鮮度 | 15点 |
| データ欠損チェック | 10点 |
| 分析根拠の明確さ | 15点 |
| Web調査の信頼性 | 10点 |
| オッズ期待値 | 15点 |
| バックテスト結果 | 15点 |
| 券種別予想の妥当性 | 10点 |
| Noteの読みやすさ | 10点 |
| 誇大表現の排除 | 10点 |
| リスク説明 | 10点 |

#### 通過条件
- 100点以上
- 誇大表現がない
- 根拠が明確
- 期待値評価がある
- 見送り判断ができている
- データ品質チェックが通っている
- リスク説明がある

---

## 5. 主要データモデル

### base.py — 共通Enum

```python
class TrackType(str, Enum):      # 芝 / ダート / 障害
class TrackCondition(str, Enum): # 良 / 稍重 / 重 / 不良
class Weather(str, Enum):        # 晴 / 曇 / 雨 / 雪
class RaceGrade(str, Enum):      # GI / GII / GIII / L
class BetType(str, Enum):        # 単勝 / 複勝 / 馬単 / 馬連 / 3連単 / 3連複
class ConfidenceGrade(str, Enum):# S / A / B / C
class RunningStyle(str, Enum):   # 逃げ / 先行 / 差し / 追込
class Gender(str, Enum):         # 牡 / 牝 / せん
```

### race.py

```python
class Race:
    race_id: str          # "20260607-Tokyo-11"
    race_name: str        # "第93回東京優駿（日本ダービー）"
    race_date: date
    race_number: int      # R番 (1-12)
    course: str           # "東京", "中山", "京都"
    distance: int         # meters
    track_type: TrackType
    grade: RaceGrade
    weather: Weather | None
    track_condition: TrackCondition | None
    post_time: str | None
    prize_money_first: int | None

class RaceCard:
    race: Race
    entries: list[Entry]
```

### horse.py

```python
class Horse:
    horse_id: str
    horse_name: str
    birth_year: int
    gender: Gender
    age: int
    trainer_name: str
    pedigree_sire: str | None
    pedigree_dam_sire: str | None

class PastPerformance:
    race_id: str
    race_date: date
    race_name: str
    course: str
    distance: int
    track_type: TrackType
    track_condition: TrackCondition
    finish_position: int
    total_runners: int
    jockey_name: str
    weight_carried: float
    finish_time: float | None
    popularity: int
    odds: float
    last_3f: float | None
    running_style: RunningStyle | None
    passing_order: str | None   # "3-3-2-1"

class Entry:
    entry_id: str
    horse: Horse
    jockey: Jockey
    weight_carried: float
    post_position: int
    bracket_number: int
    horse_weight: float | None
    weight_change: float | None
    past_performances: list[PastPerformance]
```

### odds.py

```python
class OddsEntry:
    entry_id: str
    horse_name: str
    win_odds: float
    place_odds_min: float | None
    place_odds_max: float | None
    popularity_rank: int

class PredictedOdds:
    race_id: str
    is_provisional: bool = True
    calculated_at: datetime
    entries: list[OddsEntry]
    method: str   # "model", "morning_line"

class ActualOdds:
    race_id: str
    is_final: bool
    recorded_at: datetime
    entries: list[OddsEntry]
    total_pool: int | None
```

### features.py

```python
class HorseFeatures:
    entry_id: str
    horse_id: str
    # 距離適性
    distance_aptitude_score: float      # 0-100
    optimal_distance_min: int
    optimal_distance_max: int
    # 馬場適性
    track_turf_score: float             # 0-100
    track_dirt_score: float             # 0-100
    course_specific_score: dict[str, float]
    # 脚質
    primary_style: RunningStyle
    style_consistency: float            # 0-1
    # 上がり
    average_last_3f: float | None
    best_last_3f: float | None
    closing_speed_rank: int | None
    # 近走
    recent_3_runs: list[int]
    recent_5_runs: list[int]
    form_score: float                   # 0-100
    # クラス・距離変更
    class_change: str | None            # "up", "down", "same"
    distance_change: str | None
    # 馬体重
    weight_carried_change: float | None
    horse_weight_trend: str | None
    # 騎手・厩舎
    jockey_trainer_win_rate: float | None
    jockey_course_win_rate: float | None

class FeatureSet:
    race_id: str
    generated_at: datetime
    horse_features: list[HorseFeatures]
    field_size: int
```

### analysis.py

```python
class ProbabilityEstimate:
    entry_id: str
    horse_name: str
    win_probability: float          # 0.0-1.0
    place_probability: float       # P(top3)
    model_confidence: float        # 0.0-1.0
    rank_by_model: int

class AnalysisResult:
    race_id: str
    analyzed_at: datetime
    method: str                     # "statistical", "ml_xgboost"
    probabilities: list[ProbabilityEstimate]
    key_factors: list[str]
    caveats: list[str]
    data_sufficiency: str           # "sufficient", "limited", "minimal"
```

### evidence.py

```python
class StrengthWeakness:
    category: str           # "distance", "track", "form", "jockey"...
    type: str               # "strength" | "weakness" | "concern"
    description: str
    confidence: float       # 0.0-1.0
    source: str             # "statistical" | "web_research" | "combined"

class HorseEvidence:
    entry_id: str
    horse_name: str
    strengths: list[StrengthWeakness]
    weaknesses: list[StrengthWeakness]
    concerns: list[StrengthWeakness]
    overall_assessment: str
    integrated_probability: float
    integrated_place_probability: float
    evidence_grade: ConfidenceGrade

class EvidenceProfile:
    race_id: str
    integrated_at: datetime
    horses: list[HorseEvidence]
    race_narrative: str
```

### prediction.py

```python
class BetRecommendation:
    bet_type: BetType
    selection: str              # "07", "03-07", "03-07-01"
    horse_names: list[str]
    predicted_probability: float
    estimated_odds: float | None
    expected_value: float | None
    confidence: ConfidenceGrade
    reasoning: str
    risk_level: str             # "low", "medium", "high"
    stake_suggestion: str | None

class RacePrediction:
    race_id: str
    race_name: str
    generated_at: datetime
    prediction_type: str        # "predicted_odds" | "actual_odds"
    win_prediction: BetRecommendation | None
    place_prediction: BetRecommendation | None
    exacta_prediction: BetRecommendation | None
    quinella_prediction: BetRecommendation | None
    trifecta_prediction: BetRecommendation | None
    trio_prediction: BetRecommendation | None
    skip_recommended: bool
    skip_reason: str | None
    disclaimer: str
```

### quality.py

```python
class QACriterion:
    criterion_name: str
    max_score: int
    actual_score: int
    passed: bool
    notes: str

class QAReport:
    target_agent: str
    race_id: str
    evaluated_at: datetime
    total_score: int             # 120満点
    passed: bool                 # >= 100
    criteria: list[QACriterion]
    overall_feedback: str
    route_back_to: str | None    # 差し戻し先エージェント名
    retry_count: int
```

### pipeline.py

```python
class AgentResult:
    agent_name: str
    success: bool
    started_at: datetime
    completed_at: datetime
    duration_seconds: float
    output: dict
    error: str | None

class PipelineContext:
    pipeline_id: str
    race_id: str
    started_at: datetime
    current_stage: str
    # 各エージェントの出力（段階的に設定）
    historical_data: dict | None
    current_race_data: RaceCard | None
    quality_check: dict | None
    features: FeatureSet | None
    analysis: AnalysisResult | None
    web_research: WebResearchResult | None
    evidence: EvidenceProfile | None
    predicted_odds_eval: dict | None
    actual_odds_eval: dict | None
    prediction_predicted: RacePrediction | None
    prediction_actual: RacePrediction | None
    backtest: BacktestSummary | None
    note_suggestion: NoteSuggestion | None
    note_article: NoteArticle | None
    qa_report: QAReport | None
    # 実行ログ
    agent_results: list[AgentResult]
    status: str  # "running" | "completed" | "failed" | "qa_retry"
```

---

## 6. BaseAgent 設計

```python
class BaseAgent(ABC):
    """全エージェントの抽象基底クラス"""

    def __init__(self):
        self.name: str = self.__class__.__name__
        self.logger = get_agent_logger(self.name)

    @abstractmethod
    def validate_input(self, context: PipelineContext) -> bool: ...

    @abstractmethod
    def process(self, context: PipelineContext) -> PipelineContext: ...

    def execute(self, context: PipelineContext) -> PipelineContext:
        """テンプレートメソッド: validate → process → 結果ラップ → ログ"""
        started = datetime.now()
        try:
            if not self.validate_input(context):
                raise ValueError(f"Input validation failed for {self.name}")
            result = self.process(context)
            # 成功ログ
            ...
            return result
        except Exception as e:
            # 失敗ログ・エラー情報をcontextに記録
            ...
            return context
```

**設計ポイント**:
- テンプレートメソッドパターンで `validate → process → 結果ラップ → ログ` を統一
- エラー時は context を部分的に変更しない（不変性）
- 各エージェントの実行時間・成功/失敗を自動記録
- どのエージェントで失敗したか分かる構造化ログ

---

## 7. オーケストレーション設計

### パイプライン定義

```python
PIPELINE_STAGES = [
    Stage(HistoricalDataManager,   "historical_data",    []),
    Stage(CurrentDataFetcher,      "current_data",       ["historical_data"]),
    Stage(DataQualityChecker,      "quality_check",      ["current_data"]),
    Stage(FeatureGenerator,        "feature_gen",        ["quality_check"]),
    Stage(PythonAnalyzer,          "python_analysis",    ["feature_gen"],     parallel="group_1"),
    Stage(WebResearcher,           "web_research",       ["current_data"],    parallel="group_1"),
    Stage(EvidenceIntegrator,      "evidence",           ["python_analysis", "web_research"]),
    Stage(PredictedOddsEvaluator,  "predicted_odds",     ["evidence"]),
    Stage(ActualOddsEvaluator,     "actual_odds",        ["predicted_odds"]),
    Stage(PredictionGenerator,     "prediction",         ["actual_odds"]),
    Stage(Backtester,              "backtest",           ["prediction"]),
    Stage(NoteStructureResearcher, "note_research",      ["prediction"]),
    Stage(NoteWriter,              "note_write",         ["note_research"]),
    Stage(QualityAssurance,        "qa",                 ["note_write"]),
]
```

### 並列実行

- Agent 5 (PythonAnalyzer) と Agent 6 (WebResearcher) は `concurrent.futures.ThreadPoolExecutor` で並列実行
- 両方完了後に Agent 7 (EvidenceIntegrator) が統合

### QA差し戻しロジック

```
QA判定 → スコア >= 100 → 完了
       → スコア < 100 → route_back_to に基づき該当ステージ以降を再実行
                       → 最大3回までリトライ
                       → 3回超えたら強制終了
```

---

## 8. 設定・ログ

### default.yaml 主要設定

```yaml
pipeline:
  max_qa_retries: 3
  parallel_execution: true

data_source:
  active: "sample"         # "sample" (MVP) / "production" (本番)

analysis:
  method: "statistical"    # "statistical" / "ml"
  feature_weights:
    distance_aptitude: 0.15
    track_aptitude: 0.12
    recent_form: 0.20
    closing_speed: 0.15
    running_style: 0.08
    jockey_stats: 0.12
    trainer_stats: 0.08
    pedigree: 0.05
    weight_factors: 0.05

odds:
  max_web_evidence_adjustment: 0.15   # Web証拠の確率調整上限 ±15%
  value_threshold: 0.10               # 推奨に必要な最小EVエッジ
  skip_if_no_value: true

quality:
  passing_score: 100
  total_score: 120
  prohibited_words:
    - "絶対"
    - "確定"
    - "鉄板"
    - "必ず儲かる"
    - "回収保証"
    - "100%"
    - "間違いなく"

note:
  disclaimer: |
    ※本予想は個人的な分析に基づくものであり、馬券の購入を保証するものではありません。
    競馬にはリスクがあり、投資額以上の損失が生じる可能性があります。
    自己責任でご判断ください。
```

### ログ戦略

| 出力先 | フォーマット | 内容 |
|--------|-------------|------|
| コンソール | 人間可読プレーン | `[時刻] [エージェント名] LEVEL: メッセージ` |
| ファイル (JSONL) | 構造化JSON | timestamp, level, agent, race_id, pipeline_id, message, exception |
| エージェント別 | 個別ファイル | `output/logs/FeatureGenerator.jsonl` 等 |

---

## 9. 実行方法

```bash
# セットアップ
pip install -e ".[dev]"

# サンプルデータで実行（デフォルト）
keiba

# レースID指定
keiba 20260607-Tokyo-11

# 詳細ログ
keiba -v

# データソース指定（本番実装後）
keiba --source production 20260614-Nakayama-11

# テスト
pytest

# カバレッジ付きテスト
pytest --cov=keiba --cov-report=html

# 型チェック
mypy src/keiba

# Lint
ruff check src/ tests/ --fix
```

### 依存関係

| パッケージ | 用途 |
|-----------|------|
| pydantic >= 2.0 | データモデル・バリデーション |
| pyyaml >= 6.0 | 設定ファイル読込 |
| rich >= 13.0 | コンソール出力の整形 |
| pytest >= 7.0 | テスト（dev） |
| pytest-cov >= 4.0 | カバレッジ（dev） |
| ruff >= 0.1 | Lint（dev） |
| mypy >= 1.0 | 型チェック（dev） |

---

## 10. MVP対象範囲

### サンプルレース

- 架空のGIレース（東京優駿風）1レース
- レースID: `20260607-Tokyo-11`
- 東京 芝2400m GI

### サンプル出走馬（10頭）

| タイプ | 頭数 | 特徴 |
|--------|------|------|
| 逃げ | 1頭 | 常に先頭でレースを作る |
| 先行 | 2頭 | 好位から差を詰める |
| 差し | 4頭 | 中団から末脚で追込 |
| 追込 | 3頭 | 後方から一気に伸びる |

バリエーション:
- 3連勝中の人気馬
- 休み明けの実力馬
- 距離初挑戦の馬
- 重賞初挑戦の馬
- キャリア浅めの若駒

### サンプルデータ一式

- 各馬5-8走分の過去成績
- 予想オッズ（1セット）: 人気は1.8倍〜98.3倍
- 実オッズ（1セット）: 人気薄が支持される等の変動あり
- Web調査: 架想の調教情報・陣営コメント・コース傾向
- バックテスト用過去レース: 架想20レース分

### MVPで動くもの

- ✅ 全14エージェント稼働
- ✅ 特徴量生成
- ✅ スコアリング・勝率推定
- ✅ 暫定期待値評価（予想オッズ）
- ✅ 実オッズ期待値評価
- ✅ 買い目生成（券種別）
- ✅ 見送り判定
- ✅ バックテスト（簡易版）
- ✅ Note記事案生成
- ✅ QA採点
- ✅ テストコード

---

## 11. 差し替え設計（将来拡張）

### DataSource 抽象化

```python
class DataSource(ABC):
    def get_historical_data(self, race_id: str) -> dict: ...
    def get_current_race_card(self, race_id: str) -> RaceCard: ...
    def get_predicted_odds(self, race_id: str) -> PredictedOdds: ...
    def get_actual_odds(self, race_id: str) -> ActualOdds: ...
    def get_web_content(self, race_id: str, horse_ids: list[str]) -> dict: ...
    def get_backtest_data(self, config: dict) -> list[dict]: ...
```

### 切替方法

`config/default.yaml` の `data_source.active` を変更するだけ:

```yaml
data_source:
  active: "production"  # "sample" → "production"
```

エージェントはDataSourceインターフェースしか知らないため、コード変更なしで切替可能。

### 将来の拡張予定

| 拡張 | 内容 |
|------|------|
| 本番データ取得 | netkeiba / JRA公式 からのスクレイピング |
| 機械学習モデル | XGBoost / LightGBM による勝率推定 |
| Web検索API | Google/Bing API によるリアルタイム調査 |
| リアルタイムオッズ | JRA IPAT からのオッズ取得 |
| 地方競馬対応 | DataSouce の追加実装 |
| 全レース対応 | 対象レースのフィルタリング拡張 |
| 可視化ダッシュボード | 分析結果のグラフ・チャート |

---

## 12. 実装順序

### Phase 1: 基盤（モデル・設定）

1. `pyproject.toml`, `.gitignore`, フォルダ構造
2. `models/base.py` — 共通Enum, KeibaBaseModel
3. 全モデルファイル（15ファイル）
4. `utils/config.py`, `utils/logging.py`

### Phase 2: データ層

5. `data/base_source.py` — DataSource ABC
6. `data/sample/` — サンプルデータ全件
7. `data/sample/sample_source.py` — SampleDataSource

### Phase 3: エージェント実装（前半）

8. `agents/base.py` — BaseAgent
9. Agent 1: HistoricalDataManager + テスト
10. Agent 2: CurrentDataFetcher + テスト
11. Agent 3: DataQualityChecker + テスト
12. Agent 4: FeatureGenerator + テスト
13. Agent 5: PythonAnalyzer + テスト
14. Agent 6: WebResearcher + テスト

### Phase 4: エージェント実装（後半）

15. Agent 7: EvidenceIntegrator + テスト
16. Agent 8: PredictedOddsEvaluator + テスト
17. Agent 9: ActualOddsEvaluator + テスト
18. Agent 10: PredictionGenerator + テスト
19. Agent 11: Backtester + テスト
20. Agent 12: NoteStructureResearcher + テスト
21. Agent 13: NoteWriter + テスト
22. Agent 14: QualityAssurance + テスト

### Phase 5: オーケストレーション

23. `orchestration/pipeline.py` — ステージ定義
24. `orchestration/orchestrator.py` — 実行エンジン
25. `cli.py` — CLI エントリポイント

### Phase 6: 統合テスト

26. `tests/conftest.py` — 共通フィクスチャ
27. `tests/test_integration/test_full_pipeline.py` — E2Eテスト
28. `README.md` — 使い方説明

---

## 13. テスト戦略

### 3層テスト構成

| 層 | 内容 |
|----|------|
| 単体テスト | 各エージェントの入力検証・出力スキーマ・コアロジック |
| オーケストレーションテスト | パイプライン実行順序・並列実行・QA差し戻し |
| 統合テスト | サンプルデータでパイプライン全行程E2E実行 |

### 各エージェントのテスト観点

| エージェント | テストケース |
|-------------|-------------|
| HistoricalDataManager | サンプルデータ正常読込・想定構造返却 |
| CurrentDataFetcher | 10頭のRaceCard返却・全フィールド設定済み |
| DataQualityChecker | 欠損検出・異常検出（休み明け）・正常データ通過 |
| FeatureGenerator | 全特徴量が有効範囲・脚質分類正しい・上がり順位正しい |
| PythonAnalyzer | 確率合計≈1.0・全確率>0・順位整合性 |
| WebResearcher | 全10頭の情報返却・コース傾向あり |
| EvidenceIntegrator | 確率調整±15%以内・収束信号検出 |
| PredictedOddsEvaluator | 暫定マークあり・妙味計算正しい |
| ActualOddsEvaluator | Grade S/A/B/C 妥当・市場比較あり |
| PredictionGenerator | 各券種予想生成・低信頼度時見送り・免責事項あり |
| Backtester | ROI計算正しい・券種別内訳あり |
| NoteStructureResearcher | 有効な構成返却・タイトル案あり |
| NoteWriter | 全セクション含む・禁止語なし・免責事項あり |
| QualityAssurance | 120点満点・禁止語検出・正しい差し戻し先 |

---

## 14. 検証方法

1. **単体テスト**: `pytest tests/test_agents/` — 各エージェントの入力検証・出力スキーマ確認
2. **統合テスト**: `pytest tests/test_integration/test_full_pipeline.py` — サンプルデータでパイプライン全行程実行
3. **手動確認**: `keiba` コマンド実行 → `output/json/` と `output/markdown/` の成果物確認
4. **品質チェック**: QAエージェントのスコアが100点以上であることを確認
5. **禁止語チェック**: 出力に「絶対」「確定」「鉄板」等が含まれていないことを確認
6. **型チェック**: `mypy src/keiba` で型エラーなし
7. **Lint**: `ruff check src/ tests/` で警告なし

---

## 最終成果物一覧

| 成果物 | 出力先 |
|--------|--------|
| レース別分析レポート | `output/json/{race_id}.json` |
| 馬ごとの評価表 | JSON内 `features` + `evidence` |
| 予想順位 | JSON内 `analysis.probabilities` |
| 本命・対抗・単穴・連下・穴馬 | JSON内 `prediction` |
| 券種別買い目 | JSON内 `prediction.*_prediction` |
| 信頼度 | JSON内各 `confidence` |
| 予想オッズベースの暫定期待値 | JSON内 `predicted_odds_eval` |
| 実オッズベースの期待値 | JSON内 `actual_odds_eval` |
| 見送り判定 | JSON内 `skip_recommended` + `skip_reason` |
| 根拠一覧 | JSON内 `evidence.horses[*].strengths/weaknesses/concerns` |
| バックテスト結果 | JSON内 `backtest` |
| QA採点レポート | JSON内 `qa_report` |
| Note記事案 | `output/markdown/{race_id}.md` |
| 当日更新用チェックリスト | Note記事内「当日更新項目」セクション |
