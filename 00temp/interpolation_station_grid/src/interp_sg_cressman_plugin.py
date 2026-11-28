# -*- coding: utf-8 -*-
"""站点→格点 Cressman 插件 ``InterpSgCressman``。

接口：``process(sta, grid=None, background=None)``（与 station_grid 同形）。

- ``reprocess=False``：公里半径最初版（绝对值加权替换）；须 ``grid``（或由 ``background`` 取网格）。
- ``reprocess=True``：度制差值累加再处理；须 ``background``（``grid`` 可不传）。

算法核为类内私有方法，对外只导出本插件类与默认半径常量。
"""
from __future__ import annotations

import copy
import math
import os
import sys
from typing import Any, Optional, Sequence

import meteva_base as meb
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

from utils.base_plugin import PostProcessingPlugin


def _ensure_interpolation_grid_grid_on_path() -> None:
    """将同级 ``interpolation_grid_grid`` 的根与 ``src`` 追加到 sys.path。"""
    here = os.path.dirname(os.path.abspath(__file__))
    temp_root = os.path.normpath(os.path.join(here, "..", ".."))
    gg_root = os.path.join(temp_root, "interpolation_grid_grid")
    gg_src = os.path.join(gg_root, "src")
    for p in (gg_root, gg_src):
        if os.path.isdir(p) and p not in sys.path:
            sys.path.append(p)


_ensure_interpolation_grid_grid_on_path()

from interp_gg_linear_plugin import InterpGgLinear  # noqa: E402

# 度→千米近似（创新量扫里把度制半径换成 _absolute_km 使用的千米半径）
_KM_PER_DEG = float(getattr(meb.basicdata.const, "ER", 6371.229)) * math.pi / 180.0
# 创新量路径统一背景/站点时间维，避免与站点真时间轴纠缠
_SAFE_TIME = pd.Timestamp("2000-01-01 00:00:00")

DEFAULT_R_LIST_KM = (60.0, 40.0, 20.0)  # reprocess=False，单位千米
DEFAULT_R_LIST_DEG = (1.0, 0.8, 0.6, 0.4)  # reprocess=True


class InterpSgCressman(PostProcessingPlugin):
    """站点→格点 Cressman。

    - ``reprocess=False``：``_absolute_km``；``r_list`` 为公里。
    - ``reprocess=True``：``_innov_accum``；``r_list`` 为度，须 ``background``。

    Parameters
    ----------
    r_list :
        影响半径列表。``None`` 时按 ``reprocess`` 选用默认：
        ``reprocess=False`` 为 ``(60.0, 40.0, 20.0)``（千米，``DEFAULT_R_LIST_KM``），
        ``reprocess=True`` 为 ``(1.0, 0.8, 0.6, 0.4)``（度，``DEFAULT_R_LIST_DEG``）。
    nearNum :
        近邻站点数上限。
    outer_value :
        False 路径背景对齐越界填充。
    reprocess :
        是否走差值累加。
    rain_limit, num_limit, smooth, power_param, r_km_scale, innov_gain,
    residual_passes, residual_degree_polish, residual_polish_rounds,
    degree_blend, station_anchor_radius, station_anchor_strength :
        仅 ``reprocess=True`` 生效。
    """

    def __init__(
        self,
        r_list: Optional[Sequence[float]] = None,
        nearNum: int = 100,
        outer_value=None,
        reprocess: Any = False,
        rain_limit=None,
        num_limit: float = 1.0,
        smooth: float = 0.001,
        power_param: float = 2.0,
        r_km_scale: float = 1.35,
        innov_gain: float = 1.0,
        residual_passes: int = 0,
        residual_degree_polish: bool = True,
        residual_polish_rounds: int = 1,
        degree_blend: float = 0.85,
        station_anchor_radius: float = 0.35,
        station_anchor_strength: float = 0.0,
    ):
        if int(nearNum) < 1:
            raise ValueError("nearNum 必须 >= 1")
        self.reprocess = self._as_bool(reprocess, False)
        if r_list is not None:
            radii = [float(r) for r in r_list]
            if not radii:
                raise ValueError("r_list 不能为空")
            for r in radii:
                if r <= 0:
                    raise ValueError("r_list 中半径必须大于 0")
            self.r_list = radii
        else:
            self.r_list = None
        self.nearNum = int(nearNum)
        self.outer_value = outer_value
        self.rain_limit = rain_limit
        self.num_limit = float(num_limit)
        self.smooth = float(smooth)
        self.power_param = float(power_param)
        self.r_km_scale = float(r_km_scale)
        self.innov_gain = float(innov_gain)
        self.residual_passes = int(residual_passes)
        self.residual_degree_polish = self._as_bool(residual_degree_polish, True)
        self.residual_polish_rounds = int(residual_polish_rounds)
        self.degree_blend = float(degree_blend)
        self.station_anchor_radius = float(station_anchor_radius)
        self.station_anchor_strength = float(station_anchor_strength)

    @staticmethod
    def _as_bool(value: Any, default: bool = False) -> bool:
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        text = str(value).strip().lower()
        if text in ("1", "true", "yes", "y", "on"):
            return True
        if text in ("0", "false", "no", "n", "off", ""):
            return False
        return bool(value)

    def _absolute_km(self, sta, grid, r_list, background=None, nearNum=None, outer_value=None):
        """km 核：站点绝对值 Cressman 加权替换。

        - 按 member/level/time/dtime 切片；每片用该片站点的时间维建 ``grid2``（输出网格信息）。
        - 背景作初场（无则 0）；仅对最近站距离 ``< R`` 的格点用站点加权平均覆盖。
        - 插值列取表末列 ``sta.values[:, -1]``（多要素时只插最后一列）。
        - 亦被创新量扫复用：传入创新量表时末列即为 Δ。
        """
        nearNum = self.nearNum if nearNum is None else int(nearNum)
        outer_value = self.outer_value if outer_value is None else outer_value
        sta1 = meb.sele_by_para(sta, drop_IV=True)
        sta_list = meb.split(sta1, ["member", "level", "time", "dtime"])
        grd_list = []
        for sta_slice in sta_list:
            # 要素名列表可能多于 1；grid 元数据可带多名，插值仍只用末列
            data_name = meb.get_stadata_names(sta_slice)
            index0 = sta_slice.index[0]
            # grid2：本切片输出场网格（水平取自入参 grid，时间/层次/要素名取自站点切片）
            grid2 = meb.basicdata.grid(
                grid.glon,
                grid.glat,
                [sta_slice.loc[index0, "time"]],
                [sta_slice.loc[index0, "dtime"]],
                [sta_slice.loc[index0, "level"]],
                data_name,
            )
            xyz_sta = meb.tool.math_tools.lon_lat_to_cartesian(
                sta_slice["lon"].values,
                sta_slice["lat"].values,
                R=meb.basicdata.const.ER,
            )
            lon = np.arange(grid2.nlon) * grid2.dlon + grid2.slon
            lat = np.arange(grid2.nlat) * grid2.dlat + grid2.slat
            grid_lon, grid_lat = np.meshgrid(lon, lat)
            xyz_grid = meb.tool.math_tools.lon_lat_to_cartesian(
                grid_lon.flatten(),
                grid_lat.flatten(),
                R=meb.basicdata.const.ER,
            )
            tree = cKDTree(xyz_sta)
            nsta = len(sta_slice.index)
            k_near = nearNum if nearNum <= nsta else nsta
            d, inds = tree.query(xyz_grid, k=k_near)
            d = np.asarray(d, dtype=float) + 1e-6
            inds = np.asarray(inds)

            # 初场：无背景则全 0；有背景则对齐到 grid2（远点保留初场）
            bg = meb.basicdata.grid_data(grid2)
            if background is not None:
                bg_interp = InterpGgLinear(outer_value=outer_value).process(background, grid2)
                if bg_interp is not None:
                    bg = bg_interp

            bg_dat = np.asarray(bg.values, dtype=float).flatten()
            input_dat = sta_slice.values[:, -1]  # 与包内其它插件一致：末列

            if d.ndim == 1:
                d = d[:, np.newaxis]
                inds = inds[:, np.newaxis]

            # 多圈：大半径→小半径；圈内格点写为 Cressman 加权平均（覆盖初场）
            d2 = d ** 2
            for R in r_list:
                index_in = np.where(d[:, 0] < R)[0]
                if len(index_in) == 0:
                    continue
                inds_in = inds[index_in, :]
                r2 = R ** 2
                d2_in = d2[index_in, :]
                w = (r2 - d2_in) / (r2 + d2_in)
                w[w < 0] = 0
                w_sum = np.sum(w, axis=1)
                valid = w_sum > 0
                if not np.any(valid):
                    continue
                idx_valid = index_in[valid]
                dat = np.sum(w[valid] * input_dat[inds_in[valid]], axis=1) / w_sum[valid]
                bg_dat[idx_valid] = dat[:]

            grd = meb.basicdata.grid_data(grid2, bg_dat)
            grd.name = data_name[0]
            grd_list.append(grd)

        grd_all = meb.concat(grd_list)
        grd_all.attrs = copy.deepcopy(sta.attrs)
        return grd_all

    @staticmethod
    def _bg_idw_at_stations(cur, lon, lat, sta_lon, sta_lat, r_deg, dlon, smooth=0.001, power_param=2.0):
        """站上 IDW 取背景（创新量扫 / 度制一步共用）。"""
        lon = np.asarray(lon, float)
        lat = np.asarray(lat, float)
        dlon = float(dlon)
        nlat, nlon = cur.shape
        r_deg = float(r_deg)
        r2 = r_deg * r_deg
        influence = max(int(r_deg / dlon), 0)
        start_lon, start_lat = float(lon[0]), float(lat[0])
        out = np.empty(len(sta_lon), dtype=float)
        for n, (x, y) in enumerate(zip(sta_lon, sta_lat)):
            i0 = int((x + 1e-5 - start_lon) / dlon)
            j0 = int((y + 1e-5 - start_lat) / dlon)
            i1, i2 = max(i0 - influence, 0), min(i0 + influence, nlon - 1)
            j1, j2 = max(j0 - influence, 0), min(j0 + influence, nlat - 1)
            sub = cur[j1 : j2 + 1, i1 : i2 + 1]
            dlon_v = lon[i1 : i2 + 1] - x
            dlat_v = lat[j1 : j2 + 1][:, np.newaxis] - y
            dist_sq = dlon_v ** 2 + dlat_v ** 2
            m = dist_sq <= r2
            if not np.any(m):
                out[n] = np.nan
                continue
            dist = np.sqrt(dist_sq[m])
            w = 1.0 / ((dist + smooth) ** power_param)
            ws = float(np.sum(w))
            out[n] = float(np.sum(w * sub[m]) / ws) if ws >= 1e-5 else np.nan
        return out

    def _gressman_one_step(
        self,
        cur,
        lon,
        lat,
        sta_lon,
        sta_lat,
        sta_val,
        r_deg,
        dlon,
        num_limit=None,
        smooth=None,
        power_param=None,
        rain_limit=None,
    ):
        """度制 GressMan 一步（polish / blend）。"""
        if num_limit is None:
            num_limit = self.num_limit
        if smooth is None:
            smooth = self.smooth
        if power_param is None:
            power_param = self.power_param
        if rain_limit is None:
            rain_limit = self.rain_limit

        lon = np.asarray(lon, float)
        lat = np.asarray(lat, float)
        dlon = float(dlon)
        nlat, nlon = cur.shape
        r_deg = float(r_deg)
        r2 = r_deg * r_deg
        influence = max(int(r_deg / dlon), 0)
        start_lon = float(lon[0])

        bg_sta = self._bg_idw_at_stations(
            cur, lon, lat, sta_lon, sta_lat, r_deg, dlon, smooth, power_param
        )
        innov = np.asarray(sta_val, float) - np.where(
            np.isnan(bg_sta), np.asarray(sta_val, float), bg_sta
        )

        acc_w_val = np.zeros_like(cur)
        acc_w = np.zeros_like(cur)
        acc_n = np.zeros_like(cur)

        for n in range(len(sta_lon)):
            i0 = int((sta_lon[n] - start_lon) / dlon)
            j0 = int((sta_lat[n] - float(lat[0])) / dlon)
            i1, i2 = max(i0 - influence, 0), min(i0 + influence, nlon - 1)
            j1, j2 = max(j0 - influence, 0), min(j0 + influence, nlat - 1)
            if i1 > i2 or j1 > j2:
                continue
            dlon_v = lon[i1 : i2 + 1] - sta_lon[n]
            dlat_v = lat[j1 : j2 + 1][:, np.newaxis] - sta_lat[n]
            dist_sq = dlon_v ** 2 + dlat_v ** 2
            m = dist_sq <= r2
            if not np.any(m):
                continue
            dist = np.sqrt(dist_sq[m])
            w = 1.0 / ((dist + smooth) ** power_param)
            acc_w_val[j1 : j2 + 1, i1 : i2 + 1][m] += w * innov[n]
            acc_w[j1 : j2 + 1, i1 : i2 + 1][m] += w
            acc_n[j1 : j2 + 1, i1 : i2 + 1][m] += 1.0

        with np.errstate(divide="ignore", invalid="ignore"):
            blended = np.where(acc_w >= 1e-5, acc_w_val / acc_w + cur, cur)
        if rain_limit is not None:
            blended = np.where(blended <= float(rain_limit), cur, blended)
        return np.where((acc_w >= 1e-5) & (acc_n >= float(num_limit)), blended, cur)

    def _innov_one_sweep(
        self,
        radii,
        field,
        lon,
        lat,
        sta_lon,
        sta_lat,
        sta_val,
        sta_work,
        grid,
        dlon,
        k_near,
        scale,
        gain,
    ):
        """按半径列表扫创新量并累加到场上（主扫 / residual）。

        每圈：站上取当前场 → 算 Δ=obs−bg_sta → 用 ``_absolute_km`` 把 Δ 铺到格点
        → 仅在度制影响圆内 ``field += gain * Δ``。
        """
        smooth = self.smooth
        power_param = self.power_param
        num_limit = self.num_limit
        rain_limit = self.rain_limit
        nsta = int(len(sta_work))

        for r in radii:
            bg_sta = self._bg_idw_at_stations(
                field, lon, lat, sta_lon, sta_lat, r, dlon, smooth=smooth, power_param=power_param
            )
            bg_sta = np.where(np.isnan(bg_sta), sta_val, bg_sta)
            # 内部表末列约定为 data0；写入创新量后再交给 _absolute_km（读末列）
            innov_sta = sta_work.copy()
            innov_sta["data0"] = sta_val - bg_sta
            # 度制半径 → 千米，复用 km 绝对值核铺 Δ（无背景初场）
            grd_inc = self._absolute_km(
                innov_sta,
                grid,
                r_list=[float(r) * _KM_PER_DEG * scale],
                background=None,
                nearNum=k_near,
            )
            inc = np.asarray(
                grd_inc.values if hasattr(grd_inc, "values") else grd_inc.data,
                dtype=float,
            ).squeeze()

            # 度制影响圆掩膜（单站直接算，多站用最近站距离）
            lon_m = np.asarray(lon, float)
            lat_m = np.asarray(lat, float)
            slon = np.atleast_1d(np.asarray(sta_lon, float))
            slat = np.atleast_1d(np.asarray(sta_lat, float))
            lon2d, lat2d = np.meshgrid(lon_m, lat_m)
            if slon.size == 1:
                mask = (lon2d - slon[0]) ** 2 + (lat2d - slat[0]) ** 2 <= float(r) ** 2
            else:
                tree = cKDTree(np.column_stack([slon, slat]))
                pts = np.column_stack([lon2d.ravel(), lat2d.ravel()])
                dist, _ = tree.query(pts, k=1)
                mask = (dist <= float(r)).reshape(lon2d.shape)

            if float(num_limit) > 1.0 and nsta > 0:
                tree = cKDTree(np.column_stack([sta_lon, sta_lat]))
                lon2d, lat2d = np.meshgrid(lon, lat)
                pts = np.column_stack([lon2d.ravel(), lat2d.ravel()])
                n_near = tree.query_ball_point(pts, r=float(r), return_length=True)
                n_near = np.asarray(n_near, dtype=float).reshape(field.shape)
                mask = mask & (n_near >= float(num_limit))
            new = field + np.where(mask, gain * inc, 0.0)
            if rain_limit is not None:
                new = np.where(new <= float(rain_limit), field, new)
            field = new
        return field

    def _innov_accum(self, sta, grd, distance_limits):
        """差值累加再处理：在**背景场本网格**上扫创新量 + 度制 polish/blend。

        与 ``_absolute_km`` 不同：不另建目标 ``grid`` 扩域；输出域 = 背景域。
        ``distance_limits``（``r_list``）单位为度。
        """
        nearNum = self.nearNum
        residual_passes = self.residual_passes
        residual_degree_polish = self.residual_degree_polish
        residual_polish_rounds = self.residual_polish_rounds
        degree_blend = self.degree_blend
        station_anchor_radius = self.station_anchor_radius
        station_anchor_strength = self.station_anchor_strength
        rain_limit = self.rain_limit

        # 统一时间维，避免与站点时间轴不对齐
        grd_use = grd.copy()
        try:
            n_time = int(grd_use.sizes.get("time", len(np.atleast_1d(grd_use.time.values))))
        except Exception:
            n_time = 1
        grd_use = grd_use.assign_coords(time=("time", [_SAFE_TIME] * max(n_time, 1)))

        lon = np.asarray(grd_use.lon, float)
        lat = np.asarray(grd_use.lat, float)
        grid = (
            meb.get_grid_of_data(grd_use)
            if hasattr(meb, "get_grid_of_data")
            else meb.basicdata.get_grid_of_data(grd_use)
        )
        dlon = float(grid.dlon)
        # 格点压成 2D 初值（后续在 cur 上累加）
        bg0 = np.asarray(
            grd_use.values if hasattr(grd_use, "values") else grd_use.data, dtype=float
        ).squeeze().copy()
        cur = bg0.copy()

        # 内部站点表：固定 time/level/dtime 与背景对齐；末列统一为 data0 供扫半径写 Δ
        # 观测取值与 _absolute_km 一致用末列（不强制外部列名必须叫 data0）
        n_sta_raw = len(sta)
        sta_ids = (
            list(sta["id"]) if "id" in getattr(sta, "columns", []) else list(range(n_sta_raw))
        )
        sta_vals = np.asarray(sta.iloc[:, -1], float)
        sta_work = pd.DataFrame(
            {
                "level": [0] * n_sta_raw,
                "time": [_SAFE_TIME] * n_sta_raw,
                "dtime": [0] * n_sta_raw,
                "id": sta_ids,
                "lon": list(np.asarray(sta["lon"], float)),
                "lat": list(np.asarray(sta["lat"], float)),
                "data0": list(sta_vals),
            }
        )
        sta_lon = np.asarray(sta_work["lon"], float)
        sta_lat = np.asarray(sta_work["lat"], float)
        sta_val = np.asarray(sta_work["data0"], float)
        nsta = int(len(sta_work))
        if nsta == 0:
            return grd.copy()
        if nearNum is None:
            k_near = 8 if nsta <= 1 else min(100, nsta)
        else:
            k_near = max(1, min(int(nearNum), nsta))
        gain = float(self.innov_gain)
        scale = float(self.r_km_scale)
        n_extra = max(int(residual_passes), 0)
        n_polish = max(int(residual_polish_rounds), 1) if residual_degree_polish else 0
        blend = float(np.clip(degree_blend, 0.0, 1.0))

        if blend >= 1.0:
            # 纯度制 GressMan 路径：跳过前面的 km 核扫与 polish，避免无用计算
            cur = bg0.copy()
            for r in distance_limits:
                cur = self._gressman_one_step(
                    cur, lon, lat, sta_lon, sta_lat, sta_val, r, dlon
                )
        else:
            sweep_args = (lon, lat, sta_lon, sta_lat, sta_val, sta_work, grid, dlon, k_near, scale, gain)
            cur = self._innov_one_sweep(distance_limits, cur, *sweep_args)
            for _ in range(n_extra):
                small = list(distance_limits[-2:]) if len(distance_limits) >= 2 else list(distance_limits)
                cur = self._innov_one_sweep(small, cur, *sweep_args)

            for _ in range(n_polish):
                for r in distance_limits:
                    cur = self._gressman_one_step(
                        cur, lon, lat, sta_lon, sta_lat, sta_val, r, dlon
                    )

            if blend > 0.0:
                deg = bg0.copy()
                for r in distance_limits:
                    deg = self._gressman_one_step(
                        deg, lon, lat, sta_lon, sta_lat, sta_val, r, dlon
                    )
                cur = (1.0 - blend) * cur + blend * deg

        # 可选：站点锚定（向观测值局部拉近）
        if float(station_anchor_strength) > 0.0 and len(sta_lon) > 0:
            lon2d, lat2d = np.meshgrid(np.asarray(lon, float), np.asarray(lat, float))
            r2 = float(station_anchor_radius) ** 2
            s = float(np.clip(station_anchor_strength, 0.0, 1.0))
            for x, y, v in zip(sta_lon, sta_lat, sta_val):
                d2 = (lon2d - x) ** 2 + (lat2d - y) ** 2
                w = np.clip(1.0 - d2 / r2, 0.0, 1.0) * s
                cur = cur * (1.0 - w) + float(v) * w

        if rain_limit is not None:
            cur = np.where(cur <= float(rain_limit), bg0, cur)

        out = grd.copy()
        out.data = [[[[cur]]]]
        return out

    def process(self, sta, grid=None, background=None):
        """站点→格点 Cressman：校验参数后分派核。

        Args:
            sta: 站点数据。
            grid: 目标网格信息；``reprocess=False`` 时须给出，或可由 ``background`` 取网格。
            background: 背景场；``reprocess=True`` 时必需（在本场上累加）；
                ``False`` 时可选作初场。

        Returns:
            订正后的格点场。
        """
        # False：绝对值 km 核（可扩到 grid；背景仅作初场）
        if not self.reprocess:
            if grid is None:
                if background is None:
                    raise ValueError(
                        "reprocess=false 时须提供 grid，或提供 background 以取网格"
                    )
                g0 = (
                    meb.get_grid_of_data(background)
                    if hasattr(meb, "get_grid_of_data")
                    else meb.basicdata.get_grid_of_data(background)
                )
                grid = meb.basicdata.grid(g0.glon, g0.glat)
            radii = (
                list(self.r_list) if self.r_list is not None else list(DEFAULT_R_LIST_KM)
            )
            return self._absolute_km(sta, grid, r_list=radii, background=background)

        # True：创新量累加（锁在 background 网格上；忽略独立扩域 grid）
        if background is None:
            raise ValueError("reprocess=true 时必须提供 background 格点场")
        radii = (
            list(self.r_list) if self.r_list is not None else list(DEFAULT_R_LIST_DEG)
        )
        return self._innov_accum(sta, background, radii)


__all__ = [
    "InterpSgCressman",
    "DEFAULT_R_LIST_KM",
    "DEFAULT_R_LIST_DEG",
]
