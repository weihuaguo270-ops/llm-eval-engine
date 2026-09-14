# 生成侧正式评测（需 GPU）

本 Cloud Agent / CPU 机：**NO_GPU、无 torch**，不能跑正式 Diffusers 出图/出视频。  
理解侧 DeepSeek-V4.1-Flash 不依赖 GPU，已在无卡环境跑通 `offline_real`。

## 门禁对照

| 轨道 | 正式脚本 | 本机 | GPU 机 |
|------|----------|------|--------|
| 理解 | `run_real_understanding_benchmark.py` + `deepseek_vision` | ✅ 可跑 | ✅ |
| 文生图 | `run_real_image_benchmark.py` | ❌ NO_GPU | ✅ Diffusers + CLIP/安全 |
| 文生视频 | `run_real_video_benchmark.py` | ❌ NO_GPU | ✅ 真 MP4 |

图像发布级结论额外需要人工盲评（`prepare-review` / panel → `finalize`）。

## GPU 机依赖

```bash
nvidia-smi
pip install '.[multimodal]'   # torch / diffusers / transformers / CLIP 等
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
# 人工盲评填写后：
python examples/run_real_image_benchmark.py finalize --output "$OUT"
```

自动阶段通过 → `completion_gate.evidence_level=offline_real`（偏好结论仍等盲评）。

## 文生视频

```bash
export PYTHONPATH=src
OUT=/tmp/real-video-gpu

python examples/run_real_video_benchmark.py init --output "$OUT"
python examples/run_real_video_benchmark.py generate --output "$OUT"
python examples/run_real_video_benchmark.py score --output "$OUT"
python examples/run_real_video_benchmark.py finalize --output "$OUT"
```

## 证据边界

- GPU Diffusers 真出图/出视频 + CLIP/安全 = 生成侧 `offline_real`
- 图像发布级偏好 = 还需盲评完成
- 不得用 synthetic/sidecar 媒体冒充 Diffusers 产物
- ModelScope 等非商用许可证模型仅作研究对比
