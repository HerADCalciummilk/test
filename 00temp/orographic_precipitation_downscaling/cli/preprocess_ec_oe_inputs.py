#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""将 EC 等压面温湿风插到离地约 1000 m，并写出降水率。

垂直转换使用共享插件 ``utils.pressure_to_height_plugin``。
高度语义为 **AGL**（目标海拔 = 地表 + 1000 m）。气压按 ln(p) 插值，
温度、湿度和风分量沿位势高度线性插值。

本地 EC 气压层产品为 3 h 时效，气象场只在 3 h 节点处理。
降水 `APCP01` 为 1 h，可逐时写出。
"""

from __future__ import annotations

import csv
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import xarray as xr

import meteva_base as meb

# ---------------------------------------------------------------------------
# 路径与常量
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[2]
RESOURCE = REPO_ROOT / "orographic_precipitation_downscaling" / "resource"
EC_ROOT = RESOURCE / "EC"
OUT_ROOT = RESOURCE / "data"  # 原 ECD1D，已重命名为 data

# 气压层自低到高（hPa）；HGT 随层升高而增大，便于垂向插值
PRESSURE_LEVELS_HPA: Tuple[int, ...] = (950, 925, 900, 850, 700, 500)
AGL_TARGET_M = 1000.0
ELEMENTS_MET = ("HGT", "TMP", "RH", "UGRD", "VGRD")

# 个例检验域：浙闽赣湘粤桂琼（含台湾西侧强降水带），避开青藏高原 AGL 缺测
# 经核对：AGL1000 缺测约 <1%；EC/CMPAS 过程累积最大雨量仍落在此框内
CASE_DOMAIN = {
    "lon_min": 105.0,
    "lon_max": 122.0,
    "lat_min": 18.0,
    "lat_max": 31.0,
    "label": "SE_China_浙闽赣湘粤桂琼",
}


@dataclass(frozen=True)
class ForecastKey:
    """一次起报 + 时效。"""

    init: datetime
    lead_h: int

    @property
    def init_str(self) -> str:
        return self.init.strftime("%Y%m%d%H")

    @property
    def valid(self) -> datetime:
        return self.init + timedelta(hours=self.lead_h)

    @property
    def stem(self) -> str:
        return f"{self.init_str}.{self.lead_h:03d}"


def _parse_yyyymmddhh(text: str) -> datetime:
    return datetime.strptime(text, "%Y%m%d%H")


def _ensure_repo_on_path() -> None:
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))


def _read_nc(path: Path) -> xr.DataArray:
    return meb.checkout_griddata(
        meb.read_griddata_from_nc(str(path)),
        valid_val=(-np.inf, np.inf, np.nan),
    )


def _write_nc(da: xr.DataArray, path: Path, var_name: str) -> None:
    """用 xarray 直写，避免 meb 量化把小量级场写成 0。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    out = da.copy()
    out.name = var_name
    out.to_dataset(name=var_name).to_netcdf(path, mode="w")


def _field_2d(da: xr.DataArray) -> np.ndarray:
    return np.asarray(da.values, dtype=np.float64).reshape(da.lat.size, da.lon.size)


def _as_griddata(
    values2d: np.ndarray,
    template: xr.DataArray,
    *,
    level: float,
    units: str,
    name: str,
    time: datetime,
    dtime: int = 0,
) -> xr.DataArray:
    """按模板经纬重建六维 grid_data，写入指定 level/time。"""
    arr = np.asarray(values2d, dtype=np.float32)[None, None, None, None, :, :]
    da = xr.DataArray(
        arr,
        dims=("member", "level", "time", "dtime", "lat", "lon"),
        coords={
            "member": ["EC"],
            "level": [level],
            "time": [np.datetime64(time.strftime("%Y-%m-%dT%H:%M:%S"))],
            "dtime": [dtime],
            "lat": template.lat.values,
            "lon": template.lon.values,
        },
        name=name,
        attrs={"units": units},
    )
    da.level.attrs["units"] = "m"
    return da


def _interp_orography_to_grid(orog: xr.DataArray, target: xr.DataArray) -> np.ndarray:
    """把模式地形插到气压层网格（EC 层数据 0.2°，ancil 地形 0.1°）。"""
    # 仅保留与地形 ancilla 重叠的经纬，减少无效外推
    lat_min = max(float(orog.lat.min()), float(target.lat.min()))
    lat_max = min(float(orog.lat.max()), float(target.lat.max()))
    lon_min = max(float(orog.lon.min()), float(target.lon.min()))
    lon_max = min(float(orog.lon.max()), float(target.lon.max()))
    tgt = target.sel(lat=slice(lat_min, lat_max), lon=slice(lon_min, lon_max))
    # meteva：格点→格点线性
    zs = meb.interp_gg_linear(orog, meb.get_grid_of_data(tgt))
    zs = meb.checkout_griddata(zs, is_single=True, valid_val=(-np.inf, np.inf, np.nan))
    return _field_2d(zs), tgt


def _surface_on_template(orog_on_grid: np.ndarray, template: xr.DataArray) -> xr.DataArray:
    """把已对齐的地表海拔收成与气压层网格一致的二维场。"""
    return xr.DataArray(
        np.asarray(orog_on_grid, dtype=np.float32),
        dims=("lat", "lon"),
        coords={"lat": template.lat.values, "lon": template.lon.values},
        name="surface_altitude",
        attrs={"units": "m"},
    )


def _stamp_height_field(
    data: xr.DataArray,
    key: ForecastKey,
    *,
    units: str,
    name: str,
) -> xr.DataArray:
    """写成个例约定：有效时、member=EC、level 为离地高度。"""
    out = data.copy()
    out.name = name
    attrs = dict(out.attrs)
    attrs["units"] = units
    attrs["level_type"] = "height"
    attrs["agl_m"] = AGL_TARGET_M
    attrs["source_init"] = key.init_str
    attrs["source_lead_h"] = key.lead_h
    attrs["source_stem"] = key.stem
    out.attrs = attrs
    out = out.assign_coords(
        member=["EC"],
        time=[np.datetime64(key.valid.strftime("%Y-%m-%dT%H:%M:%S"))],
        dtime=[0],
    )
    out.level.attrs["units"] = "m"
    return out


def _met_path(elem: str, level_hpa: int, key: ForecastKey) -> Path:
    day = key.init.strftime("%Y%m%d")
    year = key.init.strftime("%Y")
    return EC_ROOT / elem / str(level_hpa) / year / day / f"{key.stem}.nc"


def _apcp_path(key: ForecastKey) -> Path:
    day = key.init.strftime("%Y%m%d")
    year = key.init.strftime("%Y")
    # 本地解压结构含 NC 子目录
    p = EC_ROOT / "APCP01" / year / day / "NC" / f"{key.stem}.nc"
    if p.exists():
        return p
    return EC_ROOT / "APCP01" / year / day / f"{key.stem}.nc"


def _discover_forecast_index(root: Path) -> Dict[str, List[int]]:
    """扫描目录下 ``YYYYMMDDHH.TTT.nc``，得到 init_str → lead 列表。"""
    index: Dict[str, List[int]] = {}
    for p in root.rglob("*.nc"):
        stem = p.stem
        if "." not in stem:
            continue
        init_s, lead_s = stem.split(".", 1)
        try:
            lead = int(lead_s)
        except ValueError:
            continue
        index.setdefault(init_s, []).append(lead)
    for init_s in index:
        index[init_s] = sorted(set(index[init_s]))
    return index


def _best_forecast(
    valid: datetime,
    index: Dict[str, List[int]],
    *,
    lead_step: int = 1,
    min_lead: int = 0,
) -> Optional[ForecastKey]:
    """对给定有效世界时，在 ``index`` 内选 lead 最短的起报。"""
    best: Optional[ForecastKey] = None
    for init_s, leads in index.items():
        init = _parse_yyyymmddhh(init_s)
        lead = int((valid - init).total_seconds() // 3600)
        if lead < min_lead or lead not in leads:
            continue
        if lead_step > 1 and lead % lead_step != 0:
            continue
        cand = ForecastKey(init=init, lead_h=lead)
        if best is None or cand.lead_h < best.lead_h:
            best = cand
    return best


def _load_level_stack(
    elem: str,
    key: ForecastKey,
    template: xr.DataArray,
) -> xr.DataArray:
    """读取各气压层并裁到模板网格，沿 level 叠成一个等压层场。"""
    _ensure_repo_on_path()
    from utils.pressure_to_height_plugin import stack_pressure_levels

    layers = []
    for lev in PRESSURE_LEVELS_HPA:
        path = _met_path(elem, lev, key)
        if not path.exists():
            raise FileNotFoundError(f"缺少 {elem}/{lev}: {path}")
        da = _read_nc(path)
        da = da.sel(lat=template.lat, lon=template.lon)
        da = da.assign_coords(level=[float(lev)])
        layers.append(da)
    stacked = stack_pressure_levels(layers, level_units="hPa")
    if not str(stacked.attrs.get("units") or "").strip() and elem == "HGT":
        stacked.attrs["units"] = "gpm"
    return stacked


def process_agl1000(
    key: ForecastKey,
    orog_on_grid: np.ndarray,
    grid_template: xr.DataArray,
    out_root: Path = OUT_ROOT,
) -> Dict[str, Path]:
    """单时次：等压面 → AGL1000 温湿压风，写出 nc。

    垂直转换调用共享插件 ``PressureToHeightPlugin``。温度、湿度和风分量
    沿位势高度线性插值；气压由层次坐标构成，并按 ln(p) 插值。
    """
    _ensure_repo_on_path()
    from utils.pressure_to_height_plugin import (
        PressureToHeightPlugin,
        pressure_field_from_levels,
        wind_speed_and_direction,
    )

    height = _load_level_stack("HGT", key, grid_template)
    if not str(height.attrs.get("units") or "").strip():
        height.attrs["units"] = "gpm"
    surface = _surface_on_template(orog_on_grid, grid_template)
    linear = PressureToHeightPlugin(
        target_height=AGL_TARGET_M,
        height_units="m",
        height_type="agl",
        vertical_interp="linear",
    )
    log_pressure = PressureToHeightPlugin(
        target_height=AGL_TARGET_M,
        height_units="m",
        height_type="agl",
        vertical_interp="log",
    )

    temperature = _load_level_stack("TMP", key, grid_template)
    temperature = temperature.copy(data=np.asarray(temperature.values, dtype=np.float64) + 273.15)
    temperature.attrs["units"] = "K"
    temperature.name = "air_temperature"

    humidity = _load_level_stack("RH", key, grid_template)
    humidity = humidity.copy(data=np.asarray(humidity.values, dtype=np.float64) / 100.0)
    humidity.attrs["units"] = "1"
    humidity.name = "relative_humidity"

    pressure = pressure_field_from_levels(height, level_units="hPa", output_units="Pa")
    u_wind = _load_level_stack("UGRD", key, grid_template)
    v_wind = _load_level_stack("VGRD", key, grid_template)
    u_at_height = linear(u_wind, height, surface)
    v_at_height = linear(v_wind, height, surface)
    speed, direction = wind_speed_and_direction(u_at_height, v_at_height)

    fields = {
        "TMP": (linear(temperature, height, surface), "K", "air_temperature"),
        "RH": (linear(humidity, height, surface), "1", "relative_humidity"),
        "PRES": (log_pressure(pressure, height, surface), "Pa", "air_pressure"),
        "wind_speed": (speed, "m s-1", "wind_speed"),
        "wind_direction": (direction, "degrees", "wind_from_direction"),
    }

    valid_tag = key.valid.strftime("%Y%m%d%H")
    written: Dict[str, Path] = {}
    for elem, (data, units, var_name) in fields.items():
        stamped = _stamp_height_field(data, key, units=units, name=var_name)
        out_path = out_root / "agl1000" / elem / f"{valid_tag}.nc"
        _write_nc(stamped, out_path, var_name)
        written[elem] = out_path
    return written


def process_precip_rate(key: ForecastKey, out_root: Path = OUT_ROOT) -> Path:
    """把 APCP01 单小时累积当作降水率（mm/h）写出。"""
    path = _apcp_path(key)
    if not path.exists():
        raise FileNotFoundError(f"缺少 APCP01: {path}")
    da = _read_nc(path)
    vals = _field_2d(da)
    # 缺测/填充
    vals = np.where(np.isfinite(vals) & (np.abs(vals) < 1e10), vals, np.nan)
    out = _as_griddata(
        vals,
        da,
        level=0.0,
        units="mm h-1",
        name="precipitation_rate",
        time=key.valid,
        dtime=0,
    )
    out.level.attrs["units"] = "m"
    out.attrs["source_init"] = key.init_str
    out.attrs["source_lead_h"] = key.lead_h
    out.attrs["source_stem"] = key.stem
    out.attrs["note"] = "APCP01 treated as hourly accumulation = rate mm/h"
    out_path = out_root / "precip_rate" / f"{key.valid.strftime('%Y%m%d%H')}.nc"
    _write_nc(out, out_path, "precipitation_rate")
    return out_path


def _cmpas_path(bjt: datetime) -> Path:
    day = bjt.strftime("%Y%m%d")
    year = bjt.strftime("%Y")
    # BJT_YYMMDDHH.000.nc
    name = f"BJT_{bjt.strftime('%y%m%d%H')}.000.nc"
    return RESOURCE / "CMPAS_APCP" / year / day / name


def build_valid_times(
    start_utc: datetime,
    end_utc: datetime,
    step_h: int,
) -> List[datetime]:
    out = []
    cur = start_utc
    while cur <= end_utc:
        out.append(cur)
        cur += timedelta(hours=step_h)
    return out


def write_meta_table(
    rows: Sequence[dict],
    out_root: Path = OUT_ROOT,
) -> Path:
    path = out_root / "meta" / "time_alignment.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return path
    fieldnames = list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return path


def run_batch(
    *,
    case_start_bjt: str = "2026083100",
    case_end_bjt: str = "2026090323",
    met_only_3h: bool = True,
    out_root: Path = OUT_ROOT,
) -> None:
    """批量：3 h AGL1000 + 逐时降水率 + 对照表。"""
    _ensure_repo_on_path()
    out_root.mkdir(parents=True, exist_ok=True)

    start_bjt = _parse_yyyymmddhh(case_start_bjt)
    end_bjt = _parse_yyyymmddhh(case_end_bjt)
    # 北京时 → 世界时
    start_utc = start_bjt - timedelta(hours=8)
    end_utc = end_bjt - timedelta(hours=8)

    met_index = _discover_forecast_index(EC_ROOT / "TMP" / "850")
    apcp_index = _discover_forecast_index(EC_ROOT / "APCP01")
    if not met_index:
        raise RuntimeError(f"未在 {EC_ROOT}/TMP/850 发现 EC 文件")
    if not apcp_index:
        raise RuntimeError(f"未在 {EC_ROOT}/APCP01 发现降水文件")

    # 地形：插到与一层 TMP 相同的 0.2° 网格，并裁到重叠区
    sample_init = sorted(met_index.keys())[0]
    sample_lead = met_index[sample_init][0]
    sample_key = ForecastKey(init=_parse_yyyymmddhh(sample_init), lead_h=sample_lead)
    sample_tmp = _read_nc(_met_path("TMP", 850, sample_key))
    orog = _read_nc(RESOURCE / "ancil" / "ec_source_orography.nc")
    orog_2d, grid_tmpl = _interp_orography_to_grid(orog, sample_tmp)
    # 缓存裁剪后的地形，便于 OE/检查
    zs_da = _as_griddata(
        orog_2d,
        grid_tmpl,
        level=0.0,
        units="m",
        name="surface_altitude",
        time=datetime(1970, 1, 1),
        dtime=0,
    )
    zs_da.level.attrs["units"] = "m"
    _write_nc(zs_da, out_root / "ancil" / "ec_orography_on_met_grid.nc", "surface_altitude")

    met_times = build_valid_times(
        # 对齐到 3 h 节点
        start_utc.replace(hour=(start_utc.hour // 3) * 3, minute=0, second=0, microsecond=0),
        end_utc,
        3 if met_only_3h else 1,
    )
    precip_times = build_valid_times(start_utc, end_utc, 1)

    rows: List[dict] = []
    n_met_ok = n_met_miss = n_pr_ok = n_pr_miss = 0

    print(f"资源目录: {RESOURCE}")
    print(f"输出目录: {out_root}")
    print(f"个例 BJT {case_start_bjt}–{case_end_bjt} → UTC {start_utc}–{end_utc}")
    print(f"AGL 目标: {AGL_TARGET_M} m；气压层: {PRESSURE_LEVELS_HPA}")
    print(f"气象时次(3h): {len(met_times)}；降水时次(1h): {len(precip_times)}")
    print(f"APCP 起报数: {len(apcp_index)}；TMP 起报数: {len(met_index)}")

    # 先写降水率（快），再写 AGL1000
    for valid in precip_times:
        # APCP01 无 lead=0；按 APCP 自身 1 h 时效索引选最短 lead
        key = _best_forecast(valid, apcp_index, lead_step=1, min_lead=1)
        bjt = valid + timedelta(hours=8)
        row = {
            "bjt": bjt.strftime("%Y%m%d%H"),
            "utc_valid": valid.strftime("%Y%m%d%H"),
            "met_init": "",
            "met_lead": "",
            "met_stem": "",
            "precip_init": "",
            "precip_lead": "",
            "precip_stem": "",
            "cmpas": "",
            "agl1000": "",
            "precip_rate": "",
            "note": "",
        }
        cmpas = _cmpas_path(bjt)
        row["cmpas"] = str(cmpas.relative_to(RESOURCE)) if cmpas.exists() else "MISSING"

        if key is None:
            row["note"] = "no_ec_forecast_for_valid"
            n_pr_miss += 1
            rows.append(row)
            continue

        try:
            pr_path = process_precip_rate(key, out_root=out_root)
            row["precip_init"] = key.init_str
            row["precip_lead"] = str(key.lead_h)
            row["precip_stem"] = key.stem
            row["precip_rate"] = str(pr_path.relative_to(out_root))
            n_pr_ok += 1
        except Exception as exc:  # noqa: BLE001 — 批量时记录失败继续
            row["note"] = f"precip_fail:{exc}"
            n_pr_miss += 1
        rows.append(row)

    # 按 utc 建索引，回填 met 列
    row_by_utc = {r["utc_valid"]: r for r in rows}

    for valid in met_times:
        key = _best_forecast(valid, met_index, lead_step=3, min_lead=0)
        utc_s = valid.strftime("%Y%m%d%H")
        row = row_by_utc.get(utc_s)
        if row is None:
            # 3h 节点若因对齐落在降水窗外，补一行
            bjt = valid + timedelta(hours=8)
            row = {
                "bjt": bjt.strftime("%Y%m%d%H"),
                "utc_valid": utc_s,
                "met_init": "",
                "met_lead": "",
                "met_stem": "",
                "precip_init": "",
                "precip_lead": "",
                "precip_stem": "",
                "cmpas": "",
                "agl1000": "",
                "precip_rate": "",
                "note": "",
            }
            rows.append(row)
            row_by_utc[utc_s] = row

        if key is None:
            row["note"] = (row["note"] + "|no_met_3h").strip("|")
            n_met_miss += 1
            print(f"[MISS met] {utc_s}")
            continue
        try:
            written = process_agl1000(key, orog_2d, grid_tmpl, out_root=out_root)
            row["met_init"] = key.init_str
            row["met_lead"] = str(key.lead_h)
            row["met_stem"] = key.stem
            row["agl1000"] = str(Path("agl1000") / "TMP" / f"{utc_s}.nc")
            n_met_ok += 1
            # 粗略有效比例
            da = _read_nc(written["TMP"])
            v = np.asarray(da.values, float).ravel()
            frac = float(np.mean(np.isfinite(v)))
            print(f"[OK met] {utc_s} init={key.stem} finite_TMP={frac:.3f}")
        except Exception as exc:  # noqa: BLE001
            row["note"] = (row.get("note", "") + f"|agl_fail:{exc}").strip("|")
            n_met_miss += 1
            print(f"[FAIL met] {utc_s}: {exc}")

    meta_path = write_meta_table(sorted(rows, key=lambda r: r["utc_valid"]), out_root=out_root)
    readme = out_root / "meta" / "README.md"
    readme.write_text(
        "\n".join(
            [
                "# ECD1D 预处理说明",
                "",
                f"- 个例 BJT：`{case_start_bjt}`–`{case_end_bjt}`",
                f"- AGL 目标：`{AGL_TARGET_M}` m（目标海拔 = 模式地形 + AGL）",
                f"- 气压层：{', '.join(str(x) for x in PRESSURE_LEVELS_HPA)} hPa",
                "- 温湿风：仅 3 h 节点（本地无逐时气压层）",
                "- 降水率：`APCP01` 按小时累积当作 mm/h",
                "- `agl1000/*/YYYYMMDDHH.nc` 中时间为 **UTC 有效时**，`level=1000` 单位 m（离地）",
                "- RH 已改为分数（units=`1`）；TMP 为 K；PRES 为 Pa，并按 ln(p) 插到目标高度",
                f"- 对照表：`{meta_path.relative_to(out_root).as_posix()}`",
                f"- 统计：met_ok={n_met_ok} met_miss={n_met_miss} precip_ok={n_pr_ok} precip_miss={n_pr_miss}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    print(f"meta → {meta_path}")
    print(f"完成：met_ok={n_met_ok} met_miss={n_met_miss} precip_ok={n_pr_ok} precip_miss={n_pr_miss}")


def run_smoke() -> None:
    """单时次冒烟：UTC 2026083103（有 APCP01 的 3 h 节点）。"""
    _ensure_repo_on_path()
    met_index = _discover_forecast_index(EC_ROOT / "TMP" / "850")
    apcp_index = _discover_forecast_index(EC_ROOT / "APCP01")
    valid = datetime(2026, 8, 31, 3)
    key = _best_forecast(valid, met_index, lead_step=3, min_lead=0)
    if key is None:
        raise RuntimeError("找不到 UTC 2026083103 的 3 h 预报")
    key_pr = _best_forecast(valid, apcp_index, lead_step=1, min_lead=1)
    if key_pr is None:
        raise RuntimeError("找不到 UTC 2026083103 的 APCP01")
    sample_tmp = _read_nc(_met_path("TMP", 850, key))
    orog = _read_nc(RESOURCE / "ancil" / "ec_source_orography.nc")
    orog_2d, grid_tmpl = _interp_orography_to_grid(orog, sample_tmp)
    written = process_agl1000(key, orog_2d, grid_tmpl)
    pr = process_precip_rate(key_pr)
    print("smoke agl1000:", {k: str(v) for k, v in written.items()})
    print("smoke precip:", pr)
    da = _read_nc(written["TMP"])
    v = np.asarray(da.values, float)
    print(
        "TMP K finite%",
        float(np.mean(np.isfinite(v))),
        "min/max",
        np.nanmin(v),
        np.nanmax(v),
        "level",
        da.level.values,
        da.level.attrs,
    )
    rh = _read_nc(written["RH"])
    rv = np.asarray(rh.values, float)
    print("RH fraction finite% / max", float(np.mean(np.isfinite(rv))), np.nanmax(rv))


def crop_da_to_domain(da: xr.DataArray, domain: Optional[dict] = None) -> xr.DataArray:
    """按个例经纬框裁剪六维场（含端点）。"""
    dom = domain or CASE_DOMAIN
    return da.sel(
        lat=slice(dom["lat_min"], dom["lat_max"]),
        lon=slice(dom["lon_min"], dom["lon_max"]),
    )


def crop_ecd1d_to_case_domain(
    out_root: Path = OUT_ROOT,
    domain: Optional[dict] = None,
) -> dict:
    """把已写出的 ECD1D 温湿风/降水率/地形裁到个例域，原地覆盖。

    用于排除高原 AGL 空缺，同时保留浙闽赣湘粤桂琼一带强降水。
    """
    dom = domain or CASE_DOMAIN
    patterns = [
        "agl1000/*/*.nc",
        "precip_rate/*.nc",
        "ancil/*.nc",
    ]
    n_ok = n_skip = 0
    finite_before = finite_after = None
    for pattern in patterns:
        for path in sorted(out_root.glob(pattern)):
            da = _read_nc(path)
            if "lat" not in da.coords or "lon" not in da.coords:
                n_skip += 1
                continue
            if finite_before is None and "agl1000" in path.as_posix().replace("\\", "/"):
                finite_before = float(np.mean(np.isfinite(np.asarray(da.values, float))))
            cropped = crop_da_to_domain(da, dom)
            if cropped.lat.size < 2 or cropped.lon.size < 2:
                raise RuntimeError(f"裁剪后网格过小: {path}")
            if finite_after is None and "agl1000" in path.as_posix().replace("\\", "/"):
                finite_after = float(np.mean(np.isfinite(np.asarray(cropped.values, float))))
            var_name = cropped.name or path.stem
            cropped.attrs["case_domain"] = dom["label"]
            cropped.attrs["lon_min"] = dom["lon_min"]
            cropped.attrs["lon_max"] = dom["lon_max"]
            cropped.attrs["lat_min"] = dom["lat_min"]
            cropped.attrs["lat_max"] = dom["lat_max"]
            _write_nc(cropped, path, var_name)
            n_ok += 1

    # 细网格 DEM 一并裁到同框，供后续 OE 用
    dem_src = RESOURCE / "ancil" / "HGT_M_1KM_CHINA.nc"
    dem_dst = out_root / "ancil" / "HGT_M_1KM_case_domain.nc"
    if dem_src.exists():
        dem = crop_da_to_domain(_read_nc(dem_src), dom)
        dem.attrs["case_domain"] = dom["label"]
        _write_nc(dem, dem_dst, dem.name or "surface_altitude")
        print(f"DEM → {dem_dst} shape lat/lon={dem.lat.size}/{dem.lon.size}")

    # 实况 CMPAS：保留原库全域，裁剪副本写入 ECD1D/CMPAS_APCP
    cmpas_src = RESOURCE / "CMPAS_APCP"
    cmpas_dst = out_root / "CMPAS_APCP"
    n_cmpas = 0
    if cmpas_src.exists():
        for path in sorted(cmpas_src.rglob("BJT_*.nc")):
            out = cmpas_dst / path.relative_to(cmpas_src)
            da = crop_da_to_domain(_read_nc(path), dom)
            da.attrs["case_domain"] = dom["label"]
            _write_nc(da, out, da.name or "precipitation")
            n_cmpas += 1
        print(f"CMPAS → {cmpas_dst} n={n_cmpas}")
        n_ok += n_cmpas

    readme = out_root / "meta" / "README.md"
    extra = [
        "",
        "## 个例空间域（已裁剪）",
        f"- 标签：`{dom['label']}`",
        f"- 经度：`{dom['lon_min']}`–`{dom['lon_max']}` °E",
        f"- 纬度：`{dom['lat_min']}`–`{dom['lat_max']}` °N",
        "- 目的：覆盖浙闽赣湘粤桂琼强降水，排除青藏高原 AGL1000 缺测区",
        f"- 裁剪文件数：{n_ok}（跳过 {n_skip}）",
    ]
    if finite_before is not None and finite_after is not None:
        extra.append(
            f"- AGL 样例有效比例：裁前 {finite_before:.3f} → 裁后 {finite_after:.3f}"
        )
    if readme.exists():
        text = readme.read_text(encoding="utf-8")
        if "## 个例空间域" in text:
            text = text.split("## 个例空间域")[0].rstrip() + "\n"
        readme.write_text(text + "\n".join(extra) + "\n", encoding="utf-8")
    else:
        readme.parent.mkdir(parents=True, exist_ok=True)
        readme.write_text("\n".join(extra).lstrip() + "\n", encoding="utf-8")

    domain_json = out_root / "meta" / "case_domain.csv"
    with domain_json.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["label", "lon_min", "lon_max", "lat_min", "lat_max", "note"],
        )
        w.writeheader()
        w.writerow(
            {
                "label": dom["label"],
                "lon_min": dom["lon_min"],
                "lon_max": dom["lon_max"],
                "lat_min": dom["lat_min"],
                "lat_max": dom["lat_max"],
                "note": "exclude_Tibetan_Plateau_AGL_gap; keep_SE_China_heavy_rain",
            }
        )

    summary = {
        "n_ok": n_ok,
        "n_skip": n_skip,
        "finite_before": finite_before,
        "finite_after": finite_after,
        "domain": dom,
    }
    print(
        f"裁剪完成 domain={dom['label']} "
        f"{dom['lon_min']}-{dom['lon_max']}E / {dom['lat_min']}-{dom['lat_max']}N "
        f"files={n_ok} finite {finite_before} -> {finite_after}"
    )
    return summary


if __name__ == "__main__":
    _ensure_repo_on_path()
    args = sys.argv[1:]
    if args and args[0] == "smoke":
        run_smoke()
    elif args and args[0] == "crop":
        crop_ecd1d_to_case_domain()
    else:
        run_batch()
        # 批量后默认裁到个例域，避免高原空缺进入后续 OE/检验
        crop_ecd1d_to_case_domain()
