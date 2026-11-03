#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""把 EC 等压面要素插到离地 1000 m，按要素分目录写出。

使用 ``read_pressure_levels`` 逐时次读取各气压层，再用 ``PressureToHeightPlugin``
插值。地形为 ``EC_D1D_orography_20km.nc``。温湿风在目标落在地面与最低有效气压层之间时，
用近地面场作下界：``TMP_2M``、``RH_2M``、``UGRD_100M``、``VGRD_100M``。
结果网格与 EC 气压层一致，覆盖 ``resource/data`` 中的同名文件。

输出目录 ``resource/data/<要素>/YYYY/YYYYMMDD/YYYYMMDDHH.TTT.nc``：
TMP、RH、UGRD、VGRD 保留源文件单位；PRES 为 Pa；另写出风速和来向风向。
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import meteva_base as meb
import numpy as np
import xarray as xr

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from utils.pressure_to_height_plugin import (  # noqa: E402
    PressureToHeightPlugin,
    pressure_field_from_levels,
    read_pressure_levels,
    wind_speed_and_direction,
)

RESOURCE = REPO_ROOT / "orographic_precipitation_downscaling" / "resource"
EC_ROOT = RESOURCE / "EC"
ANCIL = RESOURCE / "ancil" / "EC_D1D_orography_20km.nc"
OUT_ROOT = RESOURCE / "data"
NEAR_SURFACE = {
    "TMP": "TMP_2M",
    "RH": "RH_2M",
    "UGRD": "UGRD_100M",
    "VGRD": "VGRD_100M",
}

# 各要素都有的气压层，自地面往上（hPa）
LEVELS = (1000, 950, 925, 900, 850, 800, 700, 600, 500, 400, 300, 250, 200, 150, 100, 50, 10)
AGL_M = 1000.0
SOURCE_ELEMENTS = ("TMP", "RH", "UGRD", "VGRD")


def _template(element: str) -> str:
    return str(EC_ROOT / element / "{level}" / "YYYY" / "YYYYMMDD" / "YYYYMMDDHH.TTT.nc")


def _discover_forecasts() -> list[tuple[str, int]]:
    """从 TMP/850 文件名收集 (起报 YYYYMMDDHH, 时效小时)。"""
    keys = []
    for path in sorted((EC_ROOT / "TMP" / "850").rglob("*.nc")):
        init_s, lead_s = path.stem.split(".", 1)
        keys.append((init_s, int(lead_s)))
    if not keys:
        raise FileNotFoundError(f"未找到 EC 温度文件: {EC_ROOT / 'TMP' / '850'}")
    return keys


def _read_surface_altitude() -> xr.DataArray:
    """读取 0.2° 模式地形。与气压层网格不同的部分由插件插值，范围外为缺测。"""
    surface = meb.read_griddata_from_nc(str(ANCIL))
    if not str(surface.attrs.get("units") or "").strip():
        surface.attrs["units"] = "m"
    surface.name = "surface_altitude"
    return surface


def _read_near_surface(element: str, init_s: str, lead_h: int) -> xr.DataArray:
    """读取与等压层要素对应的一份近地面场。"""
    day = init_s[:8]
    path = EC_ROOT / NEAR_SURFACE[element] / init_s[:4] / day / f"{init_s}.{lead_h:03d}.nc"
    if not path.is_file():
        raise FileNotFoundError(path)
    field = meb.read_griddata_from_nc(str(path))
    if element == "RH":
        # 数值是百分数，文件单位写成了 ℃。
        field.attrs["units"] = "%"
    return field


def _write(field: xr.DataArray, element: str, init_s: str, lead_h: int) -> Path:
    path = OUT_ROOT / element / init_s[:4] / init_s[:8] / f"{init_s}.{lead_h:03d}.nc"
    path.parent.mkdir(parents=True, exist_ok=True)
    out = field.copy()
    out.name = element
    attrs = dict(out.attrs)
    for key, value in attrs.items():
        if isinstance(value, (bool, np.bool_)):
            attrs[key] = int(value)
    out.attrs = attrs
    out.to_dataset(name=element).to_netcdf(path, mode="w")
    return path


def _one(template: str, init_s: str, lead_h: int) -> xr.DataArray:
    fields = read_pressure_levels(template, init_s, LEVELS, dt=lead_h, level_units="hPa")
    if len(fields) != 1:
        raise RuntimeError(f"期望单个时次，实际 {len(fields)} 个: {init_s}.{lead_h:03d}")
    return fields[0]


def main() -> None:
    forecasts = _discover_forecasts()
    print(f"时次 {len(forecasts)}，气压层 {LEVELS}")
    print(f"输入 {EC_ROOT}")
    print(f"输出 {OUT_ROOT}")

    linear = PressureToHeightPlugin(
        target_height=AGL_M,
        height_units="m",
        height_type="agl",
        vertical_interp="linear",
        output_grid="isobaric",
        use_surface_field=True,
    )
    log_p = PressureToHeightPlugin(
        target_height=AGL_M,
        height_units="m",
        height_type="agl",
        vertical_interp="log",
        output_grid="isobaric",
        fill_below_lowest=True,
    )
    surface = _read_surface_altitude()
    written = 0

    for init_s, lead_h in forecasts:
        tag = f"{init_s}.{lead_h:03d}"
        started = datetime.now()
        height = _one(_template("HGT"), init_s, lead_h)
        if not str(height.attrs.get("units") or "").strip():
            height.attrs["units"] = "gpm"

        fields = {name: _one(_template(name), init_s, lead_h) for name in SOURCE_ELEMENTS}
        near = {name: _read_near_surface(name, init_s, lead_h) for name in SOURCE_ELEMENTS}
        pressure = pressure_field_from_levels(height, level_units="hPa", output_units="Pa")
        u_h = linear(fields["UGRD"], height, surface, near["UGRD"])
        v_h = linear(fields["VGRD"], height, surface, near["VGRD"])
        speed, direction = wind_speed_and_direction(u_h, v_h)

        outputs = {
            "TMP": linear(fields["TMP"], height, surface, near["TMP"]),
            "RH": linear(fields["RH"], height, surface, near["RH"]),
            "UGRD": u_h,
            "VGRD": v_h,
            "PRES": log_p(pressure, height, surface),
            "wind_speed": speed,
            "wind_direction": direction,
        }
        for element, data in outputs.items():
            _write(data, element, init_s, lead_h)
            written += 1
        finite = float(np.mean(np.isfinite(outputs["TMP"].values)))
        print(f"[OK] {tag} TMP有效比例 {finite:.3f} 用时 {(datetime.now() - started).total_seconds():.1f}s")

    print(f"完成，写出 {written} 个文件，目录 {OUT_ROOT}")


if __name__ == "__main__":
    main()
