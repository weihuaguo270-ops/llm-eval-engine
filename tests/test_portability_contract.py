from pathlib import Path

from eval_engine.integrations import import_episode


def test_episode_import_does_not_require_agent_sdk(monkeypatch):
    monkeypatch.setitem(__import__("sys").modules, "langgraph", None)
    episode = import_episode(
        {
            "schema_version": "evaluation-episode/v1",
            "episode_id": "portable-1",
            "task": "portable task",
            "trajectory": {
                "session_id": "portable-1",
                "query": "portable task",
                "steps": [{"step": 1, "thought": "done"}],
                "final_answer": "done",
            },
        }
    )
    assert episode.episode_id == "portable-1"


def test_repositories_document_isolated_langgraph_environments():
    root = Path(__file__).resolve().parents[1]
    text = (root / "docs" / "PORTABILITY.md").read_text(encoding="utf-8")
    assert "evaluation-episode/v1" in text
    assert "deliberately isolated" in text
