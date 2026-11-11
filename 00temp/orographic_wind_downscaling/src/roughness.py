"""由高分辨率地形和模式地形计算订正使用的 sigma 与轮廓粗糙度。"""

from __future__ import annotations

from typing import Tuple

import numpy as np
import xarray as xr
from scipy.interpolate import griddata

from orographic_wind_downscaling.utils.base_plugin import BasePlugin


class RoughnessCalculation(BasePlugin):
    """计算 ``RoughnessCorrection`` 使用的网格单元高度标准差与轮廓粗糙度。

    输入是高分辨率地形和模式地形。模式格点的位置和格距从模式地形的经纬度读取。
    对每个模式格点，取以其为中心、边长等于模式格距/高分辨率格距（例如 0.2°/0.01° → 20）的窗口。
    窗口必须完整落在高分辨率网格内且高度全部有效，否则该模式格点缺测。
    sigma 是窗口内高度的总体标准差。a/s 是窗口内东西、南北截面上升段高度增量除以截面长度后的平均。
    缺测的模式格点先在模式网格上由周围完整格点线性填补，再插到高分辨率网格。
    模式地形必须处在模式网格上，不能是已经插到高分辨率网格的场。
    """

    # 1 度约等于 R*π/180，R=6371 km
    METRES_PER_DEGREE = 111195.0

    def process(
        self,
        orography: xr.DataArray,
        model_orography: xr.DataArray,
    ) -> Tuple[xr.DataArray, xr.DataArray]:
        """计算模式格点内高度标准差和轮廓粗糙度。

        参数
        ----------
        orography :
            高分辨率地形高度（米），带 ``lat``、``lon``。
        model_orography :
            模式网格上的地形高度（米），带 ``lat``、``lon``。只用它的网格，不用高度值。

        返回
        -------
        sigma, a_over_s
            与高分辨率地形同网格。sigma 单位米，a/s 无量纲。
        """
        values, lat_1d, lon_1d, template = self._spatial_field(orography)
        model_lat, model_lon = self._axis_coords(model_orography)
        sigma = self.cell_height_std(values, lat_1d, lon_1d, model_lat, model_lon)
        a_over_s = self.cell_silhouette(values, lat_1d, lon_1d, model_lat, model_lon)
        return (
            self._like(template, sigma, "standard_deviation_of_height_in_grid_cell", "m"),
            self._like(template, a_over_s, "silhouette_roughness", "1"),
        )

    @staticmethod
    def window_size(lat: np.ndarray, lon: np.ndarray, model_lat: np.ndarray, model_lon: np.ndarray) -> Tuple[int, int]:
        """中心窗口的纬向、经向边长（高分辨率格点数）。"""
        nlat = int(round(float(np.median(np.diff(model_lat))) / float(np.median(np.diff(lat)))))
        nlon = int(round(float(np.median(np.diff(model_lon))) / float(np.median(np.diff(lon)))))
        if nlat < 1 or nlon < 1:
            raise ValueError("模式格距须大于高分辨率格距，才能统计次网格起伏。")
        return nlat, nlon

    @staticmethod
    def nearest_indices(centers: np.ndarray, values: np.ndarray) -> np.ndarray:
        """每个 ``values`` 对应 ``centers`` 中最近的下标。"""
        idx = np.clip(np.searchsorted(centers, values, side="left"), 1, centers.size - 1)
        left = idx - 1
        closer_right = np.abs(values - centers[idx]) < np.abs(values - centers[left])
        return np.where(closer_right, idx, left)

    @classmethod
    def model_on_fine(
        cls,
        lat: np.ndarray,
        lon: np.ndarray,
        model_lat: np.ndarray,
        model_lon: np.ndarray,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """模式格点中心在高分辨率网格上的最近下标。"""
        return cls.nearest_indices(lat, model_lat), cls.nearest_indices(lon, model_lon)

    @staticmethod
    def window_slices(center: int, size: int, limit: int) -> Tuple[int, int] | None:
        """返回中心窗口 ``[start, end)``；越界则 ``None``。"""
        start = center - size // 2
        end = start + size
        if start < 0 or end > limit:
            return None
        return start, end

    @classmethod
    def cell_height_std(
        cls,
        height: np.ndarray,
        lat: np.ndarray,
        lon: np.ndarray,
        model_lat: np.ndarray,
        model_lon: np.ndarray,
    ) -> np.ndarray:
        """完整中心窗口内的高度标准差，填补后插到高分辨率网格。"""
        model_lat = np.asarray(model_lat, dtype=np.float64).reshape(-1)
        model_lon = np.asarray(model_lon, dtype=np.float64).reshape(-1)
        nlat_w, nlon_w = cls.window_size(lat, lon, model_lat, model_lon)
        iy, ix = cls.model_on_fine(lat, lon, model_lat, model_lon)
        sigma_cell = np.full((model_lat.size, model_lon.size), np.nan, dtype=np.float64)
        for i, i0 in enumerate(iy):
            ysl = cls.window_slices(int(i0), nlat_w, height.shape[0])
            if ysl is None:
                continue
            y0, y1 = ysl
            for j, j0 in enumerate(ix):
                xsl = cls.window_slices(int(j0), nlon_w, height.shape[1])
                if xsl is None:
                    continue
                x0, x1 = xsl
                block = height[y0:y1, x0:x1]
                if not np.isfinite(block).all():
                    continue
                sigma_cell[i, j] = float(np.std(block, dtype=np.float64))
        sigma_cell = cls.fill_model_field(sigma_cell, model_lat, model_lon)
        return cls.to_fine_grid(sigma_cell, model_lat, model_lon, lat, lon)

    @classmethod
    def cell_silhouette(
        cls,
        height: np.ndarray,
        lat: np.ndarray,
        lon: np.ndarray,
        model_lat: np.ndarray,
        model_lon: np.ndarray,
    ) -> np.ndarray:
        """完整中心窗口内的轮廓粗糙度，填补后插到高分辨率网格。"""
        model_lat = np.asarray(model_lat, dtype=np.float64).reshape(-1)
        model_lon = np.asarray(model_lon, dtype=np.float64).reshape(-1)
        nlat_w, nlon_w = cls.window_size(lat, lon, model_lat, model_lon)
        iy, ix = cls.model_on_fine(lat, lon, model_lat, model_lon)
        aos_cell = np.full((model_lat.size, model_lon.size), np.nan, dtype=np.float64)
        for i, i0 in enumerate(iy):
            ysl = cls.window_slices(int(i0), nlat_w, height.shape[0])
            if ysl is None:
                continue
            y0, y1 = ysl
            lat_win = lat[y0:y1]
            for j, j0 in enumerate(ix):
                xsl = cls.window_slices(int(j0), nlon_w, height.shape[1])
                if xsl is None:
                    continue
                x0, x1 = xsl
                block = height[y0:y1, x0:x1]
                if not np.isfinite(block).all():
                    continue
                lon_win = lon[x0:x1]
                aos_cell[i, j] = cls.window_silhouette(block, lat_win, lon_win)
        aos_cell = cls.fill_model_field(aos_cell, model_lat, model_lon)
        return cls.to_fine_grid(aos_cell, model_lat, model_lon, lat, lon)

    @classmethod
    def window_silhouette(cls, height: np.ndarray, lat: np.ndarray, lon: np.ndarray) -> float:
        """单个窗口的轮廓粗糙度：东西、南北上坡增量之和除以截面长度后平均。"""
        dh_x = np.diff(height, axis=1)
        dx = np.diff(lon) * cls.METRES_PER_DEGREE * np.cos(np.deg2rad(lat))[:, None]
        up_x = np.maximum(dh_x, 0.0).sum()
        len_x = float(np.broadcast_to(dx, dh_x.shape).sum())

        dh_y = np.diff(height, axis=0)
        dy = np.diff(lat)[:, None] * cls.METRES_PER_DEGREE
        up_y = np.maximum(dh_y, 0.0).sum()
        len_y = float(np.broadcast_to(dy, dh_y.shape).sum())

        ratios = []
        if len_x > 0:
            ratios.append(up_x / len_x)
        if len_y > 0:
            ratios.append(up_y / len_y)
        if not ratios:
            return np.nan
        return float(np.mean(ratios))

    @staticmethod
    def fill_model_field(
        field: np.ndarray,
        model_lat: np.ndarray,
        model_lon: np.ndarray,
    ) -> np.ndarray:
        """在模式网格上用周围有效格点线性填补缺测，凸包外用最近邻。"""
        field = np.asarray(field, dtype=np.float64)
        valid = np.isfinite(field)
        if valid.all() or not valid.any():
            return field.copy()
        yy, xx = np.meshgrid(model_lat, model_lon, indexing="ij")
        filled = griddata(
            (yy[valid], xx[valid]),
            field[valid],
            (yy, xx),
            method="linear",
        )
        still = ~np.isfinite(filled)
        if np.any(still):
            filled[still] = griddata(
                (yy[valid], xx[valid]),
                field[valid],
                (yy[still], xx[still]),
                method="nearest",
            )
        return filled

    @classmethod
    def to_fine_grid(
        cls,
        field: np.ndarray,
        model_lat: np.ndarray,
        model_lon: np.ndarray,
        lat: np.ndarray,
        lon: np.ndarray,
    ) -> np.ndarray:
        """把模式格点上的场线性插值到高分辨率网格，中心范围外取最近格点。"""
        field = np.asarray(field, dtype=np.float64)
        nlat_m, nlon_m = field.shape
        iy_raw = np.searchsorted(model_lat, lat, side="right") - 1
        ix_raw = np.searchsorted(model_lon, lon, side="right") - 1
        inside_lat = (lat >= model_lat[0]) & (lat <= model_lat[-1])
        inside_lon = (lon >= model_lon[0]) & (lon <= model_lon[-1])
        iy_near = cls.nearest_indices(model_lat, lat)
        ix_near = cls.nearest_indices(model_lon, lon)
        out = np.asarray(field[iy_near[:, None], ix_near[None, :]], dtype=np.float32)
        if not np.any(inside_lat) or not np.any(inside_lon):
            return out

        iy = np.minimum(np.maximum(iy_raw, 0), nlat_m - 2)
        ix = np.minimum(np.maximum(ix_raw, 0), nlon_m - 2)
        y0 = iy[inside_lat]
        y1 = y0 + 1
        wy = (lat[inside_lat] - model_lat[y0]) / (model_lat[y1] - model_lat[y0])
        x0 = ix[inside_lon]
        x1 = x0 + 1
        wx = (lon[inside_lon] - model_lon[x0]) / (model_lon[x1] - model_lon[x0])
        lat_idx = np.flatnonzero(inside_lat)
        lon_idx = np.flatnonzero(inside_lon)
        for start in range(0, lat_idx.size, 200):
            stop = start + 200
            wy_c = wy[start:stop][:, None]
            wx_c = wx[None, :]
            rows0 = y0[start:stop]
            rows1 = y1[start:stop]
            corners = (
                field[np.ix_(rows0, x0)],
                field[np.ix_(rows0, x1)],
                field[np.ix_(rows1, x0)],
                field[np.ix_(rows1, x1)],
            )
            weights = (
                (1.0 - wy_c) * (1.0 - wx_c),
                (1.0 - wy_c) * wx_c,
                wy_c * (1.0 - wx_c),
                wy_c * wx_c,
            )
            acc = np.zeros(corners[0].shape, dtype=np.float64)
            wsum = np.zeros(corners[0].shape, dtype=np.float64)
            for value, weight in zip(corners, weights):
                finite = np.isfinite(value)
                acc += np.where(finite, value * weight, 0.0)
                wsum += np.where(finite, weight, 0.0)
            block = np.divide(acc, wsum, out=np.full(corners[0].shape, np.nan), where=wsum > 0)
            out[np.ix_(lat_idx[start:stop], lon_idx)] = block
        return out

    @staticmethod
    def _axis_coords(field: xr.DataArray) -> Tuple[np.ndarray, np.ndarray]:
        if not isinstance(field, xr.DataArray):
            raise TypeError("地形须为带 lat/lon 的 DataArray。")
        if "lat" not in field.coords or "lon" not in field.coords:
            raise ValueError("地形场必须带 lat、lon 坐标。")
        lat = np.asarray(field.lat.values, dtype=np.float64)
        lon = np.asarray(field.lon.values, dtype=np.float64)
        if lat.ndim != 1 or lon.ndim != 1:
            raise ValueError("lat/lon 须为一维坐标。")
        return lat, lon

    @staticmethod
    def _spatial_field(
        orography: xr.DataArray,
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray, xr.DataArray]:
        if not isinstance(orography, xr.DataArray):
            raise TypeError("高分辨率地形须为带 lat/lon 的 DataArray。")
        drop = [dim for dim in orography.dims if dim not in ("lat", "lon") and orography.sizes[dim] == 1]
        spatial = orography.squeeze(drop, drop=True) if drop else orography
        if spatial.ndim != 2 or set(spatial.dims) != {"lat", "lon"}:
            raise ValueError("orography 压缩后必须是带 lat/lon 的二维场。")
        spatial = spatial.transpose("lat", "lon")
        lat_1d = np.asarray(spatial.lat.values, dtype=np.float64)
        lon_1d = np.asarray(spatial.lon.values, dtype=np.float64)
        if lat_1d.size < 2 or lon_1d.size < 2 or np.any(np.diff(lat_1d) <= 0) or np.any(np.diff(lon_1d) <= 0):
            raise ValueError("高分辨率 lat/lon 至少两个点，且必须严格递增。")
        values = np.asarray(spatial.values, dtype=np.float64)
        return values, lat_1d, lon_1d, orography

    @staticmethod
    def _like(template: xr.DataArray, values: np.ndarray, name: str, units: str) -> xr.DataArray:
        filled = np.asarray(values, dtype=np.float32)
        if template.ndim != 2:
            filled = np.broadcast_to(filled, template.shape).copy()
        out = template.copy(data=filled)
        out.name = name
        out.attrs["units"] = units
        return out
