"""Pluggable predictors for understanding-side image/video QA.

Default local adapters read materialized sidecars for offline wiring. Optional
OpenAI-compatible vision and Hugging Face VLM adapters enable real-model
prediction when credentials / GPU weights are available.
"""

from __future__ import annotations

import base64
import hashlib
import json
import mimetypes
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Protocol


class UnderstandingPredictor(Protocol):
    """Predict an answer for one materialized understanding case."""

    model_id: str
    adapter_name: str

    def predict(self, case: Mapping[str, Any]) -> dict[str, Any]:
        """Return prediction payload with latency and model metadata."""
        ...


@dataclass
class SidecarUnderstandingPredictor:
    """Deterministic local reader over materialized JSON sidecars."""

    model_id: str = "local/sidecar-reader"
    adapter_name: str = "sidecar"
    noisy: bool = False

    def predict(self, case: Mapping[str, Any]) -> dict[str, Any]:
        started = time.perf_counter()
        artifact = case.get("artifact") or {}
        sidecar = Path(str(artifact.get("sidecar_uri") or ""))
        if not sidecar.is_file():
            raise FileNotFoundError(f"missing sidecar for case {case.get('id')}: {sidecar}")
        gold = str(json.loads(sidecar.read_text(encoding="utf-8"))["answer"])
        if self.noisy:
            digest = hashlib.sha256(str(case.get("id", "")).encode("utf-8")).hexdigest()
            prediction = gold if int(digest[-1], 16) % 5 else f"noise-{gold}"
        else:
            prediction = gold
        return {
            "prediction": prediction,
            "latency_ms": round((time.perf_counter() - started) * 1000, 3),
            "model": self.model_id,
            "adapter": self.adapter_name,
            "model_revision": "sidecar-v1",
            "claim_boundary": (
                "Sidecar reader validates media+scoring wiring. Replace with a "
                "calibrated VLM/Video-LLM for capability claims."
            ),
        }


@dataclass
class OpenAIVisionUnderstandingPredictor:
    """Call an OpenAI-compatible chat-completions vision endpoint."""

    model_id: str = "openai/gpt-4o-mini"
    adapter_name: str = "openai_vision"
    api_base: str = "https://api.openai.com/v1"
    api_key_env: str = "OPENAI_API_KEY"
    timeout_s: float = 60.0
    claim_boundary: str = (
        "OpenAI-compatible vision predictions are offline model evidence "
        "for understanding QA, not a hosted MMMU leaderboard submission."
    )

    def predict(self, case: Mapping[str, Any]) -> dict[str, Any]:
        api_key = os.environ.get(self.api_key_env, "").strip()
        if not api_key:
            raise RuntimeError(
                f"{self.api_key_env} is required for adapter={self.adapter_name}"
            )
        artifact = case.get("artifact") or {}
        media_uri = Path(str(artifact.get("uri") or case.get("media_uri") or ""))
        if not media_uri.is_file():
            raise FileNotFoundError(f"missing media for case {case.get('id')}: {media_uri}")
        if str(case.get("task_type")) == "video_qa":
            # OpenAI vision chat typically takes images; use middle-frame proxy via sidecar desc.
            # Prefer an explicit frame export if present.
            frame_uri = Path(str(artifact.get("preview_frame_uri") or ""))
            if frame_uri.is_file():
                media_uri = frame_uri
            else:
                raise RuntimeError(
                    "openai_vision video cases require artifact.preview_frame_uri; "
                    "materialize with preview frames or use a Video-LLM adapter"
                )
        mime = mimetypes.guess_type(media_uri.name)[0] or "image/png"
        encoded = base64.b64encode(media_uri.read_bytes()).decode("ascii")
        question = str(case.get("question") or "")
        choices = list(case.get("choices") or [])
        guidance = (
            "Answer with the final short answer only. "
            + (f"Choices: {choices}. " if choices else "")
            + "Do not explain."
        )
        body = {
            "model": self.model_id.split("/", 1)[-1],
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": f"{question}\n{guidance}"},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{mime};base64,{encoded}"},
                        },
                    ],
                }
            ],
            "temperature": 0,
            "max_tokens": 256,
        }
        # DeepSeek-V4.1-Flash may spend completion budget on reasoning_content.
        if self.adapter_name == "deepseek_vision":
            body["thinking"] = {"type": "disabled"}
        request = urllib.request.Request(
            url=f"{self.api_base.rstrip('/')}/chat/completions",
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        started = time.perf_counter()
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_s) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"{self.adapter_name} HTTP {exc.code}: {detail}") from exc
        latency_ms = round((time.perf_counter() - started) * 1000, 3)
        message = payload.get("choices", [{}])[0].get("message", {}) or {}
        prediction = message.get("content") or ""
        if not str(prediction).strip():
            # Some DeepSeek responses put the answer only in reasoning_content
            # when thinking consumes the token budget.
            reasoning = str(message.get("reasoning_content") or "").strip()
            if reasoning:
                prediction = reasoning.splitlines()[-1].strip()
        return {
            "prediction": str(prediction).strip(),
            "latency_ms": latency_ms,
            "model": self.model_id,
            "adapter": self.adapter_name,
            "model_revision": str(payload.get("model") or self.model_id),
            "raw_response_id": payload.get("id"),
            "claim_boundary": self.claim_boundary,
        }


@dataclass
class HuggingFaceVLMUnderstandingPredictor:
    """Lazy Hugging Face vision-language predictor (requires torch + transformers)."""

    model_id: str = "llava-hf/llava-1.5-7b-hf"
    adapter_name: str = "hf_vlm"
    max_new_tokens: int = 32

    def predict(self, case: Mapping[str, Any]) -> dict[str, Any]:
        try:
            import torch
            from PIL import Image
            from transformers import AutoProcessor, AutoModelForVision2Seq
        except ImportError as exc:  # pragma: no cover - optional heavy stack
            raise RuntimeError(
                "hf_vlm adapter requires torch, transformers, and Pillow. "
                "Install with: pip install '.[multimodal]'"
            ) from exc
        if not torch.cuda.is_available():
            raise RuntimeError("hf_vlm adapter requires CUDA in this environment")
        artifact = case.get("artifact") or {}
        media_uri = Path(str(artifact.get("uri") or case.get("media_uri") or ""))
        if not media_uri.is_file():
            raise FileNotFoundError(f"missing media for case {case.get('id')}: {media_uri}")
        if str(case.get("task_type")) == "video_qa":
            frame_uri = Path(str(artifact.get("preview_frame_uri") or ""))
            if not frame_uri.is_file():
                raise RuntimeError(
                    "hf_vlm video cases require artifact.preview_frame_uri"
                )
            media_uri = frame_uri
        started = time.perf_counter()
        processor = AutoProcessor.from_pretrained(self.model_id)
        model = AutoModelForVision2Seq.from_pretrained(
            self.model_id,
            torch_dtype=torch.float16,
            device_map="auto",
        )
        image = Image.open(media_uri).convert("RGB")
        question = str(case.get("question") or "")
        choices = list(case.get("choices") or [])
        prompt = (
            f"USER: <image>\n{question}\n"
            + (f"Choices: {choices}\n" if choices else "")
            + "Answer briefly.\nASSISTANT:"
        )
        inputs = processor(text=prompt, images=image, return_tensors="pt").to(model.device)
        with torch.inference_mode():
            output_ids = model.generate(**inputs, max_new_tokens=self.max_new_tokens)
        text = processor.batch_decode(output_ids, skip_special_tokens=True)[0]
        prediction = text.split("ASSISTANT:")[-1].strip()
        return {
            "prediction": prediction,
            "latency_ms": round((time.perf_counter() - started) * 1000, 3),
            "model": self.model_id,
            "adapter": self.adapter_name,
            "model_revision": getattr(getattr(model, "config", None), "_name_or_path", self.model_id),
            "claim_boundary": (
                "Local HF VLM predictions are offline understanding evidence. "
                "Not a hosted public-leaderboard submission."
            ),
        }


def _resolve_remote_model_id(adapter: str, model_id: str | None, default: str) -> str:
    """Keep registry aliases for local adapters; map local/* away from remote APIs."""
    if model_id and not str(model_id).startswith("local/"):
        return str(model_id)
    return default


def build_understanding_predictor(
    *,
    adapter: str,
    model_id: str | None = None,
    **kwargs: Any,
) -> UnderstandingPredictor:
    """Factory for understanding predictors used by the real benchmark CLI."""
    name = str(adapter).strip().lower()
    if name in {"sidecar", "sidecar_reader"}:
        return SidecarUnderstandingPredictor(
            model_id=model_id or "local/sidecar-reader",
            adapter_name="sidecar",
            noisy=False,
        )
    if name in {"noisy_sidecar", "noisy-sidecar", "noisy_sidecar_reader"}:
        return SidecarUnderstandingPredictor(
            model_id=model_id or "local/noisy-sidecar-reader",
            adapter_name="noisy_sidecar",
            noisy=True,
        )
    if name in {"openai_vision", "openai-vision", "openai"}:
        return OpenAIVisionUnderstandingPredictor(
            model_id=_resolve_remote_model_id(
                name, model_id, "openai/gpt-4o-mini"
            ),
            **kwargs,
        )
    if name in {
        "deepseek_vision",
        "deepseek-vision",
        "deepseek_flash",
        "deepseek-flash",
        "deepseek-v4-flash",
        "deepseek-v4.1-flash",
        "deepseek_v4_flash",
        "deepseek_v4_1_flash",
        "deepseek",
    }:
        return OpenAIVisionUnderstandingPredictor(
            model_id=_resolve_remote_model_id(name, model_id, "deepseek/deepseek-flash"),
            adapter_name="deepseek_vision",
            api_base=os.environ.get("DEEPSEEK_API_BASE", "https://api.deepseek.com").rstrip("/"),
            api_key_env="DEEPSEEK_API_KEY",
            claim_boundary=(
                "DeepSeek-V4.1-Flash (deepseek-flash) vision predictions are offline "
                "understanding evidence from a real multimodal model, not a hosted "
                "MMMU/Video-MME leaderboard submission."
            ),
            **kwargs,
        )
    if name in {"hf_vlm", "hf-vlm", "huggingface"}:
        return HuggingFaceVLMUnderstandingPredictor(
            model_id=_resolve_remote_model_id(
                name, model_id, "llava-hf/llava-1.5-7b-hf"
            ),
            **kwargs,
        )
    raise ValueError(f"unsupported understanding adapter: {adapter!r}")


DEFAULT_UNDERSTANDING_BENCHMARK_MODELS = (
    {
        "id": "local/sidecar-reader",
        "alias": "sidecar-reader",
        "adapter": "sidecar",
        "license": "CC0-1.0",
    },
    {
        "id": "local/noisy-sidecar-reader",
        "alias": "noisy-sidecar-reader",
        "adapter": "noisy_sidecar",
        "license": "CC0-1.0",
    },
)
