"""口径变体选择防护（**配额 = 每批一次 adopt 级对照**）+ 预注册强制的测试。

覆盖 `docs/EVAL_DESIGN.md` §3.3 的语义表全部 7 行：

===========  ==================================================  ==========
行           情形                                                消耗配额
===========  ==================================================  ==========
1            该批尚无基线，本次 adopt → 记为 baseline             否
2            已有基线，指纹 == 基线 → 允许重复                    否
3            已有基线，指纹 ≠ 基线，配额未用 → comparison 臂       **是**
4            配额已用，指纹 == comparison 臂 → 允许复现           否
5            配额已用，第三个不同 adopt 指纹 → **拒绝**            —
6            ``purpose=probe`` → 允许                             否
7            ``allow_selection=1`` → 允许但标 selection_use       否
===========  ==================================================  ==========

外加 §B.3 的**预注册强制**：缺文件 / 字段不全 / 指纹不匹配 / 冻结时间在未来 → 拒绝；
冻结后**被改动或删除** → 复现时拒绝（账本记了 sha256）。

最后是两个**端到端**用例：起一个本地 HTTP 桩当 Judge，验证 CLI 在
**调用 Judge LLM 之前**就已经拒绝（桩收到 0 次请求）/ 放行（桩收到请求）。
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from eval_engine.judge import variant_ledger as vl

BATCH = "calibration_human_judge@v5/held_out"
BASE_FP = "base000000000000"
CMP_FP = "cmp0000000000000"

REPO = Path(__file__).resolve().parents[1]
EXAMPLE = REPO / "examples" / "run_calibration.py"
DATASET_FILE = REPO / "src" / "eval_engine" / "dataset" / "data" / "calibration_human_judge.json"


@pytest.fixture()
def ledger(tmp_path, monkeypatch):
    """把账本指向 tmp，并确保环境变量不把路径又拽回仓库。"""
    monkeypatch.delenv("JUDGE_VARIANT_LEDGER", raising=False)
    path = tmp_path / "ledger.json"
    monkeypatch.setattr(vl, "LEDGER_PATH", path)
    return path


def _saved(ledger: Path) -> dict:
    return json.loads(ledger.read_text(encoding="utf-8"))


def _entry(ledger: Path) -> dict:
    return _saved(ledger)["batches"][BATCH]


def _prereg(tmp_path: Path, *, batch: str = BATCH, variant: str = CMP_FP,
            baseline: str = BASE_FP, frozen_at: str = "2020-01-01T00:00:00", **overrides) -> Path:
    """写一份合规预注册（可用 overrides 破坏某个字段）。"""
    payload = {
        "batch": batch,
        "baseline_sha16": baseline,
        "variant_sha16": variant,
        "hypothesis": "把「工具相关但非首选」写成可判定的两档，预期减少跨带分歧",
        "predicted_direction": "决策级一致率↑",
        "decision_rule": {
            "primary": "决策级一致率 不低于 baseline（差值 ≥ 0）",
            "secondary": ["线性加权 κ 不低于 baseline", "α(ordinal) 不低于 baseline − 0.01"],
            "offtarget": "与改动无关的题，判分变动 ≤ 3 条；且变差条数 ≤ 变好条数",
            "significance": "报配对置换 p；p > 0.05 时结论只能写「无显著差异」",
        },
        "negative_result_action": "保留 v2.1，写一条负结果记录，不在本批上再试第二个变体",
        "frozen_at": frozen_at,
    }
    payload.update(overrides)
    path = tmp_path / f"prereg_{variant}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


# ──────────────────────────────────────────────
# §3.3 语义表：7 行
# ──────────────────────────────────────────────


def test_row1_first_adopt_is_baseline_and_does_not_consume_quota(ledger):
    d = vl.check_and_record(BATCH, BASE_FP)
    assert d["allowed"] and d["role"] == vl.ROLE_BASELINE
    assert d["consumes_quota"] is False and d["selection"] is False
    entry = _entry(ledger)
    assert entry["baseline"] == BASE_FP
    assert entry["comparison"] is None and entry["quota_used"] is False


def test_row2_repeating_the_baseline_is_allowed_and_free(ledger):
    vl.check_and_record(BATCH, BASE_FP)
    d = vl.check_and_record(BATCH, BASE_FP)
    assert d["allowed"] and d["role"] == vl.ROLE_BASELINE and d["consumes_quota"] is False
    entry = _entry(ledger)
    assert entry["quota_used"] is False
    assert entry["arms"][BASE_FP]["runs"] == 2


def test_row3_second_distinct_fingerprint_with_prereg_is_the_comparison_arm(ledger, tmp_path):
    vl.check_and_record(BATCH, BASE_FP)
    prereg = _prereg(tmp_path)
    d = vl.check_and_record(BATCH, CMP_FP, prereg_file=prereg)
    assert d["allowed"] and d["role"] == vl.ROLE_COMPARISON
    assert d["consumes_quota"] is True and d["selection"] is False
    entry = _entry(ledger)
    assert entry["comparison"] == CMP_FP and entry["quota_used"] is True
    # 账本记录预注册的 sha256（冻结后被动过就能查出来）
    recorded = entry["arms"][CMP_FP]["prereg"]
    assert recorded["sha256"] == hashlib.sha256(prereg.read_bytes()).hexdigest()
    assert recorded["frozen_at"] == "2020-01-01T00:00:00"


def test_row4_repeating_the_comparison_arm_is_allowed_and_free(ledger, tmp_path):
    vl.check_and_record(BATCH, BASE_FP)
    prereg = _prereg(tmp_path)
    vl.check_and_record(BATCH, CMP_FP, prereg_file=prereg)
    d = vl.check_and_record(BATCH, CMP_FP, prereg_file=prereg)
    assert d["allowed"] and d["role"] == vl.ROLE_COMPARISON and d["consumes_quota"] is False
    assert _entry(ledger)["arms"][CMP_FP]["runs"] == 2


def test_row5_third_distinct_adopt_fingerprint_is_refused(ledger, tmp_path):
    vl.check_and_record(BATCH, BASE_FP)
    vl.check_and_record(BATCH, CMP_FP, prereg_file=_prereg(tmp_path))
    d = vl.evaluate(BATCH, "cccc000000000000")
    assert d["allowed"] is False
    assert "配额已用尽" in d["reason"]
    assert "cccc000000000000" not in _entry(ledger)["arms"]


def test_row5_refusal_happens_even_if_a_prereg_exists(ledger, tmp_path):
    """配额用尽后，再补一份合规预注册也不放行——预注册不是配额的替代品。"""
    vl.check_and_record(BATCH, BASE_FP)
    vl.check_and_record(BATCH, CMP_FP, prereg_file=_prereg(tmp_path))
    late = _prereg(tmp_path, variant="dddd000000000000")
    d = vl.evaluate(BATCH, "dddd000000000000", prereg_file=late)
    assert d["allowed"] is False and "配额已用尽" in d["reason"]


def test_row6_probe_is_allowed_and_does_not_consume_quota(ledger):
    vl.check_and_record(BATCH, BASE_FP)
    d = vl.check_and_record(BATCH, "broken0000000000", purpose="probe")
    assert d["allowed"] and d["role"] == vl.ROLE_PROBE
    assert d["selection"] is False and d["consumes_quota"] is False
    entry = _entry(ledger)
    assert entry["quota_used"] is False and entry["comparison"] is None
    assert entry["baseline"] == BASE_FP


def test_row6_probe_first_does_not_become_the_baseline(ledger):
    """先跑 probe 不能占掉基线位——否则真正的基线再也建不起来。"""
    d = vl.check_and_record(BATCH, "broken0000000000", purpose="probe")
    assert d["role"] == vl.ROLE_PROBE
    assert _entry(ledger)["baseline"] is None
    later = vl.check_and_record(BATCH, BASE_FP)
    assert later["role"] == vl.ROLE_BASELINE


def test_row7_allow_selection_on_third_fingerprint_marks_but_keeps_arms_intact(ledger, tmp_path):
    vl.check_and_record(BATCH, BASE_FP)
    vl.check_and_record(BATCH, CMP_FP, prereg_file=_prereg(tmp_path))
    d = vl.check_and_record(BATCH, "cccc000000000000", allow_selection=True)
    assert d["allowed"] and d["selection"] is True and d["role"] == vl.ROLE_SELECTION
    assert d["consumes_quota"] is False
    entry = _entry(ledger)
    assert entry["arms"]["cccc000000000000"]["selection_use"] is True
    # 官方那一次对照不受影响
    assert entry["comparison"] == CMP_FP and entry["quota_used"] is True


def test_row7_allow_selection_can_bypass_missing_prereg_without_spending_quota(ledger):
    vl.check_and_record(BATCH, BASE_FP)
    d = vl.check_and_record(BATCH, CMP_FP, allow_selection=True)
    assert d["allowed"] and d["selection"] is True and d["role"] == vl.ROLE_SELECTION
    entry = _entry(ledger)
    assert entry["quota_used"] is False and entry["comparison"] is None


def test_row7_selection_fingerprint_stays_barred_on_repeat(ledger):
    vl.check_and_record(BATCH, BASE_FP)
    vl.check_and_record(BATCH, CMP_FP, allow_selection=True)
    again = vl.evaluate(BATCH, CMP_FP)
    assert again["allowed"] is True and again["selection"] is True
    assert "不得用于采纳" in again["reason"]


def test_different_batch_is_independent(ledger):
    vl.check_and_record(BATCH, BASE_FP)
    d = vl.evaluate("calibration_human_judge@v5/dev", "bbbb")
    assert d["allowed"] and d["role"] == vl.ROLE_BASELINE


# ──────────────────────────────────────────────
# §B.3 预注册强制
# ──────────────────────────────────────────────


def test_comparison_without_prereg_is_refused_and_does_not_spend_quota(ledger):
    vl.check_and_record(BATCH, BASE_FP)
    d = vl.evaluate(BATCH, CMP_FP)
    assert d["allowed"] is False
    assert "必须先写预注册" in d["reason"]
    entry = _entry(ledger)
    assert entry["quota_used"] is False and entry["comparison"] is None


def test_prereg_default_path_is_tracked_package_data_not_reports():
    """预注册必须落在**入库跟踪**的路径下，否则外部无法验证它早于那次运行。"""
    package = Path(vl.__file__).resolve().parents[1]
    assert vl.PREREG_DIR == package / "dataset" / "data" / "prereg"
    assert "reports" not in vl.PREREG_DIR.parts


def test_prereg_path_slug_has_no_separators():
    """批次标识里有 `/`，不能让它变成子目录。"""
    path = vl.prereg_path(BATCH, "0a780f5ad7916440")
    assert path.parent == vl.PREREG_DIR
    assert "/" not in path.name and "\\" not in path.name
    assert path.name == "calibration_human_judge@v5_held_out_0a780f5ad7916440.json"


@pytest.mark.parametrize(
    "broken, needle",
    [
        ({"variant_sha16": "someoneelse000000"}, "variant_sha16"),
        ({"batch": "other_dataset@v5/held_out"}, "batch"),
        ({"baseline_sha16": "notthebaseline000"}, "baseline_sha16"),
        ({"hypothesis": ""}, "hypothesis"),
        ({"predicted_direction": "   "}, "predicted_direction"),
        ({"negative_result_action": ""}, "negative_result_action"),
        ({"decision_rule": {"secondary": ["x"]}}, "decision_rule.primary"),
        ({"decision_rule": "not-a-dict"}, "decision_rule.primary"),
        ({"frozen_at": "not-a-date"}, "frozen_at"),
        ({"frozen_at": "2099-01-01T00:00:00"}, "在未来"),
        ({"frozen_at": ""}, "frozen_at"),
    ],
)
def test_bad_prereg_is_refused(ledger, tmp_path, broken, needle):
    vl.check_and_record(BATCH, BASE_FP)
    prereg = _prereg(tmp_path, **broken)
    d = vl.evaluate(BATCH, CMP_FP, prereg_file=prereg)
    assert d["allowed"] is False, f"不应放行：{broken}"
    assert needle in d["reason"]
    assert _entry(ledger)["quota_used"] is False


def test_prereg_that_is_not_json_is_refused(ledger, tmp_path):
    vl.check_and_record(BATCH, BASE_FP)
    bad = tmp_path / "broken.json"
    bad.write_text("{not json", encoding="utf-8")
    d = vl.evaluate(BATCH, CMP_FP, prereg_file=bad)
    assert d["allowed"] is False and "不是合法 JSON" in d["reason"]


def test_prereg_missing_entirely_is_refused(ledger, tmp_path):
    vl.check_and_record(BATCH, BASE_FP)
    d = vl.evaluate(BATCH, CMP_FP, prereg_file=tmp_path / "nope.json")
    assert d["allowed"] is False and "未找到预注册文件" in d["reason"]


def test_prereg_tampered_after_freeze_refuses_replay(ledger, tmp_path):
    """冻结后改了预注册 → 同一个对照臂再跑时必须拒绝（账本记着 sha256）。"""
    vl.check_and_record(BATCH, BASE_FP)
    prereg = _prereg(tmp_path)
    first = vl.check_and_record(BATCH, CMP_FP, prereg_file=prereg)
    assert first["allowed"] is True

    # 事后偷偷把采纳判据改松
    payload = json.loads(prereg.read_text(encoding="utf-8"))
    payload["decision_rule"]["primary"] = "只要不崩就算通过"
    prereg.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    replay = vl.evaluate(BATCH, CMP_FP, prereg_file=prereg)
    assert replay["allowed"] is False
    assert "已被改动" in replay["reason"]


def test_prereg_deleted_after_freeze_refuses_replay(ledger, tmp_path):
    vl.check_and_record(BATCH, BASE_FP)
    prereg = _prereg(tmp_path)
    vl.check_and_record(BATCH, CMP_FP, prereg_file=prereg)
    prereg.unlink()
    replay = vl.evaluate(BATCH, CMP_FP, prereg_file=prereg)
    assert replay["allowed"] is False and "不可用" in replay["reason"]


def test_unchanged_prereg_still_replays(ledger, tmp_path):
    vl.check_and_record(BATCH, BASE_FP)
    prereg = _prereg(tmp_path)
    vl.check_and_record(BATCH, CMP_FP, prereg_file=prereg)
    replay = vl.evaluate(BATCH, CMP_FP, prereg_file=prereg)
    assert replay["allowed"] is True and replay["role"] == vl.ROLE_COMPARISON


# ──────────────────────────────────────────────
# 旧 schema 迁移 + 批次标识
# ──────────────────────────────────────────────


def test_legacy_fingerprints_ledger_migrates_conservatively(ledger):
    """旧账本没有角色概念：按登记顺序当作「基线 + 一次对照」= 视配额已用。"""
    ledger.write_text(
        json.dumps(
            {
                "batches": {
                    BATCH: {
                        "fingerprints": {
                            "aaaa": {"runs": 1, "purposes": ["adopt"]},
                            "bbbb": {"runs": 2, "purposes": ["adopt"]},
                        }
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    d = vl.evaluate(BATCH, "cccc")
    assert d["allowed"] is False and "配额已用尽" in d["reason"]
    baseline_repeat = vl.evaluate(BATCH, "aaaa")
    assert baseline_repeat["allowed"] and baseline_repeat["role"] == vl.ROLE_BASELINE


def test_legacy_probe_only_entry_does_not_block_the_baseline(ledger):
    ledger.write_text(
        json.dumps({"batches": {BATCH: {"fingerprints": {"broken": {"runs": 1, "purposes": ["probe"]}}}}}),
        encoding="utf-8",
    )
    d = vl.evaluate(BATCH, "aaaa")
    assert d["allowed"] and d["role"] == vl.ROLE_BASELINE


def test_batch_key_shape():
    assert vl.batch_key("calibration_human_judge", 5, "held_out") == "calibration_human_judge@v5/held_out"
    assert vl.batch_key(None, None, None) == "unknown@v?/all"


# ──────────────────────────────────────────────
# 端到端：CLI 在调用 Judge LLM **之前** 拒绝 / 放行
# ──────────────────────────────────────────────


def _example_fingerprint() -> str:
    """CLI 实际会用的指纹（`examples/run_calibration.py` 的 SCALE_ANCHORS sha256[:16]）。"""
    spec = importlib.util.spec_from_file_location("run_calibration_e2e_probe", EXAMPLE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.RUBRIC_BOUNDARY_SHA256


def _real_batch() -> str:
    meta = json.loads(DATASET_FILE.read_text(encoding="utf-8"))["meta"]
    repro = meta.get("reproducibility") or {}
    return vl.batch_key(repro.get("dataset_id") or meta.get("title"), meta.get("version"), "held_out")


def _serve_score3():
    """本地 Judge 桩：返回合法 JSON（全 3 分），并**计数**被调用了多少次。"""
    hits = {"n": 0}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802 - http.server 的接口名
            hits["n"] += 1
            length = int(self.headers.get("Content-Length") or 0)
            self.rfile.read(length)
            inner = json.dumps(
                {"score": 3, "rubrics": [{"dimension": "overall", "score": 3, "reason": "e2e stub"}]}
            )
            body = json.dumps(
                {"choices": [{"message": {"content": inner}}], "usage": {}}
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):  # 静音
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, hits


def _run_cli(ledger_path: Path, base_url: str, prereg: Path | None = None):
    env = dict(os.environ)
    env.update(
        {
            "JUDGE_BASE_URL": base_url,
            "JUDGE_API_KEY": "e2e-dummy-key",
            "JUDGE_MODEL": "e2e-stub-model",
            "JUDGE_VARIANT_PURPOSE": "adopt",
            "JUDGE_VARIANT_LEDGER": str(ledger_path),
            "PYTHONIOENCODING": "utf-8",
        }
    )
    env.pop("JUDGE_ALLOW_SELECTION", None)
    cmd = [sys.executable, str(EXAMPLE), "--live", "--split", "held_out"]
    if prereg is not None:
        cmd += ["--prereg", str(prereg)]
    return subprocess.run(
        cmd,
        cwd=str(REPO),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
    )


def test_e2e_cli_refuses_exhausted_quota_before_calling_judge(tmp_path, monkeypatch):
    """★ 核心端到端断言：拒绝发生在**调用 Judge LLM 之前**（桩收到 0 次请求）。"""
    batch = _real_batch()
    ledger_path = tmp_path / "ledger.json"
    monkeypatch.setenv("JUDGE_VARIANT_LEDGER", str(ledger_path))
    # 预置：基线 + 一个不同的对照臂 → 配额已用尽，真实指纹就成了第三个
    vl.record(batch, BASE_FP, role=vl.ROLE_BASELINE)
    vl.record(
        batch,
        CMP_FP,
        role=vl.ROLE_COMPARISON,
        prereg={"path": "x", "sha256": "y", "frozen_at": "z"},
    )

    server, hits = _serve_score3()
    try:
        proc = _run_cli(ledger_path, f"http://127.0.0.1:{server.server_address[1]}")
    finally:
        server.shutdown()

    assert proc.returncode == 2, f"stdout={proc.stdout}\nstderr={proc.stderr}"
    assert "拒绝运行" in proc.stdout
    assert "配额已用尽" in proc.stdout
    assert hits["n"] == 0, "Judge LLM 不该被调用一次"
    # 拒绝不得改动账本里的配额状态
    entry = json.loads(ledger_path.read_text(encoding="utf-8"))["batches"][batch]
    assert entry["quota_used"] is True and entry["comparison"] == CMP_FP


def test_e2e_cli_allows_preregistered_comparison_and_then_calls_judge(tmp_path, monkeypatch):
    """放行侧：合规预注册 → 通过防护 → **确实调用了** Judge（桩收到请求）。"""
    batch = _real_batch()
    fingerprint = _example_fingerprint()
    ledger_path = tmp_path / "ledger.json"
    monkeypatch.setenv("JUDGE_VARIANT_LEDGER", str(ledger_path))
    vl.record(batch, BASE_FP, role=vl.ROLE_BASELINE)
    prereg = _prereg(tmp_path, batch=batch, variant=fingerprint, baseline=BASE_FP)

    server, hits = _serve_score3()
    try:
        proc = _run_cli(ledger_path, f"http://127.0.0.1:{server.server_address[1]}", prereg=prereg)
    finally:
        server.shutdown()

    assert "拒绝运行" not in proc.stdout, proc.stdout
    assert f"role={vl.ROLE_COMPARISON}" in proc.stdout
    assert hits["n"] > 0, "放行后应当真的调用 Judge LLM"

    entry = json.loads(ledger_path.read_text(encoding="utf-8"))["batches"][batch]
    assert entry["quota_used"] is True and entry["comparison"] == fingerprint
    assert entry["arms"][fingerprint]["prereg"]["sha256"] == hashlib.sha256(
        prereg.read_bytes()
    ).hexdigest()

    # 桩全返回 3 分 → CLI 判定疑似 fallback，在**写快照之前**中止（不污染 docs/ 与 reports/）
    assert proc.returncode == 3
    assert "疑似 Judge fallback" in (proc.stdout + proc.stderr)
