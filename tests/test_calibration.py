"""Tests for judge calibration"""
import json

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
    print(f"✅ 相反评分 κ={k:.3f}（应 < 0）")


def test_calibrator_agreement():
    """JudgeCalibrator 计算两位评分者的一致性"""
    calibrator = JudgeCalibrator(threshold=0.7)

    data = [
        {"step_index": 0, "judge_a": 5, "judge_b": 5},
        {"step_index": 1, "judge_a": 4, "judge_b": 4},
        {"step_index": 2, "judge_a": 2, "judge_b": 3},
        {"step_index": 3, "judge_a": 1, "judge_b": 2},
    ]
    calibrator.load_golden(data)
    result = calibrator.run()
    assert "kappa" in result
    assert result["sample_size"] == 4
    print(f"✅ JudgeCalibrator: κ={result['kappa']:.3f}, sample={result['sample_size']}")


def test_calibrator_below_threshold():
    """低一致性触发告警"""
    calibrator = JudgeCalibrator(threshold=0.5)
    data = [
        {"step_index": 0, "judge_a": 5, "judge_b": 1},
        {"step_index": 1, "judge_a": 4, "judge_b": 2},
    ]
    calibrator.load_golden(data)
    result = calibrator.run()
    assert result.get("needs_calibration", False) is True
    print(f"✅ 低一致性触发校准: κ={result['kappa']:.3f}, needs_calibration={result.get('needs_calibration')}")


if __name__ == "__main__":
    test_cohens_kappa_perfect()
    test_cohens_kappa_random()
    test_cohens_kappa_negative()
    test_calibrator_agreement()
    test_calibrator_below_threshold()
    print("\n🎉 All calibration tests passed!")
