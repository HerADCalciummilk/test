"""插件基类：约定算法的统一入口。"""

from __future__ import annotations

import xarray as xr


class BasePlugin:
    """诊断量算法插件基类，子类实现 process。"""

    def __init__(self) -> None:
        """记录插件名，供日志与产品编目使用。"""
        self.name = self.__class__.__name__

    def process(self, *args, **kwargs) -> xr.DataArray:
        """算法主入口，入参与出参均为 meb 标准网格数据。"""
        raise NotImplementedError
