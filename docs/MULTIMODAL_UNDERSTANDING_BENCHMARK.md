# 理解侧多模态 Benchmark 数据集

## 定位

补充生成侧（文生图 / 文生视频）之外的 **理解侧** 评测数据：

| 套件 | 规模 | 任务 | 对标风格 |
|------|------|------|----------|
| Image VQA | 40 | OCR / 计数 / 空间 / 属性 / 场景 / 图表 / 文档 / 推理 | MMMU-lite、OCR-VQA |
| Video QA | 30 | 动作 / 时序 / 计数 / 运镜 / 空间 / 因果 / 场景 | Video-MME、MVBench |

媒体以 `media_uri` + `media_description` 引用形式入库，**不托管**大规模原图/原视频二进制。CI 校验契约与切分隔离；线上 VLM 评测时把 `media_uri` 换成真实文件即可。

## API

```python
from eval_engine.multimodal import (
    build_image_vqa_dataset,
    build_video_qa_dataset,
    image_vqa_dataset_manifest,
    video_qa_dataset_manifest,
    evaluate_understanding_predictions,
)

image_cases = build_image_vqa_dataset()
video_cases = build_video_qa_dataset()
image_vqa_dataset_manifest(image_cases)
video_qa_dataset_manifest(video_cases)
report = evaluate_understanding_predictions(
    image_cases,
    {"img-vqa-01": "Acme"},
)
```

## 运行

```bash
PYTHONPATH=src python examples/run_understanding_benchmark.py --out reports/understanding-benchmark
```

## 与 generation 双轨、offline_real

理解侧不再停在 `reference_only` 契约。请与生成侧分开跑：

```bash
PYTHONPATH=src python examples/run_multimodal_offline_tracks.py \
  --out reports/multimodal-offline-tracks
```

| 轨道 | offline_level 条件 | 不含什么 |
|------|-------------------|----------|
| generation | 图像自动证据 + 视频 `video_completion_gate` 通过 | 图像双人盲评偏好结论 |
| understanding | 物化 PNG/MP4 + 两路本地 reader + held_out | 托管 MMMU/Video-MME 官方榜 |

## 边界

- 这是项目自建探针集，不是 MMMU / Video-MME 官方数据镜像。
- Oracle/sidecar 满分只证明计分器与物化媒体接线，不证明前沿 VLM 能力。
- 本地 synthetic 渲染可达到 track 级 `offline_real`；GPU diffusion / 校准 VLM 仍是独立证据。
