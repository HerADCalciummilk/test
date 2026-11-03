#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""SAMOS 概率订正命令行。

在本包目录执行::

    python -m cli samos --historic-forecast-path PATH --truth-path PATH
    python cli/run_samos.py --historic-forecast-path PATH --truth-path PATH

Python::

    from cli.run_samos import RunSamosCli
    RunSamosCli.call(historic_forecast_path="PATH", truth_path="PATH")

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

import argparse
import contextlib
import io
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence


def _bootstrap_paths() -> None:
    """沿用原顺序：兄弟包 emos src，再本包 src；并保证能导入共享 utils。"""
    root = Path(__file__).resolve().parent.parent
    src = root / "src"
    emos_src = root.parent / "emos_probability_calibration" / "src"
    parent = root.parent
    for path in (emos_src, src):
        path_s = str(path)
        if path_s not in sys.path:
            sys.path.insert(0, path_s)
    root_s = str(root)
    parent_s = str(parent)
    if root_s not in sys.path:
        sys.path.insert(0, root_s)
    if parent_s not in sys.path:
        sys.path.append(parent_s)


_bootstrap_paths()

import meteva_base as meb
import numpy as np
import pandas as pd
import xarray as xr

from utils.cli_base import CliBase

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
    realizations_count: Optional[int] = None, config=None) -> Dict[str, Optional[xr.Dataset]]:
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


def _parse_float_list(text: str):
    parts = [part.strip() for part in str(text).split(",") if part.strip()]
    if not parts:
        raise argparse.ArgumentTypeError("需要至少一个数值，多个用逗号分隔")
    return [float(part) for part in parts]


def _parse_str_list(text: str):
    parts = [part.strip() for part in str(text).split(",") if part.strip()]
    if not parts:
        raise argparse.ArgumentTypeError("需要至少一个名称，多个用逗号分隔")
    return parts


def _omit_none(kwargs):
    return {key: value for key, value in kwargs.items() if value is not None}


_CONFIG_HELP = (
    "运行配置文件，传给 process 的 config。"
    "省略则为 None，process 使用各参数自身的默认值。"
)


class RunSamosCli(CliBase):
    """SAMOS 概率订正。``run`` 调用 ``process``。"""

    prog = "python cli/run_samos.py"
    description = (
        "训练 GAM 与异常空间 EMOS，并对预报订正。\n"
        "未在命令行给出的可选项保持 process 的默认值。"
    )
    epilog = (
        "示例（在本包目录执行）:\n"
        "  python -m cli samos --help\n"
        "  python -m cli samos --historic-forecast-path PATH --truth-path PATH --output-dir DIR\n"
        "  python cli/run_samos.py --historic-forecast-path PATH --truth-path PATH "
        "--static-paths PATH --gam-features lat,lon,altitude\n"
    )

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--historic-forecast-path", required=True, metavar="PATH", help="历史预报（.nc 或 .csv）。")
        parser.add_argument("--truth-path", required=True, metavar="PATH", help="实况（.nc 或 .csv）。")
        parser.add_argument("--forecast-path", default=None, metavar="PATH", help="待订正预报。省略则用历史预报最后一起报。")
        parser.add_argument(
            "--static-paths",
            nargs="+",
            default=None,
            metavar="PATH",
            help="GAM 静态因子路径列表。省略则为 None。",
        )
        parser.add_argument("--output-dir", default=None, metavar="DIR", help="输出目录。省略则不写文件。")
        parser.add_argument(
            "--gam-features",
            type=_parse_str_list,
            default=None,
            metavar="NAME[,...]",
            help="GAM 特征名，逗号分隔。省略则由 lat,lon 与 static 文件名推断。",
        )
        parser.add_argument("--window-length", type=int, default=None, help="气候滚动窗。省略则使用 process 默认值 3。")
        parser.add_argument("--max-iter", type=int, default=None, help="pyGAM 最大迭代次数。省略则使用 process 默认值 30。")
        parser.add_argument("--distribution", default=None, help="norm 或 truncnorm。省略则使用 process 默认值 norm。")
        parser.add_argument("--predictor", default=None, help="预报统计量，如 mean。省略则使用 process 默认值 mean。")
        CliBase.add_optional_bool(
            parser,
            "--point-by-point",
            help_true="逐站或逐格点估计系数。",
            help_false="全场共用系数。省略则使用 process 默认值。",
        )
        CliBase.add_optional_bool(
            parser,
            "--use-default-initial-guess",
            help_true="使用默认初值。",
            help_false="不使用默认初值。省略则使用 process 默认值。",
        )
        parser.add_argument(
            "--thresholds",
            type=_parse_float_list,
            default=None,
            metavar="FLOAT[,...]",
            help="概率阈值，逗号分隔。省略则跳过概率输出。",
        )
        parser.add_argument(
            "--thresholds-operator",
            default=None,
            help="below 或 above。省略则使用 process 默认值 below。",
        )
        parser.add_argument(
            "--percentiles",
            type=_parse_float_list,
            default=None,
            metavar="FLOAT[,...]",
            help="输出分位，逗号分隔。省略则跳过分位输出。",
        )
        parser.add_argument(
            "--realizations-count",
            type=int,
            default=None,
            help="分位路径 ECC 成员数。省略则为 None。",
        )
        parser.add_argument("--config", default=None, metavar="PATH", help=_CONFIG_HELP)

    def run(
        self,
        historic_forecast_path,
        truth_path,
        forecast_path=None,
        static_paths=None,
        output_dir=None,
        gam_features=None,
        window_length=None,
        max_iter=None,
        distribution=None,
        predictor=None,
        point_by_point=None,
        use_default_initial_guess=None,
        thresholds=None,
        thresholds_operator=None,
        percentiles=None,
        realizations_count=None,
        config=None,
    ) -> int:
        process(
            **_omit_none(
                dict(
                    historic_forecast_path=historic_forecast_path,
                    truth_path=truth_path,
                    forecast_path=forecast_path,
                    static_paths=static_paths,
                    output_dir=output_dir,
                    gam_features=gam_features,
                    window_length=window_length,
                    max_iter=max_iter,
                    distribution=distribution,
                    predictor=predictor,
                    point_by_point=point_by_point,
                    use_default_initial_guess=use_default_initial_guess,
                    thresholds=thresholds,
                    thresholds_operator=thresholds_operator,
                    percentiles=percentiles,
                    realizations_count=realizations_count,
                    config=config,
                )
            )
        )
        return 0


def run_samos_cli(argv: Optional[Sequence[str]] = None) -> int:
    """命令行入口。``python -m cli samos`` 与直接运行本文件都进这里。"""
    return RunSamosCli().main(argv)


main = run_samos_cli


if __name__ == "__main__":
    raise SystemExit(run_samos_cli())
