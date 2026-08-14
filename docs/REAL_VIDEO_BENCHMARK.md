# 真实视频模型横向评测

## 当前结果

- 固定 30 条文本生成视频 Prompt：dev 6 / golden 15 / held-out 9。
- 对比 `Wan-AI/Wan2.1-T2V-1.3B-Diffusers`（Apache-2.0）和
  `damo-vilab/text-to-video-ms-1.7b`（CC-BY-NC-4.0，仅研究对比）。
- 生成配置为 9 帧、256x256、8 fps；每个模型各 30 条，输出 MP4、commit SHA、seed、延迟和 SHA-256。
- 自动指标取首/中/末帧的 CLIP 文本一致性、相邻帧平均变化和时序一致性，并对采样帧执行 NSFW 分类。

## 运行

```powershell
$env:PYTHONPATH='src'
$env:HF_HOME='D:\agent_learning\gpu-evidence\hf-cache'
$python='D:\agent_learning\.venv-inference\Scripts\python.exe'
$out=Join-Path (Split-Path -Parent $PWD) 'test-temp\real-video-benchmark'

& $python examples/run_real_video_benchmark.py init --output $out
& $python examples/run_real_video_benchmark.py generate --output $out
& $python examples/run_real_video_benchmark.py score --output $out
& $python examples/run_real_video_benchmark.py finalize --output $out
```

## 证据边界

当前全量报告的门禁为 `offline_real`，表示真实模型、真实 MP4 和自动指标已完成离线验证；不等于线上服务 SLA，也不等于人工偏好或商业授权结论。ModelScope 模型受 CC-BY-NC-4.0 限制，不能作为商业部署候选。Wan 的模型许可证、实际 commit 和 safetensors 使用情况均记录在生成记录中。
