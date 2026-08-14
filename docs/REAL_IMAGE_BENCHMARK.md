# 真实图像模型横向评测

## 当前实验

- 数据：100 个项目自建 Prompt，dev 20 / golden 50 / held-out 30，来源簇不跨切分；
- 模型：`stable-diffusion-v1-5/stable-diffusion-v1-5` 与 `stabilityai/sd-turbo`，记录固定 Hugging Face commit SHA，并强制使用 safetensors；
- 输出：200 张 512x512 PNG，逐张保存 SHA-256、seed、生成配置、延迟和显卡信息；
- 自动指标：CLIP 文图余弦相似度、NSFW 分类器、成对 bootstrap 95% CI；
- 人工指标：100 组随机 A/B 独立盲评，覆盖 Prompt 遵循、视觉质量、整体偏好和安全。
  当前采用一名全量评分者与五名分块评分者组成的面板，不表述为“两名全量评分者”。

## 已完成结果

| 模型 | 样本 | 平均 CLIP | 平均延迟 | P95 延迟 | 安全通过率 |
|---|---:|---:|---:|---:|---:|
| SD-Turbo | 100 | 0.330860 | 473.260 ms | 1012.648 ms | 100% |
| SD v1.5 | 100 | 0.326175 | 3587.011 ms | 4929.311 ms | 100% |

两模型 CLIP 均值差为 0.004685，bootstrap 95% CI 为 [-0.000299, 0.009790]，
区间跨 0，自动指标不能证明某一模型总体显著更好。

旧版 Tiny-SD 与 SD-Turbo 的实验只能作为一次被供应链门禁淘汰的历史运行，不能用于当前发布结论。

## 运行

```powershell
$env:PYTHONPATH='src'
$env:HF_HOME='D:\agent_learning\gpu-evidence\hf-cache'
$python='D:\agent_learning\.venv-inference\Scripts\python.exe'
$out=Join-Path (Split-Path -Parent $PWD) 'test-temp\real-image-benchmark-v2'

& $python examples/run_real_image_benchmark.py init --output $out
& $python examples/run_real_image_benchmark.py generate --output $out
& $python examples/run_real_image_benchmark.py score --output $out
& $python examples/run_real_image_benchmark.py prepare-review --output $out
& $python examples/run_real_image_benchmark.py prepare-panel --output $out
```

## 分块人工面板

全量评分者已经完成 100 条；第一名面板评分者完成并冻结 20 条。其余 80 条按类别、风格和
golden/held-out 比例拆成四组。每名新志愿者填写 20 条独占目标题与 5 条公共校准题，共 25 条。
分配清单位于 `$out\panel_review_manifest.json`，工作表位于 `$out\panel\`。

门禁要求目标题恰好覆盖 100 条且无重复、所有校准题完成、评分者 ID 相互独立。报告输出
逐样本偏好一致率、nominal Krippendorff alpha、分块一致率和校准题一致率。该协议的准确口径是
“一名全量评分者 + 五名分块面板评分者”，不是“两名评分者各填 100 条”。

完成后执行：

```powershell
& $python examples/run_real_image_benchmark.py finalize --output $out
```

## 证据边界

当前 200 张真实生成、自动指标和 held-out 分析已经完成，但分块人工面板尚未全部填写，所以
图像人工偏好门禁仍为失败。安全结果只覆盖良性 Prompt 的输出内容，
不等同于多模态红队攻击评测。

当前生成器设置 `use_safetensors=True`，只接受 safetensors 权重。模型仓库仍需结合许可证、
commit 固定和依赖扫描进行供应链审计；文件格式本身不代表模型绝对可信。
