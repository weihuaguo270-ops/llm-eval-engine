# 安全评测证据

> **2026-09-22：** 生成侧选型（文生图/文生视频横向榜、CLIP 成对选型、图像 v2 `offline_real`）已从本仓库**删除**。下文仅保留安全决策评测；勿再引用已删的图像/视频生成榜。

## 安全决策任务

冻结数据集包含 30 条策略决策任务：20 条攻击场景、10 条良性任务，按 dev 6 / golden 15 / held-out 9 切分。攻击场景覆盖间接提示注入、秘密泄露、破坏性操作、权限提升和外部副作用。运行器调用 `deepseek-v4-flash`，只要求模型输出授权决策，不执行任何工具。

入口：`examples/run_real_safety_benchmark.py`  
快照：`examples/fixtures/real_safety_benchmark_20260813.json`

## 与主线的关系

发布主结论走轨迹过程评测（`run_release_audit.py`）与理解侧 VQA。安全门禁是独立证据栏，不与已删除的生成选型混引为同一 SLA。
