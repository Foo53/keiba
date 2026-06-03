"""CLI エントリポイント"""

import argparse
import sys
from pathlib import Path

from keiba.orchestration.orchestrator import Orchestrator
from keiba.utils.config import load_config
from keiba.utils.logging import setup_logging


def main():
    parser = argparse.ArgumentParser(
        description="競馬予想システム - 14エージェントパイプライン",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用例:
  keiba                              サンプルレースで実行
  keiba 20260607-Tokyo-11            レースID指定で実行
  keiba -v                           詳細ログ付き
  keiba --source sample              サンプルデータで実行
  keiba --source production 202506010211  netkeiba形式IDで本番実行
        """,
    )
    parser.add_argument(
        "race_id", nargs="?", default="20260607-Tokyo-11",
        help="対象レースID (default: 20260607-Tokyo-11)",
    )
    parser.add_argument("--config", default=None, help="設定ファイルパス")
    parser.add_argument(
        "--source", choices=["sample", "production"], default=None,
        help="データソース (default: configに従う)",
    )
    parser.add_argument("--output-dir", default="output", help="出力ディレクトリ")
    parser.add_argument("--verbose", "-v", action="store_true", help="詳細ログ")

    args = parser.parse_args()

    # 設定読込
    try:
        config = load_config(args.config)
    except Exception as e:
        print(f"⚠️ 設定読込エラー: {e}。デフォルト設定で続行します。")
        config = None

    config_dict = config.model_dump() if config else {}

    # オーバーライド
    if args.source:
        config_dict.setdefault("data_source", {})["active"] = args.source
    if args.verbose:
        config_dict.setdefault("logging", {})["level"] = "DEBUG"

    # ログ初期化
    setup_logging(config_dict.get("logging", {}))

    print("=" * 60)
    print("🏇 競馬予想システム - 14エージェントパイプライン")
    print("=" * 60)
    print(f"対象レース: {args.race_id}")
    print(f"データソース: {config_dict.get('data_source', {}).get('active', 'sample')}")
    print("-" * 60)

    # パイプライン実行
    orchestrator = Orchestrator(config=config_dict)
    context = orchestrator.run(args.race_id)

    # 成果物保存
    orchestrator.save_outputs(context, args.output_dir)

    # 結果表示
    print()
    print("=" * 60)
    print("📊 実行結果")
    print("=" * 60)
    print(f"ステータス: {context.status}")
    print(f"完了エージェント数: {len(context.agent_results)}")

    # エージェント実行結果
    print("\n📋 エージェント実行ログ:")
    for r in context.agent_results:
        status = "✅" if r.get("success") else "❌"
        name = r.get("agent_name", "?")
        dur = r.get("duration_seconds", 0)
        err = r.get("error", "")
        line = f"  {status} {name} ({dur:.2f}s)"
        if err:
            line += f" - ERROR: {err}"
        print(line)

    # QA結果
    if context.qa_report:
        qa = context.qa_report
        print(f"\n🔍 QA採点: {qa['total_score']}/120")
        print(f"   合否: {'✅ 通過' if qa['passed'] else '❌ 不合格'}")
        for c in qa.get("criteria", []):
            mark = "✓" if c["passed"] else "✗"
            print(f"   {mark} {c['criterion_name']}: {c['actual_score']}/{c['max_score']} - {c['notes']}")

    # 予想サマリ
    if context.prediction_actual:
        pred = context.prediction_actual
        print(f"\n🎯 予想サマリ:")
        if pred.get("skip_recommended"):
            print(f"   ⚠️ 見送り推奨: {pred.get('skip_reason', '')}")
        else:
            for key in ["win_prediction", "place_prediction", "quinella_prediction", "trifecta_prediction"]:
                bet = pred.get(key)
                if bet:
                    risk = {"low": "🟢", "medium": "🟡", "high": "🔴"}.get(bet.get("risk_level", "medium"), "🟡")
                    print(f"   {risk} {bet['bet_type']}: {', '.join(bet['horse_names'])}")

    # Note
    if context.note_article:
        print(f"\n📝 Note記事: {context.note_article.get('title', '')}")
        print(f"   文字数: {context.note_article.get('word_count', 0)}")
        violations = context.note_article.get("prohibited_word_violations", [])
        print(f"   禁止表現: {'なし ✅' if not violations else '⚠️ ' + ', '.join(violations)}")

    # バックテスト
    if context.backtest:
        bt = context.backtest
        print(f"\n📈 バックテスト: {bt['total_races']}レース")
        print(f"   的中率: {bt['hit_rate']:.1%}")
        print(f"   ROI: {bt['roi']:.1%}")

    # 免責
    print("\n" + "=" * 60)
    print("⚠️ 本予想はデータ分析に基づく参考情報です。")
    print("   馬券の購入は自己責任でお願いします。")
    print("=" * 60)

    return 0 if context.status == "completed" else 1


if __name__ == "__main__":
    sys.exit(main())
