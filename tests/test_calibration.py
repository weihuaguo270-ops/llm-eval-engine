"""Tests for judge calibration"""
from eval_engine.judge.calibration import cohens_kappa, JudgeCalibrator


def test_cohens_kappa_perfect():
    """完全一致 → κ = 1.0"""
    k = cohens_kappa([1, 2, 3], [1, 2, 3])
    assert k == 1.0
    print("✅ 完全一致 κ=1.0")


def test_cohens_kappa_random():
    """随机一致 → κ ≈ 0.0"""
    k = cohens_kappa([1, 1, 2, 2], [2, 2, 1, 1])
    print(f"✅ 随机评分 κ={k:.3f}（应接近 0）")


def test_cohens_kappa_negative():
    """相反评分 → κ < 0"""
    k = cohens_kappa([5, 5, 1, 1], [1, 1, 5, 5])
    print(f"✅ 相反评分 κ={k:.3f}（应为负）")


def test_calibrator_run():
    """JudgeCalibrator.run() 需要 judge_fn"""
    calibrator = JudgeCalibrator(threshold=0.7)
    data = [
        {"step_index": 0, "judge_a": 5, "judge_b": 5},
        {"step_index": 1, "judge_a": 4, "judge_b": 4},
    ]
    calibrator.load_golden(data)

    def mock_judge(prompt):
        return {"score": 4.0}

    result = calibrator.run(judge_fn=mock_judge)
    assert "kappa" in result
    assert result["sample_size"] == 2
    print(f"✅ JudgeCalibrator: κ={result['kappa']:.3f}")


if __name__ == "__main__":
    test_cohens_kappa_perfect()
    test_cohens_kappa_random()
    test_cohens_kappa_negative()
    test_calibrator_run()
    print("\n🎉 All calibration tests passed!")
