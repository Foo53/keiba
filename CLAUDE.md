# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## このリポジトリについて

中央競馬（JRA）の重賞レース向け予想システム。16エージェントのパイプラインでデータ取得→特徴量生成→統計分析+ML予測→根拠統合→予想生成→Note記事生成までを自動実行する。

### 技術スタック

- **言語**: Python 3.11+
- **ML**: LightGBM + Optuna（二値分類、25次元特徴量）
- **データ**: JRA-VAN DataLab（27年分・SQLite）、netkeiba/JRA（Webスクレイピング）
- **フレームワーク**: Pydantic v2（データモデル）、Rich（コンソール出力）

### プロジェクト構成

```
src/keiba/
├── agents/         # 16エージェント（BaseAgent継承）
├── data/           # データソース（DataSource ABC）
│   ├── sample/     # 架空データ（動作確認用）
│   ├── production/ # netkeiba/JRAスクレイパ（キャッシュ付き）
│   └── jrvan/      # JRA-VAN DataLab CSV→SQLite
├── ml/             # LightGBM学習・特徴量ベクトル化
├── models/         # Pydanticデータモデル
├── orchestration/  # パイプライン管理
└── utils/          # 設定・ログ
scripts/            # 個別実行スクリプト（学習・出馬表取得・レース予測）
data/store/         # SQLite DB・学習済みモデル
config/default.yaml # 設定ファイル
```

### 主要コマンド

```bash
source .venv/bin/activate
keiba                              # サンプルデータでパイプライン実行
keiba train --source jrvan         # JRA-VANデータでMLモデル学習
.venv/bin/python scripts/fetch_racecard.py <race_id>  # 出馬表取得
pytest                             # テスト実行
```

### 注意点

- **必ず `.venv/bin/python` を使用**: system python3にはlightgbmがインストールされていない
- **学習済みモデル**: `data/store/models/lgbm_latest.txt`（AUC=0.7707）
- **データファイルはGit管理外**: `JRA_VAN_DATA/`、`data/store/`、`output/` は`.gitignore`対象

### 16エージェント一覧

パイプラインは16ステージの直列・並列混在構成。Agent 5/6/7は並列実行。

| # | エージェント | 役割 |
|---|------------|------|
| 1 | HistoricalDataManager | DataSource経由で過去レース・出走馬・騎手・厩舎データを取得 |
| 2 | CurrentDataFetcher | DataSource経由で対象レースの出馬表（entries）を取得 |
| 3 | DataQualityChecker | 出走馬ごとの過去成績不足・馬体重変動・騎手欠落を検出し、完成度スコアを算出 |
| 4 | FeatureGenerator | 各馬の特徴量を生成（距離適性・芝適性・脚質・上がり3F・近走成績・騎手勝率など18項目） |
| 5 | PythonAnalyzer | 特徴量の加重和で複合スコアを算出し、ソフトマックスで勝率・複勝率を推定（統計分析） |
| 6 | MLPredictor | 学習済みLightGBMモデルで25次元特徴量から勝率を推定（softmax正規化）。モデル未学習時はスキップ |
| 7 | WebResearcher | DataSource経由でWeb調査結果（調教・ニュース等）を取得し、信頼度・影響度を付与 |
| 8 | EvidenceIntegrator | 統計分析+ML予測+Web調査を統合し、強み/弱み/懸念を抽出して確率調整・グレード(S/A/B/C)付与 |
| 9 | PredictedOddsEvaluator | 予想オッズとモデル確率を比較し、バリューギャップで妙味あり/見送りを判定（暫定） |
| 10 | ActualOddsEvaluator | 実オッズで期待値(EV)を計算し、推奨グレード(S/A/B/C)と市場センチメントを判定（最終） |
| 11 | PredictionGenerator | 統合確率とEVに基づき、単勝/複勝/馬連/3連単の買い目を生成。全EV < -0.3なら見送り推奨 |
| 12 | Backtester | DataSource経由で過去レースを取得し、予想ロジックの的中率・ROIをコース/距離/馬場別に検証 |
| 13 | VisualizerAgent | matplotlib/seabornで5種のEDAチャート（勝率ランキング・特徴量比較・EV散布図等）をPNG生成 |
| 14 | NoteStructureResearcher | レース情報からNote記事の構成（無料/有料境界・18セクション・禁止表現リスト）を提案 |
| 15 | NoteWriter | 予想結果をMarkdown記事に構築。無料5セクション＋有料13セクション。禁止表現17種を自動検出 |
| 16 | QualityAssurance | 全成果物を10項目・120点満点で採点。100点未満なら該当エージェントに差し戻し（最大3回リトライ） |

---

Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.

## 5. Environment

**WSL2 環境の制約に注意。**

- `sudo` が必要な操作（システムパッケージのインストール等）は実行せず、ユーザーにコマンドを提示して手動実行を依頼する。
- ユーザーが `! <command>` で直接実行することも可能。

