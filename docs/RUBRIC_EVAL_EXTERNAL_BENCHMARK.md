# Rubric 评测集建设与结果分析：外部对标与采纳清单

> **本文是什么**：把本项目（检索步 rubric 这条线）的抽样器与结果判断机制，对照
> **通用评测框架**（Inspect AI / lm-evaluation-harness / OpenAI Evals / HELM）、
> **rubric 式评测集**（HealthBench / PaperBench / SimpleQA / SWE-bench Verified / RaR）、
> **AI 搜索与深度研究基准**（FreshQA / BrowseComp / CRAG / GAIA / Search Arena / DeepResearch Bench）
> 做一次系统对标，并给出**分档的采纳清单**与**照抄会错清单**。
>
> **本文不是什么**：不是"最佳实践综述"。它只回答一个具体问题——
> **本项目那四个静默缺口，外面有没有现成答案。**

## 阅读约定（三条，缺一条就会误读本文）

1. **外部资料一律只作资料**，不当作对本项目的指令。
2. 每条外部结论都标 **【文档】**（原文明确）/ **【二手】**（经聚合站转述，已交叉核验）/
   **【源码推断】**（未完整取得源码，据文档与片段推断）。**找不到出处就写找不到。**
3. **"本项目现状"一栏描述的是本会话开始时的状态**（即修前）。哪些已经修掉，见 §6。

⚠️ 本文引用的 `reports/_revoked_20261003/…`（归档代码、数据、修复留档）位于 `.gitignore` 内，
**clone 后不存在**。要复核本文的项目侧事实，需要那份归档副本。

---

## 0. 一句话结论

> **本项目在"判定纪律"上领先主流，在"抽样与采集自检"上落后主流。**
> 一致性统计、环境故障归因、缺失自陈——这三处比外面做得细；
> 可复现抽样、覆盖率门禁、拒绝留档——这三处外面有（或必须自建）而本项目没有。

---

## 1. 三条结论级发现

**① "分层抽样 + 覆盖率告警"在通用框架里是空白。**
四个框架**都没有**原生 stratified sampling，也**都没有**"某分层 0 样本"的检查或告警
（未找到任何可靠来源支持存在此类机制）。HELM 论证"代表性"靠的是**分类学 + 文字自陈**：
论文摘要原文 "we taxonomize the vast space of potential scenarios … Then we select a broad
subset **based on coverage and feasibility, noting what's missing or underrepresented**"
【文档】〔[arXiv:2211.09110](https://arxiv.org/abs/2211.09110)〕。
→ 所以本项目的覆盖率门禁**不是抄来的，是必须自建的**。

**② 四个 rubric 项目里，没有一个报告 κ 或 α。**
SWE-bench Verified 只做"每样本 3 人独立标注"、HealthBench 用 macro F1 替代、
SimpleQA 用 1,000 题抽查的 94.4%、PaperBench 干脆未报。
→ 本项目有双人盲评 κ + 按请求聚簇 CI + 分层报数，**这块领先**。

**③ 存在两类漏斗，且难度漏斗明确放弃代表性。**

| 漏斗类型 | 代表 | 做法 |
|---|---|---|
| **质量漏斗** | SWE-bench Verified | 2,294 → 随机抽 1,699 → **500**（剔除 ≈68.3%），93 名 Python 开发者、**每样本 3 人独立审**【二手·经交叉核验】 |
| **难度漏斗** | HealthBench Hard / SimpleQA | 取**模型分最低**的 1,000 条（排除全模型无解项）；或**对抗式富集**（每题 4 个模型回答至少 1 个必须错，否则重写题）【文档】 |

**难度与代表性此消彼长**——BrowseComp 明说它 "sidesteps … a true user query distribution"，
SimpleQA 明说是 "adversarially collected"，Search Arena 明说 "may not be fully representative"。
这个取舍**必须显式做**，不能默认。本项目当前是**两者都没有**（手写池子 + 一句免责声明）。

---

## 2. 对照表：六个缺口 × 主流做法

| 缺口 | 主流怎么做 | 本项目（修前） | 判定 |
|---|---|---|---|
| **① 层内取书写头部** | 四家**全部随机下采样**：Inspect `--sample-shuffle [seed]`【文档】、OpenAI Evals `--max_samples`（先打乱；`SHUFFLE_SEED=123` **写死**、不受 `--seed` 影响【源码推断】）、HELM `--max-eval-instances`（`np.random.seed(0)` + `np.random.choice(replace=False)`【源码推断】） | `buckets[key].pop(0)`＝按池子书写顺序取头部 | **落后** |
| **② 零样本请求静默出局** | Inspect 最完整：`EvalSampleSummary.error`（可按 error 筛清单）+ **`--fail-on-error`（比例/计数阈值）** + `--retry-on-error` + `--continue-on-fail` + 崩溃恢复 `incomplete_action`【文档】；HELM 有 NaN 统计剔除并 `hwarn`【文档】 | 有记录（`meta.requests_without_search`），**无阈值、无告警、无门禁** | **落后一半** |
| **③ 无覆盖率断言** | **四家都没有** | `intents_missing` 字段 + 测试"不得为空" | **自定义门禁（已领先）** |
| **④ 无拒绝留档** | SWE-bench Verified 有**四类拒绝理由**：① problem statement under-specified ② tests unfairly scoped/unrelated ③ unreliable dev environment ④ otherwise problematic【二手·经交叉核验】；但**拒绝样本未公开留档**。HealthBench 唯一做到"**可追溯撤回**"：淘汰 31 名医生的标注**整批删除**【文档】 | 无筛选步骤、无拒绝类别、无拒绝清单 | **主流基本空白** |
| **⑤ 无难度门** | HealthBench Hard（5,000→1,000 取模型分最低者）、SimpleQA（对抗式富集）、BrowseComp（**三重难度门**：GPT-4o±浏览 / o1 / 早期 deep research 均解不出 + Google 前 5 条无答案 + 他人 10 分钟解不出则返修）【文档】 | 完全没有；采样只看 `style` | **缺失，有现成模板** |
| **⑥ 快照无过期机制** | FreshQA：每题记"答案上次变化年份" + 权威 URL + **预计下次复核日期**；排除变化快于每周的题；版本定期更新；全部模型**同日**评测【文档】 | 声明 `live_snapshot` **不可再采集**，却**无寿期字段** | **缺失，有现成模板** |

### 另外三个可以直接借的素材

| 素材 | 出处 | 用途 |
|---|---|---|
| **来源多样性拒绝规则** | SimpleQA：两标注者来源**域名去重后 < 2 个唯一域名则弃用**【文档】 | 用于 `value_grounded` / `citation_grounding` 的样本筛选 |
| **每样本 3 名标注者** | SWE-bench Verified（93 人，每样本 3 人独立审）【二手】 | 本项目是 2 人（r1/r2）；高危子集可升到 3 人 |
| **样本量-精度量化表** | Efficient-HELM：10→±5、200→±2、1000→±1（95% CI of Rank Location）【文档】 | 给"可判格 < 15""n < 5 不引用 κ"**补量化出处** |

---

## 3. 可采纳清单（三档）

### A 档 · 主流标配（本项目落后，该补）

| # | 补什么 | 对标 | 状态 |
|---|---|---|---|
| A1 | 层内改**带种子 shuffle**，**保留分层轮转** | Inspect / HELM / Evals 三家一致 | ✅ 已做（§6 P0） |
| A2 | 选中清单**落盘**（"这批选了谁、凭什么"） | HELM `--cache-instances` | ✅ 已做（写入 `meta.sampling`） |
| A3 | **阈值门禁**：零样本请求比例超阈 → 采集失败；层覆盖为 0 → 报错 | Inspect `--fail-on-error` | ✅ 已做（§6 P0） |
| A4 | 写清 filter 语义（**数据集筛选** vs **输出后处理**） | Inspect = 前者；lm-eval `filters`/`filter_list` = 后者（`take_first_k`/`regex`/`majority_vote`）——**A 线程点名的最易误读处**【文档】 | ⬜ 待做（P2） |
| A5 | **来源多样性规则**（域名去重） | SimpleQA | ⬜ 待做（P2） |

### B 档 · 主流部分有，按本项目约束裁剪

| # | 做法 | 裁剪理由 |
|---|---|---|
| B1 | 分层下采样 | **不要照抄纯随机**——会丢掉分层保证（那正是缺口②③的成因）。正确形态是**分层 + 层内 seed shuffle** |
| B2 | epochs/repeats 的"归约"（Inspect `EvalSampleReduction`、lm-eval `repeats` → `req.resps` → filter 归约） | **不抄**：见 §4 第 2 条。本项目用"按请求聚簇"，更强 |
| B3 | 样本量量化依据 | 用 Efficient-HELM 表给现有阈值补出处 |
| B4 | **难度漏斗**（按模型分低分位富集） | 本项目已有 judge 分可直接算；但**必须同时声明放弃代表性**，与现有"不得称代表性评测集"合并 |
| B5 | HealthBench 的 **meta-evaluation** | ⭐ 本项目**已经在做**：同时报 `Judge vs r1 κ≈0.86` 与 `r1 vs r2 κ≈0.72`，正是"模型-人 vs 人-人 一致度可比"的同一论证，**只是没这么表述过** |
| B6 | 每样本 3 名标注者 | 高危子集可选，成本换稳健性 |

### C 档 · 主流也没有 → 自定义门禁（要论证为什么非有不可）

| # | 门禁 | 为什么本项目非有不可 | 状态 |
|---|---|---|---|
| C1 | **层覆盖率断言** | HELM 只自陈；本项目可字段化 + 测试强制 | ✅ 已做（P0-2） |
| C2 | **拒绝留档**（漏斗 + 类别 + 清单） | 主流空白；可借 SWE-bench Verified 四类 + HealthBench 撤回机制 | ⬜ 待做（P2-1） |
| C3 | **故障成簇检测** | 25 步 `tool_error` 挤在 **2 个窗口 / 16 个请求**——主流**完全不查**；本项目因坚持按请求聚簇报 CI，**必须**查 | ⬜ 待做（P1） |
| C4 | **meta 与样本对账** | `outcome_strata` 硬编码两键，静默丢掉 29 条 | ✅ 已做（P0-1） |
| C5 | **快照寿期** | 仿 FreshQA"下次复核日期"；但本项目**不能重采** → 寿期只能是"**作废/降级引用**" | ⬜ 待做（P1） |
| C6 | **难度门** | 主流有模板（B4），但本项目成本约束不同（不能再跑 5 个前沿模型） | ⬜ 待做（P1） |

---

## 4. 照抄会错清单

> **术语约定（P2-5）**：`filter` / "筛选"在主流里**意思相反**，本项目**两个都不能裸用**：
>
> | 含义 | 代表 | 行为 | 本项目对应物 |
> |---|---|---|---|
> | **数据集筛选** | Inspect `dataset.filter(predicate, name=)` | 从候选里**去掉**样本 | 「拒绝留档」（P2-1） |
> | **输出后处理** | lm-eval `filters` / `filter_list`（`take_first_k`、`regex`、`majority_vote`） | **不减少样本**，只改模型输出 | `auxiliary_metrics.json` 那一类 |
>
> 写文档或代码时**一律加限定词**（"数据集筛选" / "输出后处理"），**不得只写"筛选"**——
> 这是 A 线程点名的"最易误读处"。

| 主流通行做法 | 直接抄会错在哪 |
|---|---|
| **纯随机下采样** | 丢掉分层保证 → 某层可能 0 样本。**这正是本项目缺口②③的成因**，抄过去是加重病情 |
| **"先归约再算指标"** | 主流处理的是"**同一样本跑多次**"；本项目的相关单位是**请求**（一条请求最多 3 个检索步）。归约会**抹掉簇内相关**，而按请求聚簇**保留**它 → **本项目更强，别退回去** |
| **加权树合成总分**（PaperBench：二元 leaf + 同级权重 + 父节点加权平均；HealthBench：−10~+10；RaR：Essential=5 / Important=3–4 / Optional=1–2 / **Pitfall=−1~−2**） | 本项目**刻意"分栏不合成"**。这是**有理由的分歧**（合并值受层构成影响、单报会误导），不是落后。**照抄加权树会毁掉分栏纪律** |
| `--limit`（lm-eval 文档明写 **"For testing only."**） | 本项目的 `--limit` 是**生产口径**（决定批次样本量），性质不同 |
| FreshQA 式"定期更新版本 + 同日评测全部模型" | `live_snapshot` **不可再采集** → 不能更新版本，只能**新增分栏**；寿期做成"作废/降级引用" |
| 只公布保留集、拒绝样本只报统计 | 本项目已因同类**静默丢失**吃过两次亏（`meta` 丢 29 行、`w12–w14` 出局） |
| 用 **κ 之外**的一致性统计替代（macro F1 / 抽查） | 主流这么做是因为人工成本；本项目已有 κ + 聚簇 CI，**退回 F1 是降级**。但可以**并列**报告（见 B5） |

---

## 5. 三个反超点（可对外讲）

| # | 本项目 | 主流对应 |
|---|---|---|
| 1 | **一致性统计**：双人盲评 κ + 按请求聚簇 CI + 分层报数 + 主动标注"退化/样本不足不可引用" | **四个 rubric 项目没有一个报告 κ 或 α** |
| 2 | **环境故障的归因纪律**：B16「补偿按**是否采取合理补救动作**判，不按动作是否成功判」+ B6「不得用后一步失败追罚前一步」——**明确禁止把环境故障记成被测对象的错** | 七个搜索基准里**只有 CRAG** 区分 `Missing`（系统错误/空回答）与 `Incorrect`（计分 1/0.5/0/−1，**缺答优于错答**）；其余均未区分，且**没有"不得归因于被测对象"这条纪律** |
| 3 | **缺失自陈的形态**：字段 `intents_missing` + 测试"**不得为空**"强制 | HELM 用**文字**自陈 "noting what's missing"；BrowseComp / Search Arena 用**一段话**声明局限；FreshQA / CRAG / GAIA **未见**此类声明 |

---

## 6. 落到代码：已经做的与还没做的

### 已落实（本会话，全部有测试锁住）

| 项 | 内容 | 守卫 |
|---|---|---|
| **P0-1** | `meta.outcome_strata` 改按**真实取值**计数 | `tests/test_collect_p0_sampling.py` |
| **P0-2** | 覆盖率门禁（零样本比例 + 层清空）→ `collection_coverage.json` + **退出码 2**，**产物全保留** | 同上 |
| **P0-3** | 层内 `pop(0)` → **带种子 shuffle**；顺带修"`limit`<层数时字母序靠后层一条取不到"（显式报 `starved_strata`） | 同上 |
| **P0-4** | `_notarize` 已存在时**核对磁盘 sha**，不一致即 `raise`（证据本体完整性优先） | 同上 |
| **池子出处** | 三支请求池各带 `POOL_PROVENANCE` 块（作者/日期/文本来源/意图覆盖/采集缺口/状态），落进 `meta.pool_provenance` | `tests/test_search_pool_provenance.py` |
| **失败码通道** | 归档流水线三处断点（文案说"无需人工填" / 表格只两列 / 重放不回填证据列）；活侧新增 `code_channel_status()` 区分"算不了"与"**通道未启用**" | `tests/test_rubric_quality_report.py` |
| **合格线兼容** | `load_bands` 兼容扁平与带外壳两种结构（外壳曾让全表静默变 `unbanded`）+ 缺合格线时告警 | `tests/test_result_verdict.py` |
| **口径四修** | 未标 ≠ Rubric 分歧；退化＝任一方恒定；同分但归类不同不再被丢；冗余证据要求两侧都有变异 + `n<15` 不报 r | `tests/test_rubric_quality_report.py` |
| **环境** | `tests/conftest.py` 指向修正（原先插入了不存在的 `tests/src`，测试实际在测**另一个目录**）；venv 的 editable `.pth` 重装指向本工作区 | — |

**实测效果**（真实历史批次）：
`meta.outcome_strata` 旧值合计 **51/80 行**（29 行无声消失）→ 新值 **80/80**；
覆盖率门禁重放成功层那次采集 → `ok=False`，精确指出 **`ambiguous` 层被清空**。
**注意**：该次零样本比例 **18.75% < 25% 阈值**，比例检查会放行——**是"层被清空"抓住的**，
两道检查互补、缺一不可。

### 还没做

| 档 | 项 |
|---|---|
| **P1** | 故障成簇检测 · 难度门 · 快照寿期 · 滥用拒答的惩罚缺口（后者**未在数据上验证**，仅从 `result_sufficiency` 锚点推出：锚点把"有依据的拒答"给到 4–5，却不罚**滥用拒答**；SimpleQA 的 `p=9` 正是为此设计） |
| **P2** | 拒绝留档 · 来源多样性规则 · filter 语义分离 · 样本量阈值量化出处 · 请求池 `author`/`date` 填真（现为"未记录"，需作者确认） |
| **P3** | 上游记录器 **500 字截断**（→ `citation_grounding` 可判率仅 2%，本仓之外）· 归档流水线不可导入故无法端到端验证 · 失败码历史数据仍为 0 |
| **P4** | 清理验算目录 · 取回 SWE-bench 官方标注指南 PDF · 归档真实轨迹改按配额抽样（手上已有 772 条真实运行记录，可对标 DeepResearch Bench 的"按真实域分布配题"） |

---

## 7. 外部资料的限制（不遮掩）

1. **`openai.com` 对本环境全部 HTTP 403**（含各语言版本）。SWE-bench Verified、HealthBench、
   PaperBench、SimpleQA 的数字是经 **Epoch AI / Longterm Wiki（含博文正文缓存）/
   systems-analysis wiki** 转述并**交叉核验**的 → 标 **【二手·经交叉核验】**。
2. **PDF 无法解析**，故官方标注指南 `swe-b-annotation-instructions.pdf` 的**逐条标签原文**
   与 HealthBench §8 的**精确 F1 数值**未取得——只拿到定性结论。
   这是唯一能拿到"逐条筛选标准原文"的一手件，**需在能下载的机器上取回**。
3. **`raw.githubusercontent.com` / `web.archive.org` / `huggingface.co` 在本环境不可达**，
   GitHub 文件经 `api.github.com/contents` 读取 → 代码级结论标 **【源码推断】**。
4. **arXiv HTML 全文抓取超时**，论文表述取自摘要页原文。
5. 本项目侧的对照事实（层消失、29 行丢失、2 个故障窗口等）**均在归档代码与数据中实测**，
   不是引用他人结论。

---

## 附录 A · 通用评测框架：抽样与筛选机制

| 维度 | Inspect AI | lm-evaluation-harness | OpenAI Evals | HELM |
|---|---|---|---|---|
| 限量 | `--limit`（`10` 或 `10-20`） | `--limit`/`-L`（整数=条数，小数=百分比，**"For testing only."**） | `--max_samples`（**先打乱再取前 N**） | `--max-eval-instances`（必填，随机打乱顺序） |
| 按 id 选/排除 | `--sample-id 22` / `22,23,24` / glob `*_advanced` / 跨任务 `task:id`；空列表=不选。**无排除语法** | `--samples`/`-E` `'{"task1":[0,1,2]}'`（**下标**），**与 `--limit` 互斥**（`ValueError`） | **没有** | **没有**（只能按 run entry 限定 scenario 子集） |
| 随机/种子 | `--sample-shuffle [42]`；`dataset.shuffle(seed=42)` | `--seed 0,1234,1234,1234`（python,numpy,torch,fewshot），结果 JSON 记录各 seed | `--seed`（默认 20220722）用于每样本 RNG `f"{sample_id};{seed}"`；**打乱种子是写死的 `SHUFFLE_SEED=123`**【源码推断】 | `np.random.seed(0)` + `np.random.choice(replace=False)`【源码推断】；`--cache-instances` **落盘选中样本** |
| 分层抽样 | **没有**（仅 filter/shuffle/sort/slice） | **没有** | **没有** | **没有原生**；"分层"在 scenario 空间（run entry `subject=`/`dataset=`） |
| 样本级筛选 | `dataset.filter(predicate, name=)`、切片 `dataset[0:100]` | `filters`/`filter_list` **只作用于模型输出**（`filtered_resps`），**不是数据集筛选** | **没有** | **没有**（`--skip-instances` 只是跳过生成） |
| 覆盖率检查 | **没有** | **没有** | **没有** | **没有** |
| 重复/epochs | `--epochs` + `--epochs-reducer`（mean/median/mode/pass_at_k…）；日志 `EvalSampleReduction`：**先归约再算指标** | `repeats: K`（self-consistency）→ `req.resps` 列表 → filter 归约成单答案 | **没有** | `--num-train-trials`（重采样 in-context 示例；`max_train_instances=0` 时强制 1） |
| 跳过/失败记录 | **最完整**：`log.status`、`EvalSampleSummary.error`（可按 error 筛清单）、`--fail-on-error`、`--retry-on-error`、`--continue-on-fail`、`incomplete_action` | **未找到可靠来源** | 无样本级计数（只有 `--http-fail-percent-threshold`、oaievalset 进度文件） | run 级：`_is_run_completed`、`--skip-completed-runs`、`failed_run_specs`→`RunnerError`、NaN 统计剔除并 `hwarn` |

**HELM 的覆盖论证**：分类学 + 覆盖度自陈（16 core scenarios × 7 metrics，87.5%；30 模型 96.0%）
【文档】，**不是**抽样统计论证。

---

## 附录 B · Rubric 评测集的筛选漏斗与分层设计

| 项目 | 漏斗（筛前→筛后） | 拒绝理由 | 审核 | rubric 结构 | IAA |
|---|---|---|---|---|---|
| **SWE-bench Verified** | 2,294 → 随机抽 1,699 → **500**（剔除 ≈68.3%）【二手】 | ① under-specified 描述 ② 测试过严/无关 ③ 环境不可靠 ④ otherwise【二手·经交叉核验】 | 93 名 Python 开发者，**每样本 3 人独立审** | 非 rubric（pass/fail 测试 + 人类标注元数据，含难度） | **未见 κ/α** |
| **HealthBench** | 5,000 对话 + **48,562 criteria**（consensus 8,053 = 14%） | 对话过滤 3 条由 **o1-preview 自动判**（不 realistic/非 physical health/含 incomplete message） | 1,021 名医生报名 → 选 **262（26%）** → 后**淘汰 31 人并删除其标注** | 每条 criterion **−10 ~ +10 非零分值**，负分作惩罚项；命中给满分否则 0；例内求和后除以最大可能分 | **无 κ**；用 macro F1 比 model–physician vs physician–physician，结论"相当" |
| **HealthBench Hard** | 5,000 → **1,000** | 取 5 个前沿模型平均归一化分**最低**者，**排除全模型无解项** | 【推断】无人工复核 | 同 HealthBench | — |
| **HealthBench Consensus** | → 3,671 条含 ≥1 条正 consensus criterion | 需 **>50% 且 ≥2 名医生**同意 | 多名医生投票 | 34 条预写 criterion，出现 8,053 次 | 医师共识机制本身 |
| **PaperBench** | 20 篇 ICML 2024 Spotlight/Oral（筛选数未公布）；**8,316 leaf** | 按"可复现性/合适性"（Appendix B），**具体类别与计数未公开** | **与每篇论文原作者共同开发**，每篇数周（阅读→初稿→评审→迭代→签字） | **分层树**：leaf 二元 pass/fail；parent = 子节点**加权平均**；每节点手工赋权；三类 leaf（Result Match / Execution / Code Development） | JudgeEval 上 o3-mini judge **F1 0.83**；**人类 IAA 未报** |
| **SimpleQA** | 未公布筛前总数；最终 **4,326 题** | ① 少样本 ChatGPT 分类器检出违规（未指定单位/答案随时间变/多解）→ 退回改写 ② 两标注者答案不一致 ③ 第二标注者判"非 timeless"或"非唯一" ④ **域名去重后 <2 个唯一域名则弃用** | AI trainers；两阶段（创作者 + 独立答题者），答案须**完全一致** | 无 rubric：单标准答案 + 三分类 **correct / incorrect / not attempted** | 无 κ；1,000 题抽查第三人正确率 **94.4%**，估数据错误率 **≈3%** |
| **RaR** | RaR-Medicine 22.4k / RaR-Science 22.9k prompt | 未公布（训练集而非 benchmark） | 未详述 | `{title, description, weight}` + `binary`；**Essential=5 / Important=3–4 / Optional=1–2 / Pitfall=−1~−2** | 未报 |

**SimpleQA 的 `not attempted` 定义**：参考答案未被完整给出、**且没有与参考答案矛盾** →
"我不知道"、反问用户、含糊其辞均归此类，**不当作错**。指标为 `overall correct` 与
`correct given attempted`，二者调和平均 = **F-score**；另有显式惩罚版
（correct=1、not attempted=0、incorrect=**−p**，文中以 **p=9** 举例）。

---

## 附录 C · AI 搜索 / 深度研究基准的请求集与筛选

| 基准 | 请求来源 | 分层维度 | gold 与时效 | false premise | 工具失败 vs 内容错 |
|---|---|---|---|---|---|
| **FreshQA** | 人工（作者 + NLP 研究者 + 众包，$2/题）；非流量日志 | never / slow / fast-changing + false-premise；1-hop / multi-hop | 双模式判分（Relaxed 只看主答案 / Strict 要求全部事实准确且最新，二者差值即幻觉度量）；每题记"上次变化年份" + 权威 URL + **预计下次复核日期**；排除变化快于每周的题；全部模型**同日**评测 | **独立一类（125 题）**；**必须点明前提错误才得分** | 文档未说明（只评回答） |
| **BrowseComp** | 全部 human trainers 人工撰写 | 后验 topic 分类 | 先定事实再**反向出题**；答案为单一短串、易语义比对；题面事实"不随时间变化"；canary 防污染；**明说 sidesteps a true user query distribution** | 文档未说明 | 文档未说明；另报 calibration error |
| **CRAG** | 混合：KG 模板 + 标注者写"用户可能问"的 Web 题；4,409 题 | 5 域 × 8 题型；dynamism 四档（real-time/fast/slow/static）；popularity head/torso/tail | 人工核验 + 等价答案；**web 页/KG/实时题同时采集成"快照"**（50 页 HTML + mock KG + 38 mock API，含同名 hard negative） | 单列题型 **525 题（12%）** | **明确区分 `Missing`（含 "I don't know"、空回答、system error）vs `Incorrect`**；计分 1/0.5/0/−1，**缺答优于错答** |
| **GAIA** | 人工（作者 + Surge AI 付费标注者）；466 题 | Level 1/2/3（按步数与工具数）+ 能力维度 | 每题 **2 名新标注者独立作答验证唯一答案**，不一致则修/删；**68% 原样通过**；核查 robots.txt；答案须无训练数据明文；仅英文（自陈局限） | 无（设计上只收唯一正确答案） | 文档未说明（不评 trace） |
| **Search Arena** | **真实流量**：Chatbot Arena search tab 7 周全量，24,069 会话 / 12,652 偏好票 / 136 国 | 9 类 intent；70+ 语言；22.4% 多轮 | 无 gold：人类偏好 + Bradley-Terry；citation 支持性由 LLM 管线判 | 文档未说明 | 有 tie 票（31–45%）；**未区分工具失败** |
| **DeepResearch Bench** | 混合：**96,147 条真实 query** → 过滤得 44,019 → 按 22 域比例压成 **100 题**（中/英各 50） | 22 个 topic 域；中英双语 | 无标准答案：RACE 用参考报告 + 动态权重；FACT 用 Jina Reader 实时抓网页判支持性 | 文档未说明 | 文档未说明 |
| **Mind2Web**（导航） | 众包开放任务 >2,000 / 137 真实网站 / 31 域 | 域 / 网站 / 交互模式 | gold = 众包动作序列；真实站点未冻结【推断：复现性风险】 | 文档未说明 | 文档未说明 |

**贯穿性缺口**：七个基准里**只有 CRAG** 明确把"系统错误/空回答"归入 `Missing` 并单独计分；
**被拒样本普遍只报统计，未见公开留档**（GAIA 68% 通过、BrowseComp 返修）。
**外部效度声明**：只有 BrowseComp、Search Arena 明确声明"不代表真实流量分布"；
Search Arena 自陈人口统计学偏差；DeepResearch Bench 反向操作——按真实 query 域分布配题。

---

## 附录 D · 来源清单

**通用框架**：<https://inspect.aisi.org.uk/options.html> ·
<https://inspect.aisi.org.uk/datasets.html> · <https://inspect.aisi.org.uk/eval-logs.html> ·
<https://inspect.aisi.org.uk/tasks.html> ·
<https://github.com/UKGovernmentBEIS/inspect_ai/blob/main/src/inspect_ai/dataset/_dataset.py> ·
<https://github.com/EleutherAI/lm-evaluation-harness/blob/main/docs/interface.md> ·
<https://github.com/EleutherAI/lm-evaluation-harness/blob/main/docs/task_guide.md> ·
<https://github.com/EleutherAI/lm-evaluation-harness/blob/main/lm_eval/evaluator.py> ·
<https://github.com/openai/evals/blob/main/evals/eval.py> ·
<https://github.com/openai/evals/blob/main/evals/cli/oaieval.py> ·
<https://crfm-helm.readthedocs.io/en/latest/tutorial/> ·
<https://crfm-helm.readthedocs.io/en/latest/efficient_benchmarking/> ·
<https://crfm-helm.readthedocs.io/en/latest/run_entries/> ·
<https://github.com/stanford-crfm/helm/blob/main/src/helm/benchmark/runner.py> ·
[arXiv:2211.09110](https://arxiv.org/abs/2211.09110)（HELM）

**Rubric 评测集**：[arXiv:2505.08775](https://arxiv.org/abs/2505.08775)（HealthBench）·
[arXiv:2504.01848](https://arxiv.org/abs/2504.01848)（PaperBench）·
[arXiv:2411.04368](https://arxiv.org/abs/2411.04368)（SimpleQA）·
[arXiv:2507.17746](https://arxiv.org/abs/2507.17746)（RaR）·
<https://openai.com/index/introducing-swe-bench-verified/>（**本环境 403**）·
<https://epoch.ai/benchmarks/swe-bench-verified> ·
<https://www.longtermwiki.com/resources/e1f512a932def9e2>（含博文缓存）

**AI 搜索与深度研究**：[arXiv:2310.03214](https://arxiv.org/abs/2310.03214)（FreshQA）·
[arXiv:2504.12516](https://arxiv.org/abs/2504.12516)（BrowseComp）·
[arXiv:2406.04744](https://arxiv.org/abs/2406.04744)（CRAG）·
[arXiv:2311.12983](https://arxiv.org/abs/2311.12983)（GAIA）·
[arXiv:2506.05334](https://arxiv.org/abs/2506.05334)（Search Arena）·
[arXiv:2506.11763](https://arxiv.org/abs/2506.11763)（DeepResearch Bench）·
[arXiv:2306.06070](https://arxiv.org/abs/2306.06070)（Mind2Web）

**待取一手件**：`https://cdn.openai.com/introducing-swe-bench-verified/swe-b-annotation-instructions.pdf`
（SWE-bench Verified 逐条标注标准；本环境无法解析 PDF）
