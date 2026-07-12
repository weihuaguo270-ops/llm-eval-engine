"""Tests for judge calibration"""
from eval_engine.judge.calibration import cohens_kappa, JudgeCalibrator


def test_cohens_kappa_perfect():
    k = cohens_kappa([1, 2, 3], [1, 2, 3])
    assert k == 1.0
    print("✅ 完全一致 κ=1.0")


def test_calibrator_run():
    calibrator = JudgeCalibrator(threshold=0.7)
    data = [{"step_index": 0, "judge_a": 5, "judge_b": 5}]
    calibrator.load_golden(data)
    result = calibrator.run(judge_fn=lambda p: {"score": 4.0})
    assert "kappa" in result
    print(f"✅ JudgeCalibrator: κ={result.get('kappa', 'N/A')}")


if __name__ == "__main__":
    test_cohens_kappa_perfect()
    test_calibrator_run()
    print("\n✅ All calibration tests passed!")
