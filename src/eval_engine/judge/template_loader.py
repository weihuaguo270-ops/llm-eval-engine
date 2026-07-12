"""template_loader — 加载 YAML 评分模板为 VerifierContract

将 judge/templates/ 目录下的 YAML 模板加载为可用的评分契约。
支持有 PyYAML（完整解析）和无 PyYAML（简易解析）两种模式。
"""

from __future__ import annotations
import os
import re
from typing import Optional

from eval_engine.core.contract import VerifierContract

_TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")


def _parse_simple_yaml(text: str) -> dict:
    """简易 YAML 解析（不依赖 PyYAML）

    仅支持模板文件的键值对格式，不支持嵌套结构。
    """
    result = {}
    for line in text.split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = re.match(r"^(\w+):\s*(.*)", line)
        if match:
            key, value = match.group(1), match.group(2).strip()
            # 去掉引号
            if value.startswith('"') and value.endswith('"'):
                value = value[1:-1]
            elif value.startswith("'") and value.endswith("'"):
                value = value[1:-1]
            # 收集 rubric（多行则追加）
            if key == "rubric":
                existing = result.get("rubric", "")
                result["rubric"] = (existing + "\n" + value).strip()
            else:
                result[key] = value
    return result


def _try_load_yaml(filepath: str) -> Optional[dict]:
    """尝试加载 YAML 文件，优先用 PyYAML"""
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
    """按名称加载单个评分模板

    参数:
        name: 模板名（不含 .yaml 后缀）

    返回:
        VerifierContract 或 None（模板不存在时）
    """
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
    """加载所有可用的评分模板"""
    contracts = []
    if not os.path.isdir(_TEMPLATES_DIR):
        return contracts

    for fname in sorted(os.listdir(_TEMPLATES_DIR)):
        if fname.endswith(".yaml"):
            name = fname.replace(".yaml", "")
            contract = load_template(name)
            if contract:
                contracts.append(contract)
    return contracts


def list_available_templates() -> list[str]:
    """列出所有可用的模板名称"""
    if not os.path.isdir(_TEMPLATES_DIR):
        return []
    return sorted(
        fname.replace(".yaml", "")
        for fname in os.listdir(_TEMPLATES_DIR)
        if fname.endswith(".yaml")
    )
