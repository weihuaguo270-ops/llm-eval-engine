"""pytest configuration for eval-engine tests"""
import sys
import os

# Ensure **this checkout's** src/ is on the path.
#
# 【2026-10-05 修】原写法 `os.path.dirname(__file__)` 得到的是 `tests/`，
# 于是插入的是 `tests/src`——**这个目录不存在**，真正的 src 从未进入 sys.path。
# 后果：测试 import 的是 venv 里 editable 安装（`.pth`）指向的那份代码；
# 若 `.venv` 是随目录一起复制过来的，其 `.pth` 会指向**别处的另一个 checkout**。
# 也就是说：**改本仓库 src 下的代码，不会被任何测试覆盖**（实测：
# `load_bands` 的新逻辑在脚本里生效、在 pytest 里失效，才暴露出来）。
# 改为用本文件所在目录的上一级，并放在 sys.path 最前，确保本地代码优先。
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
