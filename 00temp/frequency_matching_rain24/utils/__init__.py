# -*- coding: utf-8 -*-
"""multi_optimize_tp_24h ``utils`` 包入口：合并共享插件与 ``src/utils``。

导入约定：``from utils.xxx import ...``。

路径合并顺序：
1. 本目录（仅本文件，不放业务模块）
2. ``00temp/utils`` — 共享：``multipro_plugin`` / ``data_prepare_plugin`` / ``base_plugin`` 等
3. ``src/utils`` — 本算法：``config`` / ``data_proc`` / ``data_save`` / ``verify`` /
   ``logger`` / ``util_env``

``src/utils/`` 下仅放模块文件，不要添加 ``__init__.py``。
与共享目录内容一致（换行规范化后）的模块已删除，统一使用 ``00temp/utils``。
"""
import os

_here = os.path.dirname(os.path.abspath(__file__))
_shared_utils = os.path.normpath(os.path.join(_here, "..", "..", "utils"))
_src_utils = os.path.normpath(os.path.join(_here, "..", "src", "utils"))

__path__ = [_here]
for _p in (_shared_utils, _src_utils):
    if os.path.isdir(_p) and _p not in __path__:
        __path__.append(_p)
