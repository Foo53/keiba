"""フルデータ学習スクリプト"""
import sys
import time
sys.path.insert(0, "src")

from keiba.data.jrvan.data_source import JrVanDataSource
from keiba.ml.trainer import LightGBMTrainer

ds = JrVanDataSource()
trainer = LightGBMTrainer(ds)

print("フル学習開始: max_races=40000, optuna_trials=50", flush=True)
t0 = time.time()

report = trainer.train(months=12, max_races=40000, optuna_trials=50)

elapsed = time.time() - t0
print(f"\n学習完了: {elapsed:.0f}秒 ({elapsed/60:.1f}分)", flush=True)

print("=" * 60, flush=True)
print(f"train: {report['train_samples']:,} 件 (70%)", flush=True)
print(f"val:   {report['val_samples']:,} 件 (15%)", flush=True)
print(f"test:  {report['test_samples']:,} 件 (15%)", flush=True)
total = report["train_samples"] + report["val_samples"] + report["test_samples"]
print(f"合計:  {total:,} 件", flush=True)
print(flush=True)
print(f"val AUC:  {report['val_auc']:.4f}", flush=True)
print(f"test AUC: {report['test_auc']:.4f}", flush=True)
print(flush=True)
print("上位特徴量:", flush=True)
for f in report["top_features"][:10]:
    print(f"  {f['feature']}: {f['importance']}", flush=True)
print(flush=True)
print("best_params:", flush=True)
for k, v in report["best_params"].items():
    print(f"  {k}: {v}", flush=True)
