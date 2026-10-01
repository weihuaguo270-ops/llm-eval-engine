# 检索步过程维度：独立 κ 分栏登记（2026-10-01）

> **这不是一次校准运行的快照。** 本文件登记的是一个**新分栏**及其当前状态，
> 其中**没有任何 κ 数值**，因为尚无 held-out 人工校准样本。
> 补齐后应另写 `calibration_snapshot_YYYYMMDD_search_*.md`。

## 1. 为什么新开一栏（而不是并进主钉）

[`METRICS_TRUST.md`](METRICS_TRUST.md) 已把多模态主钉的 κ 单位**钉死**：

| 项 | 规定 |
|---|---|
| 主单位 | `dimension_cell = episode × media/final step × dimension` |
| 不是 | 按轨迹聚合的过程分（该分只进发布门禁，不进 κ） |
| 并列报告 | `sample_size` = cell n；`episode_count` = 独立轨迹数 |

把检索步维度并进那一栏会**改变 κ 的分母定义**，等于同时作废现有 0.70 / 0.62
主钉与新增证据。因此检索步走独立分栏。

## 2. 本分栏的定义

| 项 | 值 |
|---|---|
| `kappa_unit` | `search_dimension_cell` = `episode × search step × dimension` |
| `dimensions` | `query_quality` / `result_utilization` / `fallback_behavior` / `citation_grounding` |
| `gate_split` | `held_out` |
| `threshold` | `0.6`（与主钉同一门槛语义：κ < 0.6 表示口径未写好，先改 rubric） |
| 状态 | **`uncalibrated`**（缺 held-out 人工校准样本） |

**禁止**与文本 Judge κ、多模态 `dimension_cell` 合成"一个总分"；引用时必须分栏，
并各自报 cell n 与 `episode_count`。

## 3. 实现落点

| 位置 | 职责 |
|---|---|
| `src/eval_engine/core/search_step.py` | 检索步工具名分派（`is_search_tool` / `is_search_step`）+ 四维定义与判定标准 |
| `src/eval_engine/gates/search_calibration.py` | 分栏构造：`search_calibration_column(rows)`；无样本返回 `status="uncalibrated"` |
| `src/eval_engine/core/failure_taxonomy.py` | 检索步**确定性**失败类型：`search_empty` / `search_weak` / `search_timeout` |
| `src/eval_engine/core/dynamic_rubric.py` | docstring §实现状态：明确检索步维度**未实现**（原先只有示意） |

### 与既有维度的边界（防重复打分）

- `citation_grounding` 只判"引用与本步返回结果的对应关系"；
  **答案级**忠实度（是否添加观测中没有的结论）仍归 `context_faithfulness`。
- 检索步判的是**动作与结果处理质量**，不是"搜索结果的内容相关度"。
  对外表述必须区分这两件事。

## 4. 当前状态与证据级别

- **证据级别：`missing`（无实现级数据）→ 分栏已就绪，但无样本。**
  按 [`ROLE_COVERAGE_ROADMAP.md`](ROLE_COVERAGE_ROADMAP.md) 的五级证据制，
  本栏在拿到 `offline_real` 之前**不得写入简历、不得对客户或面试官引用**。
- 确定性失败归因已打通（`search_empty` 等不再落 `wrong_tool` / `other`），
  这属于**归因**改进，不构成本分栏的 κ 证据。

## 5. 补齐路径（拿到数据后怎么做）

需要的数据行（`run_calibration` 风格，每行 = 一个检索步维度单元格）：

```
episode_id, step_index, dimension, split="held_out",
human_score, judge_score, id(可选)
```

- `dimension` 必须属于上面四维；传入媒体维度会**直接抛错**（分栏隔离约束）。
- 同一来源簇（站点/域名）不得跨 dev 与 held_out。
- 第二标注者盲评（不得先看 human_score / judge_score），协议见
  [`SECOND_RATER_PROTOCOL.md`](SECOND_RATER_PROTOCOL.md)。

补齐后：

1. 用 `search_calibration_column(rows)` 出分栏结果（`agreement_table` +
   `bootstrap_ci`，与 `run_calibration.py` 同一套 helper）；
2. 另写一份带日期的快照，写明样本量、日期、模型/工具版本、CI；
3. 再更新 [`STATUS.md`](STATUS.md) / [`METRICS_TRUST.md`](METRICS_TRUST.md)
   的对外口径——**这一步做完之前，不得引用任何 κ**。

## 6. 口径红线

- 无样本 ⇒ 不报数（本文件即示例：状态可见、数值为空）。
- 小样本 ⇒ 必须报 95% CI，不报单点；CI 很宽时只作趋势证据。
- 不把"分栏已建立"表述为"已完成检索维度校准"。
- 不与主钉合成总分，不把 offline 结果表述为线上 SLA。
