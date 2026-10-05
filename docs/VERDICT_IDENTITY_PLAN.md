# 判定标准身份计划（VERDICT IDENTITY PLAN）

> **状态：部分实施 —— P0–P3 已落地，P4 未做。** 本文件描述"要让判定标准具备可校验身份"
> 的设计与分期。当前实际行为见 [`METRICS_TRUST.md`](METRICS_TRUST.md)、
> [`EVAL_DESIGN.md`](EVAL_DESIGN.md)、[`STATUS.md`](STATUS.md)；
> **P0–P3 的落地记录依次见 §5.1 / §5.2 / §5.3 / §5.4**。
>
> **命名约定**：标识符均为仓库中既有（提交前已逐一核对）；P1 之前标 `拟新增` 的对象
> （如 `bands_identity`）**已随 P1 落地**，不再是纸面字段。
> 判定标准在本仓的既有叫法是**合格线**（`verdict_bands.json`、`load_bands`、`verdict_for`）。

---

## 0. 问题

> 本仓把判定绑到了**证据**上，却没绑到**判据**上，也没绑到**门禁自己的阈值**上。

`snapshots_manifest.json` 的 `note` 明写「**判定与 κ 绑定这些快照**」，并为每份快照留了 `sha256`。
合格线——判定真正依赖的那份标准——**没有对应的清单**。

### 0.1 四条实证

| # | 事实 | 出处 |
|---|---|---|
| 1 | **发布门禁不读合格线**：`src/eval_engine/gates/` 下 **0 处**引用 `bands`／`verdict`／`unbanded`／`合格线` | 全目录检索 |
| 2 | **"读不到合格线"被降级成一个判定类别，而不是失败**：缺失 → `load_bands` 返回 `{}` → `verdict_for` 给 `unbanded` → 缺陷率显示 **0**（最好看的数） | `src/eval_engine/core/verdict.py` |
| 3 | **判定脚本无条件 `return 0`**：一句合格线都没加载也只打印告警 | `scripts/result_verdict.py` |
| 4 | **没有任何跨运行比对**：报告里已有 `bands_meta`，但没有"本次 vs 上次/声明"的对比 | `scripts/result_verdict.py` |

附带：`tests/test_result_verdict.py` 断言"合格线必须留出处"，但它保护的是**那一份被跟踪的文件**；
运行时 `load_bands` **接受任意文件、不校验出处**——典型的「**只在写入端校验、读取端不校验**」。

### 0.2 外部对照的总结论

主流评测框架与发布治理体系里，**"判定标准须与结论一同发布并被核对"的统一机制，一处都没找到**：

- 五家评测框架（lm-evaluation-harness／HELM／Inspect AI／SWE-bench／OpenAI Evals）：
  **记录普遍有，强制比对与阻断一家都没有**；
- 溯源与策略即代码（SLSA／in-toto／cosign／OPA／Conftest／Kyverno）：
  有"产物↔输入绑定"与"策略版本化"的成熟做法，但**没有**把"判定标准本身"做成需与结论一并核对的对象；
- 校准与标注域（GLUE／HELM／医学 IRR）：**未找到**"指南换版后旧标注/旧阈值如何处理"的成文规范；
- 连 **GitHub 自己的"必需状态检查"配置都存在仓库设置里、不在版本控制中**，官方文档亦**未找到**
  "该配置本身可被哈希/版本化"的说法。

> 因此本计划**不主张"业界通行做法"**，只主张：这些机制的思想已被反复验证，
> 而**把它们用到"判定标准"上是缺口**。

---

## 1. 设计原则

| # | 原则 | 依据 |
|---|---|---|
| **P1** | 合格线必须有**内容身份**（规范化内层对象的 sha256） | 本仓对 Rubric 文本已有 `rubric_boundary_sha256`；**外部原型**：SLSA 把 `buildConfig` 从**内联**改为**记 digest**，并用 `resolvedDependencies[{uri, digest}]` 记录依赖 |
| **P2** | 身份必须**随数字走**（缺陷率/判定分布必须携带它依赖的身份） | 本仓「结论必须自带限定」；Krippendorff 实践要求**预设阈值并报告软件及版本** |
| **P3** | **读不到 ≠ 通过**（`unbanded` 必须能升级为失败） | 本仓「未标不得当作通过」；cosign 官方原则 *"should be designed to **fail closed rather than open**"*；SWE-bench 缺证据即 `resolved=False` |
| **P4** | **两级阻断**：身份**缺失/不一致** ⇒ `review`；**伪造/篡改** ⇒ `hold` | Kyverno `Enforce`/`Audit` 二分；dbt `severity: warn\|error`；GX `notify_on`；本仓 `schema_version` 与 calibration 两个先例 |
| **P5** | **读取端必须校验**（不能只靠测试保护某一份文件） | SLSA 明确 `externalParameters` **不可信、MUST 被下游校验** |
| **P6** | **多版本可以并存，但必须标注且跨版不可比** | 医学现实：PI-RADS 2.0 与 2.1 被直接对比、两版并存是常态 |

**P6 的作用**：防止方案走极端。本计划**不要求**"发现两版就报错"，只要求**并存必须被标注、且跨版不得合并统计**。

---

## 2. 主流对照与三档采纳

### 2.1 照抄

| 抄什么 | 出处 |
|---|---|
| **fail-closed**（缺证据/缺身份 ⇒ 不得判过） | cosign 官方原则；SWE-bench `resolved` 保持 False |
| **记 digest，不内联配置** | SLSA provenance：`buildConfig` v0.2 已移除，改为记 digest |
| **两级动作显式二分** | Kyverno `validationFailureAction: Enforce` / `Audit` |

### 2.2 改造

| 改什么 | 怎么改 |
|---|---|
| lm-eval 的 `task_hashes` | 它哈希**任务定义与样本**、用途是**事后比对**、**无门禁**；本仓改为哈希**合格线内容**并**接进阻断** |
| `snapshots_manifest.json` 的形状 | 保留 `sha256` + `note`（声明意图）＋来源声明；**去掉 `path`**——该文件在 `.gitignore` 保护的 `reports/` 下，路径不可靠，身份只能靠内容哈希 |

### 2.3 弃用

| 弃用什么 | 为什么 |
|---|---|
| SLSA 的 L1–L3 分级、DSSE/签名链、attestation 存储 | 对本仓过重；要的是"摘要 + 下游校验 + fail closed"这三个**思想**，不是整套基础设施 |
| HELM 的"5 个产物齐即完成" | 那是**完整性**，不是**一致性**；本缺陷恰恰是"东西齐了、两份东西不一致" |
| Datasheets for Datasets / Model Cards | 查实为**纯文档框架、无哈希机制**，不能当机制用（可作对外说明的**报告框架**） |
| "禁止多版并存" | 与 P6 的现实反证冲突 |

---

## 3. 失效模式自审

外部有出处的四条坑，逐条对照本方案：

| 外部失效模式 | 本方案如何防 |
|---|---|
| **只签名产物、不校验"陈述是否到达"**（删掉 attestation 即绕过） | **P5 读取端校验**；且 **P3 在"无身份"时也阻断**，而不是"有身份才查" |
| **只哈希代码、不哈希配置** | 本缺陷本身；**注意 §7 的范围问题**——只哈希合格线、漏掉门禁阈值，是同一错误的缩小版 |
| **校验做成告警而非阻断** | **P4 两级阻断**；并防"没配身份就静默放行"（OPA **未配签名则静默激活**是同构风险） |
| **策略自身缺乏完整性保护** | 验收例 ⑤：「身份与内容不符 ⇒ `hold`」 |

---

## 4. 交付物

| | 内容 | 关键决定 |
|---|---|---|
| **D1 规范** ✅ | 合格线身份：字段、哈希对象、规范化规则、**缺失语义**、**冲突语义** | 哈希**规范化后的内层**，不是整份文件。依据：本仓实测过"外壳结构不符 → 全表 `unbanded`"；那份合格线还带一段"本文件是重建版"的 `note`——**若哈希整份文件，改一句注释就会产生假的漂移**。**冲突语义**（身份与内容不符）明确**不在本层**，属 P3 |
| **D2 生成端** ✅ | 身份写进报告（`bands_identity`，**P1 已落地**） | 内容哈希承担身份；**版本号只作人类可读**（本仓自己写过："只记 v2.1 这个名字，无法证明跑的是哪个字节"） |
| **D3 读取端** ✅ | `load_bands` 的调用方校验身份，并以**退出码**报警（**P2 已落地**，见 §5.3） | ⚠️ **前置已由 P0 完成**：合格线原有**三份读法**（`core/verdict.py`、`examples/run_result_evaluation.py`、`scripts/result_verdict.py` 内联），现已收敛为一份（见 §5.1）——不先做完这一步，身份校验**又会变成几个口径** |
| **D4 门禁端点** ✅ | `evaluate_evidence_bundle` 增一类判定证据 + 两级阻断（**P3 已落地**，见 §5.4） | 沿用既有分级：缺失/不一致 ⇒ `review`；篡改 ⇒ `hold` |

---

## 5. 分阶段实施

每个阶段**独立可验收、可单独回滚**。

| 阶段 | 状态 | 做什么 | 验收（可复现） |
|---|---|---|---|
| **P0 收敛** | ✅ **已实施**（见 §5.1） | 把**三份**合格线读法收敛成**一份**；归档那条线（`reports/_revoked_20261003/`）**保持原样** | 不同外壳键对同一份文件给出**同一判定** |
| **P1 规范 + 生成端** | ✅ **已实施**（见 §5.2） | 算身份、写进报告；**不动门禁** | 同内容不同外壳 ⇒ **身份相同**；改一个档位 ⇒ **身份变** |
| **P2 读取端软校验** | ✅ **已实施**（见 §5.3） | 身份缺失/不一致 → 显著标记 + **退出码非 0**（门禁尚未接） | 缺身份时**不再 `exit 0`** |
| **P3 门禁接入** | ✅ **已实施**（见 §5.4） | 两级阻断 | **换合格线**用例 ⇒ 门禁**不得 pass**；**改注释**用例 ⇒ 门禁**仍 pass**（假阳性校准） |
| **P4 历史迁移** | 待做 | 无身份的历史报告标为「未登记」 | 历史报告**不再被当同等证据**；文档写明**不得与有身份的报告同栏引用** |

### 5.1 P0 的实测记录（**计划被现实纠正**）

计划原写"收敛**两份** `load_bands`"。实测是**三份读法**，而且其中一份
**对着被跟踪的合格线文件必然读错、并且全程静默**：

| 读法 | 认的外壳键 | 对着 `verdict_bands_line1.json` |
|---|---|---|
| `core/verdict.py::load_bands` | `verdict_bands` | **全表落空 → 全 `unbanded`，且不报错** |
| `examples/run_result_evaluation.py::load_bands` | `bands` | 正常 |
| `scripts/result_verdict.py` 内联的原始读法 | —— | 只为取 `note` 等元数据 |

实测（同一份内容、同一维度、同一个 5 分）：

```
修复前：  键 bands → unbanded        键 verdict_bands → pass
修复后：  键 bands → pass            键 verdict_bands → pass
```

**"两边都不报错"是关键**：旧实现读不到内层就把整份文档当维度表，返回非空 →
调用方那句「未加载到任何合格线」的告警**不会触发**。所以这是**静默错答**，不是重复代码。

收敛后的接口：`load_bands`（兼容三种外形；兜底只收含 `pass_min` 的条目）+
`load_bands_document`（整份文档，留住 `provenance` / `derivation`）。

> **教训（回到计划里）**：计划的"前置"估计**低估了份数**，也**低估了性质**——
> 它以为是重复实现，实际是一条**错的判定路径**。**只有去读代码才会发现这一点。**

### 5.2 P1 的落地记录（身份算出来了，而且**真的写进了报告**）

身份 = 对**维度层**做规范化 JSON（键有序、分隔符固定、UTF-8）后的 sha256，
算法标识 `sha256:canonical-json-of-dimensions/v1`（`BANDS_IDENTITY_ALGO`）。
**元数据不参与身份**——改一句注释不该产生漂移告警，改一个档位必须产生。

真实文件上的两个身份（2026-10-05 实跑）：

| 文件 | `sha256[:16]` | 维度数 |
|---|---|---|
| `src/eval_engine/dataset/data/verdict_bands_line1.json`（被跟踪） | `e939bea70c008429` | 3 |
| 归档 `reports/_revoked_20261003/search_verdict_bands.json` | `05ff0cd55d818ce4` | 9 |

验收结果：

- 同内容、**换外壳键 + 改注释** → 身份**相同**；
- **改一个档位**（`pass_min` 4→5）→ 身份**变**；
- 键序不同 → 身份相同（规范化生效）；
- 缺失语义分两种：`unreadable`（读不到）／`no_recognizable_bands`（读到了但没有可识别合格线）。

**生成端已接**：真实归档批次实跑 `scripts/result_verdict.py`，报告里出现

```
> 合格线身份：sha256:canonical-json-of-dimensions/v1｜`05ff0cd55d818ce4`（9 维：…）
```

> **为什么专门写这一段**：本仓的失效模式第 2 条是"只哈希代码、不哈希配置"，
> 第 3 条是"校验做成告警而非阻断"。P1 只做到**把身份算出来并写下来**——
> 那时**身份拦不住任何东西**；到 P2（见 §5.3）才让读取端**以退出码报警**。

### 5.3 P2 的落地记录（读取端会报警了——**但门禁仍未接**）

两个读取端现在是**同一套退出码、同一套判断**（两处行为不一致正是 P0 修掉的那个病）：

| 情形 | 退出码 |
|---|---|
| 身份可识别、且与预期相符（或未给预期） | `0` |
| **身份不可识别**（`unreadable` / `no_recognizable_bands`） | **`2`** |
| **身份与预期不符**（`--expect-bands-sha256`，前缀匹配） | **`3`** |

**产物先落盘、告警只走退出码**——沿用采集侧 P0-2 的同一条纪律：
快照不可再采集，**报告必须留下**，判断只体现在退出码上。

真实归档批次上实跑（2026-10-05）：

```
① --bands <只有元数据的合格线>              → 退出码 2，且产物已落盘
② --expect-bands-sha256 0000000000000000    → 退出码 3（实际 05ff0cd55d818ce4）
③ --expect-bands-sha256 05ff0cd55d818ce4    → 退出码 0
```

顺带修一处**让读取端无法被测试覆盖**的缺陷：示例脚本原先用 `source.relative_to(REPO)`
显示路径，传仓库外路径（合法输入）时抛 `ValueError`；改为 `_display_path()`——
仓库内显示相对路径、仓库外显示绝对路径。

> **P2 当时的边界**：门禁（`src/eval_engine/gates/`）那时**还不读合格线**——身份**能报警、但拦不住发布**。
> 该边界已由 **P3** 推掉（见 §5.4）。

### 5.4 P3 的落地记录（门禁**真的能拦发布**了——但**不配就不查**）

`evaluate_evidence_bundle` 新增 `verdict_criteria` 一类判定证据，规则**两级**：

| 情形 | 结论 | 为什么落在这一级 |
|---|---|---|
| 身份**不可识别**（`recognized is not True`） | **`review`** | 配置/数据问题，可修；但**不得判过** |
| 与**预期**不符（`expected_sha256` 前缀不匹配） | **`review`** | 用了别的合格线，需人看一眼 |
| **声明**与**重算**矛盾（`declared_sha256 != sha256`） | **`hold`** | 产物**在自我声明上与事实不符**——篡改/换版，fail-closed |
| 一致（或 `None`） | 不改结论 | 防过度阻断 |

接线：`audit_release(..., verdict_criteria=...)` → `_gate_episode` → `evaluate_evidence_bundle`，
并把身份写进审计报告的 `verdict_criteria` 字段（`None` = 本次未评估，**不是"通过"**）。

真实 episode 夹具上实跑（2026-10-05，合格线身份 `e939bea70c008429`，3 维）：

```
① 不传身份（未评估）      → decision=pass    passed=True     verdict_criteria=None
② 身份不可识别            → decision=review  passed=False    ← 发布被拦住
③ 身份一致（匹配预期）    → decision=pass    passed=True     ← 与 ① 相同（假阳性校准）
④ 声明与重算矛盾（篡改）  → decision=hold    passed=False
```

> **仍然存在的洞（必须说清）**：这一类证据是**存在即校验**——与 `performance_evidence`、
> `multimodal_understanding` 等既有证据块同一约定。所以**调用方不传 `verdict_criteria` 时，
> 门禁不会因此变严**：`None` 只被记成"未评估"。
> 也就是说，「**没配就放行**」这个坑**还在**——正是 §3 自审里"OPA 未配签名即静默激活"的同构风险。
> 把它闭合要在**发布入口**把身份变成**必需**；`run_cross_agent_release.py` 与
> `run_expense_release_pipeline.py` **至今都还没传**。这一步会改变既有调用方的行为，**应单独决定**。

---

## 6. 验收判据

六条，均为可复现用例而非"看起来对"：

1. 同内容、不同外壳 → **同一身份**
2. 改任一个档位（`pass_min` 等）→ **身份变**，且门禁**不得 pass**
3. 改 `note`／`rulings_version` → **身份不变**，门禁**仍 pass**（反向用例，防过度阻断）
4. 缺身份 → **不得 pass**
5. 身份与内容不符（篡改）→ **`hold`**
6. 跨版本并存 → **必须被标注**，且**不得合并统计**

---

## 7. 范围：缺陷比"合格线"更宽

按同一把尺子扫门禁自己的阈值，四类里**三类记了、一类没记**：

| 阈值 | 值 | 是否出现在输出里 |
|---|---|---|
| κ 门槛 | `0.6` | **记了**（`release_audit.py` 的 `_calibration_report`） |
| 回归门槛 | `0.1` | **记了**（`regression_gate.py`） |
| 漂移门槛 | — | **记了**（`observability/drift.py`） |
| **过程分门槛 `min_process_score`** | **`3.5`** | **没记**——只在 review reason 触发时以字符串出现（`evidence_bundle.py`：`process score X below 3.500`） |

> **后果**：一份发布审计报告**无法告诉你它的决定是用哪个过程分门槛做出来的**——除非它恰好触发了。
> 这与合格线的缺陷**同类同源**：决定 pass/review/hold 的东西，**没有身份**。

**建议**：把本计划的范围定为「**所有决定 pass/review/hold 的判定输入都要有身份**」，
但**分期做**：先合格线（P0–P4），再门禁阈值（沿用同一套 D1 规范）。
**不要一次做全**——本仓的历史教训是范围一大就没人验。

---

## 8. 明确不做

- 不引入 SLSA 分级／DSSE 签名链／attestation 存储；
- 不改 `reports/` 归档（`.gitignore` 内、**git 回滚不了**）；
- 不做"自动重算合格线"；
- **不把"多版并存"当错误**（见 P6）。

---

## 9. 风险与依赖

| 风险 | 处置 |
|---|---|
| 历史报告无身份、且**不可再生成** | 只能标「未登记」，**不得补造** |
| 收敛合格线读法会碰到归档那条线（**不可 import**，依赖已被 `git rm` 的模块） | 只收敛**活着的**那几份；归档保持原状（本仓纪律：**机制活下来、口径随线走**）——**P0 已照此办理** |
| **外部无现成规范可抄** | D1 规范**以本仓证据为主**，不假装有外部背书 |
| 范围蔓延（§7） | 分期：先合格线，后门禁阈值 |
| 过度阻断（改注释就拦） | 用验收例 ②③ 成对校准 |

---

## 附录 A：外部依据（供复核）

| 项 | 标签 | 链接 |
|---|---|---|
| SLSA Build 分级与 provenance 字段 | 【官方文档】 | <https://slsa.dev/spec/v1.0/levels> · <https://slsa.dev/spec/v1.0/provenance> |
| cosign 校验与 **fail closed** 原则 | 【官方文档】 | <https://docs.sigstore.dev/cosign/verifying/attestation/> |
| OPA bundle 的 `.manifest.revision` 与签名 | 【官方文档】 | <https://www.openpolicyagent.org/docs/management-bundles> |
| Conftest：非零退出码阻断 + `conftest verify` | 【官方文档】 | <https://www.conftest.dev/> |
| Kyverno `Enforce` / `Audit` | 【官方文档】 | <https://release-1-12-0.kyverno.io/docs/writing-policies/validate/> |
| dbt 测试 `severity: warn\|error` | 【官方文档】 | <https://docs.getdbt.com/reference/data-test-configs> |
| Great Expectations Checkpoint Actions / `notify_on` | 【官方文档】 | <https://docs.greatexpectations.io/docs/core/trigger_actions_based_on_results/create_a_checkpoint_with_actions/> |
| GitHub 必需状态检查（**配置本身未版本化**） | 【官方文档】 | <https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches> |
| lm-eval `task_hashes` / `configs` | 【源码】 | <https://github.com/EleutherAI/lm-evaluation-harness/blob/main/lm_eval/loggers/evaluation_tracker.py> |
| HELM `RunSpec` 与 runner 落盘 | 【源码】 | <https://github.com/stanford-crfm/helm/blob/main/src/helm/benchmark/run_spec.py> |
| Inspect AI `EvalSpec` / `EvalRevision{dirty}` | 【源码】 | <https://github.com/UKGovernmentBEIS/inspect_ai/blob/main/src/inspect_ai/log/_log.py> |
| SWE-bench：日志缺证据即不判过 | 【源码】 | <https://github.com/SWE-bench/SWE-bench/blob/main/swebench/harness/grading.py> |
| OpenAI Evals：`spec` 入结果、无版本字段 | 【源码】 | <https://github.com/openai/evals/blob/main/evals/record.py> |
| Krippendorff：阈值需预设并报告软件版本 | 【二手】 | <https://casrai.org/guides/krippendorffs-alpha> |
| "κ 与'数据可靠性本身有问题'的情形不相容"（逐字引） | 【二手】 | <https://ar5iv.labs.arxiv.org/html/2008.00977> |
| PI-RADS 2.0/2.1 并存被直接对比 | 【二手】 | <https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0239975> |
| ML Test Score 条目与"取四类最小值" | 【二手（论文条目转述）】 | <https://research.google/pubs/pub46555/> |
| Datasheets for Datasets（纯文档框架） | 【论文】 | <https://arxiv.org/abs/1803.09010> |

## 附录 B：研究方法的限制（不遮掩）

- **多个一手来源未能取得正文**：Krippendorff 2011 原文（Cloudflare 拦截／仅返回首页）、
  MedDRA 换版指引与 DDI 受控词表迁移指南（PDF 未解析出正文）、RECIST 1.1 原文（付费墙）、
  ML Reproducibility Checklist 逐条（官方 PDF 抓取超时）。相关条目已按**「正文未核实」或「未找到」**标注，
  **未按其标题推断内容**。
- **raw.githubusercontent.com 在本机 DNS 不可解析**，源码依据经 `api.github.com` 取得。
- 因此本计划的**外部依据仅到"某机制在别处存在且被官方文档写定"这一层**；
  **"因此本仓应当这样做"是本文件的判断，不是文献结论**。
