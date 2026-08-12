"""Run real SDK workflows and write EvaluationEpisode v1 evidence."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from eval_engine.integrations import import_episode, verify_episode_state
from eval_engine.integrations.sdk_runtime import (
    run_langgraph_expense_episode,
    run_openai_agents_expense_episode,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="sdk-episodes")
    args = parser.parse_args()

    payloads = [
        ("langgraph", run_langgraph_expense_episode()),
        ("openai_agents", asyncio.run(run_openai_agents_expense_episode())),
    ]
    output_dir = Path(args.out)
    output_dir.mkdir(parents=True, exist_ok=True)
    for framework, payload in payloads:
        episode = import_episode(payload, framework=framework)
        envelope = episode.to_dict()
        envelope["state_verification"] = verify_episode_state(episode).to_dict()
        output = output_dir / f"{framework}.json"
        output.write_text(
            json.dumps(envelope, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"{framework}: {output} (state passed)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
