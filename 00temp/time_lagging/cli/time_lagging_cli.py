# -*- coding: utf-8 -*-
"""时间滞后集合。

``process`` 读入多份预报，调用 ``TimeLaggingPlugin``，再写出。
本包用 ``util/`` 而不是 ``utils/``，因此先把 ``00temp`` 放进 ``sys.path``。
"""
from __future__ import annotations

import sys
from pathlib import Path

_CLI_DIR = Path(__file__).resolve().parent
_ROOT = _CLI_DIR.parent
_TEMP = _ROOT.parent
_SRC = _ROOT / "src"
for _path in (str(_SRC), str(_ROOT), str(_TEMP)):
    if _path in sys.path:
        sys.path.remove(_path)
sys.path.insert(0, str(_TEMP))
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_SRC))

from time_lagging.src.time_lagging_plugin import TimeLaggingPlugin
from time_lagging.util.meteva_data import load_meteva, save_meteva
from utils.merge_params import merge_params


def _as_paths(inputs) -> list[str]:
    if inputs is None:
        return []
    if isinstance(inputs, (str, Path)):
        text = str(inputs)
        return [item.strip() for item in text.split(",") if item.strip()]
    return [str(item) for item in inputs]


def _default_output(path: str) -> Path:
    suffix = Path(path).suffix.lower()
    if suffix in {".nc", ".nc4"}:
        return Path("time_lagging_ensemble.nc")
    return Path("time_lagging_ensemble.csv")


@merge_params(anchor=__file__)
def process(inputs: list = None, output: str = None, config=None):
    """读入若干预报，生成时间滞后集合并写出。"""
    _ = config
    paths = _as_paths(inputs)
    if len(paths) < 1:
        raise ValueError("缺少参数: inputs（调用参数与配置文件均未提供）")
    datasets = [load_meteva(path) for path in paths]
    result = TimeLaggingPlugin().process(*datasets)
    target = Path(output) if output else _default_output(paths[0])
    save_meteva(result, target)
    print(f"已写出时间滞后集合 {target}")
    return result
