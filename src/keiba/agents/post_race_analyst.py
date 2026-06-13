"""エージェント: レース後分析官

レース結果と予測を比較し、定量評価・定性評価・5軸分析・改善提案をまとめた
反省レポートを生成する。
"""

import re
import statistics
from datetime import datetime

from keiba.agents.base import BaseAgent
from keiba.data.base_source import DataSource
from keiba.models.pipeline import PipelineContext


class PostRaceAnalyst(BaseAgent):
    """レース後の予測精度を分析し、改善提案を作成するエージェント"""

    def __init__(self, data_source: DataSource):
        super().__init__()
        self.data_source = data_source

    # ---- BaseAgent インターフェース ----

    def validate_input(self, context: PipelineContext) -> bool:
        return context.race_id is not None

    def process(self, context: PipelineContext) -> PipelineContext:
        raise NotImplementedError(
            "PostRaceAnalyst はスタンドアロン実行専用です。"
            "scripts/post_race_analysis.py を使用してください。"
        )

    # ---- メインエントリ（スタンドアロン） ----

    def analyze(
        self,
        race_id: str,
        prediction_data: dict,
        note_markdown: str,
        race_results: dict,
    ) -> str:
        """予測と結果を比較し、反省レポート（Markdown）を返す。"""
        predictions = self._load_predictions(prediction_data)
        model_info = prediction_data.get("model_info", {})
        picks = self._parse_note_picks(note_markdown)
        results_entries = race_results.get("entries", [])
        race_info = race_results.get("race", {})

        # 着順→馬番マップ
        finish_map = {e["post_position"]: e for e in results_entries}

        comparison = self._quantitative_comparison(
            predictions, picks, results_entries, finish_map,
        )
        qualitative = self._qualitative_analysis(
            predictions, picks, results_entries, finish_map, comparison,
        )
        five_axis = self._five_axis_evaluation(
            model_info, comparison, results_entries, finish_map,
        )
        improvements = self._generate_improvements(comparison, five_axis)

        return self._build_report(
            race_id=race_id,
            race_info=race_info,
            results_entries=results_entries,
            finish_map=finish_map,
            predictions=predictions,
            model_info=model_info,
            picks=picks,
            comparison=comparison,
            qualitative=qualitative,
            five_axis=five_axis,
            improvements=improvements,
        )

    # ---- 結果取得 ----

    def fetch_race_results(self, race_id: str) -> dict:
        """netkeiba からレース結果を取得"""
        return self.data_source.get_historical_data(race_id)

    # ---- 予測読み込み ----

    @staticmethod
    def _load_predictions(prediction_data: dict) -> list[dict]:
        return prediction_data.get("predictions", [])

    # ---- Note記事パース ----

    def _parse_note_picks(self, markdown: str) -> dict:
        """Note記事から◎○▲☆△・消し馬・買い目を抽出"""
        picks = {
            "honmei": None,
            "taikou": None,
            "tanana": None,
            "hyouka": None,
            "kouho": [],
            "keshi_uma": [],
            "bets": {"tanshou": [], "umaren": [], "wide": []},
        }

        # ◎○▲☆△ パース
        mark_patterns = [
            ("honmei", r"\*\*◎\s+(.+?)（(\d+)番）\*\*"),
            ("taikou", r"\*\*○\s+(.+?)（(\d+)番）\*\*"),
            ("tanana", r"\*\*▲\s+(.+?)（(\d+)番）\*\*"),
            ("hyouka", r"\*\*☆\s+(.+?)（(\d+)番）\*\*"),
        ]
        for key, pattern in mark_patterns:
            m = re.search(pattern, markdown)
            if m:
                picks[key] = {"name": m.group(1), "umaban": int(m.group(2))}

        # △候補（複数）
        for m in re.finditer(r"\*\*△\s+(.+?)（(\d+)番）\*\*", markdown):
            picks["kouho"].append({"name": m.group(1), "umaban": int(m.group(2))})

        # 消し馬セクション
        keshi_section = self._extract_section(markdown, "消し馬")
        if keshi_section:
            for m in re.finditer(r"\*\*(.+?)（(\d+)番）", keshi_section):
                picks["keshi_uma"].append({
                    "name": m.group(1),
                    "umaban": int(m.group(2)),
                })

        # 買い目パース
        picks["bets"] = self._parse_bets(markdown)

        return picks

    @staticmethod
    def _extract_section(markdown: str, header: str) -> str:
        """指定ヘッダーのセクション本文を抽出"""
        pattern = rf"##\s+[^\n]*{re.escape(header)}[^\n]*\n(.*?)(?=\n## |\Z)"
        m = re.search(pattern, markdown, re.DOTALL)
        return m.group(1) if m else ""

    def _parse_bets(self, markdown: str) -> dict:
        """買い目テーブルから券種別に抽出"""
        bets = {"tanshou": [], "umaren": [], "wide": []}

        # 単勝: | 単勝 | **11番** |
        for m in re.finditer(r"\|\s*単勝\s*\|\s*\*\*(\d+)番?\*\*", markdown):
            bets["tanshou"].append(int(m.group(1)))

        # 馬連: | 馬連 | **11-17** |
        for m in re.finditer(r"\|\s*馬連\s*\|\s*\*\*(\d+)-(\d+)\*\*", markdown):
            bets["umaren"].append([int(m.group(1)), int(m.group(2))])

        # ワイド: | ワイド | **11-6** |
        for m in re.finditer(r"\|\s*ワイド\s*\|\s*\*\*(\d+)-(\d+)\*\*", markdown):
            bets["wide"].append([int(m.group(1)), int(m.group(2))])

        return bets

    # ---- 定量比較 ----

    def _quantitative_comparison(
        self,
        predictions: list[dict],
        picks: dict,
        results_entries: list[dict],
        finish_map: dict,
    ) -> dict:
        """ML予測と結果の定量比較"""
        comparison = {}

        # 1. ML順位 vs 着順の相関
        ml_ranks, actual_ranks = [], []
        for p in predictions:
            umaban = p["umaban"]
            entry = finish_map.get(umaban)
            if entry and entry.get("finish_position", 0) > 0:
                ml_ranks.append(p["rank"])
                actual_ranks.append(entry["finish_position"])

        comparison["spearman"] = (
            self._spearman_correlation(ml_ranks, actual_ranks)
            if len(ml_ranks) >= 3 else 0.0
        )

        # 2. 上位3頭カバー率
        actual_top3 = sorted(
            [e for e in results_entries if e.get("finish_position", 99) <= 3],
            key=lambda e: e["finish_position"],
        )
        actual_top3_umabans = {e["post_position"] for e in actual_top3}
        ml_top5_umabans = {p["umaban"] for p in predictions[:5]}
        comparison["top3_coverage"] = len(actual_top3_umabans & ml_top5_umabans)

        # 3. キー馬の着順
        key_horses = {}
        for role in ["honmei", "taikou", "tanana", "hyouka"]:
            pick = picks.get(role)
            if pick:
                entry = finish_map.get(pick["umaban"])
                key_horses[role] = {
                    "name": pick["name"],
                    "umaban": pick["umaban"],
                    "actual_position": entry["finish_position"] if entry else None,
                    "popularity": entry.get("popularity") if entry else None,
                }
        for kp in picks.get("kouho", []):
            entry = finish_map.get(kp["umaban"])
            key_horses[f"kouho_{kp['umaban']}"] = {
                "name": kp["name"],
                "umaban": kp["umaban"],
                "actual_position": entry["finish_position"] if entry else None,
                "popularity": entry.get("popularity") if entry else None,
            }
        comparison["key_horses"] = key_horses

        # 4. 消し馬正解率
        keshi_results = []
        for ku in picks.get("keshi_uma", []):
            entry = finish_map.get(ku["umaban"])
            pos = entry["finish_position"] if entry else 99
            keshi_results.append({
                "name": ku["name"],
                "umaban": ku["umaban"],
                "actual_position": pos,
                "correct": pos > 3,
            })
        comparison["keshi_uma"] = keshi_results
        if keshi_results:
            comparison["keshi_accuracy"] = sum(
                1 for k in keshi_results if k["correct"]
            ) / len(keshi_results)
        else:
            comparison["keshi_accuracy"] = None

        # 5. 買い目的中判定
        bet_results = []
        actual_top3_set = {
            (i + 1, e["post_position"])
            for i, e in enumerate(actual_top3)
        }

        for umaban in picks["bets"]["tanshou"]:
            entry = finish_map.get(umaban)
            hit = entry["finish_position"] == 1 if entry else False
            bet_results.append({
                "type": "単勝",
                "numbers": str(umaban),
                "hit": hit,
            })

        for pair in picks["bets"]["umaren"]:
            e1 = finish_map.get(pair[0])
            e2 = finish_map.get(pair[1])
            pos1 = e1["finish_position"] if e1 else 99
            pos2 = e2["finish_position"] if e2 else 99
            hit = pos1 <= 2 and pos2 <= 2 and pos1 != pos2
            bet_results.append({
                "type": "馬連",
                "numbers": f"{pair[0]}-{pair[1]}",
                "hit": hit,
            })

        for pair in picks["bets"]["wide"]:
            e1 = finish_map.get(pair[0])
            e2 = finish_map.get(pair[1])
            pos1 = e1["finish_position"] if e1 else 99
            pos2 = e2["finish_position"] if e2 else 99
            hit = pos1 <= 3 and pos2 <= 3 and pos1 != pos2
            bet_results.append({
                "type": "ワイド",
                "numbers": f"{pair[0]}-{pair[1]}",
                "hit": hit,
            })

        comparison["bet_results"] = bet_results
        comparison["bet_hits"] = sum(1 for b in bet_results if b["hit"])
        comparison["bet_total"] = len(bet_results)

        # 6. 勝ち馬の予測順位
        winner_entry = None
        for e in results_entries:
            if e.get("finish_position") == 1:
                winner_entry = e
                break
        if winner_entry:
            winner_umaban = winner_entry["post_position"]
            winner_ml_rank = None
            for p in predictions:
                if p["umaban"] == winner_umaban:
                    winner_ml_rank = p["rank"]
                    break
            comparison["winner"] = {
                "name": winner_entry.get("horse_name", ""),
                "umaban": winner_umaban,
                "popularity": winner_entry.get("popularity"),
                "odds": winner_entry.get("odds"),
                "ml_rank": winner_ml_rank,
                "last_3f": winner_entry.get("last_3f"),
            }

        return comparison

    # ---- 定性分析 ----

    def _qualitative_analysis(
        self,
        predictions: list[dict],
        picks: dict,
        results_entries: list[dict],
        finish_map: dict,
        comparison: dict,
    ) -> dict:
        """良かった点・悪かった点を生成"""
        praise = []
        issues = []

        # 本命の評価
        kh = comparison.get("key_horses", {})
        honmei = kh.get("honmei")
        if honmei:
            pos = honmei.get("actual_position")
            if pos == 1:
                praise.append(
                    f"◎{honmei['name']}（{honmei['umaban']}番）が**1着で完璧的中**。"
                    f"ML評価1位を結果で証明した。"
                )
            elif pos and pos <= 3:
                praise.append(
                    f"◎{honmei['name']}（{honmei['umaban']}番）が{pos}着と馬券圏内。"
                    f"本命評価は妥当だった。"
                )
            elif pos:
                issues.append(
                    f"◎{honmei['name']}（{honmei['umaban']}番）が{pos}着に敗退。"
                    f"本命評価が結果と乖離した。"
                )

        # 対抗・単穴の評価
        for role, label in [("taikou", "○対抗"), ("tanana", "▲単穴")]:
            horse = kh.get(role)
            if horse:
                pos = horse.get("actual_position")
                if pos and pos <= 3:
                    praise.append(
                        f"{label}の{horse['name']}（{horse['umaban']}番）が{pos}着で馬券圏内。"
                        f"評価通り好走した。"
                    )
                elif pos:
                    issues.append(
                        f"{label}の{horse['name']}（{horse['umaban']}番）が{pos}着。"
                        f"期待以下の結果に終わった。"
                    )

        # 消し馬正解
        keshi_correct = [k for k in comparison.get("keshi_uma", []) if k["correct"]]
        if keshi_correct:
            names = ", ".join(k["name"] for k in keshi_correct)
            praise.append(
                f"消し馬判定が正解: **{names}** が馬券圏外に終わった。"
                f"除外の判断は適切だった。"
            )

        keshi_wrong = [k for k in comparison.get("keshi_uma", []) if not k["correct"]]

        # △候補の評価
        for role, horse in kh.items():
            if not role.startswith("kouho_"):
                continue
            pos = horse.get("actual_position")
            if pos and pos <= 3:
                praise.append(
                    f"△候補の**{horse['name']}**（{horse['umaban']}番）が"
                    f"実際{pos}着と大健闘。候補に入れておいた判断は正しかった。"
                )

        if keshi_wrong:
            for k in keshi_wrong:
                issues.append(
                    f"消し馬の**{k['name']}**（{k['umaban']}番）が{k['actual_position']}着。"
                    f"除外判定が誤りだった。"
                )

        # ML相関
        spearman = comparison.get("spearman", 0)
        if spearman > 0.4:
            praise.append(
                f"ML予測順位と着順の相関が **{spearman:.2f}** と高く、"
                f"モデルの方向性は概ね正しかった。"
            )
        elif spearman > 0.1:
            praise.append(
                f"ML予測の相関は {spearman:.2f} と弱い正の相関。"
                f"完全ではなかったが、ランダムよりは良い。"
            )
        elif spearman < -0.1:
            issues.append(
                f"ML予測の相関が {spearman:.2f} と負。"
                f"予測が実際の着順と逆方向に出た可能性がある。"
            )

        # 上位3頭カバー
        coverage = comparison.get("top3_coverage", 0)
        if coverage >= 2:
            praise.append(
                f"3連複1-2-3着のうち{coverage}頭をML上位5位以内に含んでいた。"
            )
        elif coverage == 0:
            issues.append(
                "実際の上位3頭がML上位5位に1頭も含まれていなかった。"
                "モデルの捕捉力に課題がある。"
            )

        # 勝ち馬の予測順位
        winner = comparison.get("winner")
        if winner:
            ml_rank = winner.get("ml_rank")
            if ml_rank and ml_rank <= 3:
                praise.append(
                    f"勝ち馬{winner['name']}（{winner['umaban']}番）を"
                    f"ML{ml_rank}位と高く評価していた。"
                )
            elif ml_rank:
                issues.append(
                    f"勝ち馬{winner['name']}（{winner['umaban']}番）の"
                    f"ML評価は{ml_rank}位。勝ち馬を上位に捉えきれなかった。"
                )

        return {"praise": praise, "issues": issues}

    # ---- 5軸評価 ----

    def _five_axis_evaluation(
        self,
        model_info: dict,
        comparison: dict,
        results_entries: list[dict],
        finish_map: dict,
    ) -> list[dict]:
        axes = []

        # 1. データソース
        train_samples = model_info.get("train_samples", 0)
        if train_samples >= 100000:
            axes.append({
                "category": "データソース",
                "ok": True,
                "detail": f"JRA-VAN実データ{train_samples:,}件で学習。架空データの問題なし。",
            })
        else:
            axes.append({
                "category": "データソース",
                "ok": False,
                "detail": f"学習データ{train_samples:,}件はやや少ない。",
            })

        # 2. ML区別力
        spearman = comparison.get("spearman", 0)
        axes.append({
            "category": "ML区別力",
            "ok": spearman > 0.1,
            "detail": f"スピアマン相関 {spearman:.2f}。"
                      + ("予測に有意な区別力がある。" if spearman > 0.1
                         else "相関が低く、区別力が不十分。"),
        })

        # 3. 特徴量網羅性
        winner = comparison.get("winner")
        if winner:
            ml_rank = winner.get("ml_rank", 99)
            axes.append({
                "category": "特徴量網羅性",
                "ok": ml_rank and ml_rank <= 5,
                "detail": f"勝ち馬のML順位は{ml_rank or '圏外'}。"
                          + ("必要な特徴量を捉えている。" if ml_rank and ml_rank <= 5
                             else "勝ち馬を拾うための特徴量が不足している可能性。"),
            })
        else:
            axes.append({
                "category": "特徴量網羅性",
                "ok": None,
                "detail": "勝ち馬データなし。評価不可。",
            })

        # 4. 展開予測
        top3_coverage = comparison.get("top3_coverage", 0)
        axes.append({
            "category": "展開予測",
            "ok": top3_coverage >= 2,
            "detail": f"上位3頭のMLカバー率: {top3_coverage}/3。"
                      + ("展開を読む精度は高い。" if top3_coverage >= 2
                         else "展開の予測精度に課題がある。"),
        })

        # 5. 記事整合性
        kh = comparison.get("key_horses", {})
        honmei = kh.get("honmei")
        if honmei:
            pos = honmei.get("actual_position", 99)
            axes.append({
                "category": "記事整合性",
                "ok": pos <= 5 if pos else None,
                "detail": f"本命馬が実際{pos or '?'}着。"
                          + ("記事の評価方向性は妥当。" if pos and pos <= 5
                             else "記事の評価と結果に乖離。"),
            })
        else:
            axes.append({
                "category": "記事整合性",
                "ok": None,
                "detail": "本馬情報なし。評価不可。",
            })

        return axes

    # ---- 改善提案 ----

    def _generate_improvements(
        self, comparison: dict, five_axis: list[dict],
    ) -> list[dict]:
        suggestions = []

        # ML区別力が低い場合
        if comparison.get("spearman", 0) < 0.2:
            suggestions.append({
                "priority": "high",
                "proposal": "特徴量の見直し・追加によるML区別力の向上",
                "target": "ml/feature_vectorizer.py, ml/trainer.py",
                "effect": "予測と着順の相関向上。勝ち馬の捕捉率改善。",
            })

        # 上位3頭カバーが低い場合
        if comparison.get("top3_coverage", 0) < 2:
            suggestions.append({
                "priority": "high",
                "proposal": "上位候補の幅を広げる（ML上位5→7）か、複数シナリオ分析の導入",
                "target": "agents/prediction_generator.py, agents/python_analyzer.py",
                "effect": "大穴・伏兵の捕捉率改善。",
            })

        # 本命が外れた場合
        kh = comparison.get("key_horses", {})
        honmei = kh.get("honmei")
        if honmei and honmei.get("actual_position", 99) > 3:
            suggestions.append({
                "priority": "medium",
                "proposal": "本命判定に「展開シナリオ確度」を組み込む。逃げ馬のペース予測精度を上げる",
                "target": "agents/python_analyzer.py, agents/evidence_integrator.py",
                "effect": "本命の的中率向上。",
            })

        # 払戻データ拡充
        suggestions.append({
            "priority": "medium",
            "proposal": "馬連・3連複の払戻データもスクレイピングしてROI計算を正確化",
            "target": "data/production/scrapers/netkeiba_scraper.py (_parse_payout)",
            "effect": "正確な損益計算。投資戦略の改善指標として活用。",
        })

        # 消し馬誤り
        keshi_wrong = [k for k in comparison.get("keshi_uma", []) if not k["correct"]]
        if keshi_wrong:
            suggestions.append({
                "priority": "low",
                "proposal": "消し馬判定基準に「コース適性」「馬場適性」を加味する",
                "target": "agents/prediction_generator.py",
                "effect": "消し馬の誤除外を減らす。",
            })

        return suggestions

    # ---- レポート生成 ----

    def _build_report(
        self,
        race_id: str,
        race_info: dict,
        results_entries: list[dict],
        finish_map: dict,
        predictions: list[dict],
        model_info: dict,
        picks: dict,
        comparison: dict,
        qualitative: dict,
        five_axis: list[dict],
        improvements: list[dict],
    ) -> str:
        lines = []

        # ヘッダー
        race_name = race_info.get("race_name", race_id)
        lines.append(f"# 📊 レース後分析報告: {race_name}")
        lines.append("")
        lines.append(f"> 生成日時: {datetime.now().strftime('%Y-%m-%d %H:%M')} | レースID: {race_id}")
        lines.append("")

        # レース結果
        lines.append("## レース結果")
        lines.append("")
        lines.append("| 着順 | 馬番 | 馬名 | 人気 | 単勝 | 上がり3F | 通過順 |")
        lines.append("|------|------|------|------|------|----------|--------|")
        sorted_entries = sorted(
            [e for e in results_entries if e.get("finish_position", 0) > 0],
            key=lambda e: e["finish_position"],
        )
        for e in sorted_entries:
            f3 = f"{e.get('last_3f', '-')}" if e.get('last_3f') else "-"
            passing = e.get("passing_order", "-")
            odds = f"{e.get('odds', '-'): .1f}" if e.get('odds') else "-"
            pop = str(e.get("popularity", "-"))
            lines.append(
                f"| {e['finish_position']}着 "
                f"| {e['post_position']} "
                f"| {e.get('horse_name', '-')} "
                f"| {pop} "
                f"| {odds} "
                f"| {f3} "
                f"| {passing} |"
            )
        lines.append("")

        # ML予測精度
        lines.append("## ML予測精度評価")
        lines.append("")
        lines.append(f"| 指標 | 値 |")
        lines.append(f"|------|---|")
        lines.append(f"| ML順位 vs 着順 相関 | **{comparison.get('spearman', 0):.2f}** |")
        lines.append(f"| 上位3頭カバー率 | {comparison.get('top3_coverage', 0)}/3 |")
        winner = comparison.get("winner")
        if winner:
            lines.append(f"| 勝ち馬ML順位 | {winner.get('ml_rank', '圏外')}位 |")
            lines.append(f"| 勝ち馬人気 | {winner.get('popularity', '-')}番人気 |")
        lines.append(f"| モデルtest_auc | {model_info.get('test_auc', 'N/A')} |")
        lines.append("")

        # キー馬の結果
        lines.append("## 予想馬の結果")
        lines.append("")
        lines.append("| 役割 | 馬名 | 馬番 | ML順位 | 実際の着順 | 人気 | 判定 |")
        lines.append("|------|------|------|--------|-----------|------|------|")

        kh = comparison.get("key_horses", {})
        role_labels = [
            ("honmei", "◎本命"), ("taikou", "○対抗"), ("tanana", "▲単穴"),
            ("hyouka", "☆評価"),
        ]
        for role, label in role_labels:
            horse = kh.get(role)
            if horse:
                pos = horse.get("actual_position", "?")
                pop = horse.get("popularity", "?")
                ml_r = next(
                    (p["rank"] for p in predictions if p["umaban"] == horse["umaban"]),
                    "?",
                )
                mark = "✅" if pos and pos <= 3 else "❌"
                lines.append(
                    f"| {label} | {horse['name']} | {horse['umaban']} "
                    f"| {ml_r} | {pos}着 | {pop}人気 | {mark} |"
                )

        for kp in picks.get("kouho", []):
            horse = kh.get(f"kouho_{kp['umaban']}")
            if horse:
                pos = horse.get("actual_position", "?")
                pop = horse.get("popularity", "?")
                ml_r = next(
                    (p["rank"] for p in predictions if p["umaban"] == horse["umaban"]),
                    "?",
                )
                mark = "✅" if pos and pos <= 3 else "—"
                lines.append(
                    f"| △候補 | {horse['name']} | {horse['umaban']} "
                    f"| {ml_r} | {pos}着 | {pop}人気 | {mark} |"
                )
        lines.append("")

        # 消し馬判定
        keshi = comparison.get("keshi_uma", [])
        if keshi:
            lines.append("### 消し馬判定")
            lines.append("")
            lines.append("| 馬名 | 馬番 | 実着順 | 判定 |")
            lines.append("|------|------|--------|------|")
            for k in keshi:
                mark = "✅正解" if k["correct"] else "❌誤り"
                lines.append(f"| {k['name']} | {k['umaban']} | {k['actual_position']}着 | {mark} |")
            acc = comparison.get("keshi_accuracy", 0)
            if acc is not None:
                lines.append(f"\n消し馬正解率: **{acc:.0%}**")
            lines.append("")

        # 買い目的中判定
        bet_results = comparison.get("bet_results", [])
        if bet_results:
            lines.append("## 買い目的中判定")
            lines.append("")
            lines.append("| 券種 | 買い目 | 結果 |")
            lines.append("|------|--------|------|")
            for b in bet_results:
                mark = "⭕的中" if b["hit"] else "❌不的中"
                lines.append(f"| {b['type']} | {b['numbers']} | {mark} |")
            hits = comparison.get("bet_hits", 0)
            total = comparison.get("bet_total", 0)
            lines.append(f"\n的中率: **{hits}/{total}** ({hits/total:.0%})" if total else "")
            lines.append("")

        # 的中した点
        lines.append("## ✅ 的中した点（良かったこと）")
        lines.append("")
        for p in qualitative.get("praise", []):
            lines.append(f"- {p}")
        if not qualitative.get("praise"):
            lines.append("- （該当なし）")
        lines.append("")

        # 外れた点
        lines.append("## ❌ 外れた点（課題）")
        lines.append("")
        for i in qualitative.get("issues", []):
            lines.append(f"- {i}")
        if not qualitative.get("issues"):
            lines.append("- （該当なし — 素晴らしい予想でした！）")
        lines.append("")

        # 5軸評価
        lines.append("## 5軸評価")
        lines.append("")
        lines.append("| # | カテゴリ | 評価 | 詳細 |")
        lines.append("|---|---------|------|------|")
        for i, axis in enumerate(five_axis, 1):
            ok = axis.get("ok")
            if ok is True:
                mark = "⭕"
            elif ok is False:
                mark = "❌"
            else:
                mark = "—"
            lines.append(f"| {i} | {axis['category']} | {mark} | {axis['detail']} |")
        lines.append("")

        # 改善提案
        lines.append("## 改善提案（優先度順）")
        lines.append("")
        lines.append("| 優先度 | 改善案 | 対象モジュール | 期待効果 |")
        lines.append("|--------|--------|---------------|---------|")
        priority_labels = {"high": "🔴高", "medium": "🟡中", "low": "🟢低"}
        for s in improvements:
            p_label = priority_labels.get(s["priority"], s["priority"])
            lines.append(
                f"| {p_label} | {s['proposal']} | {s['target']} | {s['effect']} |"
            )
        lines.append("")

        # 次アクション
        lines.append("## 次アクション")
        lines.append("")
        lines.append("以下は今回の分析に基づく改善の方向性です。実施するかどうかはリーダーの判断にお任せします。")
        lines.append("")
        for s in improvements:
            lines.append(f"- [{s['priority'].upper()}] {s['proposal']}")
        lines.append("")

        # フッター
        lines.append("---")
        lines.append("")
        lines.append("*本レポートは自動生成された分析です。改善提案は検討材料としてご活用ください。*")

        return "\n".join(lines)

    # ---- ユーティリティ ----

    @staticmethod
    def _spearman_correlation(ranks1: list[int], ranks2: list[int]) -> float:
        """スピアマン順位相関係数"""
        n = len(ranks1)
        if n <= 1:
            return 0.0
        d_sq = sum((r1 - r2) ** 2 for r1, r2 in zip(ranks1, ranks2))
        denom = n * (n**2 - 1)
        return 1 - (6 * d_sq) / denom if denom > 0 else 0.0
