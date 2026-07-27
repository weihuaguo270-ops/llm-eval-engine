# Benchmark Live Judge 对比

- 生成时间: `2026-07-27T21:44:52`
- 任务集版本: **v2**
- 模型数: **1**

## 总览

| 模型 | 用例数 | 通过率 | 均分 | 平均延迟(ms) | 总 tokens |
|------|------:|-------:|-----:|-------------:|----------:|
| `deepseek-v3` | 3 | 66.7% | 4.70 | 1000 | 1800 |

## 分品类通过率

| 品类 | `deepseek-v3` |
|------|---:|
| `tool` | 67% |

## 失败类型分布（未通过用例）

| 类型 | 次数 | 占比 |
|------|-----:|-----:|
| 其他 | 1 | 100.0% |

## 逐用例对比

| 用例 | `deepseek-v3` 分/过 |
|------|---:|
| `bench_tool_001` | 4.9 PASS |
| `bench_tool_002` | 4.8 PASS |
| `bench_tool_003` | 4.4 FAIL |

## Live 接线

- wiring: `JUDGE_API_KEY<-DEEPSEEK_API_KEY, JUDGE_BASE_URL=deepseek, JUDGE_LLM_CONFIG=react-agent`
- judge_model: `deepseek-chat`
- 说明: 轨迹为冻结 profile，Judge 为当次 live 调用
