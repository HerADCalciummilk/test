"""
查看 EMOS 训练/订正的输入输出结构（结果演示）。

数据::
  test_data/grid/   六维 NetCDF（member, level, time, dtime, lat, lon）
  test_data/spot/   六列 CSV（member, level, time, dtime, lat, lon + 数值列）

用法::
    python tests/emos_probability_calibration_main.py
    python tests/emos_probability_calibration_main.py --domain spot --static 1
"""

from __future__ import annotations

import argparse
import contextlib
import io
import sys
from pathlib import Path

import meteva_base as meb
import numpy as np
import pandas as pd
import xarray as xr

_PKG = Path(__file__).resolve().parents[1]
_SRC = _PKG / "src"
DATA_DIR = _PKG / "test_data"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from emos_calibration import apply_emos, create_prob_template, train_emos
from emos_grid import GRID_FORECAST_DIMS, GRID_MEMBER_DIM, normalize_grid_input

TRAINER_KWARGS = dict(
    distribution="norm",
    predictor="mean",
    point_by_point=True,
    use_default_initial_guess=True,
)
# 概率订正阈值（与数据同单位，示例为 Kelvin）
THRESHOLDS = [285.0, 288.0, 292.0]
# 订正后输出的分位（百分位，0–100）
OUTPUT_PERCENTILES = [10.0, 50.0, 90.0]
# 集合 → 输入分位场时用的百分位（min / 中位 / max）
INPUT_PERCENTILES = np.array([0.0, 50.0, 100.0], dtype=np.float32)
# 演示场景：0 / 1 / 2 个 static 协变量
STATIC_CASES = [("0 static", 0), ("1 static", 1), ("2 static", 2)]
# 站点长表维度列（打印/取值时排除这些列）
DIM_COLS = list(GRID_FORECAST_DIMS)


@contextlib.contextmanager
def _quiet_meteva():
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        yield


def _read_spot(path: Path) -> pd.DataFrame:
    with _quiet_meteva():
        sta = meb.read_stadata_from_csv(str(path), drop_same_id=False, show=False)
    if sta is None:
        raise FileNotFoundError(f"read_stadata_from_csv failed: {path}")
    df = sta.copy()
    if "time" in df.columns:
        df["time"] = pd.to_datetime(df["time"])
    for col in df.columns:
        if col not in DIM_COLS and col != "id":
            df[col] = df[col].astype(np.float32)
    if "id" in df.columns:
        df = df.drop(columns=["id"])
    return df


def _read_grid(path: Path) -> xr.DataArray:
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


def load_case(domain: str):
    """格点：meteva_base.read_griddata_from_nc；站点：read_stadata_from_csv。"""
    case_dir = DATA_DIR / domain
    if domain == "spot":
        return (
            _read_spot(case_dir / "hf.csv"),
            _read_spot(case_dir / "truth.csv"),
            [_read_spot(p) for p in sorted(case_dir.glob("static_*.csv"))],
        )
    if domain == "grid":
        return (
            _read_grid(case_dir / "hf.nc"),
            _read_grid(case_dir / "truth.nc"),
            [_read_grid(p) for p in sorted(case_dir.glob("static_*.nc"))],
        )
    raise ValueError(f"unknown domain: {domain!r}")


def _value_col(df: pd.DataFrame) -> str:
    return next(c for c in df.columns if c not in DIM_COLS)


def _print_dataframe(label: str, df: pd.DataFrame, indent: str = "  ") -> None:
    vcol = _value_col(df)
    n_stations = df[["lat", "lon"]].drop_duplicates().shape[0]
    print(f"{indent}{label:<22} rows={len(df):>4}  cols={list(df.columns)}  "
          f"stations={n_stations}  value={vcol!r}")
    print(f"{indent}  sample:")
    with pd.option_context("display.width", 120, "display.max_columns", 10):
        print(df.head(3).to_string(index=False, header=True).replace("\n", f"\n{indent}    "))


def _dim_summary(da: xr.DataArray | xr.Dataset) -> str:
    if isinstance(da, xr.Dataset):
        return _dim_summary(next(iter(da.data_vars.values())))
    parts = [f"{d}={da.sizes[d]}" for d in da.dims]
    return f"({', '.join(parts)})  {da.name!r}"


def _print_array(label: str, da: xr.DataArray, indent: str = "  ") -> None:
    finite = int(np.isfinite(da.values).sum())
    print(f"{indent}{label:<22} {_dim_summary(da)}  finite={finite}/{da.size}")


def _print_dataset(label: str, ds: xr.Dataset) -> None:
    print(f"  {label}")
    for vname, da in ds.data_vars.items():
        _print_array(f"  {vname}", da, indent="")


def _apply_slice(hf):
    if isinstance(hf, pd.DataFrame):
        return hf.loc[hf["time"] == hf["time"].max()].copy()
    fc = hf.isel(time=-1)
    if "time" not in fc.dims:
        fc = fc.expand_dims(time=[hf["time"].values[-1]])
    return fc


def _percentile_forecast(fc):
    if isinstance(fc, pd.DataFrame):
        fc = normalize_grid_input(fc)
    axis = fc.dims.index(GRID_MEMBER_DIM)
    stacked = np.moveaxis(fc.values, axis, 0)
    data = np.percentile(stacked, INPUT_PERCENTILES, axis=0).astype(np.float32)
    other = [d for d in fc.dims if d != GRID_MEMBER_DIM]
    coords = {c: fc[c] for c in fc.coords if c != GRID_MEMBER_DIM}
    coords["percentile"] = ("percentile", INPUT_PERCENTILES, {"units": "%"})
    return xr.DataArray(
        data,
        dims=["percentile"] + other,
        coords=coords,
        attrs=fc.attrs.copy(),
        name=fc.name or "air_temperature",
    )


def _print_coefficients(coeffs: xr.Dataset) -> None:
    beta = coeffs["emos_coefficient_beta"]
    n_pred = beta.sizes.get("predictor_index", 1)
    names = [str(x) for x in beta["predictor_name"].values] if "predictor_name" in beta.coords else []
    print(f"  {'coefficients':<22} level={list(coeffs.level.values)}  "
          f"beta_predictors={n_pred} {names}")
    for vname in ("emos_coefficient_alpha", "emos_coefficient_beta",
                  "emos_coefficient_gamma", "emos_coefficient_delta"):
        _print_array(f"    {vname}", coeffs[vname], indent="")


def _print_inputs(domain: str, hf, tr, static, apply_fc, prob_tpl, pct_fc) -> None:
    print("\n[输入]")
    if domain == "spot":
        print("  格式: 六列长表 DataFrame（每行一个 member×time×站点）")
        _print_dataframe("historic_forecast", hf)
        _print_dataframe("truth", tr)
        if static:
            for i, field in enumerate(static):
                _print_dataframe(f"static[{i}]", field)
        else:
            print("  (no static predictors)")
        _print_dataframe("apply_forecast", apply_fc)
    else:
        print("  格式: 六维 xarray")
        _print_array("historic_forecast", hf)
        _print_array("truth", tr)
        if static:
            for i, field in enumerate(static):
                _print_array(f"static[{i}] {field.name}", field)
        else:
            print("  (no static predictors)")
        _print_array("apply_forecast", apply_fc)
    _print_array("prob_template", prob_tpl)
    _print_array("percentile_forecast", pct_fc)


def run_scenario(domain: str, static_count: int) -> None:
    hf, tr, static_all = load_case(domain)
    static = static_all[:static_count] if static_count else None
    fmt = "六列 CSV" if domain == "spot" else "六维 NetCDF"
    print(f"\n{'=' * 72}")
    print(f"{domain} ({static_count} static) — 输入 {fmt}")
    print(f"{'=' * 72}")
    print("约定: 预报 time=起报, 实况 time=有效, 实况 dtime=0; 相同 (lat,lon) 为同一站点")

    apply_fc = _apply_slice(hf)
    apply_kw = dict(additional_fields=static)
    prob_tpl = create_prob_template(apply_fc, THRESHOLDS, "below")
    pct_fc = _percentile_forecast(apply_fc)
    _print_inputs(domain, hf, tr, static, apply_fc, prob_tpl, pct_fc)

    coeffs = train_emos(hf, tr, additional_fields=static, **TRAINER_KWARGS)
    ensemble = apply_emos(forecast=apply_fc, coefficients=coeffs, **apply_kw)
    probability = apply_emos(
        forecast=apply_fc, coefficients=coeffs, prob_template=prob_tpl, **apply_kw
    )
    percentiles = apply_emos(
        forecast=pct_fc,
        coefficients=coeffs,
        realizations_count=len(INPUT_PERCENTILES),
        percentiles=OUTPUT_PERCENTILES,
        **apply_kw,
    )

    print("\n[输出]  (内部处理后统一为 xarray)")
    _print_coefficients(coeffs)
    meta = {k: coeffs.attrs[k] for k in ("emos_n_stations", "emos_training_dtime") if k in coeffs.attrs}
    if meta:
        print(f"  {'metadata':<22} {meta}")
    _print_dataset("ensemble", ensemble)
    _print_dataset("probability", probability)
    _print_dataset("percentiles", percentiles)


def main() -> None:
    parser = argparse.ArgumentParser(description="展示 EMOS 输入/输出结构")
    parser.add_argument("--domain", choices=("spot", "grid", "all"), default="all")
    parser.add_argument("--static", type=int, choices=(0, 1, 2), default=None)
    args = parser.parse_args()

    domains = ("spot", "grid") if args.domain == "all" else (args.domain,)
    static_cases = STATIC_CASES if args.static is None else [(f"{args.static} static", args.static)]

    print("EMOS 结构检查（数据经 meteva_base 读取）")
    print("  格点: read_griddata_from_nc → 六维 xarray")
    print("  站点: read_stadata_from_csv → 六列 DataFrame")
    for domain in domains:
        for _, count in static_cases:
            run_scenario(domain, count)
    print("\n完成。")


if __name__ == "__main__":
    main()
