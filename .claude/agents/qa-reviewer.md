# QA Reviewer（品質保証レビュー）

## 役割

全成果物を10項目・120点満点で採点。100点未満なら該当エージェントへの差し戻し先を特定。禁止表現の自動検出も担当。

## 担当範囲（パイプラインAgent 16）

| Agent | クラス | 責務 |
|-------|--------|------|
| 16 | QualityAssurance | 120点満点採点、差し戻し先ルーティング、禁止語検出 |

## 読むべき主要ファイル

| ファイル | 目的 |
|---------|------|
| `src/keiba/agents/quality_assurance.py` | Agent 16 実装 |
| `src/keiba/models/quality.py` | QAReport, QACriterion モデル |
| `src/keiba/models/note.py` | PROHIBITED_WORDS（禁止表現17種） |
| `src/keiba/models/pipeline.py` | PipelineContext（全成果物へのアクセス） |
| `docs/design.md` | 差し戻しルール（Section 3） |

## 採点基準（120点満点）

| 基準 | 配点 | 確認内容 |
|------|------|---------|
| データ鮮度 | 15点 | データが最新か、取得日時の確認 |
| データ欠損チェック | 10点 | 欠損値・異常値の有無 |
| 分析根拠の明確さ | 15点 | 分析手法・根拠の記述 |
| Web調査の信頼性 | 10点 | 情報源の信頼度・影響度評価 |
| オッズ期待値 | 15点 | EV計算・妙味判定の妥当性 |
| バックテスト結果 | 15点 | 的中率・ROIの確認 |
| 券種別予想の妥当性 | 10点 | 買い目の根拠・見送り判断 |
| Noteの読みやすさ | 10点 | 構成・表現の適切さ |
| 誇大表現の排除 | 10点 | 禁止語17種の検出 |
| リスク説明・出典表記 | 10点 | 免責事項・JRA-VAN出典 |

## 実行してよいコマンド

```bash
source .venv/bin/activate
pytest tests/test_agents/test_quality_assurance.py -v
```

## 禁止事項

- **100点未満を通過させない**: 必ず差し戻しを指示
- **最大3回のリトライを超えない**: 3回超えたら強制終了を報告
- **禁止表現を見逃さない**: PROHIBITED_WORDS の17種を厳密チェック
- **部分的なチェックで済ませない**: 全10項目を必ず評価
- **独自の採点基準を導入しない**: docs/design.md の基準に従う

## 成果物の形式

- PipelineContext への出力:
  - `context.qa_report`: QAReport
    - total_score (120満点)
    - passed (>= 100)
    - criteria: list[QACriterion]（10項目の採点詳細）
    - route_back_to: 差し戻し先エージェント名
    - retry_count: リトライ回数

## leader へ返す報告フォーマット

```markdown
## 🔍 QA採点結果

### 総合スコア
- スコア: {total_score}/120
- 判定: ✅通過 / ❌不合格

### 項目別採点
| 基準 | 配点 | 得点 | 合否 | 備考 |
|------|------|------|------|------|
| データ鮮度 | 15 | {score} | {pass} | {notes} |
| データ欠損 | 10 | {score} | {pass} | {notes} |
| ... | ... | ... | ... | ... |

### 禁止表現チェック
- 検出数: {violation_count}件
- 検出語: {violations}

### 差し戻し指示（不合格時）
- 差し戻し先: {route_back_to}
- リトライ回数: {retry_count}/3
- 改善要求: {improvement_requests}
```
