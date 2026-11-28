# -*- coding: UTF-8 -*-
"""从仓库根运行时可导入 src 下模块（与 test_run_context.py、mait_1h._bootstrap_paths 一致）。"""
import os
import sys

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC = os.path.join(_REPO, "src")
_ordered = (_REPO, _SRC)
for _p in _ordered:
    while _p in sys.path:
        sys.path.remove(_p)
for _p in reversed(_ordered):
    sys.path.insert(0, _p)

import mait_1h

if __name__ == "__main__":
    mait_1h.process(
        time_inputs=["202605260000"],
        predict_valid_list=[1, 2, 3],
        para_path=os.path.join(_REPO, "resource", "local.ini"),
        is_multi=False,
    )
