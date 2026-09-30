"""Release audit scored per trajectory, on media steps only.

Generate, describe, and final-step dimension scores are averaged inside
one step; the episode process score is the weakest media step so a strong
generate cannot mask an ungrounded final. Thought steps are left out.
Several episodes are gated one by one; their scores are not averaged first.
Soft scores enter the gate only when this submission's calibration rows
match those judge_scores.

Default scoring reads fixture ``judge_scores``. Pass ``judge_fn`` (or use
the CLI ``--live`` path) to score media steps with a real Judge LLM.
"""

from __future__ import annotations

from typing import Any, Callable, Mapping, Optional, Sequence

from eval_engine.core.failure_taxonomy import summarize_failures
from eval_engine.core.attribution_anchor import (
    cross_check_attribution,
    summarize_cross_checks,
)
from eval_engine.core.multimodal_process_judge import (
    DIMENSIONS,
    _is_media_step,
    make_dimension_judge,
)
from eval_engine.core.process_reward import ProcessRewardScorer
from eval_engine.core.trajectory_parser import StepsDAG, parse_trajectory
from eval_engine.gates.evidence_bundle import evaluate_evidence_bundle
from eval_engine.integrations.episode import import_episode, verify_episode_state
from eval_engine.integrations.trace_findings import adapt_media_rule_findings
from eval_engine.judge.calibration import agreement_table, bootstrap_ci


def audit_release(
    episodes: Sequence[Mapping[str, Any]],
    *,
    judge_fn: Optional[Callable[[str], dict[str, Any]]] = None,
    judge_factory: Optional[Callable[[StepsDAG], Callable[[str], dict[str, Any]]]] = None,
    generation_appendix: Optional[Mapping[str, Any]] = None,
    calibration: Optional[Mapping[str, Any]] = None,
    rebuild_calibration: bool = False,
    min_process_score: float = 3.5,
    judge_meta: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    """Return one decision per episode, then the strictest of those decisions.

    When ``rebuild_calibration`` is true, held-out ``human_score`` labels are
    kept and ``judge_score`` is replaced by this run's media-step scores so κ
    binds to the Judge that actually scored the submission.

    Prefer ``judge_factory(dag)`` for live Judges that need a per-episode
    cursor; a single shared ``judge_fn`` is only safe for fixture mode.
    """
    if not episodes:
        raise ValueError("audit_release requires at least one episode")
    if judge_fn is not None and judge_factory is not None:
        raise ValueError("pass only one of judge_fn or judge_factory")
    scored: list[dict[str, Any]] = []
    for raw in episodes:
        scored.append(
            _score_episode(raw, judge_fn=judge_fn, judge_factory=judge_factory)
        )

    episode_ids = {item["episode_id"] for item in scored}
    cells = {
        item["episode_id"]: item["dimension_cells"]
        for item in scored
    }
    calibration_doc = calibration
    rebuilt_calibration = None
    if rebuild_calibration:
        if calibration is None:
            raise ValueError("rebuild_calibration requires a prior calibration doc")
        rebuilt_calibration = rebuild_held_out_calibration(calibration, cells)
        calibration_doc = rebuilt_calibration
    calibrated_rows = _matching_calibration_rows(calibration_doc, episode_ids, cells)
    calibration_report = _calibration_report(calibrated_rows)

    episode_reports: list[dict[str, Any]] = []
    for item in scored:
        episode_reports.append(
            _gate_episode(
                item,
                calibrated=calibration_report is not None,
                calibration_report=calibration_report,
                min_process_score=min_process_score,
            )
        )

    outcome = _strictest(episode["decision"] for episode in episode_reports)
    review_reasons: list[str] = []
    hard_failures: list[str] = []
    for episode in episode_reports:
        review_reasons.extend(episode["review_reasons"])
        hard_failures.extend(episode["hard_failures"])
    single = episode_reports[0] if len(episode_reports) == 1 else None
    live = judge_factory is not None or (
        judge_meta is not None and str(judge_meta.get("mode") or "") == "live"
    )
    judge_block = {
        "mode": "live" if live else "fixture",
        "model": None,
        "provider": None,
        "base_url": None,
        "scored_at": None,
    }
    if judge_meta:
        judge_block.update({key: judge_meta[key] for key in judge_meta})
    return {
        "schema_version": "release-audit/v1",
        "decision": outcome,
        "passed": outcome == "pass",
        "hard_failures": hard_failures,
        "review_reasons": review_reasons,
        "decision_basis": (
            "process_reward_soft_dimensions" if calibration_report is not None else "uncalibrated"
        ),
        "process_quality": None if single is None else single["process_quality"],
        "episodes": episode_reports,
        "calibration": calibration_report,
        "rebuilt_calibration": rebuilt_calibration,
        "judge": judge_block,
        "rule_findings": [
            finding
            for episode in episode_reports
            for finding in episode["rule_findings"]
        ],
        "attribution_anchors": _attribution_block(scored),
        "failure_taxonomy": summarize_failures(
            [item["taxonomy_input"] for item in scored]
        ).to_dict(),
        "auxiliary_evidence": (
            dict(generation_appendix) if generation_appendix is not None else None
        ),
    }


def _score_episode(
    raw: Mapping[str, Any],
    *,
    judge_fn: Optional[Callable[[str], dict[str, Any]]],
    judge_factory: Optional[Callable[[StepsDAG], Callable[[str], dict[str, Any]]]] = None,
) -> dict[str, Any]:
    episode = import_episode(raw)
    payload = episode.to_dict()
    payload["state_verification"] = verify_episode_state(episode).to_dict()
    dag = parse_trajectory(episode.trajectory)
    if judge_factory is not None:
        judge = judge_factory(dag)
    else:
        judge = judge_fn or make_dimension_judge(dag)
    report = ProcessRewardScorer(judge_fn=judge, enable_trace_findings=False).score_trajectory(
        dag
    )
    media_steps = []
    cells: list[tuple[int, str, float]] = []
    for node in dag.nodes:
        if node.step_type != "final" and not _is_media_step(node):
            continue
        scored = next(step for step in report.per_step if step.step_index == node.step_index)
        dim_scores = {
            rubric.dimension: float(rubric.score)
            for rubric in scored.rubrics
            if rubric.dimension in DIMENSIONS
        }
        if len(dim_scores) != len(DIMENSIONS):
            step_score = None
        else:
            step_score = round(sum(dim_scores.values()) / len(DIMENSIONS), 3)
            for name, value in dim_scores.items():
                cells.append((node.step_index, name, value))
        media_steps.append(
            {
                "episode_id": episode.episode_id,
                "step_index": node.step_index,
                "step_kind": node.metadata.get("step_kind") or node.step_type,
                "tool_name": node.tool_name,
                "artifacts": [
                    {
                        "uri": str(item.get("uri") or ""),
                        "sha256": str(item.get("sha256") or ""),
                    }
                    for item in (node.metadata.get("artifacts") or [])
                    if isinstance(item, Mapping)
                ],
                "rubrics": [
                    {"dimension": name, "score": value}
                    for name, value in dim_scores.items()
                ],
                "step_score": step_score,
            }
        )
    present = [step["step_score"] for step in media_steps if step["step_score"] is not None]
    # Gate on the weakest media step so a strong generate cannot mask an
    # ungrounded final (mean of 5.0 and 2.75 would wrongly clear 3.5).
    overall = round(min(present), 3) if present else None
    findings = []
    analysis = episode.metadata.get("trace_analysis")
    if isinstance(analysis, Mapping):
        for finding in adapt_media_rule_findings(analysis):
            item = finding.to_dict()
            item["episode_id"] = episode.episode_id
            findings.append(item)
    return {
        "episode_id": episode.episode_id,
        "payload": payload,
        "overall": overall,
        "media_steps": media_steps,
        "dimension_cells": cells,
        "rule_findings": findings,
        "attribution_anchor": _anchor_cross_check(report, episode, analysis),
        "taxonomy_input": (episode.episode_id, "multimodal_step", report),
    }


def _anchor_cross_check(
    report: Any,
    episode: Any,
    analysis: Optional[Mapping[str, Any]],
) -> dict[str, Any]:
    """归因锚点交叉校验：确定性失败步是否出现在 error_sources（必要条件检查）。

    只写入报告，不参与决策。trace-debugger 未安装或轨迹不可解析时记录 skipped，
    不让审计整体失败。
    """
    try:
        return cross_check_attribution(
            report,
            trajectory=episode.trajectory,
            analysis=analysis,
            episode_id=episode.episode_id,
        )
    except Exception as exc:  # pragma: no cover - 取决于运行环境是否装有 trace-debugger
        return {
            "episode_id": episode.episode_id,
            "anchors": {},
            "error_sources": sorted({int(s) for s in (report.error_sources or [])}),
            "agreed_steps": [],
            "missed_steps": [],
            "unaided_sources": [],
            "anchor_total": 0,
            "anchor_hit": 0,
            "skipped": f"{type(exc).__name__}: {exc}",
        }


def _attribution_block(scored: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """汇总每条 episode 的锚点校验结果（anchor_consistency 是必要条件通过率）。"""
    results = [item.get("attribution_anchor") or {} for item in scored]
    block = summarize_cross_checks(results)
    block["per_episode"] = [
        {
            "episode_id": item.get("episode_id", ""),
            "anchors": item.get("anchors") or {},
            "error_sources": item.get("error_sources") or [],
            "missed_steps": item.get("missed_steps") or [],
        }
        for item in results
        if item.get("anchor_total")
    ]
    block["skipped"] = [
        {"episode_id": item.get("episode_id", ""), "reason": item.get("skipped", "")}
        for item in results
        if item.get("skipped")
    ]
    return block


def _gate_episode(
    item: Mapping[str, Any],
    *,
    calibrated: bool,
    calibration_report: Optional[dict[str, Any]],
    min_process_score: float,
) -> dict[str, Any]:
    process_quality = None
    if calibrated and item["overall"] is not None:
        process_quality = {
            "metric": "process_reward_media_steps_min",
            "overall_score": item["overall"],
            "calibrated": True,
            "steps": item["media_steps"],
        }
    decision = evaluate_evidence_bundle(
        episodes=[item["payload"]],
        process_quality=process_quality,
        min_process_score=min_process_score,
    )
    review_reasons = [
        f"{item['episode_id']}: {reason}" for reason in decision.get("review_reasons") or []
    ]
    # Soft check: broken media tool args cannot be masked by high attachment/safety.
    for step in item["media_steps"]:
        if step.get("step_kind") == "final" or not step.get("tool_name"):
            continue
        for rubric in step.get("rubrics") or []:
            if (
                rubric.get("dimension") == "media_arg_fidelity"
                and rubric.get("score") is not None
                and float(rubric["score"]) <= 2.0
            ):
                review_reasons.append(
                    f"{item['episode_id']}: media_arg_fidelity "
                    f"{float(rubric['score']):.1f} on {step.get('tool_name')} "
                    f"step {step.get('step_index')} (wrong/empty media args)"
                )
    if not calibrated:
        review_reasons.append(f"{item['episode_id']}: multimodal process scores are uncalibrated")
        outcome = "review" if decision["decision"] != "hold" else "hold"
        passed = False
    else:
        outcome = decision["decision"]
        passed = decision["passed"]
        if review_reasons and outcome == "pass":
            outcome = "review"
            passed = False
    return {
        "episode_id": item["episode_id"],
        "decision": outcome,
        "passed": passed,
        "hard_failures": list(decision.get("hard_failures") or []),
        "review_reasons": review_reasons,
        "process_quality": process_quality,
        "calibration": calibration_report,
        "rule_findings": list(item["rule_findings"]),
    }


def rebuild_held_out_calibration(
    prior: Mapping[str, Any],
    cells: Mapping[str, Sequence[tuple[int, str, float]]],
) -> dict[str, Any]:
    """Replace ``judge_score`` with this run's scores; keep human labels."""
    human_by_key = {
        (
            str(row.get("episode_id")),
            int(row.get("step_index")),
            str(row.get("dimension")),
        ): row.get("human_score")
        for row in (prior.get("items") or [])
        if row.get("split") == "held_out"
        and row.get("step_index") is not None
        and row.get("dimension")
        and row.get("human_score") is not None
    }
    items: list[dict[str, Any]] = []
    for episode_id, episode_cells in cells.items():
        for step_index, dimension, score in episode_cells:
            key = (episode_id, step_index, dimension)
            if key not in human_by_key:
                raise ValueError(
                    "held-out human label missing for "
                    f"{episode_id} step {step_index} {dimension}"
                )
            items.append(
                {
                    "id": f"{episode_id}-{step_index}-{dimension}",
                    "episode_id": episode_id,
                    "step_index": step_index,
                    "split": "held_out",
                    "dimension": dimension,
                    "human_score": human_by_key[key],
                    "judge_score": float(score),
                }
            )
    meta = dict(prior.get("meta") or {})
    meta["protocol"] = (
        "held-out human vs live Judge on media steps of the submitted episodes"
    )
    return {"meta": meta, "items": items}


def _matching_calibration_rows(
    calibration: Optional[Mapping[str, Any]],
    episode_ids: set[str],
    cells: Mapping[str, Sequence[tuple[int, str, float]]],
) -> Optional[list[Mapping[str, Any]]]:
    if not calibration:
        return None
    rows = [
        row
        for row in (calibration.get("items") or [])
        if row.get("episode_id") in episode_ids and row.get("split") == "held_out"
    ]
    indexed = {
        (str(row.get("episode_id")), int(row.get("step_index")), str(row.get("dimension"))): row
        for row in rows
        if row.get("step_index") is not None and row.get("dimension")
    }
    matched: list[Mapping[str, Any]] = []
    for episode_id, episode_cells in cells.items():
        if not episode_cells:
            return None
        for step_index, dimension, score in episode_cells:
            row = indexed.get((episode_id, step_index, dimension))
            if row is None or row.get("judge_score") is None:
                return None
            if float(row.get("judge_score")) != float(score):
                return None
            if row.get("human_score") is None:
                return None
            matched.append(row)
    return matched or None


def _calibration_report(rows: Optional[Sequence[Mapping[str, Any]]]) -> Optional[dict[str, Any]]:
    """Held-out human↔Judge table in the same shape as ``run_calibration.py``.

    Primary κ unit is the **dimension cell**
    ``(episode_id × media/final step × dimension)``, not a trajectory-mean
    score. ``episode_count`` is reported separately for sample-breadth context.
    """
    if not rows:
        return None
    humans = [float(row["human_score"]) for row in rows]
    judges = [float(row["judge_score"]) for row in rows]
    ids = [
        str(
            row.get("id")
            or f"{row['episode_id']}-{row['step_index']}-{row['dimension']}"
        )
        for row in rows
    ]
    table = agreement_table(humans, judges, ids=ids)
    for pair, row in zip(table["pairs"], rows):
        pair["split"] = "held_out"
        pair["episode_id"] = str(row["episode_id"])
        pair["step_index"] = int(row["step_index"])
        pair["dimension"] = str(row["dimension"])
    boot = bootstrap_ci(humans, judges)
    episode_ids = sorted({str(row["episode_id"]) for row in rows})
    threshold = 0.6
    kappa = float(table["kappa"])
    held_out = {**table, "bootstrap": boot}
    return {
        **table,
        "gate_split": "held_out",
        "kappa_unit": "dimension_cell",
        "kappa_unit_note": (
            "Cohen's kappa over held-out dimension cells "
            "(episode x media/final step x dimension); "
            "not trajectory-aggregated process scores"
        ),
        "dimensions": list(DIMENSIONS),
        "episode_ids": episode_ids,
        "episode_count": len(episode_ids),
        "threshold": threshold,
        "needs_calibration": kappa < threshold,
        "bootstrap": boot,
        "by_split": {"held_out": held_out},
        "notes": (
            "Multimodal process held_out uses agreement_table + bootstrap CI "
            "(same helpers as run_calibration.py). Cite cell n and episode_count "
            "separately; do not synthesize a total with text Judge kappa."
        ),
    }


def _strictest(decisions: Sequence[str]) -> str:
    chosen = list(decisions)
    if any(decision == "hold" for decision in chosen):
        return "hold"
    if any(decision == "review" for decision in chosen):
        return "review"
    return "pass"
