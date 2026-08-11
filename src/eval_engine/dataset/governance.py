"""governance — 数据集版本、切分审计与标注治理。"""

from __future__ import annotations

import hashlib
import json
import math
from collections import Counter, defaultdict
from copy import deepcopy
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

_VOLATILE_FIELDS = {
    "id",
    "split",
    "human_score",
    "human_score_r2",
    "judge_score",
    "annotation_status",
    "annotator",
    "adjudicator",
    "adjudication_reason",
    "created_at",
    "updated_at",
}


@dataclass(frozen=True)
class DatasetManifest:
    """数据集版本清单。"""

    name: str
    version: str
    fingerprint: str
    case_count: int
    split_counts: dict[str, int]
    source: str
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _semantic_payload(value: Any) -> Any:
    """提取用于跨 split 去重的语义内容。"""
    if isinstance(value, Mapping):
        return {
            str(key): _semantic_payload(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
            if str(key) not in _VOLATILE_FIELDS
        }
    if isinstance(value, list):
        return [_semantic_payload(item) for item in value]
    return value


def case_fingerprint(case: Mapping[str, Any]) -> str:
    """计算样本语义指纹。"""
    # ID、split 和标签变化不应影响语义重复检测。
    payload = json.dumps(
        _semantic_payload(case),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def dataset_fingerprint(cases: Sequence[Mapping[str, Any]]) -> str:
    """计算与样本顺序无关的数据集指纹。"""
    digests = sorted(case_fingerprint(case) for case in cases)
    payload = json.dumps(digests, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_manifest(
    name: str,
    version: str,
    cases: Sequence[Mapping[str, Any]],
    *,
    source: str = "",
    created_at: str | None = None,
) -> DatasetManifest:
    """构建数据集版本清单。"""
    split_counts = Counter(str(case.get("split", "unspecified")) for case in cases)
    timestamp = created_at or datetime.now(timezone.utc).isoformat()
    return DatasetManifest(
        name=name,
        version=version,
        fingerprint=dataset_fingerprint(cases),
        case_count=len(cases),
        split_counts=dict(sorted(split_counts.items())),
        source=source,
        created_at=timestamp,
    )


def audit_splits(
    cases: Sequence[Mapping[str, Any]],
    *,
    required_splits: Sequence[str] = ("dev", "held_out"),
    min_cases_per_split: int = 1,
) -> dict[str, Any]:
    """检查 ID、切分和语义重复。"""
    counts = Counter(str(case.get("split", "unspecified")) for case in cases)
    missing_ids = [
        index for index, case in enumerate(cases)
        if not str(case.get("id", "")).strip()
    ]
    duplicate_ids = sorted(
        case_id
        for case_id, count in Counter(
            str(case.get("id")) for case in cases if case.get("id")
        ).items()
        if count > 1
    )

    # 按语义指纹而不是 ID 分组，才能发现跨 split 复制。
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for case in cases:
        grouped[case_fingerprint(case)].append(case)

    duplicate_content: list[dict[str, Any]] = []
    split_leakage: list[dict[str, Any]] = []
    for digest, group in grouped.items():
        if len(group) < 2:
            continue
        item = {
            "fingerprint": digest,
            "case_ids": [str(case.get("id", "")) for case in group],
            "splits": sorted({str(case.get("split", "unspecified")) for case in group}),
        }
        duplicate_content.append(item)
        if len(item["splits"]) > 1:
            split_leakage.append(item)

    missing_splits = [
        split for split in required_splits
        if counts.get(split, 0) < min_cases_per_split
    ]
    passed = not (
        missing_ids
        or duplicate_ids
        or split_leakage
        or missing_splits
    )
    return {
        "passed": passed,
        "case_count": len(cases),
        "split_counts": dict(sorted(counts.items())),
        "missing_id_indices": missing_ids,
        "duplicate_ids": duplicate_ids,
        "duplicate_content": duplicate_content,
        "split_leakage": split_leakage,
        "missing_required_splits": missing_splits,
    }


def build_annotation_queue(
    cases: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """生成待补标和待仲裁队列。"""
    queue: list[dict[str, Any]] = []
    for case in cases:
        status = str(case.get("annotation_status", "")).lower()
        score = case.get("human_score")
        second_score = case.get("human_score_r2")
        reasons: list[str] = []
        if score is None:
            reasons.append("missing_primary_rating")
        if status in {"pending_r1_r2", "needs_second_rater"} and second_score is None:
            reasons.append("missing_second_rating")
        # 两位标注员相差 2 分及以上时升级为高优先级仲裁。
        if score is not None and second_score is not None and abs(float(score) - float(second_score)) >= 2:
            reasons.append("rater_disagreement")
        if status in {"rejected", "needs_adjudication"}:
            reasons.append("explicit_adjudication")
        if not reasons:
            continue
        queue.append(
            {
                "case_id": str(case.get("id", "")),
                "split": str(case.get("split", "unspecified")),
                "reasons": reasons,
                "priority": 2 if "rater_disagreement" in reasons else 1,
            }
        )
    return sorted(queue, key=lambda item: (-item["priority"], item["case_id"]))


def annotation_agreement(cases: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """统计双人标注一致性。"""
    pairs = [
        (float(case["human_score"]), float(case["human_score_r2"]))
        for case in cases
        if case.get("human_score") is not None
        and case.get("human_score_r2") is not None
    ]
    if not pairs:
        return {
            "sample_size": 0,
            "cohens_kappa": None,
            "exact_agreement": None,
            "within_one": None,
            "mae": None,
            "rmse": None,
        }
    errors = [second - first for first, second in pairs]
    n = len(errors)
    from eval_engine.judge.calibration import cohens_kappa

    # Kappa 使用离散的 1-5 档；误差指标保留原始分数。
    first_likert = [max(1, min(5, round(first))) for first, _ in pairs]
    second_likert = [max(1, min(5, round(second))) for _, second in pairs]
    return {
        "sample_size": n,
        "cohens_kappa": round(cohens_kappa(first_likert, second_likert), 4),
        "exact_agreement": round(sum(error == 0 for error in errors) / n, 4),
        "within_one": round(sum(abs(error) <= 1 for error in errors) / n, 4),
        "mae": round(sum(abs(error) for error in errors) / n, 4),
        "rmse": round(math.sqrt(sum(error * error for error in errors) / n), 4),
    }


def apply_adjudications(
    cases: Sequence[Mapping[str, Any]],
    adjudications: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """应用仲裁结果，不修改输入数据。"""
    # 仲裁结果写入副本，保留原数据版本供审计。
    result = deepcopy(list(cases))
    known_ids = {str(case.get("id", "")) for case in result}
    unknown = sorted(set(adjudications) - known_ids)
    if unknown:
        raise KeyError(f"unknown adjudication case ids: {unknown}")
    for case in result:
        case_id = str(case.get("id", ""))
        decision = adjudications.get(case_id)
        if not decision:
            continue
        if "human_score" not in decision:
            raise ValueError(f"adjudication {case_id} is missing human_score")
        case["human_score"] = float(decision["human_score"])
        case["annotation_status"] = "adjudicated"
        case["adjudicator"] = str(decision.get("adjudicator", ""))
        case["adjudication_reason"] = str(decision.get("reason", ""))
    return result


def load_jsonl(path: str | Path) -> list[dict[str, Any]]:
    """加载 JSONL 记录。"""
    records: list[dict[str, Any]] = []
    with Path(path).open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"line {line_number} must contain a JSON object")
            records.append(value)
    return records


def write_jsonl(records: Iterable[Mapping[str, Any]], path: str | Path) -> Path:
    """写入 JSONL 记录。"""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(dict(record), ensure_ascii=False, sort_keys=True))
            handle.write("\n")
    return target
