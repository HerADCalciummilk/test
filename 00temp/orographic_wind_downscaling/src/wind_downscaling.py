# (C) Crown Copyright, Met Office. All rights reserved.
#
# This file is part of 'IMPROVER' and is released under the BSD 3-Clause license.
# See LICENSE in the root of the repository for full licensing details.
"""
模块包含适用于meteva数据结构的风速降尺度插件。

本模块实现了基于地形粗糙度和高度的风速订正算法，
用于提高风速预报的空间分辨率和准确性。
"""

# 导入必要的库
import json
from typing import Optional, Tuple, Union

import numpy as np
import xarray as xr
from numpy import ndarray

import meteva_base as meb

from orographic_wind_downscaling.utils.base_plugin import BasePlugin, PostProcessingPlugin
from orographic_wind_downscaling.utils.utils import rebuild_to_meb_griddata

# 真实缺测数据指示符
RMDI = -32767.0

# 用于确定参考高度的尺度参数（扰动衰减阈值）ε；Vosper/Clark 默认 0.04
ABSOLUTE_CORRECTION_TOL = 0.04

# 参考高度上限相对半峰谷高度的倍数
HREF_SCALE = 2.0

# 波数裁剪：dx_max = DX_MAX_FACTOR * 模式分辨率；dx_min = DX_MIN_FACTOR * 后处理分辨率
DX_MAX_FACTOR = 3.0
DX_MIN_FACTOR = 0.5

# 冯·卡门常数
VONKARMAN = 0.4

# 经纬网格间距换算为米时使用的地球半径（与常见气象近似一致）
EARTH_RADIUS_M = 6371000.0

# 海面点的默认粗糙度长度（米）
Z0M_SEA = 0.0001


class FrictionVelocity(BasePlugin):
    """
    摩擦速度计算类
    该类用于计算大气边界层中的摩擦速度 u*，这是表征近地面大气湍流强度的特征速度尺度。
    摩擦速度反映了地表对大气运动的摩擦拖拽作用，是连接地表和大气的关键参数。
    计算原理基于对数风速廓线方程，适用于中性大气条件下的边界层风速分布。
    所需参数包括：
    - 参考高度 h_ref
    - 参考高度处的风速 u_href
    - 表面粗糙度 z_0
    - 计算掩码 mask
    """

    def __init__(
            self, u_href: ndarray, h_ref: ndarray, z_0: ndarray, mask: ndarray
    ) -> None:
        """
        初始化摩擦速度计算类
        参数
        ----------
        u_href:
            二维浮点型数组（float32）—— 参考高度 h_ref 处的风速
        h_ref:
            二维浮点型数组（float32）—— 参考高度
        z_0:
            二维浮点型数组（float32）—— 植被粗糙度长度，反映地表粗糙程度
        mask:
            二维布尔型数组（bool）—— True 表示对应格点需计算摩擦速度 u*
        注意事项：
            * z_0 与 h_ref 必须使用相同的单位（通常为米）。
            * 计算得到的摩擦速度的单位与输入风速 u_href 的单位一致。
            * 所有输入数组必须具有相同的尺寸。
        """
        self.u_href = u_href
        self.h_ref = h_ref
        self.z_0 = z_0
        self.mask = mask
        # 检查输入数组是否具有相同的大小
        array_sizes = [np.size(u_href), np.size(h_ref), np.size(z_0), np.size(mask)]
        if not all(x == array_sizes[0] for x in array_sizes):
            raise ValueError("输入数组 u_href, h_ref, z_0, mask 的大小不一致")

    def process(self) -> ndarray:
        """
        核心计算方法：计算摩擦速度场
        计算公式：
        u* = K * (u_href / ln(h_ref / z_0))
        其中：
        - u* 为摩擦速度
        - K 为冯·卡门常数（Von Karman's constant），通常取 0.4
        - u_href 为参考高度处的风速
        - h_ref 为参考高度
        - z_0 为植被粗糙度长度
        计算步骤：
        1. 初始化结果数组为 RMDI（Real Missing Data Indicator）
        2. 提取掩码为 True 的区域的风速值作为分子
        3. 计算掩码区域的对数项作为分母
        4. 应用公式计算摩擦速度
        5. 将计算结果赋值回结果数组的对应位置
        返回值：
            二维浮点型数组（float32）—— 摩擦速度场，未计算的格点值为 RMDI
        """
        # 初始化结果数组，默认为 RMDI
        ustar = np.full(self.u_href.shape, RMDI, dtype=np.float32)

        # 提取需要计算的区域的风速值
        numerator = self.u_href[self.mask]

        # 计算对数项，忽略可能的无效计算（如除零）
        with np.errstate(invalid="ignore"):
            denominator = np.log(self.h_ref[self.mask] / self.z_0[self.mask])

        # 应用摩擦速度计算公式
        ustar[self.mask] = VONKARMAN * (numerator / denominator)

        return ustar


from orographic_wind_downscaling.src.util_plugin import RoughnessCorrectionUtilities


class RoughnessCorrection(PostProcessingPlugin):
    """
    风速降尺度主插件：对输入风速执行粗糙度订正（RC）与高度订正（HC）。

    该类是 `RoughnessCorrectionUtilities` 的上层封装，负责完成以下工作：
    1. 统一输入数据结构（`numpy.ndarray` / `xarray.DataArray`）。
    2. 校验辅助场与风速场的空间一致性。
    3. 按“批次维 + (level, lat, lon)”切片循环调用核心订正计算。
    4. 固定返回 ``(订正风速, hc_add)``：
       - `numpy.ndarray` 输入返回同型二元组；
       - `xarray.DataArray` 输入返回按 meteva_base 约定维度重组后的二元组。

    维度约定：
    - 算法内部计算阶段按 `(level, lat, lon)` 组织三维风速切片。
    - 对于高维输入，除上述三维外的其余维度都作为批次维度独立处理。
    - 对于 `xarray.DataArray` 输入，会先调用 `meb.checkout_griddata` 归一化为
      `member, level, time, dtime, lat, lon` 顺序，再参与计算。

    参数
    ----------
    a_over_s : np.ndarray 或 xr.DataArray, 形状 (lat, lon)
        地形轮廓粗糙度（无量纲）。
    sigma : np.ndarray 或 xr.DataArray, 形状 (lat, lon)
        网格单元内的高度标准差（米）。
    pporo : np.ndarray 或 xr.DataArray, 形状 (lat, lon)
        后处理网格地形高度（米）。
        当传入 xr.DataArray 且未提供 ppres 时，会自动根据坐标估算分辨率（米）。
        投影米制坐标直接取间距；真经纬坐标将度间距换算为米后再取平均。
    modoro : np.ndarray 或 xr.DataArray, 形状 (lat, lon)
        插值至后处理网格的模式地形高度（米）。
    modres : float
        模式原始平均分辨率（米）。
    ppres : float, 可选
        后处理网格分辨率（网格单元平均边长，米）。
        当 pporo 为 np.ndarray 时必须显式提供；当 pporo 为 xr.DataArray 时可省略。
    z0 : np.ndarray 或 xr.DataArray, 形状 (lat, lon)，可选
        植被粗糙度长度（米）。若为None，则跳过粗糙度订正步骤。
    """

    def __init__(
        self,
        a_over_s: Union[np.ndarray, xr.DataArray],
        sigma: Union[np.ndarray, xr.DataArray],
        pporo: Union[np.ndarray, xr.DataArray],
        modoro: Union[np.ndarray, xr.DataArray],
        modres: float,
        ppres: Optional[float] = None,
        z0: Optional[Union[np.ndarray, xr.DataArray]] = None,
        *,
        absolute_correction_tol: float = ABSOLUTE_CORRECTION_TOL,
        href_scale: float = HREF_SCALE,
        dx_max_factor: float = DX_MAX_FACTOR,
        dx_min_factor: float = DX_MIN_FACTOR,
    ) -> None:
        """
        初始化 RoughnessCorrection 类。
        
        参数
        ----------
        a_over_s : np.ndarray 或 xr.DataArray, 形状 (lat, lon)
            地形轮廓粗糙度（无量纲）。
        sigma : np.ndarray 或 xr.DataArray, 形状 (lat, lon)
            网格单元内的高度标准差（米）。
        pporo : np.ndarray 或 xr.DataArray, 形状 (lat, lon)
            后处理网格地形高度（米）。
            若传入 DataArray 且 `ppres` 为空，将自动基于坐标推断网格分辨率（米）；
            真经纬网格会将度间距换算为米。
        modoro : np.ndarray 或 xr.DataArray, 形状 (lat, lon)
            插值至后处理网格的模式地形高度（米）。
        modres : float
            模式原始平均分辨率（米）。
        ppres : float, optional
            后处理网格分辨率（网格单元平均边长，米）。
            当 `pporo` 为 DataArray 时可不传；当 `pporo` 为 ndarray 时必须显式传入。
        z0 : np.ndarray 或 xr.DataArray, 形状 (lat, lon)，可选
            植被粗糙度长度（米）。若为None，则跳过粗糙度订正步骤。
        absolute_correction_tol : float, default 0.04
            扰动衰减阈值 ε，影响粗糙度订正参考高度。
        href_scale : float, default 2.0
            参考高度相对半峰谷高度的上限倍数。
        dx_max_factor : float, default 3.0
            ``dx_max = dx_max_factor * modres``。
        dx_min_factor : float, default 0.5
            ``dx_min = dx_min_factor * ppres``。
        """
        # 存储输入参数
        self.a_over_s = self._to_lat_lon_array(a_over_s, "a_over_s")
        self.sigma = self._to_lat_lon_array(sigma, "sigma")
        # 后处理网格地形高度与分辨率：
        # - DataArray 输入时，可从投影米制或真经纬坐标推断 ppres（始终为米）；
        # - ndarray 输入时，要求外部显式提供 ppres。
        if isinstance(pporo, xr.DataArray):
            # 地形可超出 meteva 默认 [-1000, 1000]，不能把高山改成缺测。
            pporo = meb.checkout_griddata(pporo, valid_val=(-np.inf, np.inf, np.nan))
            if ppres is None:
                ppres = self.infer_grid_resolution_from_coords(pporo)
            self.pporo = np.asarray(pporo.values, dtype=np.float32).squeeze()
            if self.pporo.ndim != 2:
                raise ValueError("pporo 在压缩后必须为二维地形场 (lat, lon)。")
        else:
            self.pporo = np.asarray(pporo, dtype=np.float32)
            if ppres is None:
                raise ValueError("当 pporo 为 ndarray 时，ppres 必须显式传入。")
            if self.pporo.ndim != 2:
                raise ValueError("pporo 必须是二维地形场 (lat, lon)。")

        self.modoro = self._to_lat_lon_array(modoro, "modoro")
        self.z0 = None if z0 is None else self._to_lat_lon_array(z0, "z0")
        self.modres = modres  # 模式原始平均分辨率
        self.ppres = float(ppres)  # 后处理网格分辨率
        self.absolute_correction_tol = float(absolute_correction_tol)
        self.href_scale = float(href_scale)
        self.dx_max_factor = float(dx_max_factor)
        self.dx_min_factor = float(dx_min_factor)

    @staticmethod
    def _to_lat_lon_array(
        field: Union[np.ndarray, xr.DataArray],
        name: str,
    ) -> np.ndarray:
        """将辅助场统一为二维 `(lat, lon)` 数组。"""
        if isinstance(field, xr.DataArray):
            normalized = meb.checkout_griddata(
                field, is_single=True, valid_val=(-np.inf, np.inf, np.nan)
            )
            values = np.asarray(normalized.values.squeeze(), dtype=np.float32)
        else:
            values = np.asarray(field, dtype=np.float32)

        if values.ndim != 2:
            raise ValueError(
                f"{name} 必须是二维单场 `(lat, lon)`，当前维度为 {values.ndim}。"
            )
        return values

    @staticmethod
    def _coord_units_token(coord: xr.DataArray) -> str:
        """归一化坐标 units 字符串，便于判断米制/角度。"""
        return str(coord.attrs.get("units", "")).strip().lower()

    @classmethod
    def _coords_are_geographic_degrees(
        cls,
        data: xr.DataArray,
        y_coord: xr.DataArray,
        x_coord: xr.DataArray,
    ) -> bool:
        """判断空间坐标是否为真经纬（度）。

        判定顺序：

        1. 坐标 ``units``：明确为米 → 否；含 ``degree`` → 是。
        2. ``grid_mapping_attrs``：``latitude_longitude`` 等 → 是；投影类 → 否。
        3. **两侧均无 ``units``**：meb 网格一般默认为经纬，常不写空间坐标单位，
           此时视为经纬。例外：数值远超地理经纬度合理范围时，仍判为投影米制
           （例如官方样例仅把 ``projection_*`` 重命名为 ``lat/lon``、未改数值与单位）。
        """
        y_units = cls._coord_units_token(y_coord)
        x_units = cls._coord_units_token(x_coord)
        meter_tokens = ("m", "metre", "meter", "metres", "meters")
        if y_units in meter_tokens or x_units in meter_tokens:
            return False
        if "degree" in y_units or "degree" in x_units:
            return True

        mapping_raw = data.attrs.get("grid_mapping_attrs")
        if isinstance(mapping_raw, str) and mapping_raw.strip():
            try:
                mapping = json.loads(mapping_raw)
            except json.JSONDecodeError:
                mapping = {}
            if isinstance(mapping, dict):
                name = str(mapping.get("grid_mapping_name", "")).lower()
                if name in ("latitude_longitude", "latlon", "geographic"):
                    return True
                if "lambert" in name or "projected" in name or "azimuthal" in name:
                    return False

        y = np.asarray(y_coord.values, dtype=np.float64)
        x = np.asarray(x_coord.values, dtype=np.float64)
        y = y[np.isfinite(y)]
        x = x[np.isfinite(x)]

        # 无单位：meb 默认经纬；空坐标或数值落在经纬范围内 → True
        # 数值像投影米制（|y|≫90 或 |x|≫360）→ False，避免维名重命名误判
        units_missing = (not y_units) and (not x_units)
        if y.size == 0 or x.size == 0:
            return bool(units_missing)

        in_geo_range = bool(
            np.nanmax(np.abs(y)) <= 90.0 + 1e-6
            and np.nanmax(np.abs(x)) <= 360.0 + 1e-6
        )
        if units_missing:
            return in_geo_range
        # 仅一侧有未识别单位时，仍用范围启发
        return in_geo_range


    @staticmethod
    def infer_grid_resolution_from_coords(
        data: xr.DataArray,
        y_name: Optional[str] = None,
        x_name: Optional[str] = None,
    ) -> float:
        """基于二维空间坐标估算网格分辨率（米）。

        - 投影米制坐标：直接取 ``bounds``/``points`` 差分（米）。
        - 真经纬坐标：将纬度/经度差分换算为米后再平均；
          东西向间距按代表纬度 ``cos(lat)`` 缩放。

        参数
        ----------
        data : xr.DataArray
            包含空间坐标的输入场（通常传入目标网格地形场）。
        y_name : str, optional
            y 方向坐标名。未提供时会尝试自动识别。
        x_name : str, optional
            x 方向坐标名。未提供时会尝试自动识别。

        返回
        -------
        float
            估算的网格分辨率（米），定义为 y/x 分辨率的平均值。
            计算时优先使用坐标 `bounds`，若不存在则退回 `points` 差分。

        异常
        -------
        ValueError
            当无法识别空间坐标或坐标点数不足时抛出。
        """
        if not isinstance(data, xr.DataArray):
            raise TypeError("data 必须是 xarray.DataArray。")

        dims = list(data.dims)

        def _pick_dim(candidates, fallback_index):
            for name in candidates:
                if name in dims:
                    return name
            return dims[fallback_index] if len(dims) >= abs(fallback_index) else None

        y_name = y_name or _pick_dim(("lat", "projection_y_coordinate", "y"), -2)
        x_name = x_name or _pick_dim(("lon", "projection_x_coordinate", "x"), -1)

        if y_name is None or x_name is None:
            raise ValueError("无法从输入中识别空间维度名称。")
        if y_name not in data.coords or x_name not in data.coords:
            raise ValueError(f"输入缺少坐标 {y_name}/{x_name}，无法推断网格分辨率。")

        y_coord = data.coords[y_name]
        x_coord = data.coords[x_name]

        def _resolution_from_coord(coord: xr.DataArray) -> float:
            # CF 坐标若存在 bounds，优先用 bounds 计算分辨率。
            bound_name = coord.attrs.get("bounds")
            if bound_name and bound_name in data.coords:
                bounds = np.asarray(data.coords[bound_name].values, dtype=np.float64)
                if bounds.ndim == 2 and bounds.shape[0] >= 1 and bounds.shape[1] >= 2:
                    widths = np.abs(bounds[:, 1] - bounds[:, 0])
                    widths = widths[np.isfinite(widths)]
                    if widths.size > 0:
                        return float(np.median(widths))

            # 无 bounds 时使用 points 的相邻差分。
            points = np.asarray(coord.values, dtype=np.float64)
            if points.size < 2:
                raise ValueError("坐标点数不足，无法推断网格分辨率。")
            diffs = np.abs(np.diff(points))
            diffs = diffs[np.isfinite(diffs)]
            if diffs.size == 0:
                raise ValueError("坐标差分无有效值，无法推断网格分辨率。")
            return float(np.median(diffs))

        dy = _resolution_from_coord(y_coord)
        dx = _resolution_from_coord(x_coord)

        # 真经纬：度间距 → 米；投影米制（含维名重命名）保持原间距。
        if RoughnessCorrection._coords_are_geographic_degrees(data, y_coord, x_coord):
            lat_points = np.asarray(y_coord.values, dtype=np.float64)
            lat_points = lat_points[np.isfinite(lat_points)]
            lat0 = float(np.median(lat_points)) if lat_points.size else 0.0
            dy_m = np.deg2rad(dy) * EARTH_RADIUS_M
            dx_m = np.deg2rad(dx) * EARTH_RADIUS_M * np.cos(np.deg2rad(lat0))
            return float(np.mean([abs(dy_m), abs(dx_m)]))

        return float(np.mean([dy, dx]))

    def process(
        self,
        wind_speed: Union[np.ndarray, xr.DataArray],
        height_grid: Optional[np.ndarray] = None,
    ) -> Union[Tuple[np.ndarray, np.ndarray], Tuple[xr.DataArray, xr.DataArray]]:
        """
        对风速进行地形粗糙度订正和高度订正。

        参数
        ----------
        wind_speed : np.ndarray or xr.DataArray
            输入风速场。
            - 若为 `np.ndarray`，默认最后三个维度为 `(level, lat, lon)`；
              前导维度全部作为批次维处理。
            - 若为 `xr.DataArray`，先按 meteva_base 维度规范化后再计算。

        height_grid : np.ndarray or None
            风速层对应的高度网格，一维数组或三维数组：
            - 一维数组：表示所有点位共用的固定高度值
            - 三维数组：表示随空间变化的高度值
            当 `wind_speed` 为 `xr.DataArray` 且未显式提供该参数时，
            默认使用输入中的 `level` 坐标。
            当 `wind_speed` 为 `np.ndarray` 时，必须显式传入。

        返回值
        ----------
        ``(订正风速, hc_add)``
            - 订正风速：``u_out = max(u_RC + hc_add, 0)``；
            - ``hc_add``：高度订正附加项（截断前），与订正风速同型。
            输入为 np.ndarray 时二者均为 np.ndarray；
            输入为 xr.DataArray 时二者均为重组后的 DataArray
            （``hc_add.name='height_correction'``）。
        """
        template_da: Optional[xr.DataArray] = None

        # 处理输入数据类型
        if isinstance(wind_speed, xr.DataArray):
            template_da = meb.checkout_griddata(wind_speed)

            # 从DataArray中获取高度网格（如果未提供）
            if height_grid is None:
                height_grid = template_da.level.values.astype(np.float32)
            # DataArray 分支保持标准六维，不做 squeeze，避免 level 轴语义丢失
            wind_speed = np.asarray(template_da.values, dtype=np.float32)
            ndim = wind_speed.ndim
            axes = list(range(ndim))
            level_axis, lat_axis, lon_axis = 1, 4, 5
            n_levels = wind_speed.shape[level_axis]
            n_lat = wind_speed.shape[lat_axis]
            n_lon = wind_speed.shape[lon_axis]
        else:
            # 处理NumPy数组输入
            ndim = wind_speed.ndim
            if ndim == 2:
                wind_speed = np.asarray([wind_speed])
                ndim = wind_speed.ndim

            wind_speed = np.asarray(wind_speed, dtype=np.float32)
            axes = list(range(ndim))
            level_axis = axes[-3]
            lat_axis = axes[-2]
            lon_axis = axes[-1]
            n_levels = wind_speed.shape[level_axis]
            n_lat = wind_speed.shape[lat_axis]
            n_lon = wind_speed.shape[lon_axis]

        if height_grid is None:
            raise ValueError("height_grid 不能为空：NumPy输入必须显式传入高度网格。")

        height_grid = np.asarray(height_grid, dtype=np.float32)

        # 检查辅助数据的空间维度是否匹配
        expected_spatial = (n_lat, n_lon)
        if self.a_over_s.shape != expected_spatial:
            raise ValueError(f"a_over_s 形状 {self.a_over_s.shape} 与预期 {expected_spatial} 不匹配")
        if self.sigma.shape != expected_spatial:
            raise ValueError(f"sigma 形状 {self.sigma.shape} 与预期 {expected_spatial} 不匹配")
        if self.pporo.shape != expected_spatial:
            raise ValueError(f"pporo 形状 {self.pporo.shape} 与预期 {expected_spatial} 不匹配")
        if self.modoro.shape != expected_spatial:
            raise ValueError(f"modoro 形状 {self.modoro.shape} 与预期 {expected_spatial} 不匹配")
        if self.z0 is not None and self.z0.shape != expected_spatial:
            raise ValueError(f"z0 形状 {self.z0.shape} 与预期 {expected_spatial} 不匹配")

        # 准备高度网格用于核心订正例程
        if height_grid.ndim == 1:
            # 检查一维高度网格长度是否与高度层数匹配
            if height_grid.shape[0] != n_levels:
                raise ValueError(f"一维高度网格长度 {height_grid.shape[0]} 与高度层数 {n_levels} 不匹配")
            hgrid_for_rc = height_grid  # 保持一维，后续会自动广播
        elif height_grid.ndim == 3:
            # 检查三维高度网格形状是否匹配
            if height_grid.shape != (n_levels, n_lat, n_lon):
                raise ValueError(f"三维高度网格形状 {height_grid.shape} 与预期 ({n_levels}, {n_lat}, {n_lon}) 不匹配")
            # 转置为 (lat, lon, levels) 格式，以适应核心订正例程
            hgrid_for_rc = np.transpose(height_grid, (1, 2, 0))
        else:
            # 高度网格必须是一维或三维
            raise ValueError(f"height_grid 必须是一维或三维，当前维度为 {height_grid.ndim}")

        # 识别批量维度并重新排序为 (batch..., levels, lat, lon)
        batch_axes = [i for i in axes if i not in (level_axis, lat_axis, lon_axis)]
        new_order = batch_axes + [level_axis, lat_axis, lon_axis]
        wind_t = np.transpose(wind_speed, new_order)

        # 展平批量维度
        batch_shape = [wind_t.shape[i] for i in range(len(batch_axes))]
        total_batch = int(np.prod(batch_shape))
        wind_2d = wind_t.reshape((total_batch, n_levels, n_lat, n_lon))

        # 创建粗糙度订正工具实例
        rc_utils = RoughnessCorrectionUtilities(
            self.a_over_s, self.sigma, self.z0,
            self.pporo, self.modoro,
            self.ppres, self.modres,
            absolute_correction_tol=self.absolute_correction_tol,
            href_scale=self.href_scale,
            dx_max_factor=self.dx_max_factor,
            dx_min_factor=self.dx_min_factor,
        )

        # 初始化输出数组
        out_2d = np.zeros_like(wind_2d, dtype=np.float32)
        hc_2d = np.zeros_like(wind_2d, dtype=np.float32)

        # 处理每个批量元素
        for i in range(total_batch):
            u_slice = wind_2d[i]  # (levels, lat, lon)
            # 转置为 (lat, lon, levels) 格式，以适应核心订正例程
            u_3d = np.transpose(u_slice, (1, 2, 0))
            # 执行粗糙度订正和高度订正
            result_3d, hc_3d = rc_utils.do_rc_hc_all(hgrid_for_rc, u_3d)
            # 转回 (levels, lat, lon) 格式
            out_2d[i] = np.transpose(result_3d, (2, 0, 1))
            hc_2d[i] = np.transpose(hc_3d, (2, 0, 1))

        # 恢复批量维度的原始形状
        out_t = out_2d.reshape(wind_t.shape)
        hc_t = hc_2d.reshape(wind_t.shape)

        # 反转转置，恢复原始维度顺序
        inv_order = [new_order.index(i) for i in axes]
        output = np.transpose(out_t, inv_order)
        hc_output = np.transpose(hc_t, inv_order)

        if template_da is not None:
            result_da = rebuild_to_meb_griddata(
                output,
                template_da,
                name=template_da.name,
                units=template_da.attrs.get("units"),
            )
            # 保留 standard_name=wind_speed 的语义，同时补充处理后变量的可读描述。
            result_da.attrs["long_name"] = "downscaled wind speed"
            hc_da = rebuild_to_meb_griddata(
                hc_output,
                template_da,
                name="height_correction",
                units=template_da.attrs.get("units"),
            )
            hc_da.attrs["long_name"] = "orographic height correction"
            return result_da, hc_da

        return output, hc_output
