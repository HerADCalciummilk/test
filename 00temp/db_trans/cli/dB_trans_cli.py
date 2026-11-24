# -*- coding: utf-8 -*-
"""降水强度变换。

``@merge_params`` 挂在函数 ``process`` 上；业务经 ``DbTransPlugin`` 调度四个算法。
由 ``python -m db_trans`` 或 ``python -m utils.nimm_cli db_trans`` 启动。
"""
import os
import sys
from typing import Optional

_CLI_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT_DIR = os.path.dirname(_CLI_DIR)
_SRC_DIR = os.path.join(_ROOT_DIR, "src")
for _p in (_ROOT_DIR, _SRC_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np

from db_trans_plugin import METHODS, DbTransPlugin
from utils.merge_params import merge_params

_METHODS = ("summary",) + METHODS


def _parse_values(text):
    parts = [item.strip() for item in str(text).split(",") if item.strip()]
    if not parts:
        raise ValueError("values 未包含数值")
    return np.asarray([float(item) for item in parts], dtype=float)


@merge_params()
def process(
    method: str = "summary",
    values: str = None,
    threshold: float = 0.1,
    zerovalue: Optional[float] = None,
    lam: float = 0,
    a: float = 0,
    inverse: bool = False,
    config=None,
):
    """调用入口。``config`` 只换配置文件；变换由 ``DbTransPlugin`` 执行。"""
    _ = config
    method = (method or "summary").strip().lower()
    if method not in _METHODS:
        raise ValueError("method 无效。可选 summary、db、box、nq、sqrt")
    if method == "summary":
        print("available methods: %s" % (", ".join(METHODS),))
        return 0
    text = None if values is None else str(values).strip()
    if not text:
        raise ValueError("缺少参数: values（调用参数与配置文件均未提供）")
    try:
        result, metadata = DbTransPlugin().process(
            _parse_values(text),
            method=method,
            inverse=bool(inverse),
            threshold=threshold,
            zerovalue=zerovalue,
            Lambda=lam,
            a=a,
        )
        printable = {
            key: value
            for key, value in metadata.items()
            if isinstance(value, (str, int, float, bool)) or value is None
        }
        print(np.array2string(np.asarray(result), separator=", "))
        print(printable)
        return result
    except Exception as exc:
        print("降水强度变换失败 %s: %s" % (method, exc))
        return False
