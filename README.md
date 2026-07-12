# LLM Eval Engine

**生产级 LLM 评估框架**，支持 Process Reward 步骤级评分、动态评分标准生成、自适应 Eval Loop 和人工审批介入。

## 为什么需要这个框架

传统 LLM 评估方式的局限性：

| 问题 | 本框架的方案 |
|------|------------|
| 所有任务用固定模板评分 | **动态评分标准** — 每步基于实际上下文生成针对性评分标准 |
| 只对最终答案二分法判对错 | **Process Reward** — 逐步骤评分，追踪错误传播路径 |
| 一次性评估，没有改进机制 | **自适应 Eval Loop** — 低分触发修正指令 → Agent 重试 → 重新评分 |
| 没有人参与决策 | **四级权限系统**（SAFE/NOTIFY/CONFIRM/DENY）+ HITL 人工审批 |
| 手动判断是否需要重试 | **震荡检测** — 分数停滞时自动停止，避免无效循环 |

## 架构

```
src/eval_engine/
│
├── core/                        框架无关的核心评估原语
│   ├── contract.py              Verifier 契约接口（可组合评分标准）
│   ├── trajectory_parser.py     Agent 轨迹 → DAG 步骤结构
│   ├── dynamic_rubric.py        ★ 动态评分标准生成
│   └── process_reward.py        ★ 步骤级 Process Reward 评分 + 错误传播
│
├── judge/                       Judge LLM 调用
│   ├── executor.py              Judge LLM 封装（JSON 解析、重试）
│   ├── calibration.py           评分校准与偏差调整
│   └── templates/               评分 Prompt 模板
│
├── loop/                        自适应评估循环
│   ├── eval_loop.py             ★ 核心循环：评分 → 修正 → 重执行
│   └── fix_packer.py            修正指令打包
│
├── gates/                       评分门控
│   ├── baseline.py              Baseline 对比评分
│   └── regression_gate.py       回归检测
│
├── intent/                      任务分类路由
│   └── classifier.py            意图识别 → functional_test / generative_task
│
├── safety/                      人工审批
│   └── human_in_the_loop.py     HITL 回调接口
│
├── dataset/                     数据集管理
│   └── manager.py               数据加载与拆分
│
└── observability/               可观测性
    └── report.py                审计报告生成
```

## 核心概念

### 1. 动态评分标准生成

不再对所有任务用同一份模板打分，而是基于每步的实际上下文动态生成评分标准：

```
Step 3（Agent 执行了 web_search 搜索 "Python SQL注入"）
→ 动态评分标准：
  ① 搜索词是否合理？
  ② 搜索结果是否被后续步骤利用？
  ③ 搜索效果不好时，Agent 是否有备选方案？
```

### 2. Process Reward 步骤级评分

受 o1/o3 Process Reward Model 启发——不只看最终答案，对每一步单独评分：

```
Step 1: web_search（得分: 0.92 ✅）
Step 2: read_results（得分: 0.85 ✅）
Step 3: review_tool（得分: 0.40 ❌ — 参数错误）
Step 4: summarize（得分: 0.60 ❌ — 基于不完整数据）
         ↑ 错误传播：Step 3 失败 → Step 4 受影响
```

### 3. 自适应 Eval Loop

```
Agent 执行 → 轨迹解析 → Process Reward 评分
       │                    │
       │               ┌────┴──────┐
       │            全部达标     有低分项
       │               │          │
       │               ▼          ▼
       │            输出结果   打包修正指令
       │               │          │
       │               │          ▼
       │               │    LLM 根据反馈重试
       │               │     → 再次进入循环
       └───────────────┘
```

- **最大迭代次数**：防止无限循环（默认 3）
- **最小改进幅度**：分数停滞时自动停止（震荡检测）
- **人工审批钩子**：修正注入和重执行前可设置 HITL 审批

## 快速开始

```bash
pip install eval-engine
```

```python
from eval_engine.loop.eval_loop import EvalLoopEngine, EvalLoopConfig

# 配置
config = EvalLoopConfig(max_iterations=3, verbose=True)

# 传入你的 Agent 执行函数和 Judge LLM 调用函数
engine = EvalLoopEngine(
    agent_fn=my_agent_run,     # Callable[[str], dict]
    judge_fn=my_judge_call,    # Callable[[str], dict]
    config=config,
)

# 执行
result = engine.execute("分析 Q3 财务报告")

if result.passed:
    print(result.final_output)
else:
    print(f"评分: {result.report.overall_score}")
    print(f"失败步骤: {result.report.error_sources}")
```

## 集成方式

框架与具体的 Agent 框架无关，你需要提供：

1. **agent_fn(query: str) -> dict** — Agent 执行函数，返回 `{"output": str, "trajectory": dict}`
2. **judge_fn(prompt: str) -> dict** — Judge LLM 调用函数，返回解析后的评分 JSON

### 人工审批

```python
from eval_engine.safety.human_in_the_loop import HumanInTheLoop

def ask_user(prompt, options):
    return input(f"{prompt} {options}: ")

hitl = HumanInTheLoop(ask_fn=ask_user)
engine = EvalLoopEngine(agent_fn=..., judge_fn=..., hitl=hitl)
```

## 测试

```bash
pip install -e ".[test]"
pytest tests/
```

## 环境要求

- Python 3.10+
- 核心模块纯 Python，无外部依赖
- Judge executor 需要 `requests`（可选，使用内置 executor 时需要）

## 相关项目

- [attention-from-scratch](https://github.com/weihuaguo270-ops/transformer-attention) — NumPy/PyTorch Transformer Attention 实现
- [handwritten-react-agent](https://github.com/weihuaguo270-ops/react-agent) — 生产级 ReAct Agent 框架
- [trace-debugger](https://github.com/weihuaguo270-ops/trace-debugger) — Agent 执行轨迹分析工具

## License

MIT
