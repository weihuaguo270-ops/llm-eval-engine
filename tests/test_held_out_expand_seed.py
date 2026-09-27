"""Smoke: expand episodes parse and human seed covers every media cell."""

from __future__ import annotations

import json
from pathlib import Path

from eval_engine.core.multimodal_process_judge import DIMENSIONS, _is_media_step
from eval_engine.core.trajectory_parser import parse_trajectory
from eval_engine.gates.release_audit import rebuild_held_out_calibration
from eval_engine.integrations.episode import import_episode

ROOT = Path(__file__).resolve().parents[1]
EP_DIR = ROOT / "examples" / "fixtures" / "episodes" / "held_out_expand"
HUMAN = ROOT / "examples" / "fixtures" / "calibration" / "multimodal_held_out_expand_human.json"


def test_expand_episodes_have_no_prefilled_judge_scores():
    paths = sorted(EP_DIR.glob("*.json"))
    assert len(paths) == 36
    for path in paths:
        raw = json.loads(path.read_text(encoding="utf-8"))
        assert raw["split"] == "held_out"
        assert raw["metadata"].get("held_out_expand") is True
        for step in raw["trajectory"]["steps"]:
            assert "judge_scores" not in step


def test_expand_human_seed_covers_all_media_cells():
    human = json.loads(HUMAN.read_text(encoding="utf-8"))
    assert human["meta"]["sample_size_human_cells"] >= 300
    assert len(human["meta"]["episodes"]) == 36
    indexed = {
        (row["episode_id"], int(row["step_index"]), row["dimension"]): row
        for row in human["items"]
    }
    cells: dict[str, list[tuple[int, str, float]]] = {}
    for path in sorted(EP_DIR.glob("*.json")):
        episode = import_episode(json.loads(path.read_text(encoding="utf-8")))
        dag = parse_trajectory(episode.trajectory)
        episode_cells: list[tuple[int, str, float]] = []
        for node in dag.nodes:
            if node.step_type != "final" and not _is_media_step(node):
                continue
            for dim in DIMENSIONS:
                row = indexed[(episode.episode_id, node.step_index, dim)]
                assert row["human_score"] is not None
                assert row["judge_score"] is None
                episode_cells.append(
                    (node.step_index, dim, float(row["human_score"]))
                )
        cells[episode.episode_id] = episode_cells
    rebuilt = rebuild_held_out_calibration(human, cells)
    assert len(rebuilt["items"]) == human["meta"]["sample_size_human_cells"]
    assert all(row["judge_score"] is not None for row in rebuilt["items"])
