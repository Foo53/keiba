"""ポストレース分析スクリプト

予測JSON・Note記事を読み込み、netkeiba からレース結果を取得して
比較分析レポートを生成する。

使い方:
    source .venv/bin/activate
    python scripts/post_race_analysis.py \
        --race-id 202606070511 \
        --prediction output/20260607/yasuda_kinen_2026.json \
        --note output/20260607/note_yasuda_kinen_2026.md \
        --output-dir output/20260607/
"""

import sys
sys.path.insert(0, "src")

import json
import argparse
from pathlib import Path

import yaml

from keiba.agents.post_race_analyst import PostRaceAnalyst
from keiba.data.production.production_source import ProductionDataSource


def main():
    parser = argparse.ArgumentParser(description="ポストレース分析")
    parser.add_argument("--race-id", required=True, help="レースID (例: 202606070511)")
    parser.add_argument("--prediction", required=True, help="予測JSONパス")
    parser.add_argument("--note", required=True, help="Note記事Markdownパス")
    parser.add_argument("--output-dir", required=True, help="出力ディレクトリ")
    parser.add_argument("--results", default=None, help="事前取得済みレース結果JSON（未指定時はnetkeibaから取得）")
    args = parser.parse_args()

    # 予測データ読み込み
    print(f"📂 予測データ読み込み: {args.prediction}")
    with open(args.prediction, encoding="utf-8") as f:
        prediction_data = json.load(f)
    race_name = prediction_data.get("race", {}).get("race_name", "unknown")

    # Note記事読み込み
    print(f"📂 Note記事読み込み: {args.note}")
    with open(args.note, encoding="utf-8") as f:
        note_markdown = f.read()

    # レース結果取得
    if args.results:
        print(f"📂 レース結果読み込み: {args.results}")
        with open(args.results, encoding="utf-8") as f:
            race_results = json.load(f)
    else:
        config_path = Path("config/default.yaml")
        config = yaml.safe_load(config_path.read_text(encoding="utf-8")) if config_path.exists() else {}
        print(f"🌐 レース結果取得中: {args.race_id} ({race_name})...")
        data_source = ProductionDataSource(config)
        analyst = PostRaceAnalyst(data_source)
        try:
            race_results = analyst.fetch_race_results(args.race_id)
        except Exception as e:
            print(f"❌ レース結果取得失敗: {e}")
            print("--results オプションで事前取得済みJSONを指定してください。")
            sys.exit(1)

    analyst = PostRaceAnalyst(None)
    entries = race_results.get("entries", [])
    print(f"   エントリ数: {len(entries)}頭")

    # 分析実行
    print("📊 分析実行中...")
    report = analyst.analyze(
        race_id=args.race_id,
        prediction_data=prediction_data,
        note_markdown=note_markdown,
        race_results=race_results,
    )

    # レポート保存
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "post_race_analysis.md"
    report_path.write_text(report, encoding="utf-8")

    print(f"\n✅ レポート保存: {report_path}")
    print(f"   文字数: {len(report):,}")


if __name__ == "__main__":
    main()
