"""
评分一致性校准演示 — 计算多位 Judge 之间的 Cohen's κ

模拟场景：3 个 Judge 对 10 个步骤评分，计算一致性。
真实场景中应替换为人工标注数据。
"""

from eval_engine.judge.calibration import cohens_kappa, JudgeCalibrator


def demo_agreement():
    print("=" * 60)
    print("Judge 评分一致性校准演示")
    print("=" * 60)

    # 模拟 3 位 Judge 对 10 个步骤的评分（1-5 分）
    judges = {
        "Judge_A": [5, 4, 5, 3, 4, 5, 4, 4, 3, 5],
        "Judge_B": [5, 4, 4, 3, 4, 5, 4, 5, 3, 4],
        "Judge_C": [5, 3, 4, 2, 3, 4, 3, 3, 2, 4],
    }

    print(f"\n{'Judge':12s} {'评分序列':35s} {'均值':8s}")
    print("-" * 55)
    for name, scores in judges.items():
        avg = sum(scores) / len(scores)
        scores_str = " ".join(str(s) for s in scores)
        print(f"{name:12s} {scores_str:35s} {avg:.2f}")

    # 计算两两一致性
    print(f"\n{'Judge 对':20s} {'Cohen\'s κ':12s} {'一致性':10s}")
    print("-" * 45)
    pairs = [("Judge_A", "Judge_B"), ("Judge_B", "Judge_C"), ("Judge_A", "Judge_C")]
    for j1, j2 in pairs:
        k = cohens_kappa(judges[j1], judges[j2])
        level = "高" if k > 0.7 else ("中" if k > 0.4 else "低")
        print(f"{j1} vs {j2:<10s} {k:>8.3f}      {level}")

    # JudgeCalibrator 演示
    print(f"\n--- JudgeCalibrator 校准演示 ---")
    calibrator = JudgeCalibrator(threshold=0.7)

    data = []
    for i in range(10):
        data.append({
            "step_index": i,
            "judge_a": judges["Judge_A"][i],
            "judge_b": judges["Judge_B"][i],
        })
    calibrator.load_golden(data)
    result = calibrator.run()

    print(f"  Cohen's κ: {result['kappa']:.3f}")
    print(f"  样本量: {result['sample_size']}")
    print(f"  需要校准: {'是' if result.get('needs_calibration') else '否'}")

    print(f"\n结论: "
          f"{'Judge A 和 B 一致性较高，可互替' if result['kappa'] > 0.7 "
          f"else 'Judge A 和 B 一致性不足，需统一评分标准'}")


if __name__ == "__main__":
    demo_agreement()
