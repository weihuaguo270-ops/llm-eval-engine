from eval_engine.integrations.episode import (
    attach_output_artifacts,
    episode_as_multimodal_case,
    import_episode,
    verify_episode_state,
)
from eval_engine.multimodal import (
    ArtifactIntegrityMetric,
    ClipScoreMetric,
    MultimodalEvaluator,
    SafetyClassifierMetric,
)


def test_import_format_b_episode_and_verify_nested_state():
    episode = import_episode(
        {
            "schema_version": "evaluation-episode/v1",
            "episode_id": "expense-1",
            "task": "approve claim",
            "framework": "custom",
            "agent_version": "v2",
            "split": "held_out",
            "expected_state": {
                "claim": {"status": "approved"},
                "audit": {"decision_events": 1},
            },
            "final_state": {
                "claim": {"status": "approved", "amount": 128},
                "audit": {"decision_events": 1},
            },
            "trajectory": {
                "session_id": "s1",
                "query": "approve claim",
                "steps": [{"step": 1, "thought": "done"}],
                "final_answer": "approved",
            },
        }
    )
    result = verify_episode_state(episode)
    assert result.passed is True
    assert [check.path for check in result.checks] == [
        "$.claim.status",
        "$.audit.decision_events",
    ]


def test_state_verifier_fails_closed_without_expected_state():
    episode = import_episode(
        {
            "session_id": "s1",
            "query": "q",
            "steps": [{"step": 1, "thought": "done"}],
            "final_answer": "done",
        }
    )
    result = verify_episode_state(episode)
    assert result.passed is False
    assert result.missing_expected_state is True


def test_import_langgraph_trace():
    episode = import_episode(
        {
            "run_id": "lg-1",
            "inputs": {"message": "refund order"},
            "outputs": {"answer": "done"},
            "nodes": [
                {
                    "node_name": "operator",
                    "planner_text": "look up order",
                    "tool": "get_order",
                    "tool_payload": {"order_id": "O-1"},
                    "tool_result": "paid",
                }
            ],
        },
        framework="langgraph",
    )
    assert episode.framework == "langgraph"
    assert episode.trajectory["steps"][0]["action"]["name"] == "get_order"


def test_import_openai_agents_trace():
    episode = import_episode(
        {
            "trace_id": "oa-1",
            "input": "refund order",
            "output": "done",
            "spans": [
                {
                    "type": "tool_call",
                    "name": "refund_order",
                    "input": {"order_id": "O-1"},
                    "output": {"status": "refunded"},
                }
            ],
        },
        framework="openai_agents",
    )
    assert episode.trajectory["steps"][0]["action"]["name"] == "refund_order"
    assert "refunded" in episode.trajectory["steps"][0]["observation"]


def test_attach_output_artifacts_projects_multimodal_case():
    episode = import_episode(
        {
            "schema_version": "evaluation-episode/v1",
            "episode_id": "media-ep-1",
            "task": "generate product shot",
            "split": "held_out",
            "expected_state": {"ok": True},
            "final_state": {"ok": True},
            "trajectory": {
                "session_id": "s1",
                "query": "generate product shot",
                "steps": [{"step": 1, "thought": "done"}],
                "final_answer": "done",
            },
        }
    )
    attach_output_artifacts(
        episode,
        [
            {
                "id": "image-1",
                "media_type": "image",
                "uri": "artifacts/product.png",
                "width": 512,
                "height": 512,
            }
        ],
        prompt="a red mug on a table",
        automatic_metrics={"clip_cosine": 0.37},
        safety_result={"nsfw_probability": 0.01, "passed": True},
    )
    case = episode_as_multimodal_case(episode)
    report = MultimodalEvaluator(
        [ArtifactIntegrityMetric(), ClipScoreMetric(), SafetyClassifierMetric()]
    ).evaluate(case)
    assert case["split"] == "held_out"
    assert report["passed"] is True
    assert report["metrics"][1]["score"] == 0.37
