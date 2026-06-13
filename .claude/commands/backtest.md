# /backtest — バックテスト実行

バックテストを実行し、予想ロジックの過去検証結果を確認します。

## 使い方

```
/backtest [race_id]
```

- `race_id` 省略時はサンプルレースを使用

## 実行手順

1. **前提確認:**
   - 予想結果が存在するか（`output/json/{race_id}.json`）
   - 存在しない場合は `/race-predict` の実行を推奨

2. **バックテスト実行:**
   ```bash
   source .venv/bin/activate
   keiba lead
   # メニュー [6]「予想生成」を選択（Agent 11-12を実行）
   ```

3. **結果確認:**
   ```bash
   cat output/json/{race_id}.json | python3 -c "
   import json, sys
   data = json.load(sys.stdin)
   bt = data.get('backtest', {})
   print(f'検証レース数: {bt.get(\"total_races\", \"N/A\")}')
   print(f'的中率: {bt.get(\"hit_rate\", \"N/A\")}')
   print(f'ROI: {bt.get(\"roi\", \"N/A\")}')
   "
   ```

4. **ユーザーへ結果報告:**
   - 的中率・ROI
   - 券種別成績
   - コース/距離/馬場別成績
   - 改善提案

## 注意

- バックテスト結果は過去の検証に過ぎず、将来の成績を保証するものではありません
- ROI を収益保証として扱わないこと
