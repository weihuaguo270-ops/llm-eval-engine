"""
人机 / Judge 一致性演示

- demo_inter_judge(): 合成多 Judge 两两 κ（教学用）
- demo_human_judge(): 加载内置校准集，跑 offline 人机表（可复现）
"""

from eval_engine.judge.calibration import (
    JudgeCalibrator,
    cohens_kappa,
    format_agreement_markdown,
)


def demo_inter_judge():
    print("=" * 60)
    print("多 Judge 合成一致性（教学示例，非人标）")
    print("=" * 60)

    judges = {
        "Judge_A": [5, 4, 5, 3, 4, 5, 4, 4, 3, 5],
        "Judge_B": [5, 4, 4, 3, 4, 5, 4, 5, 3, 4],
        "Judge_C": [5, 3, 4, 2, 3, 4, 3, 3, 2, 4],
    }

    print(f"\n{'Judge 对':20s} {'Cohen\\'s κ':12s}")
    print("-" * 40)
    for j1, j2 in [("Judge_A", "Judge_B"), ("Judge_B", "Judge_C"), ("Judge_A", "Judge_C")]:
        k = cohens_kappa(judges[j1], judges[j2])
        print(f"{j1} vs {j2:<10s} {k:>8.3f}")


def demo_human_judge():
    print("\n" + "=" * 60)
    print("人机校准（内置 15 条，offline 冻结 Judge 分）")
    print("=" * 60)
    cal = JudgeCalibrator(threshold=0.6)
    cal.load_golden_file()
    report = cal.run(mode="offline")
    print(format_agreement_markdown(report, title="Offline 人机一致性"))


if __name__ == "__main__":
    demo_inter_judge()
    demo_human_judge()
