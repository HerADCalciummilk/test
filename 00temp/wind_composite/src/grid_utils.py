"""meb 标准网格的校验与构造工具。"""

from __future__ import annotations

import numpy as np
import xarray as xr
import meteva_base as meb

# meb 网格数据的六个维度，顺序固定
GRID_DIMS = ("member", "level", "time", "dtime", "lat", "lon")

# meb 网格数据必备的六项属性
GRID_ATTRS = ("units", "model_var", "dtime_units", "level_type", "time_type",
              "time_bounds")


def check_griddata(data: xr.DataArray, role: str) -> xr.DataArray:
    """校验输入为 meb 标准网格，返回规范化后的对象。

    Args:
        data: 待校验的网格数据。
        role: 该数据在算法中的角色，仅用于报错信息。

    Returns:
        经 meb 规范化的网格数据。

    Raises:
        ValueError: 维度不齐时抛出。
    """
    checked = meb.checkout_griddata(data)
    missing = [dim for dim in GRID_DIMS if dim not in checked.dims]
    if missing:
        raise ValueError(f"{role} 不是 meb 标准网格，缺少维度: {missing}")
    return checked


def rebuild_griddata(values: np.ndarray, template: xr.DataArray, units: str,
                     member: str) -> xr.DataArray:
    """按模板坐标构造输出网格，并补齐必备属性。

    Args:
        values: 与模板同形的计算结果。
        template: 提供坐标系的输入网格。
        units: 输出物理量单位。
        member: 输出成员名，通常为诊断量名称。

    Returns:
        维度与属性均符合 meb 规范的网格数据。
    """
    out = template.copy(deep=True)
    out.values = np.asarray(values, dtype=np.float32).reshape(template.shape)
    out = out.assign_coords(member=[member])

    attrs = {key: template.attrs.get(key) for key in GRID_ATTRS}
    attrs["units"] = units
    out.attrs = attrs
    return out
