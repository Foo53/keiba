# 競馬予想システム（keiba-prediction）

中央競馬の重賞・メインレース（G1/G2/G3、土日11R）向けの予想システムです。
14のエージェントがパイプライン構成で連携し、データ分析 → 予想 → Note記事生成までを自動実行します。

> ⚠️ **免責事項**: 本システムはデータ分析に基づく参考情報を提供するものです。馬券の購入を保証するものではありません。投資は自己責任でお願いします。

## アーキテクチャ

```
[1.過去データ管理] → [2.当日データ取得] → [3.品質チェック] → [4.特徴量生成]
                                                                    ↓
                                                          ┌─────────┴─────────┐
                                                          ↓                   ↓
                                                   [5.Python分析]    [6.Web調査]
                                                          └─────────┬─────────┘
                                                                    ↓
[14.品質保証] ← [13.Note作成] ← [12.Note構成調査] ← [11.バックテスト] ← [10.予想生成]
                                                                ↑
                                                    [9.実オッズ評価] ← [8.予想オッズ評価] ← [7.根拠統合]
```

## セットアップ

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## 使い方

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

## テスト

```bash
pytest                          # 全テスト実行
pytest tests/ -v                # 詳細表示
pytest --cov=keiba              # カバレッジ付き
```

## 14エージェント一覧

| # | エージェント | 役割 |
|---|------------|------|
| 1 | HistoricalDataManager | 過去レースデータの取得・管理 |
| 2 | CurrentDataFetcher | 当日の出馬表・オッズ取得 |
| 3 | DataQualityChecker | データの欠損・異常チェック |
| 4 | FeatureGenerator | 各馬の特徴量生成 |
| 5 | PythonAnalyzer | 統計分析・勝率推定 |
| 6 | WebResearcher | Web調査（ニュース・調教情報） |
| 7 | EvidenceIntegrator | 分析結果とWeb調査の統合 |
| 8 | PredictedOddsEvaluator | 予想オッズでの暫定評価 |
| 9 | ActualOddsEvaluator | 実オッズでの最終評価 |
| 10 | PredictionGenerator | 券種別買い目生成 |
| 11 | Backtester | バックテスト検証 |
| 12 | NoteStructureResearcher | Note記事構成調査 |
| 13 | NoteWriter | Note記事生成 |
| 14 | QualityAssurance | 品質保証（120点満点採点） |

## 出力物

- `output/json/{race_id}.json` — 全分析結果（JSON）
- `output/markdown/{race_id}.md` — Note記事案（Markdown）
- `output/logs/pipeline.jsonl` — 実行ログ

## プロジェクト構成

```
src/keiba/
├── models/         # Pydantic データモデル（15ファイル）
├── agents/         # 14エージェント + BaseAgent
├── data/
│   ├── base_source.py      # DataSource ABC
│   ├── sample/             # MVP用サンプルデータ
│   └── production/         # 本番データソース
│       ├── production_source.py  # ProductionDataSource
│       ├── merger.py              # データマージ・重複排除
│       └── scrapers/              # netkeiba / JRA スクレイパ
├── orchestration/  # パイプライン管理
├── utils/          # 設定・ログ・HTTP クライアント
└── cli.py          # CLI エントリポイント
```

## 外部アクセスに関する方針

- **本番モード (`--source production`)**: netkeiba.com からデータを取得します
  - robots.txt を自動確認（許可されたパスのみアクセス）
  - ドメインごと7秒以上のリクエスト間隔（レート制限）
  - 1日500リクエスト上限（ドメインごと）
  - ローカルファイルキャッシュで重複アクセスを防止
- **サンプルモード（デフォルト）**: 外部サイトへのアクセスなし
- データソースは `DataSource` ABC で抽象化されており、`config/default.yaml` の `data_source.active` を変更するだけで差し替え可能です

## 設計ドキュメント

詳細な設計・データモデル・エージェント仕様は [docs/design.md](docs/design.md) を参照してください。
