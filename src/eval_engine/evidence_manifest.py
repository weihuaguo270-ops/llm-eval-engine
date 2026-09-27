"""Artifact evidence manifest — modality metadata adapter only.

Validates sample-level Artifact fields (uri/sha/modality). This is NOT the product P0
generation leaderboard contract. P0 is trajectory / Judge / gate release-audit
(see docs/STATUS.md, docs/ROADMAP.md). Schema id `multimodal-evidence-manifest/v1`
is retained for fixture compatibility.
"""
from __future__ import annotations
import hashlib, json, re
from pathlib import Path
MODALITIES={"text","image","audio","video","document"}; SHA256=re.compile(r"^[a-f0-9]{64}$")
def validate_manifest(data):
    if data.get("schema_version") != "multimodal-evidence-manifest/v1": raise ValueError("unsupported schema_version")
    samples=data.get("samples")
    if not isinstance(samples,list) or not samples: raise ValueError("samples must be non-empty")
    ids=set()
    for s in samples:
        for k in ("sample_id","modality","input_uri","input_sha256","prediction","reference","source"):
            if k not in s or (isinstance(s[k],str) and not s[k]): raise ValueError(f"sample missing {k}")
        if s["sample_id"] in ids: raise ValueError("duplicate sample_id")
        ids.add(s["sample_id"])
        if s["modality"] not in MODALITIES: raise ValueError("unsupported modality")
        if not SHA256.fullmatch(s["input_sha256"]): raise ValueError("input_sha256 must be lowercase sha256")
    return {"valid":True,"sample_count":len(samples),"modalities":sorted({s["modality"] for s in samples})}
def validate_file(path):
    path=Path(path); result=validate_manifest(json.loads(path.read_text(encoding="utf-8")))
    return {**result,"path":str(path),"sha256":hashlib.sha256(path.read_bytes()).hexdigest()}
