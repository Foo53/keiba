"""EDA可視化エージェント"""

import logging
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns

from keiba.agents.base import BaseAgent
from keiba.models.pipeline import PipelineContext

JP_FONT = "Noto Sans CJK JP"


def _setup_japanese_fonts():
    font_path = Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc")
    if font_path.exists():
        matplotlib.rcParams["font.family"] = JP_FONT
        matplotlib.rcParams["font.sans-serif"] = [JP_FONT]
        matplotlib.rcParams["axes.unicode_minus"] = False
    else:
        logging.getLogger(__name__).warning("Noto Sans CJK JP not found, Japanese labels may not render")


class VisualizerAgent(BaseAgent):
    """EDAチャートを生成するエージェント"""

    def validate_input(self, context: PipelineContext) -> bool:
        return context.features is not None and context.evidence is not None

    def process(self, context: PipelineContext) -> PipelineContext:
        _setup_japanese_fonts()
        out_dir = Path("output/eda") / context.race_id
        out_dir.mkdir(parents=True, exist_ok=True)
        images = {}

        charts = [
            ("horse_comparison", self._chart_horse_comparison),
            ("feature_comparison", self._chart_feature_comparison),
            ("expected_value", self._chart_expected_value),
            ("backtest_summary", self._chart_backtest_summary),
            ("recent_form_heatmap", self._chart_recent_form_heatmap),
        ]

        for name, chart_fn in charts:
            try:
                path = chart_fn(context, out_dir)
                if path:
                    images[name] = str(path)
            except Exception as e:
                self.logger.warning(f"Chart '{name}' failed: {e}")

        context.eda_images = images if images else None
        self.logger.info(f"Generated {len(images)}/{len(charts)} charts")
        return context

    def _chart_horse_comparison(self, context: PipelineContext, out_dir: Path) -> str | None:
        features = {hf["entry_id"]: hf for hf in context.features.get("horse_features", [])}
        horses = context.evidence.get("horses", [])
        if not horses:
            return None

        ranked = sorted(horses, key=lambda h: h.get("integrated_probability", 0), reverse=True)
        names = [h["horse_name"] for h in ranked]
        probs = [h.get("integrated_probability", 0) for h in ranked]
        grades = [h.get("evidence_grade", "C") for h in ranked]
        grade_colors = {"S": "#e74c3c", "A": "#e67e22", "B": "#f1c40f", "C": "#95a5a6"}
        colors = [grade_colors.get(g, "#95a5a6") for g in grades]

        fig, ax = plt.subplots(figsize=(10, max(4, len(names) * 0.6)))
        bars = ax.barh(range(len(names)), probs, color=colors)
        ax.set_yticks(range(len(names)))
        ax.set_yticklabels(names, fontsize=10)
        ax.invert_yaxis()
        ax.set_xlabel("勝率推定")
        ax.set_title("出走馬 勝率推定ランキング")

        for i, h in enumerate(ranked):
            f = features.get(h.get("entry_id", ""), {})
            labels = []
            if f.get("distance_aptitude_score"):
                labels.append(f"距離{f['distance_aptitude_score']:.0f}")
            if f.get("form_score"):
                labels.append(f"調子{f['form_score']:.0f}")
            jt = f.get("jockey_trainer_win_rate")
            if jt:
                labels.append(f"JT{jt:.0%}")
            if labels:
                ax.text(bars[i].get_width() + 0.005, i, " / ".join(labels), va="center", fontsize=8)

        plt.tight_layout()
        path = out_dir / "horse_comparison.png"
        fig.savefig(path, dpi=150, bbox_inches="tight")
        plt.close(fig)
        return str(path)

    def _chart_feature_comparison(self, context: PipelineContext, out_dir: Path) -> str | None:
        features = {hf["entry_id"]: hf for hf in context.features.get("horse_features", [])}
        top5 = sorted(
            context.evidence.get("horses", []),
            key=lambda h: h.get("integrated_probability", 0),
            reverse=True,
        )[:5]
        if not top5:
            return None

        names = [h["horse_name"][:6] for h in top5]
        x = np.arange(len(names))
        width = 0.2

        dist, form, closing, jt = [], [], [], []
        for h in top5:
            f = features.get(h.get("entry_id", ""), {})
            dist.append(f.get("distance_aptitude_score", 0))
            form.append(f.get("form_score", 0))
            cr = f.get("closing_speed_rank")
            closing.append(max(0, 100 - (cr - 1) * 15) if cr else 50)
            jt.append((f.get("jockey_trainer_win_rate") or 0) * 100)

        fig, ax = plt.subplots(figsize=(10, 6))
        ax.bar(x - 1.5 * width, dist, width, label="距離適性")
        ax.bar(x - 0.5 * width, form, width, label="調子")
        ax.bar(x + 0.5 * width, closing, width, label="上がり")
        ax.bar(x + 1.5 * width, jt, width, label="騎手厩舎")
        ax.set_xticks(x)
        ax.set_xticklabels(names)
        ax.set_ylabel("スコア (0-100)")
        ax.set_title("上位5頭 特徴量比較")
        ax.legend()
        ax.set_ylim(0, 105)

        plt.tight_layout()
        path = out_dir / "feature_comparison.png"
        fig.savefig(path, dpi=150, bbox_inches="tight")
        plt.close(fig)
        return str(path)

    def _chart_expected_value(self, context: PipelineContext, out_dir: Path) -> str | None:
        evals = (context.actual_odds_eval or {}).get("evaluations", [])
        if not evals:
            return None

        odds = [e.get("actual_odds", 0) for e in evals]
        model_probs = [e.get("model_probability", 0) for e in evals]
        evs = [e.get("expected_value", 0) for e in evals]
        names = [e.get("horse_name", "")[:6] for e in evals]

        fig, ax = plt.subplots(figsize=(10, 7))
        scatter = ax.scatter(
            odds, model_probs, c=evs, cmap="RdYlGn",
            s=100, edgecolors="black", linewidths=0.5, zorder=5,
        )
        plt.colorbar(scatter, ax=ax, label="期待値 (EV)")

        max_odds = max(odds) * 1.1 if odds else 10
        x_line = np.linspace(1, max_odds, 100)
        ax.plot(x_line, 1.0 / x_line, "k--", alpha=0.5, label="フェアバリュー線")

        for i, name in enumerate(names):
            ax.annotate(name, (odds[i], model_probs[i]),
                        textcoords="offset points", xytext=(5, 5), fontsize=8)

        ax.set_xlabel("実オッズ")
        ax.set_ylabel("モデル勝率")
        ax.set_title("オッズ vs モデル勝率 (色=期待値)")
        ax.legend()

        plt.tight_layout()
        path = out_dir / "expected_value.png"
        fig.savefig(path, dpi=150, bbox_inches="tight")
        plt.close(fig)
        return str(path)

    def _chart_backtest_summary(self, context: PipelineContext, out_dir: Path) -> str | None:
        bt = context.backtest or {}
        breakdown = bt.get("breakdown_by_bet_type", {})
        if not breakdown:
            return None

        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 5))

        bet_types = list(breakdown.keys())
        rois = [breakdown[b]["roi"] for b in bet_types]
        colors = ["#2ecc71" if r >= 1.0 else "#e74c3c" for r in rois]
        ax1.barh(bet_types, rois, color=colors)
        ax1.axvline(x=1.0, color="black", linestyle="--", alpha=0.5)
        ax1.set_xlabel("回収率")
        ax1.set_title("券種別 回収率")
        for i, r in enumerate(rois):
            ax1.text(r + 0.01, i, f"{r:.2f}", va="center", fontsize=9)

        hit_rates = [breakdown[b]["hit_rate"] for b in bet_types]
        ax2.barh(bet_types, hit_rates, color="#3498db")
        ax2.set_xlabel("的中率")
        ax2.set_title("券種別 的中率")
        for i, hr in enumerate(hit_rates):
            ax2.text(hr + 0.01, i, f"{hr:.1%}", va="center", fontsize=9)

        plt.suptitle(f"バックテスト結果 ({bt.get('total_races', '?')}レース / ROI={bt.get('roi', 0):.2f})")
        plt.tight_layout()
        path = out_dir / "backtest_summary.png"
        fig.savefig(path, dpi=150, bbox_inches="tight")
        plt.close(fig)
        return str(path)

    def _chart_recent_form_heatmap(self, context: PipelineContext, out_dir: Path) -> str | None:
        features = {hf["entry_id"]: hf for hf in context.features.get("horse_features", [])}
        horses = sorted(
            context.evidence.get("horses", []),
            key=lambda h: h.get("integrated_probability", 0),
            reverse=True,
        )

        names, matrix = [], []
        for h in horses:
            f = features.get(h.get("entry_id", ""), {})
            runs = f.get("recent_5_runs", [])
            if runs:
                names.append(h["horse_name"][:8])
                padded = runs[:5] + [np.nan] * (5 - len(runs))
                matrix.append(padded)

        if not matrix:
            return None

        matrix = np.array(matrix, dtype=float)
        fig, ax = plt.subplots(figsize=(8, max(4, len(names) * 0.5)))
        sns.heatmap(
            matrix, annot=True, fmt=".0f", cmap="RdYlGn_r",
            xticklabels=[f"{i}走前" for i in range(1, 6)],
            yticklabels=names,
            ax=ax, linewidths=0.5, vmin=1, vmax=18,
        )
        ax.set_title("近5走着順ヒートマップ")

        plt.tight_layout()
        path = out_dir / "recent_form_heatmap.png"
        fig.savefig(path, dpi=150, bbox_inches="tight")
        plt.close(fig)
        return str(path)
