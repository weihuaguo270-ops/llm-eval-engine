import importlib.util
from pathlib import Path


def _load_normalizer():
    path = Path(__file__).resolve().parents[1] / "scripts" / "normalize_evidence_paths.py"
    spec = importlib.util.spec_from_file_location("normalize_evidence_paths", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_normalizer_replaces_workspace_prefix_and_preserves_payload(tmp_path):
    module = _load_normalizer()
    evidence = tmp_path / "evidence.json"
    evidence.write_text(
        '{"source": "D:/agent_learning/react-agent/run.json", "score": 0.75}',
        encoding="utf-8",
    )

    assert module.normalize_file(evidence) is True
    assert evidence.read_text(encoding="utf-8") == (
        '{"source": "${WORKSPACE_ROOT}/react-agent/run.json", "score": 0.75}'
    )
