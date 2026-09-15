# 真实视频模型横向评测

## 当前结果（2026-09-15）

正式证据目录：`test-temp/real-video-local-full`。

- 固定 30 条文本生成视频 Prompt：dev 6 / golden 15 / held-out 9。
- 证据轨对比（见 `REAL_VIDEO_MODEL_SELECTION.md`）：优先 `THUDM/CogVideoX-5b`；
  **本机 Phase 1 已跑通 Apache-2.0 回退 `THUDM/CogVideoX-2b`**（torchao INT8 + model CPU offload + VAE tiling/slicing）
  对比 `damo-vilab/text-to-video-ms-1.7b`（CC-BY-NC-4.0，仅研究）。Wan2.1-1.3B 降为可选 smoke baseline（本机 UMT5 加载峰值内存不足，未纳入正式全量）。
- CogVideoX 默认 17 帧、512×320；ModelScope 9 帧、256×256；各 30 条，输出 MP4、
  commit/revision、seed、延迟、峰值显存与 SHA-256。
- 自动指标取首/中/末帧的 CLIP 文本一致性、相邻帧平均变化和时序一致性，并对采样帧执行 NSFW 分类。

| 模型 | 样本 | 平均 CLIP 帧相似 | 平均时序一致性 | 峰值显存（记录） | 安全通过 |
|---|---:|---:|---:|---:|---:|
| CogVideoX-2b（INT8+offload） | 30 | 0.282791 | 0.831728 | ≈9154 MB | 见逐条记录 |
| ModelScope T2V 1.7b | 30 | 0.246018 | 0.884062 | ≈3095 MB | 见逐条记录 |

| 门禁 | 值 |
|---|---|
| `completion_gate.passed` | true |
| `evidence_level` | `offline_real` |
| 记录数 | 60 |

## 运行

```powershell
$env:PYTHONPATH='src'
$env:HF_HOME='D:\agent_learning\gpu-evidence\hf-cache'
$python='D:\agent_learning\.venv-inference\Scripts\python.exe'
$out=Join-Path (Split-Path -Parent $PWD) 'test-temp\real-video-local-full'

& $python examples/run_real_video_benchmark.py init --output $out
& $python examples/run_real_video_benchmark.py generate --output $out
& $python examples/run_real_video_benchmark.py score --output $out
& $python examples/run_real_video_benchmark.py finalize --output $out
```

CogVideoX 权重可通过镜像落到本地目录，并用环境变量 `COGVIDEOX_LOCAL_DIR` 指向含 `model_index.json` 的目录以离线加载。依赖含 `torchao`、`sentencepiece`、`protobuf`。

## 证据边界

当前全量报告的门禁为 `offline_real`，表示真实模型、真实 MP4 和自动指标已完成离线验证；不等于线上服务 SLA，也不等于人工偏好或商业授权结论。ModelScope 受 CC-BY-NC-4.0 限制，不能作为商业部署候选。CogVideoX INT8+offload 是**部署态**声明，不得静默等同全精度 bf16 / 未量化 5B 质量；许可证、量化与 offload 标志记在 `generation_config`。
