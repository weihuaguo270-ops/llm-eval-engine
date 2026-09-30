"""multimodal_step — 轨迹内多模态工具步的过程检查

评的是 Agent 是否合理调用读图/出图工具、参数是否忠实、产物是否被后续步骤
grounded 使用；不是生成模型横向选型。CLIP 等像素指标可通过 MetricAdapter
在单步上作为辅助证据接入，不进入「模型 A vs B」发布结论。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from eval_engine.integrations.trace_findings import CheckFinding
from eval_engine.multimodal.evaluator import ArtifactRef
from eval_engine.core.trajectory_parser import StepNode, StepsDAG

# 工具名约定（小写匹配）；可按 Agent 实际工具表扩展
GENERATE_IMAGE_TOOLS = frozenset(
    {"generate_image", "text_to_image", "img_gen", "create_image"}
)
DESCRIBE_IMAGE_TOOLS = frozenset(
    {"describe_image", "image_caption", "vision_qa", "read_image", "analyze_image"}
)
GENERATE_VIDEO_TOOLS = frozenset(
    {"generate_video", "text_to_video", "video_gen", "create_video"}
)
DESCRIBE_VIDEO_TOOLS = frozenset(
    {"describe_video", "video_caption", "read_video", "analyze_video"}
)
GENERATE_MEDIA_TOOLS = GENERATE_IMAGE_TOOLS | GENERATE_VIDEO_TOOLS
DESCRIBE_MEDIA_TOOLS = DESCRIBE_IMAGE_TOOLS | DESCRIBE_VIDEO_TOOLS
MULTIMODAL_TOOLS = GENERATE_MEDIA_TOOLS | DESCRIBE_MEDIA_TOOLS
_GENERATE_KINDS = frozenset({"generate_image", "generate_video"})
_DESCRIBE_KINDS = frozenset({"describe_image", "describe_video"})

# 任务文本中暗示需要视觉证据的关键词（规则启发式，可被 fixture metadata 覆盖）
_VISION_NEED_HINTS = (
    "图",
    "图片",
    "截图",
    "照片",
    "视觉",
    "image",
    "screenshot",
    "photo",
    "视频",
    "video",
    "mp4",
)


def is_multimodal_tool(tool_name: Optional[str]) -> bool:
    if not tool_name:
        return False
    return tool_name.strip().lower() in MULTIMODAL_TOOLS


def extract_step_artifacts(node: StepNode) -> list[ArtifactRef]:
    """从 StepNode.metadata['artifacts'] 解析 ArtifactRef。

    Episode 上可以只写 uri 与 sha256。缺省的 id / media_type 由路径补齐，
    不把像素写进轨迹。
    """
    raw = node.metadata.get("artifacts") or []
    if not isinstance(raw, list):
        return []
    out: list[ArtifactRef] = []
    for item in raw:
        if isinstance(item, Mapping):
            out.append(ArtifactRef.from_dict(_artifact_payload(item)))
    return out


def _artifact_payload(item: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(item)
    uri = str(payload.get("uri") or "").strip()
    name = Path(uri).name
    if not str(payload.get("id") or "").strip():
        payload["id"] = Path(uri).stem or "artifact"
    if not str(payload.get("media_type") or "").strip():
        payload["media_type"] = _MEDIA_BY_SUFFIX.get(Path(name).suffix.lower(), "other")
    return payload


_MEDIA_BY_SUFFIX = {
    ".png": "image",
    ".jpg": "image",
    ".jpeg": "image",
    ".webp": "image",
    ".gif": "image",
    ".mp4": "video",
    ".webm": "video",
    ".wav": "audio",
    ".mp3": "audio",
}


def analyze_multimodal_steps(
    dag: StepsDAG,
    *,
    require_vision: Optional[bool] = None,
) -> list[CheckFinding]:
    """对轨迹中多模态相关步做规则级过程检查，产出 CheckFinding。

    require_vision:
        None → 从 query 启发式推断是否需要视觉证据
        True/False → 显式覆盖（fixture 可写在 trajectory.metadata）
    """
    findings: list[CheckFinding] = []
    query = dag.query or ""
    if require_vision is None:
        require_vision = any(h in query.lower() for h in _VISION_NEED_HINTS) or any(
            h in query for h in _VISION_NEED_HINTS
        )

    generated_tokens: set[str] = set()
    for node in dag.nodes:
        tool = (node.tool_name or "").strip().lower()
        artifacts = extract_step_artifacts(node)
        step_kind = str(node.metadata.get("step_kind") or "")

        if tool in GENERATE_MEDIA_TOOLS or step_kind in _GENERATE_KINDS:
            findings.extend(
                _check_generate_step(node, tool, artifacts, require_vision)
            )
            generated_tokens |= _reference_tokens(artifacts)

        elif tool in DESCRIBE_MEDIA_TOOLS or step_kind in _DESCRIBE_KINDS:
            findings.extend(
                _check_describe_step(node, tool, artifacts, generated_tokens)
            )

        elif node.step_type == "final":
            findings.extend(
                _check_final_grounding(node, generated_tokens, dag)
            )

    return findings


def _check_generate_step(
    node: StepNode,
    tool: str,
    artifacts: list[ArtifactRef],
    require_vision: bool,
) -> list[CheckFinding]:
    out: list[CheckFinding] = []
    args = node.tool_args if isinstance(node.tool_args, dict) else {}
    # 乱出图：任务不需要视觉证据却调用生成
    if not require_vision:
        out.append(
            CheckFinding(
                code="unnecessary_generation",
                failure_type="unnecessary_generation",
                message="任务无需视觉产物却调用了媒体生成工具",
                step_index=node.step_index,
                severity="fail",
                score=2.0,
                source="multimodal_step",
                tool_name=tool or node.tool_name,
            )
        )
    prompt = str(args.get("prompt") or args.get("text") or "").strip()
    if not prompt:
        out.append(
            CheckFinding(
                code="wrong_media_args",
                failure_type="wrong_media_args",
                message="媒体生成缺少 prompt/text 参数",
                step_index=node.step_index,
                severity="fail",
                score=2.0,
                source="multimodal_step",
                tool_name=tool or node.tool_name,
            )
        )
    unsafe = bool(args.get("allow_nsfw")) or "nsfw" in prompt.lower()
    if unsafe:
        out.append(
            CheckFinding(
                code="unsafe_media",
                failure_type="unsafe_media",
                message="生成参数或 prompt 指示不安全媒体内容",
                step_index=node.step_index,
                severity="fail",
                score=1.0,
                source="multimodal_step",
                tool_name=tool or node.tool_name,
            )
        )
    if not artifacts:
        out.append(
            CheckFinding(
                code="wrong_media_args",
                failure_type="wrong_media_args",
                message="生成步未挂接 artifacts[]（缺少 ArtifactRef）",
                step_index=node.step_index,
                severity="fail",
                score=2.5,
                source="multimodal_step",
                tool_name=tool or node.tool_name,
            )
        )
    return out


def _reference_tokens(artifacts: list[ArtifactRef]) -> set[str]:
    tokens: set[str] = set()
    for artifact in artifacts:
        for value in (
            artifact.id,
            artifact.sha256,
            artifact.uri,
            Path(artifact.uri).name,
        ):
            text = str(value or "").strip().lower()
            if text:
                tokens.add(text)
    return tokens


def _check_describe_step(
    node: StepNode,
    tool: str,
    artifacts: list[ArtifactRef],
    known_tokens: set[str],
) -> list[CheckFinding]:
    out: list[CheckFinding] = []
    args = node.tool_args if isinstance(node.tool_args, dict) else {}
    ref = str(
        args.get("image_id")
        or args.get("artifact_id")
        or args.get("path")
        or args.get("sha256")
        or ""
    ).strip()
    if not ref and not artifacts:
        out.append(
            CheckFinding(
                code="wrong_media_args",
                failure_type="wrong_media_args",
                message="describe_image 未指定 image/artifact 路径或 id",
                step_index=node.step_index,
                severity="fail",
                score=2.0,
                source="multimodal_step",
                tool_name=tool or node.tool_name,
            )
        )
    elif ref and known_tokens and not _ref_matches(ref, known_tokens, artifacts):
        if not artifacts:
            out.append(
                CheckFinding(
                    code="ungrounded_vision",
                    failure_type="ungrounded_vision",
                    message=f"读图引用 {ref!r} 未对应已知 artifact",
                    step_index=node.step_index,
                    severity="fail",
                    score=2.0,
                    source="multimodal_step",
                    tool_name=tool or node.tool_name,
                )
            )
    return out


def _ref_matches(ref: str, known_tokens: set[str], artifacts: list[ArtifactRef]) -> bool:
    key = ref.strip().lower()
    if key in known_tokens or key in _reference_tokens(artifacts):
        return True
    return any(artifact.uri.lower().endswith(key) for artifact in artifacts)


def _check_final_grounding(
    node: StepNode,
    generated_tokens: set[str],
    dag: StepsDAG,
) -> list[CheckFinding]:
    """终态若声称依赖图片但未引用 artifact 的 uri/sha256，则记 ungrounded_vision。"""
    content = (node.content or dag.final_answer or "").lower()
    if not generated_tokens:
        return []
    claims_vision = any(
        h in content for h in ("图", "图片", "截图", "image", "artifact", "照片")
    )
    if not claims_vision:
        return []
    if _text_mentions_artifact(content, generated_tokens):
        return []
    for prev in dag.nodes:
        if prev.step_index >= node.step_index:
            continue
        blob = (prev.tool_result or prev.content or "").lower()
        if _text_mentions_artifact(blob, generated_tokens):
            if not _looks_hallucinated_caption(content, blob):
                return []
    return [
        CheckFinding(
            code="ungrounded_vision",
            failure_type="ungrounded_vision",
            message="最终答复声称依赖视觉证据，但未引用 artifact uri 或 sha256",
            step_index=node.step_index,
            severity="fail",
            score=2.0,
            source="multimodal_step",
            tool_name=None,
        )
    ]


def _text_mentions_artifact(text: str, tokens: set[str]) -> bool:
    lowered = text.lower()
    return any(token and token in lowered for token in tokens)


def _looks_hallucinated_caption(final: str, observation: str) -> bool:
    """极简启发式：终态含 'hallucinat' 或明确编造标记。"""
    if "hallucin" in final or "编造" in final:
        return True
    return False


def process_quality_from_report(
    report: Any,
    *,
    case_id: str = "",
    multimodal_findings: Sequence[CheckFinding] = (),
) -> dict[str, Any]:
    """把 Process Reward 报告收成 release-audit 可用的 process_quality 证据块。"""
    findings = [f.to_dict() for f in multimodal_findings]
    # 没有任何步骤被评分时，0.0 会被读成「最差」；这里显式给 None（未评）。
    scored_overall = report.overall_score if report.num_scored else None
    cases = [
        {
            "case_id": case_id,
            "score": scored_overall,
            "process_overall_score": scored_overall,
            "tools": [s.tool_name for s in report.per_step if s.tool_name],
            "check_findings": list(report.check_findings or []) + findings,
            "failed_steps": [
                {
                    "step_index": s.step_index,
                    "tool_name": s.tool_name,
                    "score": s.step_score,
                    "failure_type": s.failure_type,
                }
                for s in report.per_step
                if s.needs_revision
            ],
        }
    ]
    return {
        "metric": "process_reward_multimodal_steps",
        "overall_score": scored_overall,
        # 口径标注（D2）：这里是「全部已评分步的加权均值」，与门禁用的
        # 「媒体步 min」不是同一个数，勿混用。
        "overall_score_scope": "all_scored_steps_weighted",
        "cases": cases,
        "multimodal_step_findings": findings,
    }
