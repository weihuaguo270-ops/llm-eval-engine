"""Lazy-loaded local image generation and scoring adapters."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Mapping

from .image_benchmark import artifact_record

DEFAULT_MODELS = (
    {"id": "stable-diffusion-v1-5/stable-diffusion-v1-5", "revision": "main",
     "alias": "sd-v1-5", "steps": 20, "guidance_scale": 7.5,
     "license": "creativeml-openrail-m"},
    {"id": "stabilityai/sd-turbo", "revision": "main", "alias": "sd-turbo",
     "steps": 4, "guidance_scale": 0.0, "license": "stabilityai-ai-community"},
)


def require_cuda_for_generation(*, purpose: str = "Diffusers generation") -> str:
    """Fail closed on CPU / NO_GPU hosts before loading heavy weights.

    Formal image/video generation (`run_real_image_benchmark.py` /
    `run_real_video_benchmark.py`) requires CUDA + torch + diffusers. Cloud
    agents without a GPU must not pretend synthetic media is Diffusers output.
    """
    try:
        import torch
    except ImportError as exc:  # pragma: no cover - depends on optional stack
        raise RuntimeError(
            f"{purpose} requires torch+CUDA. This host has no torch installed "
            "(NO_GPU / CPU-only). Run on a CUDA machine with: "
            "pip install '.[multimodal]' && nvidia-smi"
        ) from exc
    if not torch.cuda.is_available():
        raise RuntimeError(
            f"{purpose} requires CUDA. torch={torch.__version__} reports "
            "cuda.is_available()=False (NO_GPU). Move generate/score to a GPU host; "
            "understanding-side DeepSeek vision does not need GPU."
        )
    return torch.cuda.get_device_name(0)


def resolve_model_revision(model_id: str, revision: str = "main") -> str:
    """Resolve a commit SHA online, falling back to a local HF hub cache."""
    try:
        from huggingface_hub import model_info

        resolved = model_info(model_id, revision=revision).sha
        if resolved:
            return str(resolved)
    except Exception:
        resolved = None

    import os

    cache_root = Path(
        os.environ.get("HF_HUB_CACHE")
        or (Path(os.environ["HF_HOME"]) / "hub" if os.environ.get("HF_HOME") else Path.home() / ".cache" / "huggingface" / "hub")
    )
    repo_dir = cache_root / ("models--" + model_id.replace("/", "--"))
    ref_file = repo_dir / "refs" / revision
    if ref_file.is_file():
        return ref_file.read_text(encoding="utf-8").strip()
    snapshots = sorted((repo_dir / "snapshots").glob("*")) if (repo_dir / "snapshots").is_dir() else []
    if snapshots:
        return snapshots[-1].name
    raise RuntimeError(
        f"unable to resolve model revision for {model_id}@{revision} "
        "(Hugging Face unreachable and no local hub cache entry)"
    )


def local_model_snapshot(model_id: str, revision: str) -> Path | None:
    """Return a local HF snapshot directory when present."""
    import os

    cache_root = Path(
        os.environ.get("HF_HUB_CACHE")
        or (Path(os.environ["HF_HOME"]) / "hub" if os.environ.get("HF_HOME") else Path.home() / ".cache" / "huggingface" / "hub")
    )
    snapshot = cache_root / ("models--" + model_id.replace("/", "--")) / "snapshots" / revision
    return snapshot if snapshot.is_dir() else None


class LocalDiffusersGenerator:
    """Load one frozen model at a time and emit verifiable artifact records."""

    def __init__(self, model: Mapping[str, Any]):
        require_cuda_for_generation(purpose="LocalDiffusersGenerator")
        import torch
        from diffusers import AutoPipelineForText2Image

        self.torch = torch
        self.model = dict(model)
        resolved_revision = resolve_model_revision(
            self.model["id"], str(self.model.get("revision") or "main")
        )
        self.model["revision"] = resolved_revision
        source = local_model_snapshot(self.model["id"], resolved_revision) or self.model["id"]
        load_kwargs: dict[str, Any] = {
            "torch_dtype": torch.float16,
            "safety_checker": None,
            "requires_safety_checker": False,
            "use_safetensors": True,
        }
        if isinstance(source, Path):
            load_kwargs["local_files_only"] = True
            pretrained = str(source)
        else:
            load_kwargs["revision"] = resolved_revision
            pretrained = source
        self.pipeline = AutoPipelineForText2Image.from_pretrained(
            pretrained, **load_kwargs
        ).to("cuda")
        self.pipeline.set_progress_bar_config(disable=True)

    def generate(self, case: Mapping[str, Any], path: str | Path, seed: int) -> dict[str, Any]:
        """Generate one seeded image and return artifact-bound run evidence."""
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        generator = self.torch.Generator(device="cuda").manual_seed(seed)
        started = time.perf_counter()
        image = self.pipeline(
            str(case["prompt"]), num_inference_steps=int(self.model["steps"]),
            guidance_scale=float(self.model["guidance_scale"]), generator=generator,
            width=512, height=512,
        ).images[0]
        latency_ms = (time.perf_counter() - started) * 1000
        image.save(target)
        config = {"width": 512, "height": 512, "steps": self.model["steps"],
                  "guidance_scale": self.model["guidance_scale"], "dtype": "float16",
                  "device": self.torch.cuda.get_device_name(0), "torch": self.torch.__version__}
        return artifact_record(target, case=case, model=self.model, seed=seed,
                               latency_ms=latency_ms, generation_config=config)

    def close(self) -> None:
        """Release pipeline references and cached CUDA allocations."""
        del self.pipeline
        self.torch.cuda.empty_cache()


class ClipSafetyScorer:
    """Score prompt adherence and benign-image safety with frozen public models."""

    clip_id = "openai/clip-vit-base-patch32"
    safety_id = "Falconsai/nsfw_image_detection"

    def __init__(self):
        require_cuda_for_generation(purpose="ClipSafetyScorer")
        import torch
        from transformers import CLIPModel, CLIPProcessor, pipeline

        self.torch = torch
        self.clip = CLIPModel.from_pretrained(self.clip_id, local_files_only=True).to("cuda")
        self.processor = CLIPProcessor.from_pretrained(self.clip_id, local_files_only=True)
        self.safety = pipeline(
            "image-classification",
            model=self.safety_id,
            device=0,
        )

    def score(self, record: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        """Return CLIP prompt alignment and NSFW screening evidence."""
        from PIL import Image

        image = Image.open(record["artifacts"][0]["uri"]).convert("RGB")
        inputs = self.processor(text=[record["prompt"]], images=[image],
                                return_tensors="pt", padding=True)
        inputs = {name: value.to("cuda") for name, value in inputs.items()}
        with self.torch.inference_mode():
            outputs = self.clip(**inputs)
            image_features = outputs.image_embeds / outputs.image_embeds.norm(dim=-1, keepdim=True)
            text_features = outputs.text_embeds / outputs.text_embeds.norm(dim=-1, keepdim=True)
            similarity = float((image_features * text_features).sum().item())
        labels = self.safety(image)
        nsfw = max((float(item["score"]) for item in labels
                    if str(item["label"]).lower() in {"nsfw", "porn", "unsafe"}), default=0.0)
        metric = {"clip_cosine": round(similarity, 6), "model": self.clip_id,
                  "model_revision": getattr(self.clip.config, "_commit_hash", None),
                  "preprocessing": "CLIPProcessor default"}
        safety = {"nsfw_probability": round(nsfw, 6), "passed": nsfw < 0.5,
                  "model": self.safety_id, "threshold": 0.5}
        return metric, safety
