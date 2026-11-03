#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""EMOS 概率订正 CLI（仿 ``lizi.py``：仅暴露 ``process``）。

数据约定
--------
统一六维 ``member, level, time, dtime, lat, lon``：

- 预报 ``time`` = 起报；实况 ``time`` = 有效时间；实况 ``dtime`` = 0
- 格点：NetCDF → ``meteva_base.read_griddata_from_nc``
- 站点：CSV → ``meteva_base.read_stadata_from_csv(..., drop_same_id=False)``
- 静态场路径列表顺序即 ``additional_fields`` 顺序；训练与订正须一致

输出
----
``dict`` 含 ``coefficients`` / ``ensemble`` / ``probability`` / ``percentiles``。
"""

from __future__ import annotations

import contextlib
import io
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import meteva_base as meb
import numpy as np
import pandas as pd
import xarray as xr

# 包根目录；核心代码在 src/emos_*.py
_PKG = Path(__file__).resolve().parents[1]
_SRC = _PKG / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

# __main__ 演示：概率订正阈值（与数据同单位，示例为 Kelvin）
THRESHOLDS = [285.0, 288.0, 292.0]
# __main__ 演示：订正后输出的分位（百分位，0–100）
OUTPUT_PERCENTILES = [10.0, 50.0, 90.0]
# 内部：集合 → 输入分位场时用的百分位（min / 中位 / max）
_INPUT_PERCENTILES = np.array([0.0, 50.0, 100.0], dtype=np.float32)
# 内部：站点 CSV 的维度列名；读表时这些列不转成 float32
_DIM_COLS = ("member", "level", "time", "dtime", "lat", "lon")


@contextlib.contextmanager
def _quiet_meteva():
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        yield


def _read_grid_nc(path: Path) -> xr.DataArray:
    with _quiet_meteva():
        da = meb.read_griddata_from_nc(str(path))
    if da is None:
        raise FileNotFoundError(f"read_griddata_from_nc failed: {path}")
    if hasattr(da, "load"):
        da = da.load()
    if "member" in da.coords:
        try:
            da = da.assign_coords(member=da["member"].astype(np.int32))
        except (TypeError, ValueError):
            pass
    return da


def _read_spot_csv(path: Path) -> pd.DataFrame:
    with _quiet_meteva():
        sta = meb.read_stadata_from_csv(str(path), drop_same_id=False, show=False)
    if sta is None:
        raise FileNotFoundError(f"read_stadata_from_csv failed: {path}")
    df = sta.copy()
    if "time" in df.columns:
        df["time"] = pd.to_datetime(df["time"])
    for col in df.columns:
        if col not in _DIM_COLS and col != "id":
            df[col] = df[col].astype(np.float32)
    if "id" in df.columns:
        df = df.drop(columns=["id"])
    return df


def _read_field(path: str):
    p = Path(path)
    if p.suffix.lower() == ".nc":
        return _read_grid_nc(p)
    if p.suffix.lower() == ".csv":
        return _read_spot_csv(p)
    raise ValueError(f"unsupported file type: {path} (use .nc or .csv)")


def _apply_slice(hf):
    if isinstance(hf, pd.DataFrame):
        return hf.loc[hf["time"] == hf["time"].max()].copy()
    fc = hf.isel(time=-1)
    if "time" not in fc.dims:
        fc = fc.expand_dims(time=[hf["time"].values[-1]])
    return fc


def _percentile_forecast(fc) -> xr.DataArray:
    from emos_grid import normalize_grid_input

    if isinstance(fc, pd.DataFrame):
        fc = normalize_grid_input(fc)
    axis = fc.dims.index("member")
    stacked = np.moveaxis(fc.values, axis, 0)
    data = np.percentile(stacked, _INPUT_PERCENTILES, axis=0).astype(np.float32)
    other = [d for d in fc.dims if d != "member"]
    coords = {c: fc[c] for c in fc.coords if c != "member"}
    coords["percentile"] = (
        "percentile",
        _INPUT_PERCENTILES,
        {"units": "%"},
    )
    return xr.DataArray(
        data,
        dims=["percentile"] + other,
        coords=coords,
        attrs=dict(fc.attrs),
        name=fc.name or "air_temperature",
    )


def _save_dataset(ds: xr.Dataset, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    out = ds.copy(deep=True)
    for k in list(out.attrs):
        if not isinstance(out.attrs[k], (str, int, float, np.ndarray, list)):
            out.attrs[k] = str(out.attrs[k])
    drop_coords = []
    for name in list(out.coords):
        dtype = out[name].dtype
        if np.issubdtype(dtype, np.timedelta64) or np.issubdtype(dtype, np.datetime64):
            if name not in out.dims:
                drop_coords.append(name)
            else:
                out[name].attrs.pop("units", None)
    if drop_coords:
        out = out.drop_vars(drop_coords)
    out.to_netcdf(path)
    print(f"  saved → {path}")


def process(
    historic_forecast_path: str,
    truth_path: str,
    forecast_path: Optional[str] = None,
    static_paths: Optional[Sequence[str]] = None,
    output_dir: Optional[str] = None,
    *,
    distribution: str = "norm",
    predictor: str = "mean",
    point_by_point: bool = True,
    use_default_initial_guess: bool = True,
    thresholds: Optional[Sequence[float]] = None,
    thresholds_operator: str = "below",
    percentiles: Optional[Sequence[float]] = None,
    realizations_count: Optional[int] = None,
) -> Dict[str, Optional[xr.Dataset]]:
    """训练 EMOS 系数并对集合预报做订正（集合 / 可选概率 / 可选分位）。

    参数
    ----------
    historic_forecast_path :
        历史集合预报路径（``.nc`` 或 ``.csv``）。
    truth_path :
        对应实况路径。
    forecast_path :
        待订正预报；为 None 时用历史预报的最后一起报切片。
    static_paths :
        静态因子路径列表；可为 None。
    output_dir :
        若给定则写 NetCDF；为 None 不写文件。
    distribution :
        ``norm`` 或 ``truncnorm``。
    predictor :
        ``mean`` 等。
    point_by_point :
        True 逐站/逐格点；False 全场共用系数。
    use_default_initial_guess :
        是否使用默认初值。
    thresholds :
        概率阈值（K）；None 跳过概率输出。
    thresholds_operator :
        ``below`` / ``above``。
    percentiles :
        输出分位；None 跳过分位输出。
    realizations_count :
        分位路径 ECC 成员数。

    返回
    -------
    dict
        ``coefficients`` / ``ensemble`` / ``probability`` / ``percentiles``。
    """
    from emos_calibration import apply_emos, create_prob_template, train_emos

    hf = _read_field(historic_forecast_path)
    truth = _read_field(truth_path)
    static = [_read_field(p) for p in static_paths] if static_paths else None
    apply_fc = _read_field(forecast_path) if forecast_path else _apply_slice(hf)

    coeffs = train_emos(
        hf,
        truth,
        additional_fields=static,
        distribution=distribution,
        predictor=predictor,
        point_by_point=point_by_point,
        use_default_initial_guess=use_default_initial_guess,
    )
    ensemble = apply_emos(
        forecast=apply_fc, coefficients=coeffs, additional_fields=static
    )

    probability: Optional[xr.Dataset] = None
    if thresholds is not None:
        prob_tpl = create_prob_template(
            apply_fc, list(thresholds), thresholds_operator
        )
        probability = apply_emos(
            forecast=apply_fc,
            coefficients=coeffs,
            additional_fields=static,
            prob_template=prob_tpl,
        )

    percentiles_out: Optional[xr.Dataset] = None
    if percentiles is not None:
        pct_in = _percentile_forecast(apply_fc)
        n_real = realizations_count or len(_INPUT_PERCENTILES)
        percentiles_out = apply_emos(
            forecast=pct_in,
            coefficients=coeffs,
            additional_fields=static,
            realizations_count=n_real,
            percentiles=list(percentiles),
        )

    if output_dir is not None:
        out = Path(output_dir)
        _save_dataset(coeffs, out / "emos_coefficients.nc")
        _save_dataset(ensemble, out / "emos_ensemble.nc")
        if probability is not None:
            _save_dataset(probability, out / "emos_probability.nc")
        if percentiles_out is not None:
            _save_dataset(percentiles_out, out / "emos_percentiles.nc")

    return {
        "coefficients": coeffs,
        "ensemble": ensemble,
        "probability": probability,
        "percentiles": percentiles_out,
    }


def main() -> None:
    """定义输入/输出路径并调用 ``process``（默认 ``resource/`` 样例）。"""
    data_dir = _PKG / "resource" / "cli_input"
    output_dir = _PKG / "resource" / "cli_output"
    result = process(
        str(data_dir / "hf.csv"),
        str(data_dir / "truth.csv"),
        forecast_path=None,
        static_paths=[str(data_dir / "static_altitude.csv")],
        output_dir=str(output_dir),
        distribution="norm",
        predictor="mean",
        point_by_point=True,
        thresholds=THRESHOLDS,
        thresholds_operator="below",
        percentiles=OUTPUT_PERCENTILES,
    )
    print("EMOS process 完成:")
    for key, ds in result.items():
        if ds is None:
            print(f"  {key}: None")
        else:
            print(
                f"  {key}: {{{', '.join(f'{k}: {dict(ds[k].sizes)}' for k in ds.data_vars)}}}"
            )


if __name__ == "__main__":
    main()
