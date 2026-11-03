#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""8 月 4–6 日窗口：Redistribute 订正 + CMPAS 检验（跳过残缺时次）。"""

from __future__ import annotations

import gc
import sys
from datetime import datetime, timedelta
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import meteva_base as meb
import numpy as np
import pandas as pd

PKG = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(PKG.parent), str(PKG)]

from orographic_precipitation_downscaling.cli.orographic_enhancement_cli import (  # noqa: E402
    process as oe_process,
)
from orographic_precipitation_downscaling.src import (  # noqa: E402
    RedistributeOrographicEnhancement,
)

DATA = PKG / "resource" / "data"
OBS_ROOT = PKG / "resource" / "CMPAS_APCP"
OUT = DATA / "output"
OROG_MODEL = str(PKG / "resource" / "ancil" / "EC_D1D_orography_20km.nc")
OROG = str(PKG / "resource" / "ancil" / "HGT_M_1KM_CHINA.nc")

CASE_INITS = ("2026080400", "2026080500", "2026080600")
# 已知残缺：0500.018 整时次未拷；0500.012 缺 UGRD/950
SKIP_TAGS = {"2026080500.012", "2026080500.018"}


def nc_index(root: Path) -> dict:
    files = meb.path_tools.get_path_list_in_dir(str(root))
    return {Path(p).stem: p for p in files if str(p).endswith(".nc")}


def parse_tag(tag: str):
    init_s, lead_s = tag.split(".")
    return datetime.strptime(init_s, "%Y%m%d%H"), int(lead_s)


def cmpas_path(bjt: datetime) -> Path:
    return OBS_ROOT / f"{bjt:%Y}" / f"{bjt:%Y%m%d}" / f"BJT_{bjt:%y%m%d%H}.000.nc"


def obs_3h_mean(valid_utc: datetime, grid):
    bjt_end = valid_utc + timedelta(hours=8)
    hours = [bjt_end - timedelta(hours=2), bjt_end - timedelta(hours=1), bjt_end]
    acc = None
    last = None
    for bjt in hours:
        path = cmpas_path(bjt)
        if not path.exists():
            raise FileNotFoundError(path)
        da = meb.read_griddata_from_nc(str(path))
        da = meb.interp_gg_linear(da, grid, outer_value=np.nan)
        values = np.asarray(da.values, dtype=np.float64)
        acc = values if acc is None else acc + values
        last = da
    out = last.copy(data=(acc / 3.0).astype(np.float32))
    out.attrs["units"] = "mm h-1"
    out.name = "cmpas_3h_mean"
    return out


def _bias_rmse(pred: np.ndarray, obs: np.ndarray) -> tuple[float, float, int]:
    mask = (
        np.isfinite(pred)
        & np.isfinite(obs)
        & (np.abs(pred) < 1e10)
        & (np.abs(obs) < 1e10)
    )
    if not np.any(mask):
        return float("nan"), float("nan"), 0
    diff = pred[mask] - obs[mask]
    return float(np.mean(diff)), float(np.sqrt(np.mean(diff**2))), int(mask.sum())


def _save_sample_figs(sample: dict) -> None:
    from meteva_base.tool.plot_tools import pcolormesh_2d_grid

    fig_dir = OUT / "figs"
    fig_dir.mkdir(parents=True, exist_ok=True)
    tag = sample["tag"]
    valid = sample["valid"]
    step = 10
    before = sample["before"].isel(lat=slice(None, None, step), lon=slice(None, None, step))
    after = sample["after"].isel(lat=slice(None, None, step), lon=slice(None, None, step))
    obs = sample["obs"].isel(lat=slice(None, None, step), lon=slice(None, None, step))
    both = np.concatenate(
        [
            np.asarray(before.values, dtype=float).ravel(),
            np.asarray(after.values, dtype=float).ravel(),
            np.asarray(obs.values, dtype=float).ravel(),
        ]
    )
    both = both[np.isfinite(both) & (both >= 0) & (both < 1e10)]
    hi = max(float(np.nanpercentile(both, 99)), 1.0)
    clevs = [0, 0.1, 1, 2, 4, 8, 16, 32]
    while clevs[-1] < hi and len(clevs) < 19:
        clevs.append(clevs[-1] * 2)
    bjt = valid + timedelta(hours=8)
    pcolormesh_2d_grid(
        before,
        save_path=str(fig_dir / f"{tag}_1_before.png"),
        title=f"1 订正前（mm/h） {tag}",
        clevs=clevs,
        cmap="rain_1h",
        show=False,
    )
    pcolormesh_2d_grid(
        after,
        save_path=str(fig_dir / f"{tag}_2_after.png"),
        title=f"2 订正后（mm/h） {tag}",
        clevs=clevs,
        cmap="rain_1h",
        show=False,
    )
    pcolormesh_2d_grid(
        obs,
        save_path=str(fig_dir / f"{tag}_3_obs.png"),
        title=f"3 实况 3h 平均（mm/h） BJT {bjt - timedelta(hours=2):%H}-{bjt:%Y%m%d%H}",
        clevs=clevs,
        cmap="rain_1h",
        show=False,
    )
    print(f"figs → {fig_dir}")


def main() -> None:
    tmp_ix = nc_index(DATA / "TMP")
    rh_ix = nc_index(DATA / "RH")
    pres_ix = nc_index(DATA / "PRES")
    u_ix = nc_index(DATA / "UGRD")
    v_ix = nc_index(DATA / "VGRD")
    apcp_list = meb.path_tools.get_path_list_in_dir(str(PKG / "resource" / "EC" / "APCP01"))
    apcp_list = sorted(
        p
        for p in apcp_list
        if str(p).endswith(".nc")
        and Path(p).stem in tmp_ix
        and Path(p).stem.split(".", 1)[0] in CASE_INITS
        and Path(p).stem not in SKIP_TAGS
    )
    print("n forecasts", len(apcp_list))
    if not apcp_list:
        raise RuntimeError("未找到 8 月窗口可检验时次")
    print("example APCP", apcp_list[0])

    redistribute = RedistributeOrographicEnhancement()
    dest = meb.read_griddata_from_nc(OROG)
    dest.attrs["units"] = "m"
    grid1km = meb.get_grid_of_data(dest)

    rows = []
    sample = None
    for apcp in apcp_list:
        tag = Path(apcp).stem
        init, lead = parse_tag(tag)
        valid = init + timedelta(hours=lead)

        oe_model = oe_process(
            tmp_ix[tag],
            rh_ix[tag],
            pres_ix[tag],
            u_ix[tag],
            v_ix[tag],
            OROG_MODEL,
            output_path=None,
        )
        oe_high = oe_process(
            tmp_ix[tag],
            rh_ix[tag],
            pres_ix[tag],
            u_ix[tag],
            v_ix[tag],
            OROG,
            output_path=None,
        )

        precip = meb.read_griddata_from_nc(apcp)
        precip.attrs["units"] = "mm h-1"
        before = meb.interp_gg_linear(precip, grid1km, outer_value=np.nan)
        before.attrs["units"] = "mm h-1"
        before.name = "precipitation_rate"
        oe_model_1km = meb.interp_gg_linear(oe_model, grid1km, outer_value=np.nan)
        oe_model_1km.attrs["units"] = oe_model.attrs.get("units") or "m s-1"
        if not (oe_high.attrs.get("units") or "").strip():
            oe_high.attrs["units"] = "m s-1"
        after = redistribute(before, oe_high, oe_model_1km)
        obs = obs_3h_mean(valid, grid1km)

        b = np.asarray(obs.values, dtype=float).ravel()
        a0 = np.asarray(before.values, dtype=float).ravel()
        a1 = np.asarray(after.values, dtype=float).ravel()
        bias0, rmse0, n = _bias_rmse(a0, b)
        bias1, rmse1, _ = _bias_rmse(a1, b)
        finite = np.isfinite(a0) & np.isfinite(a1)
        sum0 = float(a0[finite].sum())
        sum1 = float(a1[finite].sum())
        rows.append(
            {
                "tag": tag,
                "valid_utc": valid.strftime("%Y%m%d%H"),
                "bjt_end": (valid + timedelta(hours=8)).strftime("%Y%m%d%H"),
                "bias_before": bias0,
                "rmse_before": rmse0,
                "bias_after": bias1,
                "rmse_after": rmse1,
                "delta_rmse": rmse1 - rmse0,
                "sum_before": sum0,
                "sum_after": sum1,
                "n": n,
            }
        )
        print(
            f"{tag}  before bias={bias0:.3f} rmse={rmse0:.3f} | "
            f"after bias={bias1:.3f} rmse={rmse1:.3f} | "
            f"Δrmse={rmse1 - rmse0:+.3f} | "
            f"Δsum={sum1 - sum0:+.3f} mm/h"
        )
        if sample is None:
            sample = {
                "tag": tag,
                "valid": valid,
                "before": before,
                "after": after,
                "obs": obs,
            }
        else:
            del oe_model, oe_high, precip, before, after, obs, oe_model_1km
            gc.collect()

    hourly = pd.DataFrame(rows)
    ver_dir = OUT / "verify"
    ver_dir.mkdir(parents=True, exist_ok=True)
    hourly_path = ver_dir / "redistribute_hourly_20260804_06.csv"
    hourly.to_csv(hourly_path, index=False)
    print(
        f"mean  before bias={hourly.bias_before.mean():.3f} "
        f"rmse={hourly.rmse_before.mean():.3f} | "
        f"after bias={hourly.bias_after.mean():.3f} "
        f"rmse={hourly.rmse_after.mean():.3f} | "
        f"Δrmse={hourly.delta_rmse.mean():+.3f} mm/h"
    )
    print("table", hourly_path)
    if sample is not None:
        _save_sample_figs(sample)


if __name__ == "__main__":
    main()
