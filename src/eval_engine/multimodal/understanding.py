"""Understanding-side image/video QA benchmarks (VQA / temporal QA).

Project-authored, fixed-cardinality case sets modeled after public suites such
as MMMU-style image reasoning and Video-MME-style temporal QA. Cases ship media
*references and scene descriptions*, not binary corpora, so CI can validate
contracts without downloading large libraries.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from typing import Any, Mapping, Sequence

IMAGE_VQA_CASE_COUNT = 40
VIDEO_QA_CASE_COUNT = 30
_WHITESPACE_RE = re.compile(r"\s+")
_PUNCT_RE = re.compile(r"[^\w\s]", re.UNICODE)


def build_image_vqa_dataset() -> list[dict[str, Any]]:
    """Return 40 frozen image-understanding cases with isolated source clusters."""
    rows = (
        ("ocr", "short", "What brand name is printed on the mug?", "Acme", None,
         "White ceramic mug with black 'Acme' text facing the camera."),
        ("ocr", "short", "What three digits appear on the parking sign?", "120", None,
         "Blue parking sign showing the number 120."),
        ("ocr", "mcq", "Which word is on the storefront awning?", "Bakery",
         ["Bakery", "Library", "Clinic", "Garage"],
         "Street storefront with a striped awning labeled Bakery."),
        ("ocr", "short", "Read the handwritten total on the receipt.", "48.5", None,
         "Paper receipt with handwritten total 48.5 at the bottom."),
        ("counting", "exact", "How many red apples are on the plate?", "3", None,
         "White plate holding exactly three red apples."),
        ("counting", "exact", "How many windows are visible on the building facade?", "6", None,
         "Two-story brick facade with three windows per floor."),
        ("counting", "mcq", "How many people are seated at the table?", "2",
         ["1", "2", "3", "4"],
         "Cafe table with two seated adults and one empty chair."),
        ("counting", "exact", "How many yellow pencils lie beside the notebook?", "5", None,
         "Black notebook with five yellow pencils arranged beside it."),
        ("spatial", "short", "Which object is left of the red sphere?", "blue cube", None,
         "Gray floor with a blue cube to the left of a red sphere."),
        ("spatial", "mcq", "Where is the bicycle relative to the bench?", "behind",
         ["in front", "behind", "on top", "under"],
         "Park bench in foreground with a bicycle parked behind it."),
        ("spatial", "short", "Is the taller bottle on the left or right?", "right", None,
         "Two glass bottles; the taller bottle stands on the right."),
        ("spatial", "mcq", "Which object is closest to the camera?", "orange",
         ["orange", "bowl", "spoon", "napkin"],
         "Close-up orange in front of a blurred bowl and spoon."),
        ("attribute", "short", "What color is the hiking backpack?", "green", None,
         "Green hiking backpack with visible compartments on a studio table."),
        ("attribute", "mcq", "What material is the tabletop?", "wood",
         ["glass", "wood", "metal", "marble"],
         "Wireless headphones resting on a wooden tabletop."),
        ("attribute", "short", "Is the umbrella open or closed?", "open", None,
         "Pedestrian holding an open black umbrella in the rain."),
        ("attribute", "mcq", "What is the lighting condition?", "night",
         ["morning", "noon", "dusk", "night"],
         "Rainy city crossing with neon reflections at night."),
        ("scene", "short", "What outdoor setting is shown?", "harbor", None,
         "Small fishing harbor before sunrise with moored boats."),
        ("scene", "mcq", "Which indoor setting is shown?", "library",
         ["kitchen", "library", "stadium", "garage"],
         "Quiet library reading room in morning sunlight."),
        ("scene", "short", "What weather is visible outdoors?", "rain", None,
         "Wet asphalt and umbrellas at a pedestrian crossing."),
        ("scene", "mcq", "What time of day does the harbor photo suggest?", "before sunrise",
         ["noon", "before sunrise", "midnight", "afternoon"],
         "Dim blue-hour light over a quiet harbor."),
        ("chart", "exact", "What is the tallest bar value?", "40", None,
         "Bar chart with values 10, 25, 40, 15; tallest bar labeled 40."),
        ("chart", "mcq", "Which quarter has the lowest sales?", "Q1",
         ["Q1", "Q2", "Q3", "Q4"],
         "Line chart where Q1 is the minimum point."),
        ("chart", "exact", "How many slices does the pie chart contain?", "4", None,
         "Pie chart divided into four labeled slices."),
        ("chart", "short", "What unit is on the y-axis?", "percent", None,
         "Axis chart with y-axis labeled percent."),
        ("document", "short", "What is the invoice number?", "INV-2048", None,
         "Invoice header showing Invoice No. INV-2048."),
        ("document", "mcq", "What payment status is stamped?", "paid",
         ["paid", "overdue", "void", "draft"],
         "Document corner stamped PAID in green ink."),
        ("document", "exact", "How many line items are listed?", "3", None,
         "Table listing exactly three product line items."),
        ("document", "short", "Who is the bill-to name?", "Nova Labs", None,
         "Bill-to field filled with Nova Labs."),
        ("reasoning", "short", "Why is the floor wet?", "rain", None,
         "People with umbrellas entering a lobby; wet footprints on the floor."),
        ("reasoning", "mcq", "What is the most likely next action?", "board the train",
         ["board the train", "cook dinner", "swim", "ski"],
         "Passengers with luggage on a platform as a train arrives."),
        ("reasoning", "short", "Is the mug empty or filled?", "filled", None,
         "Travel mug with visible steam rising from the opening."),
        ("reasoning", "mcq", "Which claim is supported by the image?", "the road is wet",
         ["the road is wet", "it is snowing", "the sky is clear", "no cars exist"],
         "Night street with reflective wet pavement and car lights."),
        ("safety_perception", "mcq", "Is any person in immediate danger?", "no",
         ["yes", "no"],
         "Adults calmly crossing at a marked crosswalk with a green light."),
        ("safety_perception", "short", "Is smoke coming from the toaster?", "no", None,
         "Kitchen counter with a closed toaster and no visible smoke."),
        ("safety_perception", "mcq", "Does the scene show broken glass?", "no",
         ["yes", "no"],
         "Intact glass bottles standing upright on a table."),
        ("safety_perception", "short", "Are warning labels visible?", "yes", None,
         "Chemical bottle with a clearly visible warning label facing camera."),
        ("fine_grained", "short", "What fruit is sliced on the dark plate?", "dragon fruit", None,
         "Sliced dragon fruit on a dark ceramic plate."),
        ("fine_grained", "mcq", "Which macaron colors are present?", "yellow blue pink",
         ["yellow blue pink", "only brown", "red green", "black white"],
         "Three macarons in yellow, blue, and pink."),
        ("fine_grained", "short", "What animal is reading under the lamp?", "fox", None,
         "Watercolor fox reading under a street lamp."),
        ("fine_grained", "mcq", "What is the robot doing?", "organizing parcels",
         ["organizing parcels", "painting", "sleeping", "driving"],
         "Friendly service robot organizing parcels."),
    )
    if len(rows) != IMAGE_VQA_CASE_COUNT:
        raise RuntimeError("image VQA row table drifted from IMAGE_VQA_CASE_COUNT")
    return [_case_from_row("image", index, row) for index, row in enumerate(rows)]


def build_video_qa_dataset() -> list[dict[str, Any]]:
    """Return 30 frozen video-understanding cases with temporal focus."""
    rows = (
        ("action", "short", "What object moves from left to right?", "toy car", None,
         "Red toy car driving left to right across a white table."),
        ("action", "mcq", "What happens to the blue ball?", "rolls down a ramp",
         ["rolls down a ramp", "flies upward", "melts", "vanishes"],
         "Blue ball rolling down a wooden ramp and stopping."),
        ("action", "short", "What does the dog do with the ball?", "catches and returns it", None,
         "Dog catches a soft ball and returns it."),
        ("action", "mcq", "What does the robot arm place on the belt?", "parcel",
         ["parcel", "cup", "book", "plant"],
         "Robot arm moving one parcel onto a conveyor belt."),
        ("temporal", "short", "Does the flower open or close?", "open", None,
         "White flower opening gradually in morning light."),
        ("temporal", "mcq", "What happens to the ice cubes?", "melt",
         ["melt", "freeze further", "float away", "turn pink"],
         "Ice cubes melting slowly in a transparent glass."),
        ("temporal", "short", "Do cloud shadows move across the valley?", "yes", None,
         "Cloud shadows moving across a green mountain valley."),
        ("temporal", "mcq", "What stays still while the flame flickers?", "candle body",
         ["candle body", "camera", "tablecloth only", "nothing"],
         "Candle flame flickering while the candle body stays still."),
        ("counting", "exact", "How many glass bottles rotate on the table?", "2", None,
         "Exactly two glass bottles rotating slowly on a table."),
        ("counting", "exact", "How many yellow pencils move into a row?", "5", None,
         "Five yellow pencils moving into a neat row."),
        ("counting", "mcq", "How many balloons rise into the sky?", "3",
         ["1", "2", "3", "4"],
         "Three balloons rising slowly into a clear sky."),
        ("counting", "exact", "How many people exchange the folder?", "2", None,
         "Two people exchanging a blue folder in an office."),
        ("camera", "short", "Does the camera push in or pull out on the coffee cup?", "push in", None,
         "Camera pushing slowly toward a steaming cup of coffee."),
        ("camera", "mcq", "Which camera move is used on the books?", "pan right",
         ["pan right", "tilt down", "orbit left", "static"],
         "Camera panning right across a row of colorful books."),
        ("camera", "short", "What is revealed as the camera zooms out?", "fishing harbor", None,
         "Slow zoom out revealing a small fishing harbor."),
        ("camera", "mcq", "What does the tilt-up shot end on?", "glass tower",
         ["glass tower", "river", "forest", "tunnel"],
         "Camera tilting upward from a street to a glass tower."),
        ("spatial", "short", "Where does the blue cube move relative to the red sphere?", "behind", None,
         "Blue cube moving behind a stationary red sphere."),
        ("spatial", "mcq", "Where does the boat travel?", "under a stone bridge",
         ["under a stone bridge", "over a roof", "into a cave", "around a fountain"],
         "Small boat traveling under a stone bridge."),
        ("spatial", "short", "Does the bicycle move toward background or foreground?", "background", None,
         "Bicycle moving from foreground to background along a path."),
        ("spatial", "mcq", "Where does the cyclist pass relative to the bench?", "behind",
         ["behind", "through", "above", "under"],
         "Cyclist passing behind a park bench on a sunny day."),
        ("causal", "short", "Why do raindrops slide on the window?", "gravity and accumulation", None,
         "Raindrops collecting and sliding down a window."),
        ("causal", "mcq", "What causes the sugar to dissolve?", "stirring with a spoon",
         ["stirring with a spoon", "freezing", "cutting", "blowing"],
         "Spoon stirring sugar into a cup of tea."),
        ("causal", "short", "What interaction transfers the folder?", "hand exchange", None,
         "Two people exchanging a blue folder hand to hand."),
        ("causal", "mcq", "What makes the paper airplane move?", "gliding through air",
         ["gliding through air", "rolling on wheels", "sinking in water", "melting"],
         "Paper airplane gliding through a quiet classroom."),
        ("scene", "short", "What weather is shown on the city street?", "rain", None,
         "Pedestrians crossing a rainy city street at night."),
        ("scene", "mcq", "What environment surrounds the train?", "mountains",
         ["mountains", "desert", "airport", "mall"],
         "Train crossing a stone bridge in the mountains."),
        ("scene", "short", "Are the market lanterns moving?", "yes", None,
         "Lanterns swaying above an empty evening market."),
        ("scene", "mcq", "What surface do the waves reach?", "sandy beach",
         ["sandy beach", "rooftop", "carpet", "ice rink"],
         "Small waves reaching a sandy beach before sunrise."),
        ("ocr_temporal", "short", "Does any on-screen number change?", "no", None,
         "Static labeled props with no changing digits across frames."),
        ("ocr_temporal", "mcq", "What text remains readable throughout?", "EXIT",
         ["EXIT", "SALE", "STOP", "OPEN"],
         "Door sign reading EXIT visible for the full clip."),
    )
    if len(rows) != VIDEO_QA_CASE_COUNT:
        raise RuntimeError("video QA row table drifted from VIDEO_QA_CASE_COUNT")
    return [_case_from_row("video", index, row) for index, row in enumerate(rows)]


def image_vqa_dataset_manifest(cases: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Validate image VQA cardinality, split isolation, and fingerprint."""
    return _manifest(
        cases,
        schema_version="image-vqa-dataset/v1",
        expected_count=IMAGE_VQA_CASE_COUNT,
        task_type="image_vqa",
        peer_suites=("MMMU-lite style categories", "OCR-VQA / TextVQA style probes"),
    )


def video_qa_dataset_manifest(cases: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Validate video QA cardinality, split isolation, and fingerprint."""
    return _manifest(
        cases,
        schema_version="video-qa-dataset/v1",
        expected_count=VIDEO_QA_CASE_COUNT,
        task_type="video_qa",
        peer_suites=("Video-MME style temporal QA", "MVBench-style action probes"),
    )


def score_understanding_answer(
    case: Mapping[str, Any],
    prediction: str | None,
) -> dict[str, Any]:
    """Score one model answer with exact / normalized / multiple-choice rules."""
    answer_type = str(case.get("answer_type") or "short")
    gold = str(case.get("answer") or "")
    pred = "" if prediction is None else str(prediction)
    if not pred.strip():
        return {
            "case_id": case.get("id"),
            "answer_type": answer_type,
            "score": 0.0,
            "passed": False,
            "matched": False,
            "prediction": pred,
            "gold": gold,
            "reason": "empty_prediction",
        }
    if answer_type == "mcq":
        choices = [str(item) for item in case.get("choices") or []]
        matched = _normalize(pred) == _normalize(gold) or _mcq_letter_match(pred, gold, choices)
        return {
            "case_id": case.get("id"),
            "answer_type": answer_type,
            "score": 1.0 if matched else 0.0,
            "passed": matched,
            "matched": matched,
            "prediction": pred,
            "gold": gold,
            "choices": choices,
            "reason": "mcq_match" if matched else "mcq_mismatch",
        }
    if answer_type == "exact":
        matched = pred.strip() == gold.strip()
        return {
            "case_id": case.get("id"),
            "answer_type": answer_type,
            "score": 1.0 if matched else 0.0,
            "passed": matched,
            "matched": matched,
            "prediction": pred,
            "gold": gold,
            "reason": "exact_match" if matched else "exact_mismatch",
        }
    matched = _normalize(pred) == _normalize(gold)
    return {
        "case_id": case.get("id"),
        "answer_type": answer_type,
        "score": 1.0 if matched else 0.0,
        "passed": matched,
        "matched": matched,
        "prediction": pred,
        "gold": gold,
        "reason": "normalized_match" if matched else "normalized_mismatch",
    }


def evaluate_understanding_predictions(
    cases: Sequence[Mapping[str, Any]],
    predictions: Mapping[str, str],
) -> dict[str, Any]:
    """Aggregate understanding accuracy by split and category."""
    indexed = {str(case["id"]): case for case in cases}
    scores = []
    missing = []
    for case_id, case in indexed.items():
        if case_id not in predictions:
            missing.append(case_id)
            continue
        scores.append(score_understanding_answer(case, predictions[case_id]))
    by_split: dict[str, list[float]] = {}
    by_category: dict[str, list[float]] = {}
    for item in scores:
        case = indexed[str(item["case_id"])]
        by_split.setdefault(str(case["split"]), []).append(float(item["score"]))
        by_category.setdefault(str(case["category"]), []).append(float(item["score"]))
    overall = (sum(float(item["score"]) for item in scores) / len(scores)) if scores else 0.0
    return {
        "schema_version": "understanding-eval-report/v1",
        "case_count": len(cases),
        "scored_count": len(scores),
        "missing_predictions": missing,
        "overall_accuracy": round(overall, 4),
        "passed": not missing and bool(scores),
        "split_accuracy": {
            split: round(sum(values) / len(values), 4)
            for split, values in sorted(by_split.items())
        },
        "category_accuracy": {
            category: round(sum(values) / len(values), 4)
            for category, values in sorted(by_category.items())
        },
        "cases": scores,
        "claim_boundary": (
            "Contract-level understanding accuracy over project-authored media "
            "descriptions. Not a substitute for full MMMU/Video-MME leaderboard runs."
        ),
    }


def understanding_case_to_eval_input(case: Mapping[str, Any]) -> dict[str, Any]:
    """Project a dataset case into a MultimodalEvaluator-friendly payload."""
    media_type = "video" if str(case.get("task_type")) == "video_qa" else "image"
    return {
        "id": case["id"],
        "prompt": case["question"],
        "query": case["question"],
        "split": case["split"],
        "task_type": case["task_type"],
        "answer": case["answer"],
        "answer_type": case["answer_type"],
        "choices": list(case.get("choices") or []),
        "output_artifacts": [
            {
                "id": f"{case['id']}-media",
                "media_type": media_type,
                "uri": case["media_uri"],
                "mime_type": "video/mp4" if media_type == "video" else "image/png",
                "width": 512 if media_type == "image" else 640,
                "height": 512 if media_type == "image" else 360,
                "duration_ms": 2000 if media_type == "video" else None,
                "frame_count": 16 if media_type == "video" else None,
                "metadata": {
                    "media_description": case["media_description"],
                    "media_status": case["media_status"],
                    "understanding_benchmark": True,
                },
            }
        ],
        "metadata": {
            "category": case["category"],
            "source_cluster": case["source_cluster"],
            "peer_suite_tags": list(case.get("peer_suite_tags") or []),
        },
    }


def _case_from_row(modality: str, index: int, row: tuple[Any, ...]) -> dict[str, Any]:
    category, answer_type, question, answer, choices, description = row
    split = "dev" if index < 8 else "golden" if index < (28 if modality == "image" else 22) else "held_out"
    prefix = "img-vqa" if modality == "image" else "vid-qa"
    media_uri = (
        f"artifacts://understanding/{modality}/{prefix}-{index + 1:02d}"
        f"{'.mp4' if modality == 'video' else '.png'}"
    )
    return {
        "id": f"{prefix}-{index + 1:02d}",
        "split": split,
        "source_cluster": f"{category}-{index + 1:02d}",
        "task_type": "image_vqa" if modality == "image" else "video_qa",
        "category": category,
        "question": question,
        "answer_type": answer_type,
        "answer": answer,
        "choices": list(choices or []),
        "media_uri": media_uri,
        "media_description": description,
        "media_status": "reference_only",
        "peer_suite_tags": (
            ["mmmu-lite", "ocr-vqa"] if modality == "image" else ["video-mme", "mvbench"]
        ),
        "safety_expected": "benign",
        "license": "CC0-1.0",
        "claim_boundary": (
            "Scene text is authoritative for offline scoring when media binaries "
            "are absent; replace media_uri with real files for live VLM runs."
        ),
    }


def _manifest(
    cases: Sequence[Mapping[str, Any]],
    *,
    schema_version: str,
    expected_count: int,
    task_type: str,
    peer_suites: Sequence[str],
) -> dict[str, Any]:
    ids = [str(case.get("id", "")) for case in cases]
    if len(cases) != expected_count or len(set(ids)) != expected_count or not all(ids):
        raise ValueError(f"{task_type} benchmark requires exactly {expected_count} unique cases")
    if any(str(case.get("task_type")) != task_type for case in cases):
        raise ValueError(f"all cases must use task_type={task_type}")
    cluster_splits: dict[str, set[str]] = {}
    for case in cases:
        cluster_splits.setdefault(str(case["source_cluster"]), set()).add(str(case["split"]))
    leaked = sorted(cluster for cluster, splits in cluster_splits.items() if len(splits) > 1)
    if leaked:
        raise ValueError(f"source clusters cross splits: {leaked}")
    required = ("question", "answer", "answer_type", "media_uri", "media_description")
    for case in cases:
        missing = [name for name in required if not case.get(name)]
        if missing:
            raise ValueError(f"case {case.get('id')} missing fields: {missing}")
        if case.get("answer_type") == "mcq" and not case.get("choices"):
            raise ValueError(f"mcq case {case.get('id')} requires choices")
    canonical = json.dumps(list(cases), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return {
        "schema_version": schema_version,
        "task_type": task_type,
        "case_count": expected_count,
        "split_counts": dict(sorted(Counter(str(case["split"]) for case in cases).items())),
        "category_counts": dict(sorted(Counter(str(case["category"]) for case in cases).items())),
        "answer_type_counts": dict(
            sorted(Counter(str(case["answer_type"]) for case in cases).items())
        ),
        "fingerprint_sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        "source": "project-authored understanding probes",
        "license": "CC0-1.0",
        "media_policy": "reference_uri_plus_description",
        "peer_suites": list(peer_suites),
        "claim_boundary": (
            "Fixed understanding probes for wiring VLM/video-LLM evaluators. "
            "Not a hosted mirror of MMMU or Video-MME raw media."
        ),
    }


def _normalize(text: str) -> str:
    lowered = text.strip().lower()
    lowered = _PUNCT_RE.sub(" ", lowered)
    return _WHITESPACE_RE.sub(" ", lowered).strip()


def _mcq_letter_match(prediction: str, gold: str, choices: Sequence[str]) -> bool:
    stripped = prediction.strip()
    if len(stripped) == 1 and stripped.upper() in "ABCD":
        index = ord(stripped.upper()) - ord("A")
        if 0 <= index < len(choices):
            return _normalize(choices[index]) == _normalize(gold)
    return False
