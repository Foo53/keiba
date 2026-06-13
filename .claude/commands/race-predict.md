# /race-predict — レース予想パイプライン実行

レース予想のパイプラインを実行します。

## 使い方

```
/race-predict [race_id]
```

- `race_id` 省略時はサンプルレース `20260607-Tokyo-11` を使用

## 実行手順

1. **リーダーとして以下を確認:**
   - レースIDの特定（引数またはユーザーへの確認）
   - データソースの確認（sample / production / jrvan）

2. **パイプライン実行:**
   ```bash
   source .venv/bin/activate
   keiba {race_id}
   ```

3. **結果確認:**
   ```bash
   cat output/json/{race_id}.json | python3 -m json.tool | head -100
   cat output/markdown/{race_id}.md | head -50
   ls output/eda/{race_id}/
   ```

4. **QA結果の確認:**
   - QA スコアが 100/120 以上であることを確認
   - 禁止表現検出が 0 件であることを確認
   - 不合格なら差し戻し対応

5. **ユーザーへ結果報告:**
   - 予想サマリ（本命・対抗・単穴・買い目）
   - QA スコア
   - バックテスト結果（的中率・ROI）
   - 見送り推奨の有無

## 成果物

- `output/json/{race_id}.json` — 分析レポート
- `output/markdown/{race_id}.md` — Note記事
- `output/eda/{race_id}/` — EDAチャート（5種PNG）
