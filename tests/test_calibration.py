"""Tests for judge calibration"""
from pathlib import Path

from eval_engine.judge.calibration import (
    JudgeCalibrator,
    agreement_table,
    cohens_kappa,
    default_calibration_path,
    format_agreement_markdown,
    load_golden_file,
)


def test_cohens_kappa_perfect():
    k = cohens_kappa([1, 2, 3, 4, 5], [1, 2, 3, 4, 5])
    assert k == 1.0
    print("✅ 完全一致 κ=1.0")


def test_cohens_kappa_likert_not_range_binned():
    # 若错误地各自归一化分箱，这种分布会算歪；Likert 应对齐到整数分
    human = [1, 1, 5, 5]
    judge = [1, 2, 5, 4]
    k = cohens_kappa(human, judge)
    assert -1.0 <= k <= 1.0
    print(f"✅ Likert κ={k}")


def test_agreement_table_shape():
    table = agreement_table([5, 4, 2], [5, 5, 1], ids=["a", "b", "c"])
    assert table["sample_size"] == 3
    assert table["exact_agree_rate"] == round(1 / 3, 4)
    assert len(table["confusion"]) == 5
    assert len(table["pairs"]) == 3
    print("✅ agreement_table shape OK")


def test_load_builtin_calibration_file():
    path = default_calibration_path()
    assert Path(path).is_file(), path
    items = load_golden_file(path)
    assert len(items) >= 20
    assert all("human_score" in x and "judge_score" in x for x in items)
    assert any(x.get("split") == "held_out" for x in items)
    assert any(x.get("split") == "dev" for x in items)
    print(f"[PASS] builtin calibration items={len(items)}")


def test_calibrator_offline_run():
    cal = JudgeCalibrator(threshold=0.6)
    cal.load_golden_file()
    result = cal.run(mode="offline")
    assert result["sample_size"] >= 20
    assert "kappa" in result
    assert "exact_agree_rate" in result
    assert result["mode"] == "offline"
    assert "bootstrap" in result and "kappa" in result["bootstrap"]
    assert "by_split" in result
    assert "held_out" in result["by_split"]
    assert result["by_split"]["held_out"]["sample_size"] >= 8
    # held_out 门控：协议冻结后的独立栏
    assert result["gate_split"] == "held_out"
    assert result["by_split"]["held_out"]["kappa"] >= 0.6, result["by_split"]["held_out"]
    md = format_agreement_markdown(result)
    assert "held_out" in md
    assert "Cohen" in md or "κ" in md
    print(
        f"[PASS] offline calibrator: n={result['sample_size']} "
        f"κ={result['kappa']} held_outκ={result['by_split']['held_out']['kappa']}"
    )


def test_bootstrap_ci_shape():
    from eval_engine.judge.calibration import bootstrap_ci

    boot = bootstrap_ci([1, 2, 3, 4, 5], [1, 2, 3, 4, 4], n_boot=200, seed=1)
    assert boot["n_boot"] == 200
    assert "low" in boot["kappa"] and "high" in boot["kappa"]
    assert boot["kappa"]["low"] <= boot["kappa"]["high"]
    print("[PASS] bootstrap_ci shape OK")


def test_calibrator_live_fn():
    cal = JudgeCalibrator(threshold=0.6)
    cal.load_golden(
        [
            {"id": "t1", "prompt": "p1", "human_score": 4},
            {"id": "t2", "prompt": "p2", "human_score": 2},
        ]
    )
    result = cal.run(judge_fn=lambda p: {"score": 4 if "p1" in p else 2})
    assert result["sample_size"] == 2
    assert result["kappa"] == 1.0
    assert result["mode"] == "live"
    print("✅ live judge_fn path OK")


def test_needs_calibration_flag():
    cal = JudgeCalibrator(threshold=0.99)
    cal.load_golden(
        [
            {"id": "1", "human_score": 5, "judge_score": 1},
            {"id": "2", "human_score": 5, "judge_score": 1},
            {"id": "3", "human_score": 1, "judge_score": 5},
            {"id": "4", "human_score": 1, "judge_score": 5},
        ]
    )
    result = cal.run(mode="offline")
    assert result["needs_calibration"] is True
    print("✅ needs_calibration triggered")


if __name__ == "__main__":
    test_cohens_kappa_perfect()
    test_cohens_kappa_likert_not_range_binned()
    test_agreement_table_shape()
    test_load_builtin_calibration_file()
    test_calibrator_offline_run()
    test_calibrator_live_fn()
    test_needs_calibration_flag()
    print("\n✅ All calibration tests passed!")
