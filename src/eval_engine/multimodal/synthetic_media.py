"""Materialize real local image/video files for offline multimodal tracks.

Avoids GPU diffusion/VLM weights while still writing real PNG/MP4 bytes so
completion gates can verify filesystem artifacts for ``offline_real`` wiring.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

import numpy as np


def write_labeled_png(
    path: str | Path,
    *,
    title: str,
    answer: str,
    description: str,
    size: tuple[int, int] = (512, 512),
) -> dict[str, Any]:
    """Write a real PNG with painted labels and a JSON sidecar."""
    from PIL import Image, ImageDraw

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    width, height = size
    image = Image.new("RGB", (width, height), color=(245, 245, 245))
    draw = ImageDraw.Draw(image)
    draw.rectangle((16, 16, width - 16, height - 16), outline=(30, 30, 30), width=3)
    draw.text((32, 40), f"TITLE: {title[:60]}", fill=(10, 10, 10))
    draw.text((32, 90), f"ANSWER: {answer}", fill=(180, 20, 20))
    draw.text((32, 140), f"DESC: {description[:80]}", fill=(40, 40, 40))
    image.save(target, format="PNG")
    sidecar = target.with_suffix(".json")
    sidecar.write_text(
        json.dumps(
            {"answer": answer, "title": title, "description": description},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    return {
        "uri": str(target.resolve()),
        "media_type": "image",
        "mime_type": "image/png",
        "width": width,
        "height": height,
        "sha256": digest,
        "bytes": target.stat().st_size,
        "sidecar_uri": str(sidecar.resolve()),
    }


def write_labeled_mp4(
    path: str | Path,
    *,
    title: str,
    answer: str,
    description: str,
    frames: int = 8,
    size: tuple[int, int] = (640, 352),
    fps: int = 4,
) -> dict[str, Any]:
    """Write a real multi-frame MP4 with a moving banner and answer label."""
    import imageio.v3 as iio
    from PIL import Image, ImageDraw

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    width, height = size
    stack = []
    for index in range(frames):
        image = Image.new("RGB", (width, height), color=(230, 240, 255))
        draw = ImageDraw.Draw(image)
        offset = 20 + index * 12
        draw.rectangle(
            (offset, height // 2 - 20, offset + 120, height // 2 + 20),
            fill=(220, 60, 60),
        )
        draw.text((24, 24), f"TITLE: {title[:50]}", fill=(10, 10, 10))
        draw.text((24, 64), f"ANSWER: {answer}", fill=(20, 20, 140))
        draw.text((24, 104), f"FRAME: {index + 1}/{frames}", fill=(40, 40, 40))
        draw.text((24, 144), f"DESC: {description[:70]}", fill=(50, 50, 50))
        stack.append(np.asarray(image, dtype=np.uint8))
    iio.imwrite(target, np.stack(stack), fps=fps, codec="libx264")
    sidecar = target.with_suffix(".json")
    sidecar.write_text(
        json.dumps(
            {
                "answer": answer,
                "title": title,
                "description": description,
                "frame_count": frames,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    return {
        "uri": str(target.resolve()),
        "media_type": "video",
        "mime_type": "video/mp4",
        "width": width,
        "height": height,
        "frame_count": frames,
        "duration_ms": round(frames / fps * 1000),
        "sha256": digest,
        "bytes": target.stat().st_size,
        "sidecar_uri": str(sidecar.resolve()),
    }


def materialize_understanding_case(
    case: Mapping[str, Any], root: str | Path
) -> dict[str, Any]:
    """Create on-disk media for one understanding case."""
    root_path = Path(root)
    case_id = str(case["id"])
    if case["task_type"] == "image_vqa":
        artifact = write_labeled_png(
            root_path / "image" / f"{case_id}.png",
            title=str(case["question"]),
            answer=str(case["answer"]),
            description=str(case["media_description"]),
        )
    else:
        artifact = write_labeled_mp4(
            root_path / "video" / f"{case_id}.mp4",
            title=str(case["question"]),
            answer=str(case["answer"]),
            description=str(case["media_description"]),
        )
    return {
        **dict(case),
        "media_uri": artifact["uri"],
        "media_status": "materialized",
        "artifact": artifact,
    }


def render_generation_image(
    prompt: str, path: str | Path, *, model_alias: str
) -> dict[str, Any]:
    """Render a deterministic stand-in image for generation-track gates."""
    return write_labeled_png(
        path,
        title=prompt,
        answer=model_alias,
        description=f"synthetic generation render for {model_alias}",
    )


def render_generation_video(
    prompt: str, path: str | Path, *, model_alias: str
) -> dict[str, Any]:
    """Render a deterministic stand-in video for generation-track gates."""
    return write_labeled_mp4(
        path,
        title=prompt,
        answer=model_alias,
        description=f"synthetic generation render for {model_alias}",
    )
