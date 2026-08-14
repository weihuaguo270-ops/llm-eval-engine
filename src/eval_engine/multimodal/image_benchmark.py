"""Contracts and analysis for a reproducible two-model image benchmark."""

from __future__ import annotations

import hashlib
import json
import math
import random
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping, Sequence

REQUIRED_DIMENSIONS = ("prompt_adherence", "visual_quality", "preference", "safety")


def build_prompt_dataset() -> list[dict[str, Any]]:
    """Return 100 fixed prompts with source clusters isolated across splits."""
    subjects = (
        ("product", "a red ceramic travel mug on a white studio table"),
        ("product", "wireless headphones beside their charging case"),
        ("product", "a transparent mechanical keyboard on a workbench"),
        ("product", "a green hiking backpack with visible compartments"),
        ("food", "a bowl of tomato noodles with basil and chopsticks"),
        ("food", "three macarons in yellow blue and pink"),
        ("food", "a cafe breakfast with toast eggs and black coffee"),
        ("food", "a sliced dragon fruit on a dark plate"),
        ("scene", "a rainy pedestrian crossing in Shanghai at night"),
        ("scene", "a quiet library reading room in morning sunlight"),
        ("scene", "a mountain railway crossing a stone bridge"),
        ("scene", "a small fishing harbor before sunrise"),
        ("illustration", "an astronaut repairing a greenhouse on Mars"),
        ("illustration", "a friendly service robot organizing parcels"),
        ("illustration", "a paper-cut illustration of a city metro map"),
        ("illustration", "a watercolor fox reading under a street lamp"),
        ("spatial", "a blue cube left of a red sphere on a gray floor"),
        ("spatial", "five yellow pencils arranged around one black notebook"),
        ("spatial", "a bicycle behind a bench and in front of a brick wall"),
        ("spatial", "two glass bottles with the taller bottle on the right"),
    )
    styles = (
        ("photo", "realistic photograph, natural lighting, no text"),
        ("studio", "commercial studio photograph, centered composition, no logo"),
        ("cinematic", "cinematic wide shot, realistic materials, no watermark"),
        ("illustrated", "clean editorial illustration, balanced colors, no text"),
        ("detail", "close-up view, sharp subject details, uncluttered background"),
    )
    cases = []
    for subject_index, (cluster, subject) in enumerate(subjects):
        split = "dev" if subject_index < 4 else "golden" if subject_index < 14 else "held_out"
        for style_index, (style, suffix) in enumerate(styles):
            cases.append({
                "id": f"img-{subject_index + 1:02d}-{style_index + 1}",
                "split": split, "source_cluster": f"{cluster}-{subject_index + 1:02d}",
                "task_type": "text_to_image", "category": cluster, "style": style,
                "prompt": f"{subject}, {suffix}", "references": [],
                "safety_expected": "benign", "license": "CC0-1.0",
            })
    return cases


def dataset_manifest(cases: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Validate split isolation and return a stable dataset fingerprint."""
    ids = [str(case.get("id", "")) for case in cases]
    if len(cases) != 100 or len(set(ids)) != len(ids) or not all(ids):
        raise ValueError("image benchmark requires exactly 100 unique cases")
    cluster_splits: dict[str, set[str]] = defaultdict(set)
    for case in cases:
        cluster_splits[str(case["source_cluster"])].add(str(case["split"]))
    leaked = sorted(cluster for cluster, splits in cluster_splits.items() if len(splits) > 1)
    if leaked:
        raise ValueError(f"source clusters cross splits: {leaked}")
    canonical = json.dumps(list(cases), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return {"schema_version": "image-prompt-dataset/v1", "case_count": len(cases),
            "split_counts": dict(sorted(Counter(str(case["split"]) for case in cases).items())),
            "category_counts": dict(sorted(Counter(str(case["category"]) for case in cases).items())),
            "fingerprint_sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
            "source": "project-authored prompts", "license": "CC0-1.0"}


def artifact_record(path: str | Path, *, case: Mapping[str, Any], model: Mapping[str, Any],
                    seed: int, latency_ms: float, generation_config: Mapping[str, Any]) -> dict[str, Any]:
    """Build a verifiable artifact record from an actual image file."""
    target = Path(path)
    if not target.is_file() or target.stat().st_size == 0:
        raise ValueError(f"missing generated artifact: {target}")
    from PIL import Image

    with Image.open(target) as image:
        width, height, image_format = image.width, image.height, image.format
        image.verify()
    return {"case_id": str(case["id"]), "split": str(case["split"]),
            "task_type": str(case["task_type"]), "prompt": str(case["prompt"]),
            "model": str(model["id"]), "model_version": str(model["revision"]),
            "seed": int(seed), "generation_config": dict(generation_config),
            "artifacts": [{"id": f"{case['id']}::{model['alias']}", "media_type": "image",
                           "uri": target.resolve().as_posix(), "mime_type": f"image/{image_format.lower()}",
                           "sha256": _sha256_file(target), "width": width, "height": height,
                           "bytes": target.stat().st_size}],
            "latency_ms": round(float(latency_ms), 3), "cost": 0.0,
            "cost_basis": "local GPU; API cost is zero, hardware/electricity excluded"}


def build_blind_review(records: Sequence[Mapping[str, Any]], seed: int = 20260813) -> dict[str, Any]:
    """Randomize paired model outputs while keeping the key separate from the worksheet."""
    by_case: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for record in records:
        by_case[str(record["case_id"])].append(record)
    rng, worksheet, key = random.Random(seed), [], {}
    for case_id, pair in sorted(by_case.items()):
        if len(pair) != 2:
            raise ValueError(f"case {case_id} requires exactly two model outputs")
        shuffled = list(pair)
        rng.shuffle(shuffled)
        entry_id = f"blind::{case_id}"
        worksheet.append({"entry_id": entry_id, "case_id": case_id,
                          "prompt": pair[0]["prompt"],
                          "artifact_a": shuffled[0]["artifacts"][0]["uri"],
                          "artifact_b": shuffled[1]["artifacts"][0]["uri"],
                          "rater_id": "", "scores_a": {}, "scores_b": {},
                          "preference": "", "notes": ""})
        key[entry_id] = {"a": shuffled[0]["model"], "b": shuffled[1]["model"]}
    return {"worksheet": worksheet, "private_key": key, "random_seed": seed,
            "dimensions": list(REQUIRED_DIMENSIONS)}


def analyze_blind_ratings(worksheets: Sequence[Sequence[Mapping[str, Any]]],
                          private_key: Mapping[str, Mapping[str, str]]) -> dict[str, Any]:
    """Validate independent ratings and summarize agreement and paired preferences."""
    if len(worksheets) < 2:
        raise ValueError("two independent rater worksheets are required")
    by_rater, worksheet_rater_ids = [], []
    for worksheet in worksheets:
        rows = {str(row["entry_id"]): row for row in worksheet}
        rater_ids = {str(row.get("rater_id", "")).strip() for row in rows.values()}
        if len(rater_ids) != 1 or not next(iter(rater_ids), ""):
            raise ValueError("each worksheet requires one non-empty rater_id")
        worksheet_rater_ids.append(next(iter(rater_ids)))
        for entry_id, row in rows.items():
            if entry_id not in private_key or row.get("preference") not in {"a", "b", "tie"}:
                raise ValueError(f"incomplete blind rating: {entry_id}")
            for side in ("scores_a", "scores_b"):
                scores = row.get(side) or {}
                if set(scores) != set(REQUIRED_DIMENSIONS) or any(not 1 <= float(v) <= 5 for v in scores.values()):
                    raise ValueError(f"invalid rubric scores: {entry_id}.{side}")
        by_rater.append(rows)
    if len(set(worksheet_rater_ids)) != len(worksheet_rater_ids):
        raise ValueError("blind review requires distinct rater_id values")
    expected_entries = set(private_key)
    if any(set(rows) != expected_entries for rows in by_rater):
        raise ValueError("each rater must complete the same frozen entry set")
    shared = sorted(set.intersection(*(set(rows) for rows in by_rater)))
    if not shared:
        raise ValueError("raters have no shared entries")
    agreements = sum(by_rater[0][item]["preference"] == by_rater[1][item]["preference"] for item in shared)
    preference_counts: Counter[str] = Counter()
    for entry_id in shared:
        for rows in by_rater:
            choice = rows[entry_id]["preference"]
            preference_counts["tie" if choice == "tie" else private_key[entry_id][choice]] += 1
    non_ties = sum(count for name, count in preference_counts.items() if name != "tie")
    model_counts = {name: count for name, count in preference_counts.items() if name != "tie"}
    leader = max(model_counts, key=model_counts.get) if model_counts else None
    wins = model_counts.get(leader, 0) if leader else 0
    return {"schema_version": "blind-image-review/v1", "rater_count": len(worksheets),
            "rater_ids": worksheet_rater_ids,
            "shared_entries": len(shared), "preference_exact_agreement": round(agreements / len(shared), 4),
            "preference_counts": dict(preference_counts), "leader": leader,
            "leader_win_rate": round(wins / non_ties, 4) if non_ties else None,
            "leader_binomial_p_value": _two_sided_binomial(wins, non_ties) if non_ties else None,
            "claim_boundary": "Human preference applies only to this frozen prompt set and model configuration."}


def build_panel_batches(worksheet: Sequence[Mapping[str, Any]], *, volunteer_count: int = 4,
                        anchor_count: int = 5) -> dict[str, Any]:
    """Freeze completed ratings and split the remaining entries into balanced volunteer blocks."""
    rows = {str(row["entry_id"]): row for row in worksheet}
    if len(rows) != len(worksheet) or not rows:
        raise ValueError("panel source worksheet requires unique entries")
    completed = sorted(entry_id for entry_id, row in rows.items() if _rating_complete(row))
    remaining = sorted(set(rows) - set(completed), key=_entry_sort_key)
    if len(completed) < anchor_count:
        raise ValueError("completed panel ratings must cover all calibration anchors")
    if volunteer_count < 1 or len(remaining) % volunteer_count:
        raise ValueError("remaining entries must divide evenly across volunteers")
    anchor_indexes = [index * len(completed) // anchor_count for index in range(anchor_count)]
    anchors = [completed[index] for index in anchor_indexes]
    assignments = [[] for _ in range(volunteer_count)]
    for index, entry_id in enumerate(sorted(remaining, key=_entry_sort_key)):
        assignments[index % volunteer_count].append(entry_id)
    batches, batch_rows = [], {}
    for index, target_ids in enumerate(assignments, start=1):
        batch_id = f"volunteer_{index}"
        filename = f"panel/{batch_id}.json"
        entries = [_blank_panel_row(rows[entry_id], "target") for entry_id in target_ids]
        entries.extend(_blank_panel_row(rows[entry_id], "anchor") for entry_id in anchors)
        entries.sort(key=lambda row: _entry_sort_key(str(row["entry_id"])))
        batches.append({"batch_id": batch_id, "worksheet": filename,
                        "rater_id": f"image-v2-panel-{index + 1}",
                        "target_entry_ids": target_ids, "anchor_entry_ids": anchors})
        batch_rows[filename] = entries
    primary_ids = {str(rows[entry_id].get("rater_id", "")).strip() for entry_id in completed}
    if len(primary_ids) != 1 or not next(iter(primary_ids), ""):
        raise ValueError("completed source entries require one rater_id")
    manifest = {"schema_version": "blind-image-panel-assignment/v1",
                "review_mode": "full_rater_plus_block_panel",
                "expected_entries": len(rows), "full_rater_worksheet": "rater_2.json",
                "primary_panel_worksheet": "rater_1.json",
                "primary_panel_rater_id": next(iter(primary_ids)),
                "primary_target_entry_ids": completed, "anchor_entry_ids": anchors,
                "volunteer_count": volunteer_count, "batches": batches,
                "claim_boundary": "One full-set rater plus disjoint volunteer blocks; not two full-set raters."}
    return {"manifest": manifest, "worksheets": batch_rows}


def panel_review_progress(manifest: Mapping[str, Any], primary_worksheet: Sequence[Mapping[str, Any]],
                          full_worksheet: Sequence[Mapping[str, Any]],
                          batch_worksheets: Mapping[str, Sequence[Mapping[str, Any]]]) -> dict[str, Any]:
    """Report target and calibration progress without treating partial ratings as evidence."""
    primary = {str(row["entry_id"]): row for row in primary_worksheet}
    full = {str(row["entry_id"]): row for row in full_worksheet}
    primary_ids = set(map(str, manifest.get("primary_target_entry_ids", [])))
    target_done = sum(_rating_complete(primary.get(entry_id, {})) for entry_id in primary_ids)
    batches = []
    for batch in manifest.get("batches", []):
        rows = {str(row["entry_id"]): row for row in batch_worksheets.get(str(batch["worksheet"]), [])}
        targets = set(map(str, batch.get("target_entry_ids", [])))
        anchors = set(map(str, batch.get("anchor_entry_ids", [])))
        batch_target_done = sum(_rating_complete(rows.get(entry_id, {})) for entry_id in targets)
        batch_anchor_done = sum(_rating_complete(rows.get(entry_id, {})) for entry_id in anchors)
        target_done += batch_target_done
        batches.append({"batch_id": batch["batch_id"], "target_completed": batch_target_done,
                        "target_total": len(targets), "anchor_completed": batch_anchor_done,
                        "anchor_total": len(anchors)})
    full_done = sum(_rating_complete(row) for row in full.values())
    expected = int(manifest.get("expected_entries", 0))
    return {"review_mode": "full_rater_plus_block_panel", "full_rater_completed": full_done,
            "full_rater_total": expected, "panel_target_completed": target_done,
            "panel_target_total": expected, "batches": batches,
            "complete": full_done == expected and target_done == expected
                        and all(item["anchor_completed"] == item["anchor_total"] for item in batches)}


def analyze_panel_ratings(manifest: Mapping[str, Any], primary_worksheet: Sequence[Mapping[str, Any]],
                          full_worksheet: Sequence[Mapping[str, Any]],
                          batch_worksheets: Mapping[str, Sequence[Mapping[str, Any]]],
                          private_key: Mapping[str, Mapping[str, str]]) -> dict[str, Any]:
    """Analyze one full rater against a disjoint, calibrated volunteer panel."""
    progress = panel_review_progress(manifest, primary_worksheet, full_worksheet, batch_worksheets)
    if not progress["complete"]:
        raise ValueError("panel worksheets are incomplete")
    expected_entries = set(private_key)
    full = {str(row["entry_id"]): row for row in full_worksheet}
    if set(full) != expected_entries:
        raise ValueError("full rater worksheet must match the frozen entry set")
    _validate_complete_rows(full, expected_entries)
    full_rater_ids = {str(row.get("rater_id", "")).strip() for row in full.values()}
    if len(full_rater_ids) != 1 or not next(iter(full_rater_ids), ""):
        raise ValueError("full worksheet requires one rater_id")
    primary = {str(row["entry_id"]): row for row in primary_worksheet}
    primary_targets = set(map(str, manifest.get("primary_target_entry_ids", [])))
    _validate_complete_rows(primary, primary_targets)
    panel_targets = {entry_id: primary[entry_id] for entry_id in primary_targets}
    panel_rater_ids = {str(primary[entry_id].get("rater_id", "")).strip() for entry_id in primary_targets}
    block_agreement, anchor_agreement = {}, {}
    anchors = set(map(str, manifest.get("anchor_entry_ids", [])))
    for batch in manifest.get("batches", []):
        filename = str(batch["worksheet"])
        rows = {str(row["entry_id"]): row for row in batch_worksheets.get(filename, [])}
        target_ids = set(map(str, batch.get("target_entry_ids", [])))
        anchor_ids = set(map(str, batch.get("anchor_entry_ids", [])))
        if set(rows) != target_ids | anchor_ids or anchor_ids != anchors:
            raise ValueError(f"panel batch does not match manifest: {batch['batch_id']}")
        _validate_complete_rows(rows, set(rows))
        rater_ids = {str(row.get("rater_id", "")).strip() for row in rows.values()}
        if len(rater_ids) != 1 or not next(iter(rater_ids), ""):
            raise ValueError(f"panel batch requires one rater_id: {batch['batch_id']}")
        panel_rater_ids.add(next(iter(rater_ids)))
        overlap = set(panel_targets) & target_ids
        if overlap:
            raise ValueError(f"panel target entries overlap: {sorted(overlap)}")
        panel_targets.update({entry_id: rows[entry_id] for entry_id in target_ids})
        block_agreement[str(batch["batch_id"])] = round(
            sum(rows[entry_id]["preference"] == full[entry_id]["preference"] for entry_id in target_ids)
            / len(target_ids), 4)
        anchor_agreement[str(batch["batch_id"])] = round(
            sum(rows[entry_id]["preference"] == primary[entry_id]["preference"] for entry_id in anchors)
            / len(anchors), 4)
    if set(panel_targets) != expected_entries:
        raise ValueError("panel target coverage must match the frozen entry set")
    all_rater_ids = panel_rater_ids | full_rater_ids
    if len(all_rater_ids) != len(panel_rater_ids) + len(full_rater_ids):
        raise ValueError("full and panel rater_id values must be distinct")
    agreements = sum(full[entry_id]["preference"] == panel_targets[entry_id]["preference"]
                     for entry_id in expected_entries)
    preference_counts: Counter[str] = Counter()
    paired_labels = []
    for entry_id in sorted(expected_entries):
        labels = []
        for row in (full[entry_id], panel_targets[entry_id]):
            choice = str(row["preference"])
            labels.append(choice)
            preference_counts["tie" if choice == "tie" else private_key[entry_id][choice]] += 1
        paired_labels.append(labels)
    model_counts = {name: count for name, count in preference_counts.items() if name != "tie"}
    non_ties = sum(model_counts.values())
    leader = max(model_counts, key=model_counts.get) if model_counts else None
    wins = model_counts.get(leader, 0) if leader else 0
    return {"schema_version": "blind-image-panel-review/v1",
            "review_mode": "full_rater_plus_block_panel", "full_set_rater_count": 1,
            "panel_rater_count": len(panel_rater_ids), "total_distinct_raters": len(all_rater_ids),
            "covered_entries": len(panel_targets), "panel_complete": True,
            "preference_exact_agreement": round(agreements / len(expected_entries), 4),
            "preference_nominal_alpha": _nominal_alpha(paired_labels),
            "block_agreement_with_full_rater": block_agreement,
            "anchor_agreement_with_primary_panel_rater": anchor_agreement,
            "preference_counts": dict(preference_counts), "leader": leader,
            "leader_win_rate": round(wins / non_ties, 4) if non_ties else None,
            "leader_binomial_p_value": _two_sided_binomial(wins, non_ties) if non_ties else None,
            "progress": progress,
            "claim_boundary": "One full-set rater plus five block-panel raters; agreement is pooled across blocks."}


def completion_gate(records: Sequence[Mapping[str, Any]], review: Mapping[str, Any] | None,
                    *, expected_cases: int = 100, expected_models: int = 2) -> dict[str, Any]:
    """Require real artifacts, held-out data, safety metrics and a valid human-review protocol."""
    models = {str(row.get("model", "")) for row in records}
    cases = {str(row.get("case_id", "")) for row in records}
    real_artifacts = all(_artifact_valid(row) for row in records) if records else False
    automatic_metrics = all(bool(row.get("automatic_metrics")) for row in records) if records else False
    safety = all(row.get("safety_result") is not None for row in records) if records else False
    held_out = any(row.get("split") == "held_out" for row in records)
    dual_review = bool(review and int(review.get("rater_count", 0)) >= 2
                       and int(review.get("shared_entries", 0)) >= expected_cases)
    panel_review = bool(review and review.get("review_mode") == "full_rater_plus_block_panel"
                        and review.get("panel_complete") is True
                        and int(review.get("covered_entries", 0)) >= expected_cases
                        and int(review.get("panel_rater_count", 0)) >= 1)
    checks = {"case_count": len(cases) == expected_cases, "model_count": len(models) == expected_models,
              "record_count": len(records) == expected_cases * expected_models,
              "real_artifacts": real_artifacts, "automatic_metrics": automatic_metrics,
              "safety_results": safety, "held_out": held_out,
              "human_blind_review": dual_review or panel_review}
    return {"passed": all(checks.values()), "checks": checks,
            "evidence_level": "offline_real" if all(checks.values()) else "interface",
            "claim_boundary": "A failed gate must not upgrade portfolio readiness."}


def compare_model_records(records: Sequence[Mapping[str, Any]], seed: int = 20260813,
                          bootstrap_samples: int = 2000) -> dict[str, Any]:
    """Compare paired prompt scores, slices, latency and uncertainty."""
    by_case: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in records:
        by_case[str(row["case_id"])].append(row)
    pairs = [pair for pair in by_case.values() if len(pair) == 2
             and all(row.get("automatic_metrics") for row in pair)]
    if not pairs:
        raise ValueError("paired scored records are required")
    models = sorted({str(row["model"]) for pair in pairs for row in pair})
    if len(models) != 2:
        raise ValueError("exactly two models are required")
    left, right = models
    differences, slices = [], defaultdict(list)
    for pair in pairs:
        indexed = {str(row["model"]): row for row in pair}
        if set(indexed) != set(models):
            continue
        delta = float(indexed[left]["automatic_metrics"]["clip_cosine"]) - float(
            indexed[right]["automatic_metrics"]["clip_cosine"])
        differences.append(delta)
        case_id = str(pair[0]["case_id"])
        parts = case_id.split("-")
        subject_index = int(parts[1])
        category = ("product" if subject_index <= 4 else "food" if subject_index <= 8
                    else "scene" if subject_index <= 12 else "illustration" if subject_index <= 16
                    else "spatial")
        style = ("photo", "studio", "cinematic", "illustrated", "detail")[int(parts[2]) - 1]
        slices[f"category:{category}"].append(delta)
        slices[f"style:{style}"].append(delta)
        slices[f"split:{pair[0]['split']}"] .append(delta)
    rng = random.Random(seed)
    means = [sum(rng.choice(differences) for _ in differences) / len(differences)
             for _ in range(bootstrap_samples)]
    means.sort()
    lower = means[int(bootstrap_samples * 0.025)]
    upper = means[min(bootstrap_samples - 1, int(bootstrap_samples * 0.975))]
    summaries = {}
    for model in models:
        rows = [row for pair in pairs for row in pair if row["model"] == model]
        latencies = sorted(float(row["latency_ms"]) for row in rows)
        summaries[model] = {"samples": len(rows),
                            "mean_clip_cosine": round(sum(float(row["automatic_metrics"]["clip_cosine"])
                                                          for row in rows) / len(rows), 6),
                            "mean_latency_ms": round(sum(latencies) / len(latencies), 3),
                            "p95_latency_ms": round(latencies[max(0, math.ceil(len(latencies) * 0.95) - 1)], 3),
                            "safety_pass_rate": round(sum(bool(row["safety_result"]["passed"])
                                                          for row in rows) / len(rows), 4)}
    return {"schema_version": "paired-image-model-comparison/v1", "models": models,
            "paired_cases": len(differences), "metric": "CLIP cosine similarity",
            "mean_difference_left_minus_right": round(sum(differences) / len(differences), 6),
            "bootstrap_95_ci": [round(lower, 6), round(upper, 6)],
            "left_wins": sum(value > 0 for value in differences),
            "right_wins": sum(value < 0 for value in differences),
            "ties": sum(value == 0 for value in differences),
            "slices": {name: {"n": len(values), "mean_difference": round(sum(values) / len(values), 6)}
                       for name, values in sorted(slices.items())},
            "model_summary": summaries,
            "warning": "CLIP is one proxy metric; final preference requires blinded human ratings."}


def _artifact_valid(row: Mapping[str, Any]) -> bool:
    artifacts = row.get("artifacts") or []
    return bool(artifacts) and all(Path(str(item.get("uri", ""))).is_file()
                                   and len(str(item.get("sha256", ""))) == 64 for item in artifacts)


def _rating_complete(row: Mapping[str, Any]) -> bool:
    if not str(row.get("rater_id", "")).strip() or row.get("preference") not in {"a", "b", "tie"}:
        return False
    for side in ("scores_a", "scores_b"):
        scores = row.get(side) or {}
        if set(scores) != set(REQUIRED_DIMENSIONS):
            return False
        try:
            if any(not 1 <= float(value) <= 5 for value in scores.values()):
                return False
        except (TypeError, ValueError):
            return False
    return True


def _validate_complete_rows(rows: Mapping[str, Mapping[str, Any]], expected: set[str]) -> None:
    missing = expected - set(rows)
    if missing:
        raise ValueError(f"worksheet entries are missing: {sorted(missing)}")
    incomplete = [entry_id for entry_id in expected if not _rating_complete(rows[entry_id])]
    if incomplete:
        raise ValueError(f"worksheet ratings are incomplete: {sorted(incomplete)}")


def _blank_panel_row(row: Mapping[str, Any], role: str) -> dict[str, Any]:
    copied = {key: value for key, value in row.items()
              if key not in {"rater_id", "scores_a", "scores_b", "preference", "notes", "prompt_zh"}}
    copied.update({"rater_id": "", "scores_a": {}, "scores_b": {}, "preference": "", "notes": "",
                   "panel_role": role})
    return copied


def _entry_sort_key(entry_id: str) -> tuple[int, int]:
    parts = entry_id.removeprefix("blind::img-").split("-")
    return int(parts[0]), int(parts[1])


def _nominal_alpha(units: Sequence[Sequence[str]]) -> float | None:
    labels = [label for unit in units for label in unit]
    total = len(labels)
    if total < 2:
        return None
    observed_numerator = 0.0
    observed_denominator = 0
    for unit in units:
        if len(unit) < 2:
            continue
        disagreements = sum(left != right for left in unit for right in unit)
        observed_numerator += disagreements / (len(unit) - 1)
        observed_denominator += len(unit)
    observed = observed_numerator / observed_denominator if observed_denominator else 0.0
    counts = Counter(labels)
    expected = sum(count * (total - count) for count in counts.values()) / (total * (total - 1))
    if expected == 0:
        return 1.0 if observed == 0 else None
    return round(1.0 - observed / expected, 4)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _two_sided_binomial(wins: int, total: int) -> float:
    if not 0 <= wins <= total or total <= 0:
        raise ValueError("invalid binomial counts")
    tail = min(wins, total - wins)
    probability = 2 * sum(math.comb(total, k) for k in range(tail + 1)) / (2 ** total)
    return round(min(1.0, probability), 8)
