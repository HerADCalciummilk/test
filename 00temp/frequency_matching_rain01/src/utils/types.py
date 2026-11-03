# -*- coding: utf-8 -*-
"""
数据容器与 I/O（``src/utils/types.py``）。

经根目录 ``utils`` 包路径合并后导入：``from utils.types import GridData, ScatterData``。

约定
----
- 格点 ``GridData.val`` 布局为 ``[y, x]``（纬度维在前）。
- ``ScatterData``：站点集合，支持 Micaps3 / 站表读写与格点双线性取样。
- ``GridData``：规则经纬网格，支持 Micaps4/NC/二进制、平滑、掩膜、``mesh_val`` 重采样。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Iterable
import math
import random
import numpy as np
import meteva.base as meb
import xarray as xr


class FileFlag(str, Enum):
    """读写文件类型标记。"""

    M3 = "m3"
    M4 = "m4"
    M14 = "m14"
    CYBIN = "cybin"
    AWX = "awx"
    LATLON = "latlon"
    ARGRASTER = "argraster"
    STAINFO = "stainfo"
    STADATA = "stadata"


@dataclass
class PointData:
    """单站点：站号、经纬度、降水值。"""

    id: str
    lon: float
    lat: float
    val: float = 0.0

    def copy(self) -> "PointData":
        return PointData(self.id, self.lon, self.lat, self.val)


@dataclass
class LineData:
    """折线/多边形顶点序列，用于 ``frame_by_line`` 空间裁剪。"""

    point_lon: list[float]
    point_lat: list[float]
    line_value: float = 0.0

    @property
    def point_num(self) -> int:
        return len(self.point_lon)


class ScatterData:
    """站点场：由站表文件、Micaps3 或 ``PointData`` 列表构造。"""

    def __init__(
        self,
        source: str | Path | Iterable[PointData],
        file_flag: FileFlag | None = None,
    ):
        if isinstance(source, (str, Path)):
            self.sta_data = self._read_file(Path(source), file_flag or FileFlag.M3)
        else:
            # 按站号去重，保留首次出现
            dedup: dict[str, PointData] = {}
            for p in source:
                dedup.setdefault(p.id, p.copy())
            self.sta_data = list(dedup.values())

    def _read_file(self, path: Path, file_flag: FileFlag) -> list[PointData]:
        result: list[PointData] = []
        seen: set[str] = set()
        for line in path.read_text(encoding="gb2312", errors="ignore").splitlines():
            parts = line.split()
            if file_flag == FileFlag.STAINFO and len(parts) >= 3:
                pid, lon, lat = parts[:3]
                if pid not in seen:
                    result.append(PointData(pid.strip(), float(lon), float(lat), 0.0))
                    seen.add(pid)
            elif file_flag == FileFlag.STADATA and len(parts) >= 4:
                pid, lon, lat, val = parts[:4]
                if pid not in seen:
                    result.append(
                        PointData(pid.strip(), float(lon), float(lat), float(val))
                    )
                    seen.add(pid)
            elif file_flag == FileFlag.M3 and len(parts) == 5:
                pid, lon, lat, _, val = parts
                if pid not in seen:
                    result.append(
                        PointData(pid.strip(), float(lon), float(lat), float(val))
                    )
                    seen.add(pid)
        return result

    @property
    def length(self) -> int:
        return len(self.sta_data)

    def copy_scatter_data(self) -> "ScatterData":
        return ScatterData(self.sta_data)

    def _id_lookup(self) -> dict[str, PointData]:
        return {p.id: p for p in self.sta_data}

    def _lon_lat_arrays(self) -> tuple[np.ndarray, np.ndarray]:
        lon = np.fromiter(
            (p.lon for p in self.sta_data), dtype=float, count=len(self.sta_data)
        )
        lat = np.fromiter(
            (p.lat for p in self.sta_data), dtype=float, count=len(self.sta_data)
        )
        return lon, lat

    def read_val_from_micaps3(self, path: str | Path) -> None:
        """按站号匹配，从 Micaps3 更新本对象各站 ``val``（站表几何不变）。"""
        lookup = self._id_lookup()
        for line in (
            Path(path).read_text(encoding="gb2312", errors="ignore").splitlines()
        ):
            parts = line.split()
            if len(parts) == 5:
                item = lookup.get(parts[0])
                if item is not None:
                    item.val = float(parts[4])

    def read_from_scatter_data(self, other: "ScatterData") -> None:
        """按站号从另一站点场拷贝数值。"""
        lookup = self._id_lookup()
        for item in other.sta_data:
            target = lookup.get(item.id)
            if target is not None:
                target.val = item.val

    def clear_to_num(self, number: float) -> None:
        for p in self.sta_data:
            p.val = number

    def clear_to_num_less_than(self, number: float, number_limit: float) -> None:
        for p in self.sta_data:
            if p.val < number_limit:
                p.val = number

    def clear_to_num_greater_than(self, number: float, number_limit: float) -> None:
        for p in self.sta_data:
            if p.val >= number_limit:
                p.val = number

    def frame_by_rect(
        self, left: float, right: float, bottom: float, top: float
    ) -> "ScatterData":
        return ScatterData(
            [
                p
                for p in self.sta_data
                if left <= p.lon < right and bottom <= p.lat < top
            ]
        )

    def frame_by_line(self, line: LineData) -> "ScatterData":
        """保留落在多边形 ``line`` 内的站点，返回新 ``ScatterData``。"""
        lon, lat = self._lon_lat_arrays()
        mask = points_in_polygon(
            lon,
            lat,
            np.asarray(line.point_lon, dtype=float),
            np.asarray(line.point_lat, dtype=float),
        )
        return ScatterData([self.sta_data[i] for i in np.nonzero(mask)[0]])

    def bilinear_interpolation_from_grid_data(
        self, grid: "GridData", undef: float = 0.0
    ) -> None:
        """各站从格点双线性取样，写回 ``sta_data[].val``。"""
        lon, lat = self._lon_lat_arrays()
        vals = grid.interpolate_points(lon, lat, undef)
        for p, v in zip(self.sta_data, vals):
            p.val = float(v)

    def writer_to_micaps3(self, path: str | Path, header: str) -> None:
        """写出 Micaps3 站点文件（含给定文件头）。"""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("w", encoding="gb2312", errors="ignore") as f:
            f.write(header + "\n")
            f.write(f"  1    {len(self.sta_data):8d}\n")
            for item in self.sta_data:
                f.write(
                    f"{item.id:>8}  {item.lon:8.2f}  {item.lat:8.2f}  {0.0:8.2f}  {item.val:8.2f}\n"
                )


class GridData:
    """
    规则经纬网格降水/风场。

    构造方式：
    - ``GridData(path)``：从 Micaps4/NC 等读入；
    - ``GridData(lon0, lon1, lat0, lat1, dlon, dlat)``：空场初始化。

    ``val`` 形状 ``(yn, xn)``，与 ``lat``/``lon`` 一维坐标对应。
    """

    def __init__(self, *args, file_flag: FileFlag | None = None):
        if len(args) == 1 and isinstance(args[0], (str, Path)):
            self._read_micaps4(Path(args[0]))
        elif len(args) == 6:
            lon_start, lon_end, lat_start, lat_end, dlon, dlat = args
            self.lon_start = float(lon_start)
            self.lat_start = float(lat_start)
            self.dlon = float(dlon)
            self.dlat = float(dlat)
            self.xn = (
                int(round((float(lon_end) + 1e-5 - self.lon_start) / self.dlon)) + 1
            )
            self.yn = (
                int(round((float(lat_end) + 1e-5 - self.lat_start) / self.dlat)) + 1
            )
            self.lon = self.lon_start + np.arange(self.xn, dtype=float) * self.dlon
            self.lat = self.lat_start + np.arange(self.yn, dtype=float) * self.dlat
            # Convention: self.val is always shaped as [yn, xn]
            self.val = np.zeros((self.yn, self.xn), dtype=float)
        else:
            raise TypeError("Unsupported GridData constructor")

    @property
    def lon_end(self) -> float:
        return float(self.lon[-1])

    @property
    def lat_end(self) -> float:
        return float(self.lat[-1])

    def _read_micaps4(self, path: Path) -> None:
        suffix = path.suffix.lower()
        try:
            if suffix == ".nc":
                grd = meb.read_griddata_from_nc(str(path))
            else:
                grd = meb.read_griddata_from_micaps4(str(path))
            if grd is not None:
                lon = np.asarray(grd["lon"].values, dtype=float)
                lat = np.asarray(grd["lat"].values, dtype=float)
                vals = np.asarray(grd.values, dtype=float).squeeze()
                if vals.ndim == 2:
                    self.lon_start = float(lon[0])
                    self.lat_start = float(lat[0])
                    self.dlon = float(abs(lon[1] - lon[0])) if lon.size > 1 else 0.1
                    self.dlat = float(abs(lat[1] - lat[0])) if lat.size > 1 else 0.1
                    self.xn = int(lon.size)
                    self.yn = int(lat.size)
                    self.lon = lon.copy()
                    self.lat = lat.copy()
                    if vals.shape == (self.yn, self.xn):
                        self.val = vals.copy()
                    elif vals.shape == (self.xn, self.yn):
                        self.val = vals.T.copy()
                    else:
                        self.val = vals.copy()
                    return
        except Exception:
            pass
        if suffix == ".nc":
            self._read_nc_legacy(path)
            return
        self._read_micaps4_legacy(path)

    def _read_micaps4_legacy(self, path: Path) -> None:
        parts = path.read_text(encoding="utf-8", errors="ignore").split()
        self.dlon = abs(float(parts[9]))
        self.dlat = abs(float(parts[10]))
        lon1, lon2 = float(parts[11]), float(parts[12])
        lat1, lat2 = float(parts[13]), float(parts[14])
        self.lon_start = min(lon1, lon2)
        self.lat_start = min(lat1, lat2)
        self.xn = int(parts[15])
        self.yn = int(parts[16])
        self.lon = self.lon_start + np.arange(self.xn, dtype=float) * self.dlon
        self.lat = self.lat_start + np.arange(self.yn, dtype=float) * self.dlat
        values = np.asarray(parts[22 : 22 + self.xn * self.yn], dtype=float).reshape(
            self.yn, self.xn
        )
        self.val = values.copy() if lat1 < lat2 else np.flipud(values).copy()

    def _read_nc_legacy(self, path: Path) -> None:
        try:
            import xarray as xr  # type: ignore
        except Exception as exc:
            raise RuntimeError("xarray is required for fallback nc reading") from exc
        with xr.open_dataset(str(path), decode_times=False) as ds:
            lon_name = next(
                (k for k in ["lon", "longitude", "x"] if k in ds.coords or k in ds),
                None,
            )
            lat_name = next(
                (k for k in ["lat", "latitude", "y"] if k in ds.coords or k in ds), None
            )
            if lon_name is None or lat_name is None:
                raise RuntimeError(f"cannot find lon/lat coordinate in nc: {path}")
            data_var_name = next(
                (
                    name
                    for name, var in ds.data_vars.items()
                    if lon_name in var.dims and lat_name in var.dims
                ),
                None,
            )
            if data_var_name is None:
                raise RuntimeError(
                    f"cannot find 2D field with lon/lat dims in nc: {path}"
                )
            da = ds[data_var_name]
            select_indexer = {
                dim: 0 for dim in da.dims if dim not in {lon_name, lat_name}
            }
            if select_indexer:
                da = da.isel(**select_indexer)
            da = da.transpose(lat_name, lon_name)
            lon = np.asarray(ds[lon_name].values, dtype=float).reshape(-1)
            lat = np.asarray(ds[lat_name].values, dtype=float).reshape(-1)
            vals = np.asarray(da.values, dtype=float)
        if vals.ndim != 2:
            raise RuntimeError(f"unexpected nc data shape: {vals.shape}")
        if lon.size == 0 or lat.size == 0:
            raise RuntimeError(f"empty lon/lat coordinate in nc: {path}")
        self.lon_start = float(lon[0])
        self.lat_start = float(lat[0])
        self.dlon = float(abs(lon[1] - lon[0])) if lon.size > 1 else 0.1
        self.dlat = float(abs(lat[1] - lat[0])) if lat.size > 1 else 0.1
        self.xn = int(lon.size)
        self.yn = int(lat.size)
        self.lon = lon.copy()
        self.lat = lat.copy()
        self.val = vals.copy()

    def read_float_val_from_bin(self, path: str | Path) -> None:
        arr = np.fromfile(path, dtype=np.float32, count=self.xn * self.yn)
        self.val = arr.reshape(self.yn, self.xn).astype(float)

    def copy_grid_data(self) -> "GridData":
        g = GridData(
            self.lon_start,
            self.lon_end,
            self.lat_start,
            self.lat_end,
            self.dlon,
            self.dlat,
        )
        g.val = self.val.copy()
        return g

    def clear_to_num(self, number: float) -> None:
        self.val[:, :] = number

    def clear_to_num_less_than(self, number: float, number_limit: float) -> None:
        self.val[self.val < number_limit] = number

    def add_val(self, other: "GridData") -> None:
        self.val += other.val

    def sub_val(self, other: "GridData") -> None:
        self.val -= other.val

    def multi_val(self, factor: float) -> None:
        self.val *= factor

    def mask_val(self, mask: "GridData", number: float) -> None:
        """掩膜 ``mask.val<=0`` 的格点赋为 ``number``（服务区外清零）。"""
        self.val[mask.val <= 0.0] = number

    def smooth9(self, smooth_num: int) -> None:
        """九点平滑 ``smooth_num`` 次；边界用外推保持场连续。"""
        if smooth_num <= 0:
            return
        for _ in range(smooth_num):
            arr = np.zeros_like(self.val)
            # 与原 C# val[x,y] 等价的 val[y,x] 实现
            if self.xn >= 3 and self.yn >= 3:
                # interior: y=1..yn-2, x=1..xn-2
                top = (
                    0.25 * self.val[2 : self.yn, 0 : self.xn - 2]
                    + 0.5 * self.val[2 : self.yn, 1 : self.xn - 1]
                    + 0.25 * self.val[2 : self.yn, 2 : self.xn]
                )
                mid = (
                    0.25 * self.val[1 : self.yn - 1, 0 : self.xn - 2]
                    + 0.5 * self.val[1 : self.yn - 1, 1 : self.xn - 1]
                    + 0.25 * self.val[1 : self.yn - 1, 2 : self.xn]
                )
                bot = (
                    0.25 * self.val[0 : self.yn - 2, 0 : self.xn - 2]
                    + 0.5 * self.val[0 : self.yn - 2, 1 : self.xn - 1]
                    + 0.25 * self.val[0 : self.yn - 2, 2 : self.xn]
                )
                arr[1 : self.yn - 1, 1 : self.xn - 1] = 0.25 * top + 0.5 * mid + 0.25 * bot

                # x boundaries (y=1..yn-2)
                for y in range(1, self.yn - 1):
                    arr[y, 0] = arr[y, 1] + (arr[y, 1] - arr[y, 2])
                    arr[y, self.xn - 1] = arr[y, self.xn - 2] + (
                        arr[y, self.xn - 2] - arr[y, self.xn - 3]
                    )

                # y boundaries (x=0..xn-1)
                for x in range(self.xn):
                    arr[0, x] = arr[1, x] + (arr[1, x] - arr[2, x])
                    arr[self.yn - 1, x] = arr[self.yn - 2, x] + (
                        arr[self.yn - 2, x] - arr[self.yn - 3, x]
                    )
                self.val[:, :] = arr

    def interpolate(self, lon: float, lat: float, undef: float = 0.0) -> float:
        return float(
            self.interpolate_points(np.asarray([lon]), np.asarray([lat]), undef)[0]
        )

    def interpolate_points(
        self, lon: np.ndarray, lat: np.ndarray, undef: float = 0.0
    ) -> np.ndarray:
        """批量双线性插值；越界返回 ``undef``。"""
        lon = np.asarray(lon, dtype=float)
        lat = np.asarray(lat, dtype=float)
        ix = np.floor((lon - self.lon_start + 1e-5) / self.dlon).astype(int)
        iy = np.floor((lat - self.lat_start + 1e-5) / self.dlat).astype(int)
        out = np.full(lon.shape, undef, dtype=float)

        m = (0 <= ix) & (ix < self.xn - 1) & (0 <= iy) & (iy < self.yn - 1)
        if np.any(m):
            x0 = self.lon[ix[m]]
            x1 = self.lon[ix[m] + 1]
            y0 = self.lat[iy[m]]
            y1 = self.lat[iy[m] + 1]
            # 双线性：先经向再纬向
            v00 = self.val[iy[m], ix[m]]
            v10 = self.val[iy[m], ix[m] + 1]
            v01 = self.val[iy[m] + 1, ix[m]]
            v11 = self.val[iy[m] + 1, ix[m] + 1]
            top = ((x1 - lon[m]) * v00 + (lon[m] - x0) * v10) / self.dlon
            bottom = ((x1 - lon[m]) * v01 + (lon[m] - x0) * v11) / self.dlon
            out[m] = ((y1 - lat[m]) * top + (lat[m] - y0) * bottom) / self.dlat

        m = (ix == self.xn - 1) & (0 <= iy) & (iy < self.yn - 1)
        if np.any(m):
            y0 = self.lat[iy[m]]
            y1 = self.lat[iy[m] + 1]
            out[m] = (
                (y1 - lat[m]) * self.val[iy[m], ix[m]]
                + (lat[m] - y0) * self.val[iy[m] + 1, ix[m]]
            ) / self.dlat

        m = (iy == self.yn - 1) & (0 <= ix) & (ix < self.xn - 1)
        if np.any(m):
            x0 = self.lon[ix[m]]
            x1 = self.lon[ix[m] + 1]
            out[m] = (
                (x1 - lon[m]) * self.val[iy[m], ix[m]]
                + (lon[m] - x0) * self.val[iy[m], ix[m] + 1]
            ) / self.dlon

        m = (ix == self.xn - 1) & (iy == self.yn - 1)
        if np.any(m):
            out[m] = self.val[iy[m], ix[m]]
        return out

    def mesh_val(
        self,
        lon_start: float,
        lon_end: float,
        lat_start: float,
        lat_end: float,
        dlon: float,
        dlat: float,
        undef: float = 0.0,
    ) -> "GridData":
        """重采样到新网格（双线性）；常用于分块裁剪或抽稀。"""
        g = GridData(lon_start, lon_end, lat_start, lat_end, dlon, dlat)
        glon, glat = np.meshgrid(g.lon, g.lat, indexing="xy")  # 与 val[y,x] 对齐
        g.val = self.interpolate_points(glon, glat, undef)
        return g

    def to_scatter_data(self) -> ScatterData:
        pts = [
            PointData(
                f"{i}_{j}_{random.randint(0,999999):06d}",
                float(self.lon[i]),
                float(self.lat[j]),
                float(self.val[j, i]),
            )
            for j in range(self.yn)
            for i in range(self.xn)
        ]
        return ScatterData(pts)

    def write_float_val_to_bin(self, path: str | Path) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        # val already is [yn, xn] -> write in row-major order matching read_float_val_from_bin
        self.val.astype(np.float32).tofile(p)

    def write_val_to_micaps4(
        self,
        path: str | Path,
        header: str | None = None,
        dt_input: datetime | None = None,
        i_valid: int | None = None,
    ) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        try:
            grid = meb.grid(
                [self.lon_start, self.lon_end, self.dlon],
                [self.lat_start, self.lat_end, self.dlat],
                gtime=[dt_input],
                dtime_list=[i_valid],
            )
            # meteva grid_data 的最后两维与 [lat, lon] 对应；本项目约定 val 为 [yn, xn]
            data = self.val.reshape(1, 1, 1, 1, self.yn, self.xn)
            grd = meb.grid_data(grid, data=data)
            meb.write_griddata_to_micaps4(
                grd,
                str(p),
                creat_dir=True,
                title=f"{dt_input:%Y%m%d%H}_{i_valid:03d}时效001小时降水预报场",
                inte=5,
                vmin=0,
                vmax=200,
                effectiveNum=2
            )
            return
        except Exception:
            pass

        if header is None:
            if dt_input is None or i_valid is None:
                raise ValueError(
                    "Either header or (dt_input and i_valid) must be provided"
                )
            header = (
                " diamond 4 "
                f"{dt_input:%Y%m%d%H}_{i_valid:03d}时效001小时降水预报场 "
                f"{dt_input:%Y %m %d %H} {i_valid:03d} 0 {self.dlon:.2f}  {self.dlat:.2f}  "
                f"{self.lon_start:.0f} {self.lon_end:.0f} {self.lat_start:.0f} {self.lat_end:.0f} "
                f"{self.xn} {self.yn}  5  0 200 0  0"
            )
        with p.open("w", encoding="gb2312", errors="ignore") as f:
            f.write(header + "\n")
            for j in range(self.yn):
                f.write(
                    "  ".join(f"{self.val[j, i]:8.2f}" for i in range(self.xn))
                    + "\n"
                )

    def write_val_to_nc(
        self,
        path: str | Path,
        dt_input: datetime | None = None,
        i_valid: int | None = None,
        var_name: str = "data0",
    ) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        dt = dt_input if dt_input is not None else datetime(1970, 1, 1, 0, 0)
        dtime = int(i_valid) if i_valid is not None else 0

        try:
            grid = meb.grid(
                [self.lon_start, self.lon_end, self.dlon],
                [self.lat_start, self.lat_end, self.dlat],
                gtime=[dt],
                dtime_list=[dtime],
            )
            data = self.val.reshape(1, 1, 1, 1, self.yn, self.xn)
            grd = meb.grid_data(grid, data=data)
            meb.set_griddata_coords(
                grd,
                name=var_name,
                member_list=[var_name],
                level_list=[0.0],
                gtime=[dt],
                dtime_list=[dtime],
            )
            meb.write_griddata_to_nc(grd, save_path=str(p), creat_dir=True)
            return
        except Exception:
            pass

        data = self.val.reshape(1, 1, 1, 1, self.yn, self.xn).astype(np.float32)
        ds = xr.Dataset(
            data_vars={
                var_name: (
                    ("member", "level", "time", "dtime", "lat", "lon"),
                    data,
                )
            },
            coords={
                "member": np.asarray([var_name], dtype=object),
                "level": np.asarray([0.0], dtype=float),
                "time": np.asarray([np.datetime64(dt)], dtype="datetime64[ns]"),
                "dtime": np.asarray([dtime], dtype=np.int64),
                "lat": self.lat.astype(float),
                "lon": self.lon.astype(float),
            },
            attrs={"dtime_units": "hour"},
        )
        encoding = {
            var_name: {
                # Aggressive packing to minimize file size.
                # Note: this is lossy with 0.01 precision.
                "dtype": "int32",
                "scale_factor": np.float32(0.01),
                "add_offset": np.float32(0.0),
                "_FillValue": np.int16(-32768),
                "zlib": True,
                "shuffle": True,
                "complevel": 9,
                "contiguous": False,
                "chunksizes": (1, 1, 1, 1, self.yn, self.xn),
            },
            "lat": {"dtype": "float32"},
            "lon": {"dtype": "float32"},
            "level": {"dtype": "float32"},
            "dtime": {"dtype": "int32"},
        }
        # Use NETCDF4 compression in fallback path to avoid oversized files.
        ds.to_netcdf(str(p), format="NETCDF4", encoding=encoding)


def points_in_polygon(
    x: np.ndarray, y: np.ndarray, poly_x: np.ndarray, poly_y: np.ndarray
) -> np.ndarray:
    inside = np.zeros(x.shape, dtype=bool)
    j = len(poly_x) - 1
    for i in range(len(poly_x)):
        py_i = poly_y[i]
        py_j = poly_y[j]
        denom = py_j - py_i
        cross = (py_i > y) != (py_j > y)
        safe = abs(denom) > 1e-12
        # Compute x-intersection with guarded denominator to avoid RuntimeWarning.
        x_intersect = np.where(
            safe,
            (poly_x[j] - poly_x[i]) * (y - py_i) / denom + poly_x[i],
            np.inf,
        )
        cond = cross & safe & (x < x_intersect)
        inside ^= cond
        j = i
    return inside

if __name__ == "__main__":
    # Example usage
    path1 = r'C:\Users\admin\OneDrive\Desktop\rain01\rain01_qpf\C#84\ecmwf\2025100100.004.m4'
    path2 = r'C:\Users\admin\OneDrive\Desktop\rain01\rain01_qpf\C#84\ecmwf\2025100100.004.nc'
    grd = GridData(path1)
    print(grd.val.shape)
    grd.write_val_to_nc(path2)