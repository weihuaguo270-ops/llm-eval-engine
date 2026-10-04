# 预注册（prereg）

`docs/EVAL_DESIGN.md` §3.3 第 6 条要求：**每批配额内那一次 adopt 级对照，必须先有一份预注册文件**，
并由 `src/eval_engine/judge/variant_ledger.py` **机器强制**——
缺文件 / 字段不全 / 指纹不匹配 / 写就时间在未来 → 拒绝运行（退出码 2，且在调用 Judge LLM **之前**）。

## 命名与落点

- 命名：`<batch>_<variant_sha16>.json`（batch 里的 `/` 会被换成 `_`），
  由 `variant_ledger.prereg_path()` 生成；也可用 `run_calibration.py --prereg <file>` 指定别处。
- 本目录**刻意放在入库跟踪的包数据下**，而不是 `reports/`——后者被 `.gitignore` 忽略，
  放那儿等于预注册进不了仓库，外部就无法验证"它早于那次 live 运行"。
- 账本 `dataset/data/rubric_variant_ledger.json` 记录本文件的 **sha256**：
  一旦冻结，之后被改动或删除 → 该 comparison 臂复现时**拒绝**。

## 必须字段

见 `variant_ledger.validate_prereg()`：

| 字段 | 作用 |
|---|---|
| `batch` | 必须与本次批次标识一致（防止把别批的预注册拿来用） |
| `baseline_sha16` | 必须等于账本记录的基线指纹 |
| `variant_sha16` | **必须等于本次要跑的指纹**（预注册与实验的绑定） |
| `hypothesis` | 一句话：这次改动预期改变什么 |
| `predicted_direction` | 预测方向/幅度 |
| `decision_rule.primary` | 采纳判据 |
| `negative_result_action` | 未通过时怎么办 |
| `frozen_at` | 写就时间（不得晚于运行、不得在未来） |

## 已有的预注册

- `calibration_human_judge@v5_held_out_b1475b3e81f5e1d4.json` — 路线乙那**一次**对照
  （基线 v2.1 `0a780f5ad7916440` → 变体 v2.1.1）。
  **结论：未采纳**（三项统计量配对置换 p 全为 1.0；2 条变动均属与改动无关），
  `SCALE_ANCHORS` 已**逐字节回滚**到 v2.1。
  本文件**保留**为该批"配额已用 + 预注册内容"的凭证，不随回滚删除
  （账本按 sha256 引用它）。见 [`docs/NEGATIVE_RESULTS.md`](../../../../../docs/NEGATIVE_RESULTS.md)。
