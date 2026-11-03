#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""将 ``threshold_probability_conversion/test_data`` 下已有 Iris/NetCDF 样例转为 meb 六维 CLI 输入。

本脚本**不**从上游 ``improver_test_data-master`` 复制文件；官方 ``input.nc`` /
``kgo.nc`` / JSON 等须事先放在 ``test_data/`` 对应场景目录中。

写出（投影 meb）::

- ``test_data/basic/cli_inputs/input_meb.nc``
- ``test_data/vicinity/cli_inputs/input_meb.nc``、``landmask_meb.nc``
- ``test_data/vicinity_masked/cli_inputs/input_meb.nc``（海点 NaN + ``preserve_nan_fill``）

写出（Notebook 经纬对照，仅当前 notebook 用到的场景）::

- ``basic/latlon/input.nc`` + ``cli_inputs/input_meb.nc``（原方法支持经纬阈值）
- ``basic/latlon/kgo.nc``、``multiple_thresholds/latlon/kgo.nc``、``fuzzy_factor/latlon/kgo.nc``
- ``vicinity/latlon/cli_inputs/input_meb.nc``（仅迁后；原 vicinity 需等面积投影；约 ``0.02°``）
- ``vicinity/latlon/kgo.nc``（投影 KGO 重网格，供对照）

用法（仓库根目录）::

    python threshold_probability_conversion/cli/preprocess_test_data.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import meteva_base as meb
import numpy as np
import xarray as xr

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PACKAGE_ROOT.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

TEST_DATA = PACKAGE_ROOT / "test_data"
LATLON_RESOLUTION = 0.05
# vicinity 官方投影格距约 2 km；0.05° 经纬过粗会使 10 km 邻域格点数偏少（约 2 格）
VICINITY_LATLON_RESOLUTION = 0.02
LATLON_GRID_MAPPING = json.dumps(
    {"grid_mapping_name": "latitude_longitude"}, ensure_ascii=False
)

MEMBER_LIKE = ("realization", "member")
SPATIAL_RENAME = {
    "projection_y_coordinate": "lat",
    "projection_x_coordinate": "lon",
    "latitude": "lat",
    "longitude": "lon",
}
DEFAULT_TIME = "2017-02-01T03:00:00"


def _attach_grid_mapping_attrs(da: xr.DataArray, ds: xr.Dataset) -> None:
    """从 CF ``grid_mapping`` 变量写入 ``attrs['grid_mapping_attrs']``。"""
    grid_mapping_name = da.attrs.get("grid_mapping")
    if not isinstance(grid_mapping_name, str) or grid_mapping_name not in ds.variables:
        for other_name in ds.data_vars:
            cand = ds[other_name].attrs.get("grid_mapping")
            if isinstance(cand, str) and cand in ds.variables:
                grid_mapping_name = cand
                break
    if not isinstance(grid_mapping_name, str) or grid_mapping_name not in ds.variables:
        return
    mapping_attrs_raw = dict(ds[grid_mapping_name].attrs)
    mapping_attrs_json_ready = {}
    for key, value in mapping_attrs_raw.items():
        if isinstance(value, np.ndarray):
            mapping_attrs_json_ready[key] = value.tolist()
        elif isinstance(value, np.generic):
            mapping_attrs_json_ready[key] = value.item()
        else:
            mapping_attrs_json_ready[key] = value
    da.attrs["grid_mapping_attrs"] = json.dumps(
        mapping_attrs_json_ready, ensure_ascii=False
    )


def _ensure_projected_spatial_units(da: xr.DataArray) -> xr.DataArray:
    """等面积投影 meb：``grid_mapping_attrs`` 配套空间坐标 ``units=m``。

    ``latitude_longitude`` 等地理网格不改单位（保持 degree）。
    """
    raw = da.attrs.get("grid_mapping_attrs")
    if not raw:
        return da
    try:
        attrs = json.loads(raw) if isinstance(raw, str) else dict(raw)
    except (TypeError, json.JSONDecodeError, ValueError):
        return da
    name = str(attrs.get("grid_mapping_name", ""))
    if "latitude_longitude" in name:
        return da
    out = da.copy(deep=True)
    out.coords["lat"].attrs["units"] = "m"
    out.coords["lon"].attrs["units"] = "m"
    return out


def _mark_geographic_meb(da: xr.DataArray) -> xr.DataArray:
    """经纬 meb：度单位 + latitude_longitude 映射属性。"""
    out = da.copy(deep=True)
    out.attrs["grid_mapping_attrs"] = LATLON_GRID_MAPPING
    out.attrs.pop("grid_mapping", None)
    out.coords["lat"].attrs["units"] = "degrees_north"
    out.coords["lon"].attrs["units"] = "degrees_east"
    return out


def _load_primary(path: Path) -> xr.DataArray:
    """读取主变量；若含 Iris 掩码则保留 MaskedArray。"""
    try:
        import iris

        cube = iris.load_cube(str(path))
        data = np.ma.asarray(cube.data)
        dim_names = [cube.coord(axis=ax).name() for ax in ("y", "x")]
        if cube.ndim == 3:
            member_name = next(
                c.name()
                for c in cube.coords(dim_coords=True)
                if c.name() not in dim_names
            )
            dims = [member_name, dim_names[0], dim_names[1]]
            coords = {
                member_name: cube.coord(member_name).points,
                dim_names[0]: cube.coord(axis="y").points,
                dim_names[1]: cube.coord(axis="x").points,
            }
        else:
            dims = dim_names
            coords = {
                dim_names[0]: cube.coord(axis="y").points,
                dim_names[1]: cube.coord(axis="x").points,
            }
        for crd in cube.coords():
            if crd.name() in coords:
                coords[crd.name()] = crd.points
        da = xr.DataArray(
            data,
            dims=dims,
            coords=coords,
            name=cube.name(),
            attrs=dict(cube.attributes),
        )
        if hasattr(cube, "units"):
            da.attrs["units"] = str(cube.units)
        try:
            ds = xr.open_dataset(path, decode_timedelta=False)
            try:
                _attach_grid_mapping_attrs(da, ds)
            finally:
                ds.close()
        except Exception:
            pass
        return da
    except Exception:
        pass

    ds = xr.open_dataset(path, decode_timedelta=False)
    try:
        for name, da in ds.data_vars.items():
            if "bnds" not in name and name not in (
                "lambert_azimuthal_equal_area",
                "latitude_longitude",
            ):
                _attach_grid_mapping_attrs(da, ds)
                return da
        raise ValueError(f"未在 {path} 找到主变量")
    finally:
        ds.close()


def to_meb6d(da: xr.DataArray) -> xr.DataArray:
    """投影/地理二维或含 realization 的场 → meb 六维。"""
    work = da.copy()
    rename = {k: v for k, v in SPATIAL_RENAME.items() if k in work.dims}
    if rename:
        work = work.rename(rename)

    member_dim = next((d for d in MEMBER_LIKE if d in work.dims), None)
    drop = [d for d in work.dims if d not in {member_dim, "lat", "lon"} - {None}]
    for d in drop:
        if d in work.dims and work.sizes[d] == 1:
            work = work.isel({d: 0}, drop=True)

    if member_dim is None:
        values = np.asarray(work.values, dtype=np.float32)
        if np.ma.isMaskedArray(work.values):
            values = np.ma.asarray(work.values, dtype=np.float32)
        if values.ndim != 2:
            values = np.squeeze(values)
        n_lat, n_lon = values.shape
        values_6d = values.reshape(1, 1, 1, 1, n_lat, n_lon)
        if np.ma.isMaskedArray(values):
            values_6d = np.ma.asarray(values_6d, dtype=np.float32)
        member_coord = np.array([0], dtype=np.int32)
    else:
        work = work.transpose(member_dim, "lat", "lon")
        if np.ma.isMaskedArray(work.values):
            values = np.ma.asarray(work.values, dtype=np.float32)
        else:
            values = np.asarray(work.values, dtype=np.float32)
        n_member, n_lat, n_lon = values.shape
        values_6d = values.reshape(n_member, 1, 1, 1, n_lat, n_lon)
        if np.ma.isMaskedArray(values):
            values_6d = np.ma.asarray(values_6d, dtype=np.float32)
        member_coord = np.asarray(work.coords[member_dim].values)
        if np.issubdtype(member_coord.dtype, np.number):
            member_coord = member_coord.astype(np.int32)

    lat_vals = (
        np.asarray(work.coords["lat"].values, dtype=np.float32)
        if "lat" in work.coords
        else np.arange(n_lat, dtype=np.float32)
    )
    lon_vals = (
        np.asarray(work.coords["lon"].values, dtype=np.float32)
        if "lon" in work.coords
        else np.arange(n_lon, dtype=np.float32)
    )
    lat_attrs = dict(work.coords["lat"].attrs) if "lat" in work.coords else {}
    lon_attrs = dict(work.coords["lon"].attrs) if "lon" in work.coords else {}

    time_val = np.array([DEFAULT_TIME], dtype="datetime64[ns]")
    if "time" in da.coords:
        try:
            time_val = np.array(
                [np.asarray(da.coords["time"].values).ravel()[0]],
                dtype="datetime64[ns]",
            )
        except Exception:
            pass

    out = xr.DataArray(
        values_6d,
        dims=("member", "level", "time", "dtime", "lat", "lon"),
        coords={
            "member": member_coord,
            "level": np.array([0], dtype=np.float32),
            "time": time_val,
            "dtime": np.array([0], dtype=np.int32),
            "lat": lat_vals,
            "lon": lon_vals,
        },
        name=da.name or "air_temperature",
        attrs=dict(da.attrs),
    )
    if lat_attrs:
        out.coords["lat"].attrs.update(lat_attrs)
    if lon_attrs:
        out.coords["lon"].attrs.update(lon_attrs)
    if "units" not in out.attrs:
        out.attrs["units"] = str(da.attrs.get("units", "K"))
    meb.set_griddata_attrs(
        out,
        units=str(out.attrs.get("units", "K")),
        is_default=True,
    )
    return _ensure_projected_spatial_units(out)


def _landmask_to_meb2d(path: Path) -> xr.DataArray:
    """海陆掩码 → (lat, lon) DataArray。"""
    da = _load_primary(path)
    work = da.copy()
    rename = {k: v for k, v in SPATIAL_RENAME.items() if k in work.dims}
    if rename:
        work = work.rename(rename)
    for d in list(work.dims):
        if d not in {"lat", "lon"} and work.sizes[d] == 1:
            work = work.isel({d: 0}, drop=True)
    work = work.transpose("lat", "lon")
    out = xr.DataArray(
        np.asarray(work.values, dtype=np.float32),
        dims=("lat", "lon"),
        coords={
            "lat": np.asarray(work.coords["lat"].values, dtype=np.float32),
            "lon": np.asarray(work.coords["lon"].values, dtype=np.float32),
        },
        name=work.name or "landmask",
        attrs=dict(work.attrs),
    )
    if "lat" in work.coords:
        out.coords["lat"].attrs.update(dict(work.coords["lat"].attrs))
    if "lon" in work.coords:
        out.coords["lon"].attrs.update(dict(work.coords["lon"].attrs))
    return _ensure_projected_spatial_units(out)


def _apply_spatial_nan_mask(meb_da: xr.DataArray, spatial_mask: np.ndarray) -> xr.DataArray:
    """按二维空间掩码把无效格点写为 NaN（shape 与 ``lat/lon`` 一致）。"""
    values = np.asarray(meb_da.values, dtype=np.float32).copy()
    mask = np.asarray(spatial_mask, dtype=bool)
    if mask.shape != values.shape[-2:]:
        raise ValueError(
            f"空间掩码形状须与 meb 场 lat/lon 一致，mask={mask.shape}, "
            f"data={values.shape[-2:]}"
        )
    lead = values.ndim - 2
    expanded = mask.reshape((1,) * lead + mask.shape)
    values = np.where(expanded, np.nan, values).astype(np.float32)
    return meb_da.copy(data=values)


def save_meb6d_to_nc(
    data: xr.DataArray,
    dst_path: Path,
    *,
    preserve_nan_fill: bool = False,
    zlib: bool = True,
) -> None:
    """写出 meb NetCDF。

    ``preserve_nan_fill=True`` 时 encoding 设 ``_FillValue=None``，避免 xarray/NetCDF
    默认 fill 把文件中的 NaN 改成别的数（与 nbhood ``save_meb6d_to_nc`` 一致）。
    """
    path = Path(dst_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    normalized = data.copy(deep=True)
    normalized.attrs = {
        k: ("" if v is None else v) for k, v in dict(normalized.attrs).items()
    }
    var_name = normalized.name if normalized.name else "data"
    tmp = path.with_suffix(path.suffix + ".tmp")
    if tmp.exists():
        tmp.unlink()
    ds = normalized.to_dataset(name=var_name)
    encoding: dict = {var_name: {"dtype": "float32"}}
    if preserve_nan_fill:
        encoding[var_name]["_FillValue"] = None
    if zlib:
        encoding[var_name]["zlib"] = True
        encoding[var_name]["complevel"] = 4
    ds.to_netcdf(tmp, encoding=encoding)
    tmp.replace(path)


def preprocess_basic() -> None:
    """``basic/input.nc`` → ``basic/cli_inputs/input_meb.nc``。"""
    basic_src = TEST_DATA / "basic" / "input.nc"
    if not basic_src.is_file():
        raise FileNotFoundError(f"缺少本地样例: {basic_src}")

    da = _load_primary(basic_src)
    if "units" not in da.attrs:
        da.attrs["units"] = "K"
    meb_da = to_meb6d(da)
    # 避免 meb.write 的 int32+scale_factor 打包损失阈值附近的 float32 精度
    save_meb6d_to_nc(
        meb_da.astype("float32"),
        TEST_DATA / "basic" / "cli_inputs" / "input_meb.nc",
        preserve_nan_fill=False,
    )


def preprocess_vicinity() -> None:
    """``vicinity/{input,landmask}.nc`` → ``vicinity/cli_inputs/*.nc``。"""
    vic_root = TEST_DATA / "vicinity"
    input_src = vic_root / "input.nc"
    landmask_src = vic_root / "landmask.nc"
    if not input_src.is_file():
        print(f"跳过 vicinity：缺少 {input_src}")
        return
    if not landmask_src.is_file():
        print(f"跳过 vicinity：缺少 {landmask_src}")
        return

    cli_in = vic_root / "cli_inputs"
    da = _load_primary(input_src)
    if "units" not in da.attrs:
        da.attrs["units"] = "m s-1"
    save_meb6d_to_nc(
        to_meb6d(da).astype("float32"),
        cli_in / "input_meb.nc",
        preserve_nan_fill=False,
    )

    landmask = _landmask_to_meb2d(landmask_src).rename("landmask")
    save_meb6d_to_nc(
        landmask.astype("float32"),
        cli_in / "landmask_meb.nc",
        preserve_nan_fill=False,
    )


def preprocess_vicinity_masked() -> None:
    """``vicinity_masked/masked_precip.nc`` → 海点 NaN 的 meb 输入。"""
    masked_root = TEST_DATA / "vicinity_masked"
    masked_src = masked_root / "masked_precip.nc"
    if not masked_src.is_file():
        print(f"跳过 vicinity_masked：缺少 {masked_src}")
        return

    import iris

    masked_da = _load_primary(masked_src)
    if "units" not in masked_da.attrs:
        masked_da.attrs["units"] = "m s-1"
    masked_meb = to_meb6d(masked_da)
    cube = iris.load_cube(str(masked_src))
    spatial_mask = np.ma.getmaskarray(np.ma.asarray(cube.data))
    while spatial_mask.ndim > 2:
        spatial_mask = spatial_mask[0]
    masked_meb = _apply_spatial_nan_mask(masked_meb, spatial_mask)

    save_meb6d_to_nc(
        masked_meb.astype("float32"),
        masked_root / "cli_inputs" / "input_meb.nc",
        preserve_nan_fill=True,
    )


def build_regular_latlon_target(cube, resolution: float = LATLON_RESOLUTION):
    """由投影场角点范围构造规则经纬目标网格。"""
    import cartopy.crs as ccrs
    from iris.coord_systems import GeogCS
    from iris.coords import DimCoord
    from iris.cube import Cube

    cs = cube.coord_system()
    if cs is None:
        raise ValueError("Cube 没有坐标系统，无法投影到经纬。")
    src_crs = cs.as_cartopy_crs()
    target_crs = ccrs.PlateCarree()
    y_coord = cube.coord(axis="y")
    x_coord = cube.coord(axis="x")
    xx, yy = np.meshgrid(
        [x_coord.points[0], x_coord.points[-1]],
        [y_coord.points[0], y_coord.points[-1]],
    )
    transform = target_crs.transform_points(src_crs, xx, yy)
    lat_min, lat_max = float(transform[:, :, 1].min()), float(transform[:, :, 1].max())
    lon_min, lon_max = float(transform[:, :, 0].min()), float(transform[:, :, 0].max())
    target_lat = np.arange(
        lat_min, lat_max + resolution * 0.5, resolution, dtype=np.float32
    )
    target_lon = np.arange(
        lon_min, lon_max + resolution * 0.5, resolution, dtype=np.float32
    )
    geog = GeogCS(6371229.0)
    lat_coord = DimCoord(
        target_lat, standard_name="latitude", units="degrees", coord_system=geog
    )
    lon_coord = DimCoord(
        target_lon, standard_name="longitude", units="degrees", coord_system=geog
    )
    return Cube(
        np.zeros((target_lat.size, target_lon.size), dtype=np.float32),
        dim_coords_and_dims=[(lat_coord, 0), (lon_coord, 1)],
    )


def regrid_cube_to_target(cube, target_grid, *, scheme: str = "linear"):
    """投影 Cube → 规则经纬目标。"""
    from iris.analysis import Linear, Nearest

    if scheme == "nearest":
        regridder = Nearest(extrapolation_mode="extrapolate")
    else:
        regridder = Linear(extrapolation_mode="extrapolate")
    return cube.regrid(target_grid, regridder)


def save_iris_cube(cube, path: Path) -> None:
    """写出 Iris Cube NetCDF。"""
    import iris

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.parent / f".{path.stem}.tmp.nc"
    if tmp.exists():
        tmp.unlink()
    iris.save(cube, str(tmp))
    try:
        tmp.replace(path)
    except PermissionError as err:
        raise PermissionError(
            f"无法覆盖 {path}（可能被 Jupyter 或其他进程占用）。"
            f"临时文件已写至 {tmp}，请关闭占用后重试。"
        ) from err


def save_latlon_meb_from_cube(cube_path: Path, meb_path: Path, *, default_units: str) -> None:
    """经纬 Iris Cube → meb 六维。"""
    da = _load_primary(cube_path)
    if "units" not in da.attrs:
        da.attrs["units"] = default_units
    meb_da = _mark_geographic_meb(to_meb6d(da))
    save_meb6d_to_nc(meb_da.astype("float32"), meb_path, preserve_nan_fill=False)


def preprocess_notebook_latlon() -> None:
    """Notebook 用场景：投影 → 规则经纬（输入 / KGO；vicinity 仅 meb+KGO）。"""
    import iris

    basic_src = TEST_DATA / "basic" / "input.nc"
    if not basic_src.is_file():
        raise FileNotFoundError(f"缺少本地样例: {basic_src}")

    basic_cube = iris.load_cube(str(basic_src))
    basic_target = build_regular_latlon_target(basic_cube)
    basic_latlon_dir = TEST_DATA / "basic" / "latlon"
    basic_latlon_input = basic_latlon_dir / "input.nc"
    save_iris_cube(
        regrid_cube_to_target(basic_cube, basic_target, scheme="linear"),
        basic_latlon_input,
    )
    save_latlon_meb_from_cube(
        basic_latlon_input,
        basic_latlon_dir / "cli_inputs" / "input_meb.nc",
        default_units="K",
    )

    # 与 basic 同网格的阈值 KGO：Nearest，避免 0/1 场被 Linear 抹成中间值
    kgo_jobs = (
        (TEST_DATA / "basic" / "kgo.nc", basic_latlon_dir / "kgo.nc"),
        (
            TEST_DATA / "multiple_thresholds" / "kgo.nc",
            TEST_DATA / "multiple_thresholds" / "latlon" / "kgo.nc",
        ),
        (
            TEST_DATA / "fuzzy_factor" / "kgo.nc",
            TEST_DATA / "fuzzy_factor" / "latlon" / "kgo.nc",
        ),
    )
    for src, dst in kgo_jobs:
        if not src.is_file():
            print(f"跳过经纬 KGO：缺少 {src}")
            continue
        save_iris_cube(
            regrid_cube_to_target(
                iris.load_cube(str(src)), basic_target, scheme="nearest"
            ),
            dst,
        )

    # vicinity：原方法米制邻域不支持经纬 Cube → 只写 meb 输入 + 重网格 KGO
    vic_src = TEST_DATA / "vicinity" / "input.nc"
    if not vic_src.is_file():
        print(f"跳过 vicinity 经纬：缺少 {vic_src}")
        return

    vic_cube = iris.load_cube(str(vic_src))
    vic_target = build_regular_latlon_target(
        vic_cube, resolution=VICINITY_LATLON_RESOLUTION
    )
    vic_latlon_dir = TEST_DATA / "vicinity" / "latlon"
    vic_latlon_tmp = vic_latlon_dir / "_tmp_input.nc"
    save_iris_cube(
        regrid_cube_to_target(vic_cube, vic_target, scheme="linear"),
        vic_latlon_tmp,
    )
    save_latlon_meb_from_cube(
        vic_latlon_tmp,
        vic_latlon_dir / "cli_inputs" / "input_meb.nc",
        default_units="m s-1",
    )
    if vic_latlon_tmp.is_file():
        vic_latlon_tmp.unlink()

    vic_kgo = TEST_DATA / "vicinity" / "kgo.nc"
    if vic_kgo.is_file():
        save_iris_cube(
            regrid_cube_to_target(
                iris.load_cube(str(vic_kgo)), vic_target, scheme="nearest"
            ),
            vic_latlon_dir / "kgo.nc",
        )


def main() -> None:
    sample = TEST_DATA / "basic" / "input.nc"
    if not sample.is_file():
        print(
            f"官方样例不存在：{sample}\n"
            "请先补充 test_data 后再运行预处理。"
        )
        return

    preprocess_basic()
    preprocess_vicinity()
    preprocess_vicinity_masked()
    preprocess_notebook_latlon()
    print("预处理完成：", TEST_DATA)


if __name__ == "__main__":
    main()
