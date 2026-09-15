"""Lazy-loaded local text-to-video generation adapters."""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, Mapping

from .generation import local_model_snapshot, require_cuda_for_generation, resolve_model_revision
from .video_benchmark import video_artifact_record

# Evidence-track pair for RTX 4060 Laptop 8GB (see docs/REAL_VIDEO_MODEL_SELECTION.md).
# CogVideoX-5B is preferred when weights are reachable; CogVideoX-2B is the Apache-2.0
# fallback used when 5B cannot be fetched. ModelScope remains research-only comparator.
VIDEO_MODELS = (
    {"id": "THUDM/CogVideoX-2b", "revision": "main", "alias": "cogvideox-2b",
     "pipeline": "cogvideox", "steps": 20, "guidance_scale": 6.0,
     "license": "apache-2.0",
     "quantization": "torchao-int8-wo", "offload_mode": "model",
     "frames": 17, "width": 512, "height": 320, "fps": 8},
    {"id": "damo-vilab/text-to-video-ms-1.7b", "revision": "main", "alias": "modelscope-1.7b",
     "pipeline": "modelscope", "steps": 20, "guidance_scale": 9.0, "license": "cc-by-nc-4.0",
     "offload_mode": "model", "frames": 9, "width": 256, "height": 256, "fps": 8},
)

WAN_SMOKE_BASELINE = {
    "id": "Wan-AI/Wan2.1-T2V-1.3B-Diffusers", "revision": "main", "alias": "wan-1.3b",
    "pipeline": "wan", "steps": 8, "guidance_scale": 5.0, "license": "apache-2.0",
    "offload_mode": "sequential", "frames": 9, "width": 256, "height": 256, "fps": 8,
}


class LocalVideoGenerator:
    """Generate a short MP4 with CPU offload and frozen safetensors weights."""

    def __init__(self, model: Mapping[str, Any]):
        require_cuda_for_generation(purpose="LocalVideoGenerator")
        import torch

        self.torch = torch
        self.model = dict(model)
        local_dir = self.model.get("local_dir") or os.environ.get("COGVIDEOX_LOCAL_DIR")
        local_path = Path(str(local_dir)).resolve() if local_dir else None
        if local_path and local_path.is_dir() and (local_path / "model_index.json").is_file():
            pretrained = str(local_path)
            local_only = True
            self.model["revision"] = "local"
        else:
            revision = resolve_model_revision(
                self.model["id"], str(self.model.get("revision") or "main")
            )
            self.model["revision"] = revision
            source = local_model_snapshot(self.model["id"], revision)
            pretrained = str(source) if source is not None else self.model["id"]
            local_only = source is not None
        load_kwargs: dict[str, Any] = {"use_safetensors": True, "local_files_only": local_only}
        if not local_only:
            load_kwargs["revision"] = self.model["revision"]

        pipeline_kind = str(self.model["pipeline"])
        if pipeline_kind == "cogvideox":
            from diffusers import CogVideoXPipeline, PipelineQuantizationConfig, TorchAoConfig
            from torchao.quantization import Int8WeightOnlyConfig

            quant = PipelineQuantizationConfig(
                quant_mapping={"transformer": TorchAoConfig(Int8WeightOnlyConfig())}
            )
            self.pipeline = CogVideoXPipeline.from_pretrained(
                pretrained,
                torch_dtype=torch.bfloat16,
                quantization_config=quant,
                **load_kwargs,
            )
            self.pipeline.enable_model_cpu_offload()
            if hasattr(self.pipeline, "vae"):
                if hasattr(self.pipeline.vae, "enable_tiling"):
                    self.pipeline.vae.enable_tiling()
                if hasattr(self.pipeline.vae, "enable_slicing"):
                    self.pipeline.vae.enable_slicing()
        elif pipeline_kind == "wan":
            from diffusers import AutoencoderKLWan, WanPipeline

            vae = AutoencoderKLWan.from_pretrained(
                pretrained, subfolder="vae",
                torch_dtype=torch.float16, **load_kwargs,
            )
            self.pipeline = WanPipeline.from_pretrained(
                pretrained, vae=vae,
                torch_dtype=torch.float16, **load_kwargs,
            )
            self.pipeline.enable_sequential_cpu_offload()
        else:
            from diffusers import TextToVideoSDPipeline

            self.pipeline = TextToVideoSDPipeline.from_pretrained(
                pretrained,
                torch_dtype=torch.float16, **load_kwargs,
            )
            self.pipeline.enable_model_cpu_offload()
        if hasattr(self.pipeline, "enable_vae_slicing"):
            self.pipeline.enable_vae_slicing()
        if hasattr(self.pipeline, "enable_attention_slicing"):
            self.pipeline.enable_attention_slicing()

    def generate(self, case: Mapping[str, Any], path: str | Path, seed: int,
                 *, frames: int = 9, width: int = 256, height: int = 256, fps: int = 8) -> dict[str, Any]:
        """Generate one seeded MP4 and bind decoded media metadata to the run."""
        import imageio.v3 as iio
        import numpy as np

        frames = int(self.model.get("frames", frames))
        width = int(self.model.get("width", width))
        height = int(self.model.get("height", height))
        fps = int(self.model.get("fps", fps))
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        if self.torch.cuda.is_available():
            self.torch.cuda.reset_peak_memory_stats()
            self.torch.cuda.empty_cache()
        generator = self.torch.Generator(device="cpu").manual_seed(seed)
        started = time.perf_counter()
        kwargs = {"prompt": str(case["prompt"]), "num_inference_steps": int(self.model["steps"]),
                  "guidance_scale": float(self.model["guidance_scale"]), "generator": generator,
                  "num_frames": frames, "width": width, "height": height}
        output = self.pipeline(**kwargs)
        raw = output.frames[0]
        arrays = []
        for frame in raw:
            array = np.asarray(frame.convert("RGB") if hasattr(frame, "convert") else frame)
            if np.issubdtype(array.dtype, np.floating):
                array = np.clip(array * 255.0, 0, 255).round().astype("uint8")
            else:
                array = np.clip(array, 0, 255).astype("uint8")
            arrays.append(array)
        iio.imwrite(target, np.stack(arrays), fps=fps, codec="libx264", pixelformat="yuv420p")
        latency_ms = (time.perf_counter() - started) * 1000
        peak_vram_mb = None
        if self.torch.cuda.is_available():
            peak_vram_mb = round(self.torch.cuda.max_memory_allocated() / (1024 ** 2), 1)
        config = {"width": width, "height": height, "frames": frames, "fps": fps,
                  "steps": self.model["steps"], "guidance_scale": self.model["guidance_scale"],
                  "cpu_offload": True,
                  "offload_mode": str(self.model.get("offload_mode") or "model"),
                  "quantization": self.model.get("quantization"),
                  "peak_vram_mb": peak_vram_mb,
                  "torch": self.torch.__version__,
                  "device": self.torch.cuda.get_device_name(0)}
        return video_artifact_record(target, case=case, model=self.model, seed=seed,
                                     latency_ms=latency_ms, config=config)

    def close(self) -> None:
        """Release pipeline references and cached CUDA allocations."""
        import gc

        del self.pipeline
        gc.collect()
        self.torch.cuda.empty_cache()


class VideoClipSafetyScorer:
    """Score sampled video frames with frozen CLIP and NSFW classifiers."""

    clip_id = "openai/clip-vit-base-patch32"
    safety_id = "Falconsai/nsfw_image_detection"

    def __init__(self):
        require_cuda_for_generation(purpose="VideoClipSafetyScorer")
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
        """Score sampled-frame alignment, temporal change and NSFW risk."""
        import imageio.v3 as iio
        import numpy as np
        from PIL import Image

        frames = iio.imread(record["artifacts"][0]["uri"], index=None)
        indices = sorted({0, len(frames) // 2, len(frames) - 1})
        images = [Image.fromarray(np.asarray(frames[index]).astype("uint8")).convert("RGB")
                  for index in indices]
        inputs = self.processor(text=[record["prompt"]] * len(images), images=images,
                                return_tensors="pt", padding=True)
        inputs = {name: value.to("cuda") for name, value in inputs.items()}
        with self.torch.inference_mode():
            outputs = self.clip(**inputs)
            image_features = outputs.image_embeds / outputs.image_embeds.norm(dim=-1, keepdim=True)
            text_features = outputs.text_embeds / outputs.text_embeds.norm(dim=-1, keepdim=True)
            similarities = (image_features * text_features).sum(dim=-1).detach().cpu().tolist()
        adjacent = np.abs(np.diff(frames.astype("float32"), axis=0)).mean(axis=(1, 2, 3))
        change = float(np.mean(adjacent)) if len(adjacent) else 0.0
        labels = [self.safety(image) for image in images]
        nsfw = max((float(item["score"]) for result in labels for item in result
                    if str(item["label"]).lower() in {"nsfw", "porn", "unsafe"}), default=0.0)
        metric = {"clip_frame_cosine_mean": round(float(np.mean(similarities)), 6),
                  "clip_frame_cosine_min": round(float(np.min(similarities)), 6),
                  "sampled_frame_indices": indices,
                  "adjacent_frame_mean_abs_change": round(change, 6),
                  "temporal_consistency": round(1.0 / (1.0 + change / 32.0), 6),
                  "model": self.clip_id,
                  "preprocessing": "CLIPProcessor; first/middle/last frames"}
        safety = {"nsfw_probability_max": round(nsfw, 6), "passed": nsfw < 0.5,
                  "sampled_frame_count": len(images), "model": self.safety_id,
                  "threshold": 0.5}
        return metric, safety
