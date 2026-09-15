# 生成侧正式评测（需 GPU）

理解侧 DeepSeek-V4.1-Flash 不依赖 GPU，已跑通 `offline_real`。

**本机 Windows GPU（2026-09-14/15）：** RTX 4060 Laptop 8GB + `D:\agent_learning\.venv-inference`，
图像 v2 面板盲评与视频全量（CogVideoX-2b INT8 + ModelScope）均已达到 `offline_real`。
Cloud Agent / 无 CUDA 环境仍 fail-closed（`NO_GPU`）。

## 门禁对照

| 轨道 | 正式脚本 | 无 GPU 机 | 本机 GPU（已跑） |
|------|----------|-----------|------------------|
| 理解 | `run_real_understanding_benchmark.py` + `deepseek_vision` | ✅ | ✅ |
| 文生图 | `run_real_image_benchmark.py` | ❌ NO_GPU | ✅ Diffusers + CLIP/安全 + **面板盲评** → `offline_real` |
| 文生视频 | `run_real_video_benchmark.py` | ❌ NO_GPU | ✅ CogVideoX-2b INT8 + ModelScope → `offline_real` |

图像发布级偏好需要人工盲评（`prepare-review` / panel → `finalize`）；v2 已完成。视频门禁不要求人工偏好。

## GPU 机依赖

```bash
nvidia-smi
pip install '.[multimodal]'   # torch / diffusers / transformers / CLIP 等
# 视频 CogVideoX 额外：torchao sentencepiece protobuf
```

`require_cuda_for_generation()` 在加载权重前 fail-closed；无 CUDA 会明确报 `NO_GPU`。

## 文生图

```bash
export PYTHONPATH=src
OUT=/tmp/real-image-gpu

python examples/run_real_image_benchmark.py init --output "$OUT"
python examples/run_real_image_benchmark.py generate --output "$OUT"          # 或 --smoke
python examples/run_real_image_benchmark.py score --output "$OUT"
python examples/run_real_image_benchmark.py prepare-review --output "$OUT"
# 人工盲评 / panel 填写后：
python examples/run_real_image_benchmark.py finalize --output "$OUT"
```

自动 + 有效盲评协议通过 → `completion_gate.evidence_level=offline_real`。

## 文生视频

选型见 [`REAL_VIDEO_MODEL_SELECTION.md`](REAL_VIDEO_MODEL_SELECTION.md)；本机证据见 [`REAL_VIDEO_BENCHMARK.md`](REAL_VIDEO_BENCHMARK.md)。

```bash
export PYTHONPATH=src
OUT=/tmp/real-video-gpu

python examples/run_real_video_benchmark.py init --output "$OUT"
python examples/run_real_video_benchmark.py generate --output "$OUT"
python examples/run_real_video_benchmark.py score --output "$OUT"
python examples/run_real_video_benchmark.py finalize --output "$OUT"
```

## 证据边界

- GPU Diffusers 真出图/出视频 + CLIP/安全（+ 图像盲评）= 生成侧 `offline_real`
- CogVideoX INT8+offload 为部署态声明，≠ 全精度 / 5B 基线
- 不得用 synthetic/sidecar 媒体冒充 Diffusers 产物
- ModelScope 等非商用许可证模型仅作研究对比
