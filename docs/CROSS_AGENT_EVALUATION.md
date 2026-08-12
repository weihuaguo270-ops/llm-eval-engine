# 跨 Agent 评测接入

**状态：** v1 已实现  
**维护范围：** `eval_engine.integrations.episode`  
**验证日期：** 2026-08-12

## 目标

`EvaluationEpisode v1` 把任务、Agent 版本、数据切分、Format B 轨迹和业务终态放在
同一个可版本化 envelope 中。评测引擎不需要导入被测 Agent 的 Python 对象。

当前导入器支持：

| 来源 | 入口 | 状态 |
|------|------|------|
| Format B | `import_episode(payload)` | 已测试 |
| LangGraph | `framework="langgraph"` | 已执行真实 `StateGraph` 并导入节点记录 |
| OpenAI Agents SDK | `framework="openai_agents"` | 已执行真实 `Runner`、工具调用和 SDK tracing |

机器契约：`src/eval_engine/integrations/evaluation_episode.schema.json`。

## 证据分栏

发布决定必须保留四类独立证据：

1. **业务状态**：确定性 Verifier 比较 `expected_state` 与 `final_state`，失败直接 hold。
2. **过程质量**：Process Reward / Judge 评价轨迹，低分进入 review。
3. **失败回归**：trace-debugger 的 compare 决定 pass/review/hold。
4. **推理性能**：`agent-release-evidence/v1` 对 TTFT、TPOT、Cache 等预算做硬检查。

Judge 高分不能覆盖业务终态错误，性能加速比也不能替代任务质量。

## 已验证闭环

`react-agent` expense held-out 3 条导出为 Episode 后：

- 业务终态 3/3 通过；
- `llm-eval-engine` 无需导入 react-agent，发布判断为 pass；
- `trace-debugger` 导入 3/3，`needs_fix=0`；
- 覆盖额度边界、事前审批和无票优先拒绝，并检查每条只有一次决策副作用。

SDK 集成测试使用本地确定性业务节点和测试模型，验证框架调度、工具执行、tracing、
Episode 转换和终态校验。它不调用远程模型，因此不证明 OpenAI API 的质量、延迟或可用性，
也不证明线上发布、人工审批或自动回滚已经完成。

## 运行

```powershell
# 安装并运行真实 SDK 集成
python -m pip install -e ".[sdk]"
python examples/run_sdk_integrations.py --out sdk-episodes

# 先由任意 Agent 导出 Episode JSON
python examples/run_cross_agent_release.py path/to/episodes \
  --process-quality process.json \
  --failure-gate failures.json \
  --performance performance.json
```
