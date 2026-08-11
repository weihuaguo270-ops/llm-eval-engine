import json

import pytest

from eval_engine.dataset.governance import (
    annotation_agreement,
    apply_adjudications,
    audit_splits,
    build_annotation_queue,
    build_manifest,
    load_jsonl,
    write_jsonl,
)


def _clean_cases():
    return [
        {
            "id": "dev-1",
            "split": "dev",
            "query": "calculate 1+1",
            "expected": {"answer": "2"},
            "human_score": 5,
            "human_score_r2": 5,
        },
        {
            "id": "held-1",
            "split": "held_out",
            "query": "calculate 2+2",
            "expected": {"answer": "4"},
            "human_score": 4,
            "human_score_r2": 3,
        },
    ]


def test_manifest_and_clean_split_audit_are_reproducible():
    cases = _clean_cases()
    first = build_manifest("agent-eval", "v1", cases, created_at="fixed")
    second = build_manifest("agent-eval", "v1", cases, created_at="fixed")
    assert first.fingerprint == second.fingerprint
    assert first.split_counts == {"dev": 1, "held_out": 1}
    assert audit_splits(cases)["passed"] is True


def test_split_audit_detects_semantic_leakage_across_ids():
    cases = _clean_cases()
    cases.append(
        {
            "id": "held-copy",
            "split": "held_out",
            "query": "calculate 1+1",
            "expected": {"answer": "2"},
        }
    )
    audit = audit_splits(cases)
    assert audit["passed"] is False
    assert len(audit["split_leakage"]) == 1
    assert set(audit["split_leakage"][0]["splits"]) == {"dev", "held_out"}


def test_annotation_queue_agreement_and_adjudication():
    cases = _clean_cases()
    cases[1]["human_score_r2"] = 1
    cases.append(
        {
            "id": "pending",
            "split": "held_out",
            "query": "q",
            "annotation_status": "pending_r1_r2",
            "human_score": None,
        }
    )
    queue = build_annotation_queue(cases)
    assert queue[0]["case_id"] == "held-1"
    assert "rater_disagreement" in queue[0]["reasons"]
    assert annotation_agreement(cases)["sample_size"] == 2

    updated = apply_adjudications(
        cases,
        {
            "held-1": {
                "human_score": 3,
                "adjudicator": "lead",
                "reason": "rubric evidence",
            }
        },
    )
    assert updated[1]["human_score"] == 3.0
    assert updated[1]["annotation_status"] == "adjudicated"
    assert cases[1]["human_score"] == 4

    with pytest.raises(KeyError):
        apply_adjudications(cases, {"unknown": {"human_score": 3}})


def test_jsonl_roundtrip(tmp_path):
    path = write_jsonl(_clean_cases(), tmp_path / "cases.jsonl")
    records = load_jsonl(path)
    assert len(records) == 2
    assert json.loads(path.read_text(encoding="utf-8").splitlines()[0])["id"] == "dev-1"
