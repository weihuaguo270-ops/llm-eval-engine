"""Rubric 文本的**指纹与漂移检测**。

为什么需要：`SCALE_ANCHORS` 是 `examples/run_calibration.py` 里的一段字符串，
报告原先只记 `rubric_boundary_version=v2.1`（一个人写的名字），**无法证明这次跑的到底是哪个字节的 Rubric**。
本测试把三者锁在一起：

    examples/run_calibration.py 的 SCALE_ANCHORS   ← 权威来源（judge 实际读到的）
    dataset/data/rubric_boundary_line1.json 的 text ← 审计副本
    dataset/data/rubric_boundary_line1.json 的 sha256_16 ← 指纹
    dataset/data/calibration_human_judge.json 的 meta.reproducibility.rubric_boundary_version ← 版本名

**改 Rubric 必须同时**：更新审计副本 + 升版本号；否则本测试失败。
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
AUDIT_FILE = REPO / "src" / "eval_engine" / "dataset" / "data" / "rubric_boundary_line1.json"
DATASET_FILE = REPO / "src" / "eval_engine" / "dataset" / "data" / "calibration_human_judge.json"
EXAMPLE = REPO / "examples" / "run_calibration.py"


def _audit() -> dict:
    return json.loads(AUDIT_FILE.read_text(encoding="utf-8"))


def _sha16(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _load_example_module():
    """加载 `examples/run_calibration.py`（不是包，故用 importlib 按路径加载）。"""
    spec = importlib.util.spec_from_file_location("run_calibration_example", EXAMPLE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # 模块级只做常量与 import，无副作用
    return module


def test_audit_copy_matches_its_recorded_hash():
    audit = _audit()
    assert _sha16(audit["text"]) == audit["sha256_16"]
    assert audit["sha256_full"].startswith(audit["sha256_16"])


def test_judge_prompt_text_has_not_drifted():
    """**漂移检测**：judge 实际读到的文本变了 → 必须同步审计副本并升版本号。"""
    audit = _audit()
    module = _load_example_module()
    actual = _sha16(module.SCALE_ANCHORS)
    assert actual == audit["sha256_16"], (
        "SCALE_ANCHORS 已改动，但审计副本未更新：\n"
        f"  代码 sha256[:16] = {actual}\n"
        f"  副本 sha256[:16] = {audit['sha256_16']}\n"
        "请更新 dataset/data/rubric_boundary_line1.json 并**升 rubric_boundary_version**。"
    )


def test_report_fingerprint_constant_matches_audit():
    """写进报告的指纹常量必须就是审计副本的指纹（否则报告会自称一个错的版本）。"""
    module = _load_example_module()
    assert module.RUBRIC_BOUNDARY_SHA256 == _audit()["sha256_16"]


def test_dataset_meta_boundary_version_matches_audit():
    meta = json.loads(DATASET_FILE.read_text(encoding="utf-8"))["meta"]
    assert meta["reproducibility"]["rubric_boundary_version"] == _audit()["version"]
