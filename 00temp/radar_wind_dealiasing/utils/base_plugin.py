#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""本模块定义了插件基类与后处理插件基类。"""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable
from typing import Any

import numpy as np
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
    """适配 meteva_base 网格数据的后处理插件基类。"""

    def __call__(self, *args, **kwargs) -> Any:
        """调用 ``process`` 并对 xarray 结果更新 title 属性。"""
        result = super().__call__(*args, **kwargs)
        if isinstance(result, xr.DataArray):
            self.post_processed_title(result)
        elif isinstance(result, xr.Dataset):
            for var in result.data_vars:
                self.post_processed_title(result[var])
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
        return result

    @staticmethod
    def post_processed_title(data_array: xr.DataArray) -> None:
        """在 ``DataArray.attrs['title']`` 前添加 ``Post-Processed`` 前缀。"""
        default_title = "unknown"
        if (
            "title" in data_array.attrs
            and data_array.attrs["title"] != default_title
            and "Post-Processed" not in data_array.attrs["title"]
        ):
            title = data_array.attrs["title"]
            data_array.attrs["title"] = f"Post-Processed {title}"
