"""L2 测量层：有序量表一致性统计的测试。

**校验方式**：用手算值锁定（不是"跑通就算对"），再检验已知性质与配对检验的健全性。

手算样例 A（加权 κ）：scale 1–3，4 对 (1,1) (2,2) (3,3) (1,3)
    O = [[1,0,1],[0,1,0],[0,0,1]]；行和 (2,1,1)，列和 (1,1,2)，n=4
    E = [[0.5,0.5,1.0],[0.25,0.25,0.5],[0.25,0.25,0.5]]
    linear  w=|i-j|/2 → 观测罚 = 1；期望罚 = 2.0        → κ_w = 1 − 1/2   = **0.5**
    quad.   w=(|i-j|/2)² → 观测罚 = 1；期望罚 = 1.625   → κ_w = 1 − 1/1.625 = **0.3846**

手算样例 B（Krippendorff α，nominal）：units [[1,1,1],[1,2,2]]
    o = [[3,1],[1,1]]；n_1=4, n_2=2, n=6；D_o = 2；D_e = 16
    α = 1 − (n−1)·D_o/D_e = 1 − 5·2/16 = **0.375**
"""

from __future__ import annotations

import random

import pytest

from eval_engine.judge.agreement import (
    krippendorff_alpha,
    paired_permutation_kappa,
    weighted_kappa,
)


def test_weighted_kappa_matches_hand_computation():
    a, b = [1, 2, 3, 1], [1, 2, 3, 3]
    assert weighted_kappa(a, b, weights="linear", scale_min=1, scale_max=3) == pytest.approx(0.5)
    assert weighted_kappa(a, b, weights="quadratic", scale_min=1, scale_max=3) == pytest.approx(0.3846, abs=1e-4)


def test_weighted_kappa_perfect_agreement_is_one():
    a = [1, 2, 3, 4, 5, 4]
    assert weighted_kappa(a, a) == pytest.approx(1.0)


def test_weighted_kappa_rejects_unknown_weights():
    with pytest.raises(ValueError):
        weighted_kappa([1, 2], [1, 2], weights="cubic")


def test_krippendorff_alpha_matches_hand_computation():
    assert krippendorff_alpha([[1, 1, 1], [1, 2, 2]], level="nominal") == pytest.approx(0.375)


def test_krippendorff_alpha_perfect_and_degenerate():
    assert krippendorff_alpha([[3, 3], [4, 4], [5, 5]], level="ordinal") == pytest.approx(1.0)
    # 只有一个样本 / 全部同值 → 无法定义分歧，返回 1.0（不是 0，也不是抛错）
    assert krippendorff_alpha([[3, 3]], level="ordinal") == pytest.approx(1.0)


def test_krippendorff_alpha_ordinal_is_kinder_to_adjacent_disagreements():
    """**已知性质**：只有相邻分歧时，有序度量比名义度量更宽容（α_ordinal ≥ α_nominal）。"""
    units = [[1, 1], [2, 3], [2, 2], [3, 3], [4, 4], [4, 5], [5, 5], [1, 2]]
    nominal = krippendorff_alpha(units, level="nominal")
    ordinal = krippendorff_alpha(units, level="ordinal")
    assert ordinal >= nominal


def test_krippendorff_alpha_tolerates_missing_raters():
    """支持每样本标注者数不同：只有 1 位标注者的样本应被忽略，不报错。"""
    units = [[1, 2], [2, None], [3, 3], [4, 4], [5, None], [2, 3]]
    alpha = krippendorff_alpha(units, level="ordinal")
    assert -1.0 <= alpha <= 1.0


def test_paired_permutation_identical_versions_give_p_near_one():
    rng = random.Random(7)
    human = [rng.randint(1, 5) for _ in range(30)]
    judge = [h if rng.random() < 0.7 else min(5, h + 1) for h in human]
    out = paired_permutation_kappa(human, judge, judge, n_perm=300)
    assert out["observed_delta"] == pytest.approx(0.0)
    assert out["p_value"] > 0.9


def test_paired_permutation_detects_a_flipped_version():
    """把判定整体反向（1↔5）→ 与 human 的一致性应显著低于 human 自己。"""
    rng = random.Random(11)
    human = [rng.randint(1, 5) for _ in range(40)]
    flipped = [6 - h for h in human]
    out = paired_permutation_kappa(human, human, flipped, n_perm=500)
    assert out["observed_delta"] < 0
    assert out["p_value"] < 0.05


def test_paired_permutation_requires_paired_lengths():
    with pytest.raises(ValueError):
        paired_permutation_kappa([1, 2, 3], [1, 2], [1, 2, 3])


def test_ordinal_agreement_bundles_all_statistics():
    """成套统计必须齐全，且未加权项与既有 cohens_kappa 一致（不偷偷改历史口径）。"""
    from eval_engine.judge.agreement import ordinal_agreement
    from eval_engine.judge.calibration import cohens_kappa

    human = [5, 4, 3, 2, 1, 5, 5, 3]
    judge = [5, 4, 3, 1, 1, 5, 4, 3]
    out = ordinal_agreement(human, judge)
    assert out["n"] == 8
    assert out["kappa_unweighted"] == cohens_kappa(human, judge)
    # 有序量表：加权 κ 与 α 都不低于未加权（分歧全为相邻档）
    assert out["kappa_linear"] >= out["kappa_unweighted"]
    assert out["alpha_ordinal"] >= out["kappa_unweighted"]
    assert out["exact_rate"] == round(6 / 8, 4)
    assert out["within_one_rate"] == 1.0
    assert "不可混比" in out["_note"]
