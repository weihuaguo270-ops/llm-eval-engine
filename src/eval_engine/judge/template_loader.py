"""template_loader — 加载 YAML 评分模板为 VerifierContract"""
from __future__ import annotations
import os
import re
from typing import Optional
from eval_engine.core.contract import VerifierContract

def _find_templates_dir() -> str:
    """查找 templates 目录，支持多种安装方式"""
    # 方式1：相对于当前文件（pip install -e .）
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")
    if os.path.isdir(path):
        return path
    # 方式2：相对于项目根（直接运行测试时）
    for candidate in [
        "src/eval_engine/judge/templates",
        "eval_engine/judge/templates",
    ]:
        for root in [os.getcwd(), os.path.dirname(os.path.abspath(__file__))]:
            p = os.path.join(root, candidate)
            if os.path.isdir(p):
                return p
    return path  # 返回默认路径

_TEMPLATES_DIR = _find_templates_dir()

def _parse_simple_yaml(text: str) -> dict:
    result = {}
    current_key = None
    for line in text.split("\n"):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = re.match(r"^(\w+):\s*(.*)", stripped)
        if match:
            current_key = match.group(1)
            value = match.group(2).strip()
            if value.startswith("|"):
                result[current_key] = ""
            else:
                result[current_key] = value
        elif current_key and current_key in result:
            result[current_key] += "\n" + stripped
    return result

def _try_load_yaml(filepath: str) -> Optional[dict]:
    try:
        import yaml
        with open(filepath, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except ImportError:
        with open(filepath, "r", encoding="utf-8") as f:
            return _parse_simple_yaml(f.read())
    except Exception:
        return None

def load_template(name: str) -> Optional[VerifierContract]:
    filepath = os.path.join(_TEMPLATES_DIR, f"{name}.yaml")
    if not os.path.exists(filepath):
        return None
    data = _try_load_yaml(filepath)
    if not data:
        return None
    return VerifierContract(
        name=data.get("name", name),
        rubric=data.get("rubric", ""),
        min_score=int(data.get("min_score", 1)),
        max_score=int(data.get("max_score", 5)),
        weight=float(data.get("weight", 1.0)),
    )

def load_all_templates() -> list[VerifierContract]:
    contracts = []
    if not os.path.isdir(_TEMPLATES_DIR):
        return contracts
    for fname in sorted(os.listdir(_TEMPLATES_DIR)):
        if fname.endswith(".yaml"):
            contract = load_template(fname.replace(".yaml", ""))
            if contract:
                contracts.append(contract)
    return contracts

def list_available_templates() -> list[str]:
    if not os.path.isdir(_TEMPLATES_DIR):
        return []
    return sorted(fname.replace(".yaml", "") for fname in os.listdir(_TEMPLATES_DIR) if fname.endswith(".yaml"))
