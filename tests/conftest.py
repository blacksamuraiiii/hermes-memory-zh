"""Pytest bootstrap：插件目录名含连字符不能直接 import，
以包模式注册为 hermes_memory_zh_test，使 __init__.py 的相对导入可用。
"""
import importlib.util
import sys
from pathlib import Path

PLUGIN_DIR = Path(__file__).resolve().parent.parent
PKG = "hermes_memory_zh_test"

if PKG not in sys.modules:
    spec = importlib.util.spec_from_file_location(
        PKG, str(PLUGIN_DIR / "__init__.py"),
        submodule_search_locations=[str(PLUGIN_DIR)])
    mod = importlib.util.module_from_spec(spec)
    sys.modules[PKG] = mod
    spec.loader.exec_module(mod)
    sys.path.insert(0, str(PLUGIN_DIR))  # 兜底：顶层 import store/retrieval 也可用
