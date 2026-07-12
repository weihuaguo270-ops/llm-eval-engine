"""Tests for template_loader"""
import os
from eval_engine.judge.template_loader import (
    load_template,
    load_all_templates,
    list_available_templates,
)


def test_list_templates():
    """列出可用模板"""
    names = list_available_templates()
    assert len(names) > 0
    print(f"✅ 可用模板: {names}")


def test_load_faithfulness():
    """加载 faithfulness 模板"""
    tpl = load_template("faithfulness")
    assert tpl is not None
    assert tpl.name == "faithfulness"
    assert tpl.min_score >= 1
    assert tpl.weight > 0
    print(f"✅ faithfulness: min={tpl.min_score}, max={tpl.max_score}, weight={tpl.weight}")


def test_load_all():
    """加载全部模板"""
    templates = load_all_templates()
    assert len(templates) >= 2
    names = [t.name for t in templates]
    print(f"✅ 全部模板: {names}")


def test_load_nonexistent():
    """不存在的模板返回 None"""
    tpl = load_template("nonexistent_template_xyz")
    assert tpl is None
    print("✅ 不存在模板返回 None")


if __name__ == "__main__":
    test_list_templates()
    test_load_faithfulness()
    test_load_all()
    test_load_nonexistent()
    print("\n🎉 All template loader tests passed!")
