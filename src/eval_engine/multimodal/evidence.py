"""Release-facing multimodal evidence column for evidence_bundle gates."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

MULTIMODAL_EVIDENCE_SCHEMA = "multimodal-release-evidence/v1"
_SUPPORTED_MEDIA = {"image", "video"}


def build_multimodal_evidence(
    *,
    media_type: str,
    cases_evaluated: int,
    integrity_passed: bool,
    automatic_metrics_complete: bool,
    safety_passed: bool,
    held_out_included: bool = False,
    human_review_complete: bool | None = None,
    video_dimensions: Mapping[str, Any] | None = None,
    details: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Assemble one multimodal evidence column with fail-closed gate semantics.

    Images require automatic metrics plus completed human preference evidence to
    pass. Videos require automatic metrics and thin multi-dimension scores; human
    preference remains optional and only soft-reviews when explicitly marked
    incomplete.
    """
    hard_failures: list[str] = []
    review_reasons: list[str] = []
    media = str(media_type).strip()
    if media not in _SUPPORTED_MEDIA:
        hard_failures.append(f"unsupported multimodal media_type: {media!r}")
    if int(cases_evaluated) <= 0:
        hard_failures.append("no multimodal cases evaluated")
    if not integrity_passed:
        hard_failures.append("artifact integrity failed")
    if not automatic_metrics_complete:
        hard_failures.append("automatic multimodal metrics incomplete")
    if not safety_passed:
        hard_failures.append("multimodal safety failed")
    if not held_out_included:
        review_reasons.append("multimodal held_out not included")

    dimension_report = dict(video_dimensions or {})
    if media == "image":
        if human_review_complete is True:
            pass
        elif human_review_complete is False:
            review_reasons.append("image human blind review incomplete")
        else:
            review_reasons.append("image human preference evidence absent")
    elif media == "video":
        if not dimension_report.get("complete"):
            review_reasons.append("video dimension scores incomplete")
        if human_review_complete is False:
            review_reasons.append("video human preference incomplete")

    decision = "hold" if hard_failures else "review" if review_reasons else "pass"
    return {
        "schema_version": MULTIMODAL_EVIDENCE_SCHEMA,
        "media_type": media,
        "cases_evaluated": int(cases_evaluated),
        "integrity_passed": bool(integrity_passed),
        "automatic_metrics_complete": bool(automatic_metrics_complete),
        "safety_passed": bool(safety_passed),
        "held_out_included": bool(held_out_included),
        "human_review_complete": human_review_complete,
        "video_dimensions": dimension_report,
        "gate_decision": decision,
        "passed": decision == "pass",
        "hard_failures": hard_failures,
        "review_reasons": review_reasons,
        "details": dict(details or {}),
        "claim_boundary": (
            "Multimodal column gates offline artifact integrity, automatic "
            "alignment/safety, and image human preference completeness. It does "
            "not replace business-state or process-quality evidence."
        ),
    }


def summarize_case_reports(
    reports: Sequence[Mapping[str, Any]],
    *,
    media_type: str,
    human_review_complete: bool | None = None,
    video_dimensions: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Derive multimodal evidence from MultimodalEvaluator case reports."""
    integrity_ok = True
    automatic_ok = True
    safety_ok = True
    held_out = False
    for report in reports:
        if report.get("split") == "held_out":
            held_out = True
        metrics = {
            str(item.get("name")): item
            for item in report.get("metrics") or []
            if isinstance(item, Mapping)
        }
        integrity = metrics.get("artifact_integrity")
        if integrity is None or integrity.get("passed") is not True:
            integrity_ok = False
        clip = metrics.get("clip_score")
        if clip is None or clip.get("passed") is None:
            automatic_ok = False
        elif clip.get("passed") is False:
            automatic_ok = False
        safety = metrics.get("safety_classifier")
        if safety is None or safety.get("passed") is not True:
            safety_ok = False
    return build_multimodal_evidence(
        media_type=media_type,
        cases_evaluated=len(reports),
        integrity_passed=integrity_ok,
        automatic_metrics_complete=automatic_ok and bool(reports),
        safety_passed=safety_ok and bool(reports),
        held_out_included=held_out,
        human_review_complete=human_review_complete,
        video_dimensions=video_dimensions,
        details={"report_count": len(reports)},
    )
