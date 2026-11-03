#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""面向 meteva_base 网格数据的门控过滤工具。"""

from __future__ import annotations

import meteva_base as meb
import numpy as np
import xarray as xr


class GridGateFilter:
    """为 meteva_base 网格数据构建布尔门控掩码。

    参考 Py-ART ``GateFilter`` 的常用能力：维护内部排除掩码，并通过
    include/exclude 规则更新。构造时传入模板 ``grid_data``（任意与目标
    形状一致的 meteva 场）；若模板带有逐射线 ``antenna_transition`` 坐标
    （或显式传入数组），则支持天线过渡射线过滤。
    """

    def __init__(
        self,
        grid_data: xr.DataArray,
        exclude_based: bool = True,
        gate_excluded: np.ndarray | None = None,
    ):
        """基于模板网格创建过滤器。

        Parameters
        ----------
        grid_data : xr.DataArray
            用于确定过滤掩码形状的模板网格（速度、反射率等均可）；
            也可携带 ``antenna_transition`` 等辅助坐标。
        exclude_based : bool, optional
            为 True 时默认全部包含；为 False 时默认全部排除。
        gate_excluded : ndarray or None, optional
            显式排除掩码；形状须为二维平面或与 ``grid_data`` 相同。
        """
        # 模板网格不做 VALID_VAL ±1000 截断（可含缺测填充或非气象量级值）。
        self.grid_data = meb.checkout_griddata(
            grid_data,
            is_single=False,
            valid_val=(-np.inf, np.inf, np.nan),
        )
        grid_shape = self.grid_data.shape
        plane_shape = grid_shape[-2:]

        if gate_excluded is not None:
            gate_excluded = np.asarray(gate_excluded, dtype=bool)
            if gate_excluded.shape not in (plane_shape, grid_shape):
                raise ValueError(
                    "gate_excluded shape must match the 2D plane or full grid shape"
                )
            self._gate_excluded = gate_excluded.copy()
        else:
            shape = plane_shape if _is_single_context(self.grid_data) else grid_shape
            if exclude_based:
                self._gate_excluded = np.zeros(shape, dtype=bool)
            else:
                self._gate_excluded = np.ones(shape, dtype=bool)

    @classmethod
    def from_mask(cls, grid_data: xr.DataArray, mask) -> "GridGateFilter":
        """由布尔掩码创建过滤器。"""
        return cls(grid_data, gate_excluded=np.asarray(mask, dtype=bool))

    def copy(self) -> "GridGateFilter":
        """返回过滤器副本。"""
        return GridGateFilter(self.grid_data, gate_excluded=self._gate_excluded)

    @property
    def gate_included(self) -> np.ndarray:
        """参与计算的门点布尔数组（副本）。"""
        return ~self._gate_excluded.copy()

    @property
    def gate_excluded(self) -> np.ndarray:
        """被排除的门点布尔数组（副本）。"""
        return self._gate_excluded.copy()

    @gate_excluded.setter
    def gate_excluded(self, value) -> None:
        value = np.asarray(value, dtype=bool)
        if value.shape != self._gate_excluded.shape:
            raise ValueError("gate_excluded shape must match the filter shape")
        self._gate_excluded = value.copy()

    def _merge(self, marked, op: str = "or", exclude_masked: bool = True):
        """将标记门点与当前排除掩码合并。"""
        if exclude_masked not in (True, False):
            raise ValueError("exclude_masked must be True or False")

        marked = np.ma.filled(marked, exclude_masked)
        marked = np.asarray(marked, dtype=bool)
        if marked.shape != self._gate_excluded.shape:
            raise ValueError("marked gate mask must match the filter shape")

        if op == "or":
            self._gate_excluded = np.logical_or(self._gate_excluded, marked)
        elif op == "and":
            self._gate_excluded = np.logical_and(self._gate_excluded, marked)
        elif op == "new":
            self._gate_excluded = marked
        else:
            raise ValueError("op must be one of 'or', 'and', or 'new'")

    def _get_fdata(self, grid_data) -> np.ndarray:
        """返回与过滤器形状匹配的场数据。"""
        normalized = meb.checkout_griddata(
            grid_data,
            is_single=False,
            valid_val=(-np.inf, np.inf, np.nan),
        )
        if self._gate_excluded.ndim == 2:
            return _as_2d_array(normalized)
        if normalized.shape != self._gate_excluded.shape:
            raise ValueError("grid_data shape must match the full GridGateFilter shape")
        return normalized.values

    def _resolve_antenna_transition(self, antenna_transition=None):
        """从显式参数或模板坐标解析逐射线过渡旗标。"""
        if antenna_transition is not None:
            return np.ma.asarray(antenna_transition).reshape(-1)

        if "antenna_transition" in self.grid_data.coords:
            return np.ma.asarray(
                self.grid_data.coords["antenna_transition"].values
            ).reshape(-1)

        return None

    def _mark_transition_rays(self, ray_selected):
        """将长度为 nrays 的射线选择扩展为门点掩码。"""
        ray_selected = np.ma.asarray(ray_selected).reshape(-1)
        nrays = self._gate_excluded.shape[-2]
        if ray_selected.size != nrays:
            raise ValueError(
                f"antenna_transition length must be {nrays}, got {ray_selected.size}"
            )

        marked = np.zeros(self._gate_excluded.shape, dtype=bool)
        selected = np.ma.filled(ray_selected, False)
        if self._gate_excluded.ndim == 2:
            marked[selected] = True
        else:
            marked[..., selected, :] = True

        if np.ma.isMaskedArray(ray_selected) and np.any(np.ma.getmaskarray(ray_selected)):
            row_mask = np.ma.getmaskarray(ray_selected)
            if self._gate_excluded.ndim == 2:
                mask = np.broadcast_to(row_mask[:, None], marked.shape).copy()
            else:
                mask = np.zeros(marked.shape, dtype=bool)
                mask[..., row_mask, :] = True
            marked = np.ma.array(marked, mask=mask)
        return marked

    def exclude_below(
        self, grid_data, value, exclude_masked: bool = True, op: str = "or", inclusive: bool = False
    ):
        """排除 ``grid_data`` 小于（或 ≤）阈值的门点。"""
        data = self._get_fdata(grid_data)
        marked = data <= value if inclusive else data < value
        self._merge(marked, op, exclude_masked)

    def exclude_above(
        self, grid_data, value, exclude_masked: bool = True, op: str = "or", inclusive: bool = False
    ):
        """排除 ``grid_data`` 大于（或 ≥）阈值的门点。"""
        data = self._get_fdata(grid_data)
        marked = data >= value if inclusive else data > value
        self._merge(marked, op, exclude_masked)

    def exclude_inside(
        self,
        grid_data,
        v1,
        v2,
        exclude_masked: bool = True,
        op: str = "or",
        inclusive: bool = True,
    ):
        """排除 ``grid_data`` 落在区间内的门点。"""
        if v2 < v1:
            v1, v2 = v2, v1
        data = self._get_fdata(grid_data)
        marked = (data >= v1) & (data <= v2) if inclusive else (data > v1) & (data < v2)
        self._merge(marked, op, exclude_masked)

    def exclude_outside(
        self,
        grid_data,
        v1=None,
        v2=None,
        exclude_masked: bool = True,
        op: str = "or",
        inclusive: bool = False,
    ):
        """排除 ``grid_data`` 落在区间外的门点。"""
        if v1 is None and v2 is None:
            return
        if v1 is None:
            return self.exclude_above(grid_data, v2, exclude_masked, op, inclusive)
        if v2 is None:
            return self.exclude_below(grid_data, v1, exclude_masked, op, inclusive)
        if v2 < v1:
            v1, v2 = v2, v1
        data = self._get_fdata(grid_data)
        marked = (data <= v1) | (data >= v2) if inclusive else (data < v1) | (data > v2)
        self._merge(marked, op, exclude_masked)

    def exclude_equal(self, grid_data, value, exclude_masked: bool = True, op: str = "or"):
        """排除 ``grid_data`` 等于指定值的门点。"""
        self._merge(self._get_fdata(grid_data) == value, op, exclude_masked)

    def exclude_not_equal(self, grid_data, value, exclude_masked: bool = True, op: str = "or"):
        """排除 ``grid_data`` 不等于指定值的门点。"""
        self._merge(self._get_fdata(grid_data) != value, op, exclude_masked)

    def exclude_all(self):
        """排除全部门点。"""
        self._gate_excluded = np.ones_like(self._gate_excluded)

    def exclude_none(self):
        """不排除任何门点。"""
        self._gate_excluded = np.zeros_like(self._gate_excluded)

    def exclude_masked(self, grid_data, exclude_masked: bool = True, op: str = "or"):
        """排除 ``grid_data`` 中的掩码门点。"""
        self._merge(np.ma.getmaskarray(self._get_fdata(grid_data)), op, exclude_masked)

    def exclude_invalid(self, grid_data, exclude_masked: bool = True, op: str = "or"):
        """排除 ``grid_data`` 中为 NaN 或无穷的门点。"""
        self._merge(~np.isfinite(self._get_fdata(grid_data)), op, exclude_masked)

    def exclude_gates(self, mask, exclude_masked: bool = True, op: str = "or"):
        """按外部布尔掩码排除门点（True 表示排除）。"""
        self._merge(np.asarray(mask, dtype=bool), op, exclude_masked)

    def exclude_transition(
        self,
        antenna_transition=None,
        trans_value: int = 1,
        exclude_masked: bool = True,
        op: str = "or",
    ):
        """排除天线过渡射线上的全部门点。

        Parameters
        ----------
        antenna_transition : array-like or None, optional
            长度为 ``nrays`` 的逐射线旗标。为 ``None`` 时，若模板存在
            ``grid_data.coords['antenna_transition']`` 则读取之；否则不排除
            （与 Py-ART 在 ``radar.antenna_transition is None`` 时一致）。
        trans_value : int, optional
            表示“处于过渡”的旗标值，默认 ``1``。
        exclude_masked : bool, optional
            过渡旗标含掩码时，是否将掩码位视为排除。
        op : {'and', 'or', 'new'}, optional
            与当前排除掩码的合并方式。
        """
        flags = self._resolve_antenna_transition(antenna_transition)
        if flags is None:
            marked = np.zeros(self._gate_excluded.shape, dtype=bool)
        else:
            marked = self._mark_transition_rays(flags == trans_value)
        self._merge(marked, op, exclude_masked)

    def include_below(
        self, grid_data, value, exclude_masked: bool = True, op: str = "and", inclusive: bool = False
    ):
        """仅保留 ``grid_data`` 小于（或 ≤）阈值的门点。"""
        data = self._get_fdata(grid_data)
        marked = data <= value if inclusive else data < value
        self._merge(~marked, op, exclude_masked)

    def include_above(
        self, grid_data, value, exclude_masked: bool = True, op: str = "and", inclusive: bool = False
    ):
        """仅保留 ``grid_data`` 大于（或 ≥）阈值的门点。"""
        data = self._get_fdata(grid_data)
        marked = data >= value if inclusive else data > value
        self._merge(~marked, op, exclude_masked)

    def include_inside(
        self,
        grid_data,
        v1,
        v2,
        exclude_masked: bool = True,
        op: str = "and",
        inclusive: bool = True,
    ):
        """仅保留 ``grid_data`` 落在区间内的门点。"""
        if v2 < v1:
            v1, v2 = v2, v1
        data = self._get_fdata(grid_data)
        marked = (data >= v1) & (data <= v2) if inclusive else (data > v1) & (data < v2)
        self._merge(~marked, op, exclude_masked)

    def include_outside(
        self,
        grid_data,
        v1=None,
        v2=None,
        exclude_masked: bool = True,
        op: str = "and",
        inclusive: bool = False,
    ):
        """仅保留 ``grid_data`` 落在区间外的门点。"""
        if v1 is None and v2 is None:
            return
        if v1 is None:
            return self.include_below(grid_data, v2, exclude_masked, op, inclusive)
        if v2 is None:
            return self.include_above(grid_data, v1, exclude_masked, op, inclusive)
        if v2 < v1:
            v1, v2 = v2, v1
        data = self._get_fdata(grid_data)
        marked = (data <= v1) | (data >= v2) if inclusive else (data < v1) | (data > v2)
        self._merge(~marked, op, exclude_masked)

    def include_equal(self, grid_data, value, exclude_masked: bool = True, op: str = "and"):
        """仅保留 ``grid_data`` 等于指定值的门点。"""
        self._merge(~(self._get_fdata(grid_data) == value), op, exclude_masked)

    def include_not_equal(self, grid_data, value, exclude_masked: bool = True, op: str = "and"):
        """仅保留 ``grid_data`` 不等于指定值的门点。"""
        self._merge(~(self._get_fdata(grid_data) != value), op, exclude_masked)

    def include_all(self):
        """保留全部门点（清空排除状态）。"""
        self._gate_excluded = np.zeros_like(self._gate_excluded)

    def include_none(self):
        """不保留任何门点（全部排除）。"""
        self._gate_excluded = np.ones_like(self._gate_excluded)

    def include_not_masked(self, grid_data, exclude_masked: bool = True, op: str = "and"):
        """仅保留 ``grid_data`` 中非掩码的门点。"""
        self._merge(np.ma.getmaskarray(self._get_fdata(grid_data)), op, exclude_masked)

    def include_valid(self, grid_data, exclude_masked: bool = True, op: str = "and"):
        """仅保留 ``grid_data`` 中有限值的门点。"""
        self._merge(~np.isfinite(self._get_fdata(grid_data)), op, exclude_masked)

    def include_gates(self, mask, exclude_masked: bool = True, op: str = "and"):
        """按外部布尔掩码保留门点（True 表示保留）。"""
        self._merge(~np.asarray(mask, dtype=bool), op, exclude_masked)

    def include_not_transition(
        self,
        antenna_transition=None,
        trans_value: int = 0,
        exclude_masked: bool = True,
        op: str = "and",
    ):
        """仅保留非天线过渡射线上的门点。

        Parameters
        ----------
        antenna_transition : array-like or None, optional
            长度为 ``nrays`` 的逐射线旗标。为 ``None`` 时，若模板存在
            ``grid_data.coords['antenna_transition']`` 则读取之；否则保留全部
            射线（与 Py-ART 在缺少过渡元数据时一致）。
        trans_value : int, optional
            表示“非过渡”的旗标值，默认 ``0``。
        exclude_masked : bool, optional
            过渡旗标含掩码时，是否将掩码位视为排除。
        op : {'and', 'or', 'new'}, optional
            与当前排除掩码的合并方式。
        """
        flags = self._resolve_antenna_transition(antenna_transition)
        if flags is None:
            include = np.ones(self._gate_excluded.shape, dtype=bool)
            self._merge(~include, op, exclude_masked)
            return

        marked = self._mark_transition_rays(flags == trans_value)
        # marked 为 True 表示该射线应保留；合并前取反写入排除掩码。
        if np.ma.isMaskedArray(marked):
            include = np.ma.array(
                np.asarray(marked, dtype=bool),
                mask=np.ma.getmaskarray(marked),
            )
        else:
            include = np.asarray(marked, dtype=bool)
        self._merge(~include, op, exclude_masked)


def _as_2d_array(grid_data: xr.DataArray) -> np.ndarray:
    """从单个 meteva_base 网格切片提取二维数据平面。"""
    normalized = meb.checkout_griddata(
        grid_data,
        is_single=True,
        valid_val=(-np.inf, np.inf, np.nan),
    )
    return normalized.values[0, 0, 0, 0, :, :]


def _is_single_context(grid_data: xr.DataArray) -> bool:
    """判断前四维是否均为长度 1（即单一处理平面）。"""
    return all(size == 1 for size in grid_data.shape[:4])
