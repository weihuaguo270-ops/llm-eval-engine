# LLM Eval Engine

**Production-grade LLM evaluation framework** with Process Reward scoring, dynamic rubric generation, adaptive eval loop, and human-in-the-loop oversight.

## Why This Framework

Standard LLM evaluation approaches have fundamental limitations:

| Limitation | This Framework |
|------------|---------------|
| Fixed template scoring for all tasks | **Dynamic rubric** — per-step criteria generated from actual context |
| Binary pass/fail on final answer | **Process Reward** — step-level scoring traces error propagation |
| Single-pass evaluation | **Adaptive Eval Loop** — low scores trigger revision and re-execution |
| No human oversight | **Hierarchical permissions** (SAFE / NOTIFY / CONFIRM / DENY) with HITL |
| Manual retry decisions | **Oscillation detection** — automatically stops when improvement stalls |

## Architecture

```
llm-eval-engine/
│
├── core/                       # Framework-agnostic evaluation primitives
│   ├── contract.py             Verifier contract interface (composable rubrics)
│   ├── trajectory_parser.py    Agent trajectory → DAG step structure
│   ├── dynamic_rubric.py       ★ Per-step dynamic scoring criteria
│   └── process_reward.py       ★ Step-level Process Reward + error propagation
│
├── judge/                      # Judge LLM invocation
│   ├── executor.py             Judge LLM call wrapper (JSON parsing, retry)
│   ├── calibration.py          Scoring calibration and bias adjustment
│   └── templates/              Scoring prompt templates
│
├── loop/                       # Adaptive evaluation loop
│   ├── eval_loop.py            ★ Core loop: score → revise → re-execute
│   └── fix_packer.py           Revision instruction packing
│
├── gates/                      # Scoring gates
│   ├── baseline.py             Baseline comparison scoring
│   └── regression_gate.py      Regression detection across runs
│
├── intent/                     # Task classification for routing
│   └── classifier.py           Intent → functional_test / generative_task
│
├── safety/                     # Human oversight
│   └── human_in_the_loop.py    HITL callback interface
│
├── dataset/                    # Dataset management
│   └── manager.py              Dataset loading and splitting
│
└── observability/              # Observability
    └── report.py               Audit report generation
```

## Key Concepts

### 1. Dynamic Rubric Generation

Instead of scoring all tasks against a fixed template, the framework generates scoring criteria per step based on actual context:

```
Step 3 (agent executed web_search for "Python SQL injection")
→ Dynamic criteria:
  ① Is the search query reasonable given the task?
  ② Are search results used in subsequent steps?
  ③ Does the agent have a fallback if search is insufficient?
```

### 2. Process Reward Scoring

Inspired by o1/o3 Process Reward Models — evaluates each step individually rather than only the final output:

```
Step 1: web_search (score: 0.92 ✅)
Step 2: read_results (score: 0.85 ✅)
Step 3: review_tool (score: 0.40 ❌ — invalid parameters)
Step 4: summarize (score: 0.60 ❌ — based on incomplete data)
         ↑ Error propagation: Step 3 failure → Step 4 contaminated
```

### 3. Adaptive Eval Loop

```
Agent → trajectory → Process Reward
       |                    |
       |              ┌─────┴──────┐
       |          all pass     low scores
       |              |           |
       |              ▼           ▼
       |           output     pack fixes
       |              |           |
       |              |           ▼
       |              |     LLM retry with feedback
       |              |      → loop again
       └──────────────┘
```

- **Max iterations**: prevents infinite loops (default 3)
- **Min improvement threshold**: stops if score stalls (oscillation detection)
- **Human approval hooks**: optional HITL at revision injection and re-execution

## Quick Start

```bash
pip install eval-engine
```

```python
from eval_engine.loop.eval_loop import EvalLoopEngine, EvalLoopConfig

# Configure
config = EvalLoopConfig(max_iterations=3, verbose=True)

# Create engine with your agent and judge functions
engine = EvalLoopEngine(
    agent_fn=my_agent_run,     # Callable[[str], dict]
    judge_fn=my_judge_call,    # Callable[[str], dict]
    config=config,
)

# Execute
result = engine.execute("Analyze the Q3 financial report")

if result.passed:
    print(result.final_output)
else:
    print(f"Score: {result.report.overall_score}")
    print(f"Failed steps: {result.report.error_sources}")
```

## Integration

### With any Agent Framework

The framework is agent-agnostic. You provide:

1. **agent_fn(query: str) -> dict** — Your agent execution function. Returns `{"output": str, "trajectory": dict}`
2. **judge_fn(prompt: str) -> dict** — Your Judge LLM invoker. Returns parsed JSON with scores

### Permission System

```python
from eval_engine.safety.human_in_the_loop import HumanInTheLoop

def ask_user(prompt, options):
    return input(f"{prompt} {options}: ")

hitl = HumanInTheLoop(ask_fn=ask_user)
engine = EvalLoopEngine(agent_fn=..., judge_fn=..., hitl=hitl)
```

## Running Tests

```bash
pip install -e ".[test]"
pytest tests/
```

## Requirements

- Python 3.10+
- No mandatory external dependencies (core modules are pure Python)
- Judge executor requires `requests` for LLM API calls (optional, for built-in executor)

## License

MIT

## Related Projects

- [attention-from-scratch](https://github.com/weihuaguo270-ops/attention-from-scratch) — NumPy/PyTorch implementation of Transformer attention mechanisms (MHA, GQA, MLA, SpecDecoding)
