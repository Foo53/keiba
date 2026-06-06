# 競馬予想システム（keiba-prediction）

中央競馬の重賞・メインレース（G1/G2/G3、土日11R）向けの予想システムです。
16のエージェントがパイプライン構成で連携し、データ分析 → 予想 → Note記事生成までを自動実行します。

> ⚠️ **免責事項**: 本システムはデータ分析に基づく参考情報を提供するものです。馬券の購入を保証するものではありません。投資は自己責任でお願いします。

## アーキテクチャ

```
[1.過去データ管理] → [2.当日データ取得] → [3.品質チェック] → [4.特徴量生成]
                                                                    ↓
                                              ┌───────────┬─────────┴─────────┐
                                              ↓           ↓                   ↓
                                       [5.Python分析] [6.ML予測]      [7.Web調査]  ← 並列実行
                                              └───────────┴─────────┬─────────┘
                                                                    ↓
[16.品質保証] ← [15.Note作成] ← [14.Note構成調査] ← [13.EDA可視化]
                                                                ↑
                                                    [12.バックテスト] ← [11.予想生成] ← [10.実オッズ評価] ← [9.予想オッズ評価] ← [8.根拠統合]
```

## セットアップ

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## 使い方

### パイプライン実行

```bash
# サンプルデータで実行（デフォルト）
keiba

# レースID指定
keiba 20260607-Tokyo-11

# 本番データで実行（netkeiba + JRA 統合）
keiba --source production 20250601-Tokyo-11

# 詳細ログ
keiba -v
```

### 対話型リーダー

```bash
# 対話型リーダーを起動（デフォルトレース）
keiba lead

# レースID指定でリーダー起動
keiba lead 20260607-Tokyo-11
```

リーダーは16エージェントを7つのワークフローにまとめ、ユーザーと相談しながら段階的に実行します。

| メニュー | ワークフロー | 対象エージェント |
|---------|------------|----------------|
| [1] 完全予想パイプライン | 全16エージェント一括実行 | Agent 1-16 |
| [2] データ取得 | 過去データ＋出馬表＋品質確認 | Agent 1-3 |
| [3] 特徴量生成 | 18項目の特徴量生成 | Agent 4 |
| [4] 分析 | 統計/ML/Web→根拠統合 | Agent 5-8 |
| [5] オッズ評価 | 予想/実オッズで期待値計算 | Agent 9-10 |
| [6] 予想生成 | 買い目生成＋バックテスト | Agent 11-12 |
| [7] 記事生成 | チャート→記事→品質確認 | Agent 13-16 |

### MLモデル学習

```bash
# JRA-VANデータで学習（推奨）
keiba train --source jrvan

# Optuna試行数を指定
keiba train --source jrvan --optuna-trials 50

# サンプルデータで学習（動作確認用）
keiba train --source sample --optuna-trials 10
```

## テスト

```bash
pytest                          # 全テスト実行
pytest tests/ -v                # 詳細表示
pytest --cov=keiba              # カバレッジ付き
```

## 16エージェント一覧

| # | エージェント | 役割 |
|---|------------|------|
| 1 | HistoricalDataManager | 過去レースデータの取得・管理 |
| 2 | CurrentDataFetcher | 当日の出馬表・オッズ取得 |
| 3 | DataQualityChecker | データの欠損・異常チェック |
| 4 | FeatureGenerator | 各馬の特徴量生成（18項目） |
| 5 | PythonAnalyzer | 統計分析・勝率推定 |
| 6 | MLPredictor | LightGBM予測（25次元特徴量） |
| 7 | WebResearcher | Web調査（ニュース・調教情報） |
| 8 | EvidenceIntegrator | 分析結果とWeb調査の統合 |
| 9 | PredictedOddsEvaluator | 予想オッズでの暫定評価 |
| 10 | ActualOddsEvaluator | 実オッズでの最終評価 |
| 11 | PredictionGenerator | 券種別買い目生成 |
| 12 | Backtester | バックテスト検証 |
| 13 | VisualizerAgent | EDAチャート生成（5種） |
| 14 | NoteStructureResearcher | Note記事構成調査 |
| 15 | NoteWriter | Note記事生成 |
| 16 | QualityAssurance | 品質保証（120点満点採点） |

> Agent 5/6/7 は並列実行されます。

## 出力物

- `output/json/{race_id}.json` — 全分析結果（JSON）
- `output/markdown/{race_id}.md` — Note記事案（Markdown）
- `output/logs/pipeline.jsonl` — 実行ログ
- `output/eda/{race_id}/*.png` — EDA可視化チャート（5種）
- `data/store/models/lgbm_latest.txt` — 学習済みLightGBMモデル
- `data/store/models/lgbm_metadata.json` — モデルメタデータ

## プロジェクト構成

```
src/keiba/
├── models/         # Pydantic データモデル
├── agents/         # 16エージェント + BaseAgent
├── data/
│   ├── base_source.py      # DataSource ABC
│   ├── sample/             # 架空データ（動作確認用）
│   ├── production/         # netkeiba/JRA スクレイパ（キャッシュ付き）
│   └── jrvan/              # JRA-VAN DataLab CSV→SQLite
├── ml/                      # LightGBM学習・特徴量ベクトル化
├── orchestration/           # パイプライン管理
│   ├── orchestrator.py     # メインオーケストレータ
│   ├── pipeline.py         # ステージ定義・依存関係
│   └── leader.py           # 対話型リーダーエージェント
├── utils/          # 設定・ログ
└── cli.py          # CLI エントリポイント
scripts/            # 個別実行スクリプト（学習・出馬表取得・レース予測）
data/store/         # SQLite DB・学習済みモデル
config/default.yaml # 設定ファイル
```

## 外部アクセスに関する方針

- **本番モード (`--source production`)**: netkeiba.com からデータを取得します
  - robots.txt を自動確認（許可されたパスのみアクセス）
  - ドメインごと7秒以上のリクエスト間隔（レート制限）
  - 1日500リクエスト上限（ドメインごと）
  - ローカルファイルキャッシュで重複アクセスを防止
- **JRA-VANモード**: JRA-VAN DataLabの27年分CSVデータをSQLiteに変換して使用
- **サンプルモード（デフォルト）**: 外部サイトへのアクセスなし
- データソースは `DataSource` ABC で抽象化されており、`config/default.yaml` の `data_source.active` を変更するだけで差し替え可能です

## 設計ドキュメント

詳細な設計・データモデル・エージェント仕様は [docs/design.md](docs/design.md) を、使い方ガイドは [docs/usage.md](docs/usage.md) を参照してください。
