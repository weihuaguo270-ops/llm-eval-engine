"""把**描述符表**渲染成 judge 提示词（L1）。

**为什么要有这一层**：判据一旦同时存在于"散文式裁决"和"提示词"两处，就会漂移。
本模块以 `dataset/data/rubric_descriptors_line1.json` 为**单一来源**，渲染出 judge 实际读到的文本；
`examples/run_calibration.py` 用渲染结果做提示词，并对**渲染结果**取指纹（漂移测试锁定）。

形状取自业界共识（criteria × performance levels × descriptors）：
- CMU Eberly Center：rubric = criteria / descriptors / performance levels；
- Prometheus 2：`a description for the criterion itself and a set of descriptions for each score`；
- Vertex AI：`Rating Rubric — scoring scale ... with explanations about the meaning of each score`。

**弃权**（abstention）按 Inspect AI 的记账方式：判不出来时给 null，**从指标中剔除**，coverage 单列；
不得用中位数或任一档顶替。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

_DEFAULT = Path(__file__).resolve().parents[1] / "dataset" / "data" / "rubric_descriptors_line1.json"

__all__ = ["load_descriptors", "render_scale_anchors", "abstention_json_hint"]


def load_descriptors(path: Optional[Path] = None) -> dict[str, Any]:
    return json.loads(Path(path or _DEFAULT).read_text(encoding="utf-8"))


def render_scale_anchors(descriptors: Optional[dict[str, Any]] = None) -> str:
    """渲染 judge 提示词里的评分刻度段（含每个 criterion 的 1–5 描述 + 弃权通道）。"""
    d = descriptors or load_descriptors()
    scale = d["scale"]
    lines = [
        f"评分刻度（每个 criterion 各自 {scale['min']}–{scale['max']}；{scale['direction']}）",
        f"规则：{scale['rule']}",
        "",
    ]
    for name, spec in d["criteria"].items():
        lines.append(f"【{name}｜{spec.get('zh', '')}】")
        for level in sorted(spec["levels"], key=lambda x: int(x)):
            lines.append(f"{level} = {spec['levels'][level]}")
        lines.append("")
    ab = d["abstention"]
    lines += [
        "无法判定（**不是分数**）：",
        f"- 触发条件：{ab['when']}",
        f"- 输出方式：{ab['channel']}；**{ab['must_not']}**",
        f"- 记账：{ab['accounting']}",
        "",
    ]
    if d.get("shared_rules"):
        lines.append("共用规则：")
        lines += [f"- {r}" for r in d["shared_rules"]]
    return "\n".join(lines).strip() + "\n"


def abstention_json_hint() -> str:
    """给 judge 的输出格式提示（含弃权分支）。"""
    return (
        '只输出 JSON：{"score": <1-5整数>, "abstain": false, "reason": "..."}\n'
        '若材料不足以判定，输出 {"score": null, "abstain": true, "reason": "..."}——**不要猜**。'
    )
