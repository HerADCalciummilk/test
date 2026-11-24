"""站点→格点融合算法入口。

统一接口 ``process(sta, grid=None, background=None)``，由 ``reprocess`` 区分
绝对值路径与偏差/创新量路径。推荐对外使用 ``InterpSg(method=...)``；
各 ``InterpSg*`` 算法插件仍可单独调用。
"""

from .interp_sg_cressman_plugin import InterpSgCressman
from .interp_sg_gaussian_plugin import InterpSgGaussian
from .interp_sg_idw_plugin import InterpSgIdw
from .interp_sg_kriging import InterpSgKriging
from .interp_sg_plugin import InterpSg

__all__ = [
    "InterpSg",
    "InterpSgCressman",
    "InterpSgGaussian",
    "InterpSgIdw",
    "InterpSgKriging",
]
