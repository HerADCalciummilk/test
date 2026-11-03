#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""SAMOS 概率订正 CLI（仿 ``lizi.py``：仅暴露 ``process``）。

数据约定
--------
统一六维 ``member, level, time, dtime, lat, lon``（与 EMOS 相同）。

- 格点：``meteva_base.read_griddata_from_nc``
- 站点：``meteva_base.read_stadata_from_csv(..., drop_same_id=False)``
- **静态因子只进 GAM**；异常 EMOS 默认 ``emos_additional_fields=None``

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

# 包根目录；核心代码在 src/samos_*.py / gam_*.py，依赖兄弟包 emos_probability_calibration/src
_PKG = Path(__file__).resolve().parents[1]
_SRC = _PKG / "src"
_EMOS_SRC = _PKG.parent / "emos_probability_calibration" / "src"
for _p in (_EMOS_SRC, _SRC):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

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


def _infer_gam_features(
    static_paths: Optional[Sequence[str]],
    gam_features: Optional[Sequence[str]],
) -> List[str]:
    if gam_features is not None:
        return list(gam_features)
    features = ["lat", "lon"]
    if not static_paths:
        return features
    features.extend(Path(p).stem.replace("static_", "") for p in static_paths)
    return features


def process(
    historic_forecast_path: str,
    truth_path: str,
    forecast_path: Optional[str] = None,
    static_paths: Optional[Sequence[str]] = None,
    output_dir: Optional[str] = None,
    *,
    gam_features: Optional[Sequence[str]] = None,
    window_length: int = 3,
    max_iter: int = 30,
    distribution: str = "norm",
    predictor: str = "mean",
    point_by_point: bool = True,
    use_default_initial_guess: bool = True,
    thresholds: Optional[Sequence[float]] = None,
    thresholds_operator: str = "below",
    percentiles: Optional[Sequence[float]] = None,
    realizations_count: Optional[int] = None,
) -> Dict[str, Optional[xr.Dataset]]:
    """训练 GAM + 异常空间 EMOS（SAMOS），并对预报订正。

    参数
    ----------
    historic_forecast_path / truth_path :
        历史预报与实况路径（``.nc`` / ``.csv``）。
    forecast_path :
        待订正预报；None 则用历史预报最后一起报。
    static_paths :
        GAM 静态因子路径列表。
    output_dir :
        输出目录；None 不写文件。
    gam_features :
        GAM 特征名；None 时为 ``lat, lon`` + static 文件名推断。
    window_length :
        气候滚动窗（奇数；短序列建议 3）。
    max_iter :
        pyGAM 最大迭代次数。
    distribution / predictor / point_by_point / use_default_initial_guess :
        异常空间 EMOS 参数。
    thresholds / thresholds_operator :
        概率订正；thresholds 为 None 则跳过。
    percentiles / realizations_count :
        分位订正；percentiles 为 None 则跳过。

    返回
    -------
    dict
        ``coefficients`` / ``ensemble`` / ``probability`` / ``percentiles``。
    """
    from emos_calibration import create_prob_template
    from gam_calibration import train_gams
    from samos_calibration import apply_samos, train_samos

    hf = _read_field(historic_forecast_path)
    truth = _read_field(truth_path)
    static = [_read_field(p) for p in static_paths] if static_paths else None
    apply_fc = _read_field(forecast_path) if forecast_path else _apply_slice(hf)

    features = _infer_gam_features(static_paths, gam_features)
    model_spec = [["linear", [i], {}] for i in range(len(features))]

    fg = train_gams(
        hf,
        features,
        model_spec,
        additional_fields=static,
        max_iter=max_iter,
        window_length=window_length,
    )
    tg = train_gams(
        truth,
        features,
        model_spec,
        additional_fields=static,
        max_iter=max_iter,
        window_length=window_length,
    )
    if fg is None or tg is None:
        raise RuntimeError(
            "train_gams 返回 None：请减小 window_length 或增加训练时段。"
        )

    coeffs = train_samos(
        hf,
        truth,
        fg,
        tg,
        features,
        gam_additional_fields=static,
        emos_additional_fields=None,
        distribution=distribution,
        predictor=predictor,
        point_by_point=point_by_point,
        use_default_initial_guess=use_default_initial_guess,
    )
    apply_kw = dict(
        forecast_gams=fg,
        truth_gams=tg,
        emos_coefficients=coeffs,
        gam_features=features,
        gam_additional_fields=static,
        emos_additional_fields=None,
    )
    ensemble = apply_samos(forecast=apply_fc, **apply_kw)

    probability: Optional[xr.Dataset] = None
    if thresholds is not None:
        prob_tpl = create_prob_template(
            apply_fc, list(thresholds), thresholds_operator
        )
        probability = apply_samos(
            forecast=apply_fc, prob_template=prob_tpl, **apply_kw
        )

    percentiles_out: Optional[xr.Dataset] = None
    if percentiles is not None:
        pct_in = _percentile_forecast(apply_fc)
        n_real = realizations_count or len(_INPUT_PERCENTILES)
        percentiles_out = apply_samos(
            forecast=pct_in,
            realizations_count=n_real,
            percentiles=list(percentiles),
            **apply_kw,
        )

    if output_dir is not None:
        out = Path(output_dir)
        _save_dataset(coeffs, out / "samos_coefficients.nc")
        _save_dataset(ensemble, out / "samos_ensemble.nc")
        if probability is not None:
            _save_dataset(probability, out / "samos_probability.nc")
        if percentiles_out is not None:
            _save_dataset(percentiles_out, out / "samos_percentiles.nc")

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
        gam_features=None,
        window_length=3,
        max_iter=30,
        distribution="norm",
        predictor="mean",
        point_by_point=True,
        thresholds=THRESHOLDS,
        thresholds_operator="below",
        percentiles=OUTPUT_PERCENTILES,
    )
    print("SAMOS process 完成:")
    for key, ds in result.items():
        if ds is None:
            print(f"  {key}: None")
        else:
            print(
                f"  {key}: {{{', '.join(f'{k}: {dict(ds[k].sizes)}' for k in ds.data_vars)}}}"
            )


if __name__ == "__main__":
    main()
