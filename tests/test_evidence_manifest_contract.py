import pytest
from eval_engine.evidence_manifest import validate_manifest

def sample(modality="text"):
    return {"sample_id":f"{modality}-x","modality":modality,"input_uri":"fixture://x","input_sha256":"0"*64,"prediction":"a","reference":"a","source":"fixture"}

def test_all_modalities_validate():
    data={"schema_version":"multimodal-evidence-manifest/v1","samples":[sample(m) for m in ("text","image","audio","video","document")]}
    assert validate_manifest(data)["sample_count"] == 5

def test_unknown_modality_rejected():
    with pytest.raises(ValueError, match="unsupported"):
        validate_manifest({"schema_version":"multimodal-evidence-manifest/v1","samples":[sample("sensor")]})

def test_bad_fingerprint_rejected():
    item=sample(); item["input_sha256"]="abc"
    with pytest.raises(ValueError, match="sha256"):
        validate_manifest({"schema_version":"multimodal-evidence-manifest/v1","samples":[item]})
