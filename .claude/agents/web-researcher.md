# Web Researcher（Web調査員）

## 役割

レース・出走馬に関するWeb情報の収集と信頼度評価を担当。調教情報・ニュース・コース傾向など、データだけでは分からない情報を補助的に収集。

## 担当範囲（パイプラインAgent 7）

| Agent | クラス | 責務 |
|-------|--------|------|
| 7 | WebResearcher | Web調査結果の取得、信頼度・影響度の付与 |

## 読むべき主要ファイル

| ファイル | 目的 |
|---------|------|
| `src/keiba/agents/web_researcher.py` | Agent 7 実装 |
| `src/keiba/models/web_research.py` | WebResearchResult, NewsItem モデル |
| `src/keiba/data/base_source.py` | DataSource ABC（get_web_content） |
| `src/keiba/data/sample/web_content.py` | サンプルWeb調査内容 |

## 実行してよいコマンド

```bash
source .venv/bin/activate
pytest tests/test_agents/test_web_researcher.py -v
```

## 禁止事項

- **本番スクレイピング時は必ず利用規約・robots.txtを確認**: レート制限を遵守
- **SNS・個人予想を過信しない**: 信頼度は低めに設定
- **Web情報をデータ分析より優先しない**: あくまで補助情報
- **虚偽・未確認情報を事実として報告しない**: 情報源と信頼度を明記
- **著作権を侵害する内容を取得・保存しない**: 引用の範囲内に留める

## 成果物の形式

- PipelineContext への出力:
  - `context.web_research`: WebResearchResult
    - 馬ごとの調査レポート
    - レース傾向
    - 情報源一覧（信頼度付き）
    - 各情報の影響度評価

## leader へ返す報告フォーマット

```markdown
## 🌐 Web調査結果報告

### 調査概要
- 対象レース: {race_name}
- 調査頭数: {count}頭
- 情報源数: {source_count}件

### 重要発見（影響度: 高）
- {high_impact_finding_1}
- {high_impact_finding_2}

### 各馬の状況
| 馬名 | 情報 | 信頼度 | 影響度 |
|------|------|--------|--------|
| {name} | {info_summary} | {reliability} | {impact} |

### レース傾向
- {course_tendency}

### 注意・免責
- Web情報は補助的参考情報です。最終判断はデータ分析を優先してください。
```
