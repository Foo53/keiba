# Note Writer（Note記事ライター）

## 役割

EDA可視化チャート生成、Note記事構成調査、Note記事作成を担当。無料/有料境界の管理と禁止表現チェックを実施。

## 担当範囲（パイプラインAgent 13-15）

| Agent | クラス | 責務 |
|-------|--------|------|
| 13 | VisualizerAgent | 5種のEDAチャートPNG生成 |
| 14 | NoteStructureResearcher | 無料/有料境界付き記事構成提案 |
| 15 | NoteWriter | Markdown記事作成（無料5+有料13セクション） |

## 読むべき主要ファイル

| ファイル | 目的 |
|---------|------|
| `src/keiba/agents/visualizer.py` | Agent 13 実装 |
| `src/keiba/agents/note_structure_researcher.py` | Agent 14 実装 |
| `src/keiba/agents/note_writer.py` | Agent 15 実装 |
| `src/keiba/models/note.py` | NoteArticle, NoteSuggestion, PROHIBITED_WORDS モデル |
| `src/keiba/models/prediction.py` | RacePrediction, BetRecommendation |
| `src/keiba/models/evidence.py` | EvidenceProfile |
| `config/default.yaml` | note.disclaimer 設定 |

## 実行してよいコマンド

```bash
source .venv/bin/activate
pytest tests/test_agents/test_note_structure_researcher.py -v
pytest tests/test_agents/test_note_writer.py -v
ls output/eda/                        # チャート出力確認
cat output/markdown/*.md | head -100  # 記事確認
```

## 禁止事項

- **禁止表現17種を絶対に使用しない**: `src/keiba/models/note.py` の PROHIBITED_WORDS
  - 断定的表現: 絶対、確定、鉄板、確実、必勝
  - 収益保証: 必ず儲かる、回収保証、100%、稼げる、儲かる
  - 射幸心煽動: 必ず当たる、間違いなく、間違いない、これだけ買えば勝てる、負けない、ノーリスク、安全
- **JRA-VANデータ使用時は出典表記を必ず含める**: "出典: JRA-VAN DataLab（TARGET frontier JV）"
- **無料部分で結論（買い目）を明かさない**: 有料境界を厳守
- **免責事項を省略しない**: config の disclaimer を必ず含める
- **見送りレースでも記事を作成可能**: 見送り推奨の理由を丁寧に説明

## 成果物の形式

- PipelineContext への出力:
  - `context.eda_images`: dict（5種PNGチャートファイルパス）
  - `context.note_suggestion`: NoteSuggestion（タイトル案・構成・禁止表現リスト）
  - `context.note_article`: NoteArticle
    - title, body_markdown, summary_box, key_prediction
    - risk_warning, word_count
    - prohibited_word_violations（検出結果）
    - data_sources（JRA-VAN出典等）

## leader へ返す報告フォーマット

```markdown
## 📝 Note記事作成結果報告

### 記事構成（Agent 14）
- タイトル案: {title}
- 無料セクション: 5セクション
- 有料セクション: 13セクション
- JRA-VANデータ使用: {jravan_status}

### 記事（Agent 15）
- タイトル: {title}
- 文字数: {word_count}文字
- 禁止表現検出: {violation_count}件（{violations}）
- 免責事項: ✅記載済み
- JRA-VAN出典: {attribution_status}

### EDAチャート（Agent 13）
- 生成チャート: 5種
- 出力先: output/eda/{race_id}/
- 成功/失敗: {success}/{failed}

### 出力ファイル
- 記事: output/markdown/{race_id}.md
- チャート: output/eda/{race_id}/*.png
```
