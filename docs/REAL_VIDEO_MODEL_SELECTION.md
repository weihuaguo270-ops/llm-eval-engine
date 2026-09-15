# Real video model selection memo

Date: 2026-09-14  
Scope: replace the implicit “8GB ⇒ Wan2.1-T2V-1.3B only” rule with an explicit deployment-aware shortlist.

## Decision rule

Native free VRAM is **one** constraint, not a veto against larger open models. Selection must consider:

- published **quantization** recipes (e.g. torchao INT8, FP8 where hardware allows)
- **CPU / sequential offload**, VAE tiling/slicing, attention slicing
- optional **multi-GPU** or distillation — only on a separate SOTA track unless an official student checkpoint is pinned
- Diffusers (or equally pinable) stack, **commit SHA**, seed, and license for `offline_real` claims

A quantized or heavily offloaded run is a **deployment-state** claim. It must not be silently equated with full bf16 base quality.

## Deployment whitelist (evidence track)

| Allowed | Notes |
|---------|--------|
| fp16 / bf16 | Default when it fits |
| torchao INT8 (Diffusers PipelineQuantizationConfig) | Preferred for 8–12GB |
| `enable_model_cpu_offload` / `enable_sequential_cpu_offload` | Record which |
| VAE tiling / slicing, attention slicing | Record flags |
| Official distilled / high-compression CKPT | e.g. Wan2.2-TI2V-5B as its own model id |

| Deferred to SOTA track | Notes |
|------------------------|--------|
| Multi-GPU tensor / pipeline parallel | Separate protocol |
| Unofficial GGUF / extreme community quants without Diffusers pin | Weak reproducibility |
| Hybrid local+API (e.g. H3 Regenerate-2K) | Not pure offline |

## Candidate scan (2026-09-14)

| Model | Quality band | VRAM after techniques | Stack | License | Verdict |
|-------|--------------|----------------------|-------|---------|---------|
| Wan2.1-T2V-1.3B (current) | Entry | ~8GB fp16+offload | Diffusers WanPipeline | Apache-2.0 | Keep only as entry fixture |
| **CogVideoX-5B** | Strong mid | Vendor: INT8+offload ~4.4–8GB | Diffusers + torchao | Check Zhipu/Tsinghua terms for 5B | **Next primary** |
| CogVideoX-2B | Mid | INT8+offload ~3.6–6GB | Diffusers + torchao | Apache-2.0 | Clean Apache comparator / fallback |
| Wan2.2-TI2V-5B | Stronger Wan | Official ≥24GB; FP8 community | Diffusers main | Apache-2.0 | Gate on 24GB host |
| MiniMax H3-Base | Frontier open | Practical ~24–32GB INT8 | ModularPipeline / Comfy / SGLang | Community | SOTA track; Base ≠ full Hailuo |
| LTX-2.x | Frontier (+audio) | Often ≥24–32GB | Diffusers / Comfy | Dual | SOTA track |
| HunyuanVideo | Cinematic | Quant often ~16GB+ | Diffusers / community | Tencent community | License + VRAM cost |
| ModelScope T2V 1.7B (current) | Legacy | Fits 8GB | Diffusers TextToVideoSD | CC-BY-NC-4.0 | Research-only comparator |

Sources: Hugging Face Diffusers Wan / CogVideoX / MiniMax-H3 docs; CogVideoX and Wan2.2 model cards; public H3 local requirement writeups.

## Recommendation

### Phase 1 — evidence track (RTX 4060 Laptop 8GB)

1. **Primary:** `THUDM/CogVideoX-5b` (or current HF id under zai-org) with documented INT8 + CPU offload + VAE tiling/slicing.  
2. **Comparator:** keep `damo-vilab/text-to-video-ms-1.7b` (NC research), **or** switch to CogVideoX-2B if both slots must be commercially friendlier.  
3. Demote Wan2.1-1.3B from “default advanced open model” to optional smoke baseline.

Engineering order: adapter → 1-case smoke + peak VRAM log → full 30×2 only after smoke passes.

### Phase 2 — SOTA track (≥24GB or multi-GPU)

Separate claim boundary for Wan2.2-5B / H3-Base / LTX. Do not overload `run_real_video_benchmark.py` evidence semantics. H3-Base local runs must not claim Context-IR + Regenerate-2K parity.

## Claim boundary

This memo does **not** claim CogVideoX-5B is the global open-source quality leader. It claims it is the best **next primary** under: open weights + Diffusers-reproducible recipe + single 8GB GPU + auditable offline evidence, once deployment techniques are allowed.

## Execution note (2026-09-15)

Phase 1 on RTX 4060 Laptop 8GB completed with the **CogVideoX-2B** Apache fallback (HF mirror / `local_dir`; torchao INT8 weight-only + model CPU offload). Full 30×2 against ModelScope reached `offline_real` in `test-temp/real-video-local-full`. CogVideoX-5B remains preferred when weights are fetchable; Wan2.1-1.3B stayed optional after UMT5 load failures on this host.
