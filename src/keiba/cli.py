"""CLI エントリポイント"""

import argparse
import sys
from pathlib import Path

from keiba.orchestration.orchestrator import Orchestrator
from keiba.utils.config import load_config
from keiba.utils.logging import setup_logging


def main():
    parser = argparse.ArgumentParser(
        description="競馬予想システム - 16エージェントパイプライン",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用例:
  keiba                              サンプルレースで実行
  keiba 20260607-Tokyo-11            レースID指定で実行
  keiba -v                           詳細ログ付き
  keiba --source sample              サンプルデータで実行
  keiba --source production 202506010211  netkeiba形式IDで本番実行
  keiba train --source sample        サンプルデータでモデル学習
  keiba train --source production    本番データでモデル学習
  keiba train --source jrvan         JRA-VANデータでモデル学習
  keiba lead                         対話型リーダーを起動
  keiba lead 20260607-Tokyo-11       レースID指定でリーダー起動
        """,
    )
    # train サブコマンド（argparse の optional positional + subparser 競合を避けるため
    # 手動で train を検出してから該当パーサーに振り分ける）
    if len(sys.argv) > 1 and sys.argv[1] == "train":
        train_parser = argparse.ArgumentParser(
            description="LightGBM モデル学習",
        )
        train_parser.add_argument("--source", choices=["sample", "production", "jrvan"], default="production",
                                  help="データソース (default: production)")
        train_parser.add_argument("--months", type=int, default=12, help="学習データの期間（月）")
        train_parser.add_argument("--max-races", type=int, default=500, help="最大レース数")
        train_parser.add_argument("--optuna-trials", type=int, default=100, help="Optuna最適化試行数")
        train_parser.add_argument("--config", default=None, help="設定ファイルパス")
        args = train_parser.parse_args(sys.argv[2:])
        args.command = "train"
    elif len(sys.argv) > 1 and sys.argv[1] == "lead":
        lead_parser = argparse.ArgumentParser(
            description="対話型リーダーエージェント",
        )
        lead_parser.add_argument("race_id", nargs="?", default="20260607-Tokyo-11",
                                  help="対象レースID (default: 20260607-Tokyo-11)")
        lead_parser.add_argument("--config", default=None, help="設定ファイルパス")
        lead_parser.add_argument("--source", choices=["sample", "production"], default=None,
                                  help="データソース (default: configに従う)")
        lead_parser.add_argument("--verbose", "-v", action="store_true", help="詳細ログ")
        args = lead_parser.parse_args(sys.argv[2:])
        args.command = "lead"
    else:
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
        args.command = None

    # train サブコマンドの処理
    if args.command == "train":
        return _run_train(args)

    # lead サブコマンドの処理
    if args.command == "lead":
        return _run_lead(args)

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
    print("🏇 競馬予想システム - 16エージェントパイプライン")
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


def _run_lead(args) -> int:
    """対話型リーダーエージェントのエントリポイント"""
    from keiba.orchestration.leader import LeaderAgent

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

    # データソース構築
    active = config_dict.get("data_source", {}).get("active", "sample")
    if active == "sample":
        from keiba.data.sample.sample_source import SampleDataSource
        ds = SampleDataSource()
    elif active == "production":
        from keiba.data.production.production_source import ProductionDataSource
        ds = ProductionDataSource(config_dict)
    else:
        from keiba.data.sample.sample_source import SampleDataSource
        ds = SampleDataSource()

    # リーダー起動
    leader = LeaderAgent(config=config_dict, data_source=ds, race_id=args.race_id)
    leader.run()
    return 0


def _run_train(args) -> int:
    """LightGBMモデル学習のエントリポイント"""
    from keiba.utils.config import load_config
    from keiba.utils.logging import setup_logging

    try:
        config = load_config(None)
    except Exception:
        config = None
    config_dict = config.model_dump() if config else {}

    if args.source:
        config_dict.setdefault("data_source", {})["active"] = args.source

    setup_logging(config_dict.get("logging", {}))

    print("=" * 60)
    print("🏁 LightGBM モデル学習")
    print("=" * 60)
    print(f"データソース: {args.source}")
    print(f"Optuna試行数: {args.optuna_trials}")
    print("-" * 60)

    # データソース構築
    active = args.source
    if active == "sample":
        from keiba.data.sample.sample_source import SampleDataSource
        ds = SampleDataSource()
    elif active == "jrvan":
        from keiba.data.jrvan.data_source import JrVanDataSource
        ds = JrVanDataSource(config_dict)
    elif active == "production":
        from keiba.data.production.production_source import ProductionDataSource
        ds = ProductionDataSource(config_dict)
    else:
        from keiba.data.sample.sample_source import SampleDataSource
        ds = SampleDataSource()

    from keiba.ml.trainer import LightGBMTrainer
    trainer = LightGBMTrainer(ds, config_dict)

    try:
        report = trainer.train(
            months=args.months,
            max_races=args.max_races,
            optuna_trials=args.optuna_trials,
        )
    except Exception as e:
        print(f"\n❌ 学習失敗: {e}")
        return 1

    # 結果表示
    print()
    print("=" * 60)
    print("🏁 LightGBM モデル学習完了")
    print("=" * 60)
    print(f"📊 学習サンプル数: {report['train_samples']:,}")
    print(f"📊 検証サンプル数: {report['val_samples']:,}")
    print(f"📊 テストサンプル数: {report.get('test_samples', 0):,}")
    print(f"📈 検証AUC (val): {report['val_auc']:.4f}")
    print(f"📈 テストAUC (test): {report.get('test_auc', 0):.4f}")

    if report.get("top_features"):
        print("🔑 上位特徴量 (gain):")
        for i, feat in enumerate(report["top_features"][:5], 1):
            print(f"  {i}. {feat['feature']:<30s} ({feat['importance']:.3f})")

    print(f"💾 モデル保存先: data/store/models/lgbm_latest.txt")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
