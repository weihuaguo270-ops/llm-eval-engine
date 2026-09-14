# 理解侧多模态 Benchmark

## 定位

补充生成侧（文生图 / 文生视频）之外的 **理解侧** 评测：

| 套件 | 规模 | 任务 | 对标风格 |
|------|------|------|----------|
| Image VQA | 40 | OCR / 计数 / 空间 / 属性 / 场景 / 图表 / 文档 / 推理 | MMMU-lite、OCR-VQA |
| Video QA | 30 | 动作 / 时序 / 计数 / 运镜 / 空间 / 因果 / 场景 | Video-MME、MVBench |

数据集契约以 `media_uri` + `media_description` 入库；正式跑分前必须 **物化真实 PNG/MP4**，再用预测器产出答案。

## 正式流水线（对齐生成侧）

生成侧正式脚本：

- `examples/run_real_image_benchmark.py` — init → generate → score →（人工盲评）→ finalize
- `examples/run_real_video_benchmark.py` — init → generate → score → finalize

理解侧正式脚本：

```bash
PYTHONPATH=src python examples/run_real_understanding_benchmark.py init --output /tmp/u
PYTHONPATH=src python examples/run_real_understanding_benchmark.py materialize --output /tmp/u
PYTHONPATH=src python examples/run_real_understanding_benchmark.py predict --output /tmp/u
PYTHONPATH=src python examples/run_real_understanding_benchmark.py score --output /tmp/u
PYTHONPATH=src python examples/run_real_understanding_benchmark.py finalize --output /tmp/u
```

阶段含义：

| 阶段 | 产物 | 说明 |
|------|------|------|
| init | `dataset.json` | 冻结 Image VQA / Video QA 契约与默认模型表 |
| materialize | `materialized.json` + PNG/MP4 | 把 `media_uri` 换成真实媒体；视频附带 `preview_frame_uri` |
| predict | `prediction_records.json` | 真实 VLM / Video-LLM（或本地 sidecar 接线）预测 |
| score | 写入 `automatic_metrics` | `score_understanding_answer` |
| finalize | held-out 报告 + evidence | `evaluate_understanding_predictions` → `offline_real` 门禁 + release 证据 |

Smoke 子集：各阶段加 `--smoke`（每模态 1 条 + 1 条 held_out）。

### 预测器适配器

默认本地 sidecar（验证媒体 + 计分接线）：

```bash
# 默认 adapter=sidecar / noisy_sidecar
PYTHONPATH=src python examples/run_real_understanding_benchmark.py predict --output /tmp/u
```

切换真实模型：

```bash
# OpenAI-compatible vision（需 OPENAI_API_KEY）；视频用 preview frame
PYTHONPATH=src python examples/run_real_understanding_benchmark.py predict \
  --output /tmp/u \
  --adapter sidecar-reader=openai_vision

Override remaps `local/sidecar-reader` → `openai/gpt-4o-mini` in prediction records and held-out reports; claim_boundary comes from the OpenAI vision adapter (not sidecar-only).

# Hugging Face VLM（需 CUDA + transformers）
PYTHONPATH=src python examples/run_real_understanding_benchmark.py predict \
  --output /tmp/u \
  --adapter sidecar-reader=hf_vlm
```

工厂入口：`build_understanding_predictor(adapter=..., model_id=...)`。

### Release evidence

`finalize` 写出 `multimodal_understanding_evidence.json`（schema `multimodal-understanding-evidence/v1`），可喂给：

```python
from eval_engine.gates import evaluate_evidence_bundle

evaluate_evidence_bundle(
    episodes=...,
    multimodal_understanding=evidence,
    dataset_audit=dataset_audit,
)
```

held-out 报告由 `build_held_out_understanding_report(...)` 生成；只有 track 达 `offline_real` 且图/视频 held-out 完整时 evidence 为 `pass`。

## 契约 / Oracle 快速检查

仅校验数据集契约与计分器（不算真实模型评测）：

```bash
PYTHONPATH=src python examples/run_understanding_benchmark.py --out reports/understanding-benchmark
```

```python
from eval_engine.multimodal import (
    build_image_vqa_dataset,
    build_video_qa_dataset,
    evaluate_understanding_predictions,
)

report = evaluate_understanding_predictions(
    build_image_vqa_dataset(),
    {"img-vqa-01": "Acme"},
)
```

## 双轨 offline_real 快捷入口

```bash
PYTHONPATH=src python examples/run_multimodal_offline_tracks.py \
  --out reports/multimodal-offline-tracks
```

| 轨道 | evidence_level 条件 | 不含什么 |
|------|-------------------|----------|
| generation | 图像自动证据 + 视频 `video_completion_gate` 通过 | 图像双人盲评偏好结论 |
| understanding | 物化 PNG/MP4 + 预测器 + held_out | 托管 MMMU/Video-MME 官方榜 |

## 边界

- 这是项目自建探针集，不是 MMMU / Video-MME 官方数据镜像。
- Sidecar/oracle 满分只证明计分器与物化媒体接线；能力结论需要 `openai_vision` / `hf_vlm`（或自研 Video-LLM）预测。
- 本地 synthetic 渲染可达到 track 级 `offline_real`；GPU diffusion / 校准 VLM 仍是独立证据。


## DeepSeek-V4.1-Flash（推荐无 GPU 真模型路径）

```bash
export DEEPSEEK_API_KEY=...
PYTHONPATH=src python examples/run_real_understanding_benchmark.py init --output /tmp/u-ds
PYTHONPATH=src python examples/run_real_understanding_benchmark.py materialize --output /tmp/u-ds
PYTHONPATH=src python examples/run_real_understanding_benchmark.py predict \
  --output /tmp/u-ds --adapter sidecar-reader=deepseek_vision
PYTHONPATH=src python examples/run_real_understanding_benchmark.py score --output /tmp/u-ds
PYTHONPATH=src python examples/run_real_understanding_benchmark.py finalize --output /tmp/u-ds
```

记录中的 `primary_model` 应为 `deepseek/deepseek-flash`，`claim_boundary` 来自 DeepSeek 视觉适配器。


## 生成侧（需 GPU）

正式 Diffusers 出图/出视频见 [`GENERATION_GPU_RUNBOOK.md`](GENERATION_GPU_RUNBOOK.md)。本 Cloud Agent 为 NO_GPU，不能替代 GPU 机上的 `run_real_image_benchmark.py` / `run_real_video_benchmark.py`。
