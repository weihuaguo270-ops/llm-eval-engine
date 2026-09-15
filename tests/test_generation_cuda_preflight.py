"""CUDA preflight must fail closed without torch/GPU."""

import pytest

from eval_engine.multimodal.generation import require_cuda_for_generation


def test_require_cuda_for_generation_fails_without_gpu():
    with pytest.raises(RuntimeError) as exc:
        require_cuda_for_generation(purpose="unit-test")
    message = str(exc.value)
    assert "NO_GPU" in message or "no torch" in message or "CUDA" in message
