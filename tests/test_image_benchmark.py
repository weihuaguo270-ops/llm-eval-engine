import json

import pytest

from eval_engine.multimodal.image_benchmark import (
    analyze_blind_ratings,
    analyze_panel_ratings,
    artifact_record,
    build_blind_review,
    build_prompt_dataset,
    build_panel_batches,
    completion_gate,
    compare_model_records,
    dataset_manifest,
)


def _rated_row(entry_id, rater_id, preference="a"):
    scores = {name: 4 for name in ("prompt_adherence", "visual_quality", "preference", "safety")}
    return {"entry_id": entry_id, "case_id": entry_id.removeprefix("blind::"), "prompt": "p",
            "artifact_a": "a.png", "artifact_b": "b.png", "rater_id": rater_id,
            "scores_a": dict(scores), "scores_b": dict(scores), "preference": preference, "notes": ""}


def test_panel_batches_preserve_completed_rows_and_cover_remaining_once():
    rows = []
    for subject in range(1, 21):
        for style in range(1, 6):
            entry_id = f"blind::img-{subject:02d}-{style}"
            rows.append(_rated_row(entry_id, "primary") if len(rows) < 20 else
                        {**_rated_row(entry_id, ""), "scores_a": {}, "scores_b": {}, "preference": ""})
    result = build_panel_batches(rows)
    manifest = result["manifest"]
    assert len(manifest["primary_target_entry_ids"]) == 20
    assert len(manifest["anchor_entry_ids"]) == 5
    targets = [entry_id for batch in manifest["batches"] for entry_id in batch["target_entry_ids"]]
    assert len(targets) == len(set(targets)) == 80
    assert all(len(result["worksheets"][batch["worksheet"]]) == 25 for batch in manifest["batches"])


def test_panel_analysis_accepts_full_rater_and_completed_disjoint_blocks():
    source, full, private_key = [], [], {}
    for subject in range(1, 21):
        for style in range(1, 6):
            entry_id = f"blind::img-{subject:02d}-{style}"
            source.append(_rated_row(entry_id, "primary") if len(source) < 20 else
                          {**_rated_row(entry_id, ""), "scores_a": {}, "scores_b": {}, "preference": ""})
            full.append(_rated_row(entry_id, "full"))
            private_key[entry_id] = {"a": "m1", "b": "m2"}
    result = build_panel_batches(source)
    completed_batches = {}
    for batch in result["manifest"]["batches"]:
        rows = result["worksheets"][batch["worksheet"]]
        for row in rows:
            row.update(_rated_row(row["entry_id"], batch["rater_id"]))
        completed_batches[batch["worksheet"]] = rows
    report = analyze_panel_ratings(result["manifest"], source, full, completed_batches, private_key)
    assert report["covered_entries"] == 100
    assert report["panel_rater_count"] == 5
    assert report["preference_exact_agreement"] == 1.0
    assert report["preference_nominal_alpha"] == 1.0


def test_completion_gate_accepts_completed_panel_protocol(tmp_path):
    artifact = tmp_path / "artifact.png"
    artifact.write_bytes(b"real")
    records = []
    for index in range(100):
        for model in ("m1", "m2"):
            records.append({"case_id": f"case-{index}", "model": model,
                            "split": "held_out" if index >= 70 else "golden",
                            "artifacts": [{"uri": str(artifact), "sha256": "0" * 64}],
                            "automatic_metrics": {"clip_cosine": 0.3},
                            "safety_result": {"passed": True}})
    review = {"review_mode": "full_rater_plus_block_panel", "panel_complete": True,
              "covered_entries": 100, "panel_rater_count": 5}
    gate = completion_gate(records, review)
    assert gate["passed"] is True
    assert gate["evidence_level"] == "offline_real"


def test_prompt_dataset_has_100_cases_and_cluster_isolation():
    cases = build_prompt_dataset()
    manifest = dataset_manifest(cases)
    assert manifest["case_count"] == 100
    assert manifest["split_counts"] == {"dev": 20, "golden": 50, "held_out": 30}
    assert len(manifest["fingerprint_sha256"]) == 64


def test_artifact_and_blind_review_require_real_pairs(tmp_path):
    Image = pytest.importorskip("PIL.Image")
    records = []
    case = build_prompt_dataset()[0]
    for alias in ("a", "b"):
        path = tmp_path / f"{alias}.png"
        Image.new("RGB", (8, 8), alias == "a" and "red" or "blue").save(path)
        record = artifact_record(path, case=case,
                                 model={"id": f"model-{alias}", "revision": "rev", "alias": alias},
                                 seed=1, latency_ms=10, generation_config={"steps": 1})
        records.append(record)
    blind = build_blind_review(records)
    assert len(blind["worksheet"]) == 1
    assert set(blind["private_key"]["blind::img-01-1"]) == {"a", "b"}


def test_dual_review_and_gate_do_not_accept_incomplete_evidence():
    entry = {"entry_id": "e", "rater_id": "r1", "preference": "a",
             "scores_a": {name: 4 for name in ("prompt_adherence", "visual_quality", "preference", "safety")},
             "scores_b": {name: 3 for name in ("prompt_adherence", "visual_quality", "preference", "safety")}}
    second = json.loads(json.dumps(entry))
    second["rater_id"] = "r2"
    report = analyze_blind_ratings([[entry], [second]], {"e": {"a": "m1", "b": "m2"}})
    assert report["rater_count"] == 2
    assert report["leader"] == "m1"
    gate = completion_gate([], report)
    assert gate["passed"] is False
    assert gate["evidence_level"] == "interface"


def test_blind_review_requires_distinct_raters_and_frozen_entries():
    scores = {name: 4 for name in ("prompt_adherence", "visual_quality", "preference", "safety")}
    row = {"entry_id": "e", "rater_id": "same", "preference": "tie",
           "scores_a": scores, "scores_b": scores}
    with pytest.raises(ValueError, match="distinct rater_id"):
        analyze_blind_ratings([[row], [dict(row)]], {"e": {"a": "m1", "b": "m2"}})


def test_paired_comparison_reports_ci_and_slices():
    records = []
    for index in range(5):
        for model, score, latency in (("a", 0.4 + index / 100, 100), ("b", 0.3, 50)):
            records.append({"case_id": f"img-01-{index + 1}", "split": "dev", "model": model,
                            "latency_ms": latency, "automatic_metrics": {"clip_cosine": score},
                            "safety_result": {"passed": True}})
    report = compare_model_records(records, bootstrap_samples=100)
    assert report["paired_cases"] == 5
    assert report["left_wins"] == 5
    assert report["bootstrap_95_ci"][0] > 0
