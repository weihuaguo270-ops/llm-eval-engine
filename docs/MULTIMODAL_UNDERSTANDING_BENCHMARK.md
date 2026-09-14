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

## 边界

- 这是项目自建探针集，不是 MMMU / Video-MME 官方数据镜像。
- Oracle 满分只证明计分器接线，不证明模型能力。
- 发布门禁若要纳入理解列，需另接真实 VLM 预测与 held-out 报告。
