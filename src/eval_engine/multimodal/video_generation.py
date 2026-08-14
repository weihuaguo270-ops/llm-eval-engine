"""Lazy-loaded local text-to-video generation adapters."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Mapping

from .video_benchmark import video_artifact_record

VIDEO_MODELS = (
    {"id": "Wan-AI/Wan2.1-T2V-1.3B-Diffusers", "revision": "main", "alias": "wan-1.3b",
     "pipeline": "wan", "steps": 8, "guidance_scale": 5.0, "license": "apache-2.0"},
    {"id": "damo-vilab/text-to-video-ms-1.7b", "revision": "main", "alias": "modelscope-1.7b",
     "pipeline": "modelscope", "steps": 20, "guidance_scale": 9.0, "license": "cc-by-nc-4.0"},
)


class LocalVideoGenerator:
    """Generate a short MP4 with CPU offload and frozen safetensors weights."""

    def __init__(self, model: Mapping[str, Any]):
        import torch
        from huggingface_hub import model_info

        self.torch = torch
        self.model = dict(model)
        revision = model_info(self.model["id"], revision=self.model["revision"]).sha
        if not revision:
            raise RuntimeError(f"unable to resolve model revision: {self.model['id']}")
        self.model["revision"] = revision
        if self.model["pipeline"] == "wan":
            from diffusers import AutoencoderKLWan, WanPipeline

            vae = AutoencoderKLWan.from_pretrained(
                self.model["id"], subfolder="vae", revision=revision,
                torch_dtype=torch.float32, use_safetensors=True,
            )
            self.pipeline = WanPipeline.from_pretrained(
                self.model["id"], revision=revision, vae=vae,
                torch_dtype=torch.bfloat16, use_safetensors=True,
            )
        else:
            from diffusers import TextToVideoSDPipeline

            self.pipeline = TextToVideoSDPipeline.from_pretrained(
                self.model["id"], revision=revision,
                torch_dtype=torch.float16, use_safetensors=True,
            )
        self.pipeline.enable_model_cpu_offload()
        if hasattr(self.pipeline, "enable_vae_slicing"):
            self.pipeline.enable_vae_slicing()

    def generate(self, case: Mapping[str, Any], path: str | Path, seed: int,
                 *, frames: int = 9, width: int = 256, height: int = 256, fps: int = 8) -> dict[str, Any]:
        import imageio.v3 as iio
        import numpy as np

        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
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
        config = {"width": width, "height": height, "frames": frames, "fps": fps,
                  "steps": self.model["steps"], "guidance_scale": self.model["guidance_scale"],
                  "cpu_offload": True, "torch": self.torch.__version__,
                  "device": self.torch.cuda.get_device_name(0)}
        return video_artifact_record(target, case=case, model=self.model, seed=seed,
                                     latency_ms=latency_ms, config=config)

    def close(self) -> None:
        del self.pipeline
        self.torch.cuda.empty_cache()


class VideoClipSafetyScorer:
    """Score sampled video frames with frozen CLIP and NSFW classifiers."""

    clip_id = "openai/clip-vit-base-patch32"
    safety_id = "Falconsai/nsfw_image_detection"

    def __init__(self):
        import torch
        from transformers import CLIPModel, CLIPProcessor, pipeline

        self.torch = torch
        self.clip = CLIPModel.from_pretrained(self.clip_id).to("cuda")
        self.processor = CLIPProcessor.from_pretrained(self.clip_id)
        self.safety = pipeline("image-classification", model=self.safety_id, device=0)

    def score(self, record: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
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
