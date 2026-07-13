"""eval-engine — Experimental LLM evaluation framework

Provides adaptive evaluation for LLM agent outputs via:
  - Process Reward step-level scoring
  - Dynamic rubric generation per step context
  - Self-healing eval loop with oscillation detection
  - Human-in-the-loop oversight

Core modules:
  - core.contract:      Verifier contract interface for composable scoring
  - core.trajectory_parser: Agent trajectory to DAG step structure
  - core.dynamic_rubric:  Dynamic scoring criteria generation
  - core.process_reward:  Process Reward step-level scoring
  - judge:                Judge LLM invocation and calibration
  - loop:                 Adaptive eval loop with self-healing
  - gates:                Baseline scoring and regression detection
  - intent:               Task classification for routing
  - safety:               Human-in-the-loop oversight
  - dataset:              Dataset management
  - observability:        Reporting and audit
"""

__version__ = "0.1.0"
