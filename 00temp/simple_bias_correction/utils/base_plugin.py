"""本模块定义了插件基类与后处理插件基类。"""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable, MutableMapping
from typing import Any

import numpy as np
import pandas as pd
import xarray as xr


class BasePlugin(ABC):
    """基础插件类。"""

    def __call__(self, *args, **kwargs):
        """使插件类实例可以直接调用。"""
        return self.process(*args, **kwargs)

    @abstractmethod
    def process(self, *args, **kwargs):
        """插件处理主函数。"""
        pass


class PostProcessingPlugin(BasePlugin):
    """后处理插件基类。

    同时适配：
    - meteva_base 网格数据（``xarray.DataArray`` / ``Dataset``）
    - 站点表（``pandas.DataFrame``，属性写在 ``DataFrame.attrs``）
    """

    def __call__(self, *args, **kwargs) -> Any:
        """调用 ``process``，并对带 ``attrs`` 的结果更新 title。"""
        result = super().__call__(*args, **kwargs)
        if isinstance(result, xr.DataArray):
            self.post_processed_title(result)
        elif isinstance(result, xr.Dataset):
            for var in result.data_vars:
                self.post_processed_title(result[var])
        elif isinstance(result, pd.DataFrame):
            self.post_processed_title(result)
        elif isinstance(result, (np.ndarray, np.ma.MaskedArray)):
            # 裸数组无 attrs，跳过后处理属性更新。
            return result
        elif isinstance(result, Iterable) and not isinstance(result, (str, bytes)):
            for item in result:
                if isinstance(item, xr.DataArray):
                    self.post_processed_title(item)
                elif isinstance(item, xr.Dataset):
                    for var in item.data_vars:
                        self.post_processed_title(item[var])
                elif isinstance(item, pd.DataFrame):
                    self.post_processed_title(item)
        return result

    @staticmethod
    def post_processed_title(obj: Any) -> None:
        """在 ``obj.attrs['title']`` 前添加 ``Post-Processed`` 前缀。

        适用于 ``xarray.DataArray`` 与 ``pandas.DataFrame`` 等带 ``attrs`` 的对象。
        无 ``title``、值为 ``unknown``、或已含 ``Post-Processed`` 时不修改。
        """
        attrs = getattr(obj, "attrs", None)
        if not isinstance(attrs, MutableMapping):
            return
        default_title = "unknown"
        if (
            "title" in attrs
            and attrs["title"] != default_title
            and "Post-Processed" not in attrs["title"]
        ):
            title = attrs["title"]
            attrs["title"] = f"Post-Processed {title}"
