"""eval_loop — Adaptive evaluation loop engine

Core workflow (generative tasks):

    User input
        │
        ▼
    IntentClassifier → "generative_task"
        │
        ▼
    ╔══════════════════════════════════════════╗
    ║         Eval Loop (iterates until pass)   ║
    ║                                          ║
    ║  Agent → trajectory → Process Reward     ║
    ║       │                    │             ║
    ║       │               ┌───┴───┐         ║
    ║       │           all pass  low scores   ║
    ║       │               │       │         ║
    ║       │               ▼       ▼         ║
    ║       │            output   pack fixes  ║
    ║       │               │       │         ║
    ║       │               │       ▼         ║
    ║       │               │   LLM retry     ║
    ║       │               │   → loop again  ║
    ║       └───────────────┘                 ║
    ╚══════════════════════════════════════════╝

Key design decisions:
  - max_iterations: prevents infinite loops (default 3)
  - min_improvement: oscillation detection (stops if score stalls)
  - Every iteration logged in healing_log for full audit trail
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from eval_engine.intent.classifier import IntentClassifier, TaskType
from eval_engine.core.trajectory_parser import (
    parse_trajectory,
    StepsDAG,
    dag_to_text,
)
from eval_engine.core.process_reward import (
    ProcessRewardScorer,
    ProcessRewardReport,
    analyze_error_propagation,
    pack_revision_instructions,
)
from eval_engine.safety.human_in_the_loop import HumanInTheLoop


@dataclass
class EvalLoopResult:
    """Final output of the Eval Loop

    Attributes:
        query:         Original user input
        task_type:     Classified task type
        final_output:  Final agent output text
        report:        Process Reward scoring report
        iterations:    Number of loop iterations (1 = pass on first try)
        healing_log:   Self-healing process record
        error_analysis: Error propagation analysis
        passed:        Whether quality threshold was met
    """
    query: str
    task_type: str
    final_output: str
    report: ProcessRewardReport
    iterations: int
    healing_log: list[dict]
    error_analysis: dict[str, Any]
    passed: bool


@dataclass
class EvalLoopConfig:
    """Eval Loop configuration"""
    max_iterations: int = 3
    min_improvement: float = 0.1
    fast_mode_threshold: int = 5
    verbose: bool = True


class EvalLoopEngine:
    """Adaptive Eval Loop engine

    Orchestrates agent execution -> scoring -> revision -> re-execution cycles.

    Usage:
        engine = EvalLoopEngine(
            agent_fn=run_agent,       # Agent execution function
            judge_fn=call_judge_llm,  # Judge LLM invocation
        )
        result = engine.execute("Write a market analysis report")

        if result.passed:
            print(result.final_output)
        else:
            print("Quality check failed, report:")
            print(result.report)
    """

    def __init__(
        self,
        agent_fn: Callable[[str], dict[str, Any]],
        judge_fn: Callable[[str], dict[str, Any]],
        config: Optional[EvalLoopConfig] = None,
        intent_classifier: Optional[IntentClassifier] = None,
        hitl: Optional[HumanInTheLoop] = None,
    ):
        """
        Args:
            agent_fn:           Agent execution function.
                                Receives query string, returns dict with
                                "output" and "trajectory" keys.
            judge_fn:           Judge LLM invocation function.
                                Receives prompt string, returns dict.
            config:             Loop configuration.
            intent_classifier:  Intent classifier (default: new instance).
            hitl:               Human-in-the-loop manager.
                                Pass None for fully automatic mode.
        """
        self.agent_fn = agent_fn
        self.judge_fn = judge_fn
        self.config = config or EvalLoopConfig()
        self.classifier = intent_classifier or IntentClassifier()
        self.hitl = hitl

    def execute(self, user_input: str) -> EvalLoopResult:
        """Execute the full Eval Loop

        Args:
            user_input: User's request text

        Returns:
            EvalLoopResult with final output and scoring report
        """
        # 1. Classify intent
        task_type = self.classifier.classify(user_input)
        self._log(f"Intent classification: {task_type}")

        # 2. Functional test -> single execution, return directly
        if task_type == TaskType.FUNCTIONAL_TEST:
            return self._execute_functional(user_input)

        # 3. Generative task -> enter Eval Loop
        return self._execute_generative(user_input)

    def _execute_functional(self, query: str) -> EvalLoopResult:
        """Functional test: single execution with quick scoring"""
        agent_output = self.agent_fn(query)
        trajectory = agent_output.get("trajectory", {})

        try:
            dag = parse_trajectory(trajectory)
            scorer = ProcessRewardScorer(judge_fn=self.judge_fn)
            report = scorer.score_trajectory(dag, fast_mode=True)
        except Exception:
            report = ProcessRewardReport(
                query=query,
                per_step=[],
                overall_score=0,
                num_steps=0,
                num_scored=0,
                num_failed_steps=0,
                error_sources=[],
                needs_revision=False,
                healing_log=[],
                dag_summary={},
            )

        return EvalLoopResult(
            query=query,
            task_type=TaskType.FUNCTIONAL_TEST,
            final_output=agent_output.get("output", ""),
            report=report,
            iterations=1,
            healing_log=[],
            error_analysis={},
            passed=True,
        )

    def _execute_generative(self, query: str) -> EvalLoopResult:
        """Generative task: adaptive Eval Loop with revision"""
        scorer = ProcessRewardScorer(judge_fn=self.judge_fn)
        healing_log: list[dict] = []
        prev_overall_score = 0.0
        oscillation_count = 0
        dag = None
        report = None
        output_text = ""

        for iteration in range(1, self.config.max_iterations + 1):
            self._log(f"Iteration {iteration}/{self.config.max_iterations}")

            # a. Execute agent
            agent_output = self.agent_fn(query)
            trajectory = agent_output.get("trajectory", {})
            output_text = agent_output.get("output", "")

            # b. Parse trajectory -> DAG
            try:
                dag = parse_trajectory(trajectory)
            except ValueError as e:
                self._log(f"Trajectory parse failed: {e}")
                continue

            # c. Process Reward scoring
            fast = dag.num_steps < self.config.fast_mode_threshold
            report = scorer.score_trajectory(dag, fast_mode=fast)

            # d. Error propagation analysis
            error_analysis = analyze_error_propagation(report, dag)

            # e. Log iteration
            log_entry = {
                "iteration": iteration,
                "overall_score": report.overall_score,
                "needs_revision": report.needs_revision,
                "num_failed_steps": report.num_failed_steps,
                "error_sources": report.error_sources,
                "final_output_preview": output_text[:200],
            }
            healing_log.append(log_entry)

            self._log(
                f"  Score: {report.overall_score:.3f}, "
                f"Failed steps: {report.num_failed_steps}, "
                f"Needs revision: {report.needs_revision}"
            )

            # f. Check if passed
            if not report.needs_revision:
                self._log(f"✅ Passed at iteration {iteration}")
                return EvalLoopResult(
                    query=query,
                    task_type=TaskType.GENERATIVE_TASK,
                    final_output=output_text,
                    report=report,
                    iterations=iteration,
                    healing_log=healing_log,
                    error_analysis=error_analysis,
                    passed=True,
                )

            # g. Oscillation detection: score not improving
            improvement = report.overall_score - prev_overall_score
            if iteration > 1 and improvement < self.config.min_improvement:
                oscillation_count += 1
                if oscillation_count >= 2:
                    self._log(
                        f"⚠ Oscillation detected "
                        f"(improvement {improvement:.3f} < {self.config.min_improvement}), "
                        f"stopping loop"
                    )
                    return EvalLoopResult(
                        query=query,
                        task_type=TaskType.GENERATIVE_TASK,
                        final_output=output_text,
                        report=report,
                        iterations=iteration,
                        healing_log=healing_log,
                        error_analysis=error_analysis,
                        passed=False,
                    )

            prev_overall_score = report.overall_score

            # h. Human approval for revision injection
            if self.hitl:
                if not self.hitl.check_direction(
                    "Inject revision instructions",
                    details=f"Iteration {iteration}: {report.num_failed_steps} step(s) "
                            f"below threshold. Injecting fix instructions for retry.",
                ):
                    self._log(f"⏸ User rejected revision injection, stopping")
                    return EvalLoopResult(
                        query=query,
                        task_type=TaskType.GENERATIVE_TASK,
                        final_output=output_text,
                        report=report,
                        iterations=iteration,
                        healing_log=healing_log,
                        error_analysis=error_analysis,
                        passed=False,
                    )

            # i. Pack revision instructions
            fix_instructions = pack_revision_instructions(report, dag)
            self._log(f"  Generated {len(fix_instructions)} chars of fix instructions")

            # j. Human approval for re-execution
            if self.hitl:
                if not self.hitl.check_direction(
                    "Re-execute agent",
                    details=f"Retry agent execution with revision instructions "
                            f"(attempt {iteration + 1})",
                ):
                    self._log(f"⏸ User rejected re-execution, stopping")
                    return EvalLoopResult(
                        query=query,
                        task_type=TaskType.GENERATIVE_TASK,
                        final_output=output_text,
                        report=report,
                        iterations=iteration,
                        healing_log=healing_log,
                        error_analysis=error_analysis,
                        passed=False,
                    )

            # k. Inject revision instructions into query for retry
            query = (
                f"【Original task】{query}\n\n"
                f"【Previous feedback】The following steps need improvement:\n"
                f"{fix_instructions}\n\n"
                f"Please revise based on the above feedback. "
                f"Keep what works, fix identified issues only."
            )

        # Max iterations reached
        self._log(f"⚠ Max iterations ({self.config.max_iterations}) reached")
        return EvalLoopResult(
            query=query,
            task_type=TaskType.GENERATIVE_TASK,
            final_output=output_text,
            report=report,
            iterations=self.config.max_iterations,
            healing_log=healing_log,
            error_analysis=analyze_error_propagation(report, dag) if dag else {},
            passed=False,
        )

    def _log(self, msg: str) -> None:
        if self.config.verbose:
            print(f"[EvalLoop] {msg}")
