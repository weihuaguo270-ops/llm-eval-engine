import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "examples" / "serve_blind_image_review.py"
SPEC = importlib.util.spec_from_file_location("serve_blind_image_review", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _row():
    return {"entry_id": "blind::img-01-1", "case_id": "img-01-1", "prompt": "p",
            "artifact_a": "a.png", "artifact_b": "b.png", "rater_id": "reviewer-1",
            "scores_a": {name: 4 for name in MODULE.DIMENSIONS},
            "scores_b": {name: 3 for name in MODULE.DIMENSIONS},
            "preference": "a", "notes": ""}


def test_prompt_translation_keeps_frozen_english_prompt_separate():
    translated = MODULE.translate_prompt(
        "a red ceramic travel mug on a white studio table, realistic photograph, natural lighting, no text"
    )
    assert translated == "白色影棚桌面上的红色陶瓷旅行杯；真实摄影，自然光照，不含文字。"


def test_submission_rejects_changed_frozen_fields_and_wrong_rater():
    row = _row()
    frozen = {row["entry_id"]: dict(row)}
    assert MODULE._valid_submission([row], frozen, "reviewer-1") is True
    changed = dict(row, prompt="changed")
    assert MODULE._valid_submission([changed], frozen, "reviewer-1") is False
    wrong_rater = dict(row, rater_id="reviewer-2")
    assert MODULE._valid_submission([wrong_rater], frozen, "reviewer-1") is False


def test_review_config_requires_unique_tokens_and_keeps_roots_isolated(tmp_path):
    first = tmp_path / "one" / "ratings.json"
    second = tmp_path / "two" / "ratings.json"
    first.parent.mkdir()
    second.parent.mkdir()
    first.write_text(__import__("json").dumps([_row()]), encoding="utf-8")
    second.write_text(__import__("json").dumps([_row()]), encoding="utf-8")
    reviews = MODULE._prepare_reviews([
        {"worksheet": first, "rater_id": "one", "access_token": "t1"},
        {"worksheet": second, "rater_id": "two", "access_token": "t2"},
    ])
    assert set(reviews) == {"t1", "t2"}
    assert reviews["t1"]["artifact_root"] == first.parent.resolve()
    with __import__("pytest").raises(ValueError, match="unique access token"):
        MODULE._prepare_reviews([
            {"worksheet": first, "rater_id": "one", "access_token": "same"},
            {"worksheet": second, "rater_id": "two", "access_token": "same"},
        ])
