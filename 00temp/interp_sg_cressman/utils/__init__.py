# -*- coding: utf-8 -*-
"""interp_sg_cressman ``utils`` 包入口：合并共享插件与 ``src/utils``。

导入约定：``from utils.xxx import ...``。

路径合并顺序：
1. 本目录（仅本文件）
2. 仓库根 ``utils/`` — 共享：``base_plugin`` / ``interp_gg_pulgin`` 等
3. ``src/utils`` — 本算法：``util_env`` 等

``src/utils/`` 下仅放模块文件，不要添加 ``__init__.py``。
"""
import os

_here = os.path.dirname(os.path.abspath(__file__))
_shared_utils = os.path.normpath(os.path.join(_here, "..", "..", "utils"))
_src_utils = os.path.normpath(os.path.join(_here, "..", "src", "utils"))

__path__ = [_here]
for _p in (_shared_utils, _src_utils):
    if os.path.isdir(_p) and _p not in __path__:
        __path__.append(_p)
