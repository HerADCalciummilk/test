# -*- coding: utf-8 -*-
"""快速精细化插值的路径辅助。核心公式仍在 ``src/core``。"""
import os


def _infer_root_path(work_dir):
    """从工作目录向上查找含 Parameter 的业务根目录。"""
    cur = os.path.abspath(work_dir)
    for _ in range(10):
        if os.path.isdir(os.path.join(cur, "Parameter")):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
    return os.path.abspath(os.path.dirname(work_dir))


def _split_model_region(model_region):
    """把 ``EC_12P5KM`` 拆成模式名和区域。"""
    parts = model_region.split("_", 1)
    if len(parts) != 2 or not all(parts):
        raise ValueError(f"model_region must look like EC_12P5KM, got {model_region!r}")
    return parts[0], parts[1]


def _append_optional_pylib(root_path):
    """若业务根下有 lib/pylib，追加到 sys.path。"""
    import sys

    pylib_path = os.path.join(root_path, "lib", "pylib")
    if os.path.isdir(pylib_path) and pylib_path not in sys.path:
        sys.path.append(pylib_path)
