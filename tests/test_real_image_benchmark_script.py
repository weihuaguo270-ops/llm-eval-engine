import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "examples" / "run_real_image_benchmark.py"
SPEC = importlib.util.spec_from_file_location("run_real_image_benchmark", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_init_and_unrated_finalize_remain_interface(tmp_path):
    payload = MODULE.initialize(tmp_path)
    assert payload["dataset"]["case_count"] == 100
    report = MODULE.finalize(tmp_path)
    assert report["completion_gate"]["passed"] is False
    assert report["completion_gate"]["evidence_level"] == "interface"


def test_smoke_and_full_review_files_are_isolated(tmp_path):
    MODULE.write_json(tmp_path / "smoke_records.json", [])
    MODULE.write_json(tmp_path / "generation_records.json", [])
    assert MODULE.finalize(tmp_path, smoke=True)["completion_gate"]["passed"] is False
    assert MODULE.finalize(tmp_path, smoke=False)["completion_gate"]["passed"] is False
