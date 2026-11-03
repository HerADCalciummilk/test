"""meteva_base grid utilities for the Kalman workflow."""

from __future__ import annotations

from datetime import timedelta
from typing import Sequence

import numpy as np

REQUIRED_DIMS = ("member", "level", "time", "dtime", "lat", "lon")


def require_meteva_base():
    """Return meteva_base or raise a clear runtime error."""
    try:
        import meteva_base as meb
    except ImportError as exc:  # pragma: no cover - production dependency
        raise ImportError("meteva_base is required for grid I/O and meteva grid operations") from exc
    return meb


def require_xarray():
    """Return xarray or raise a clear runtime error."""
    try:
        import xarray as xr
    except ImportError as exc:  # pragma: no cover - production dependency
        raise ImportError("xarray is required for meteva grid operations") from exc
    return xr


def check_for_meb_griddata(
    grid_data,
    is_single: bool = False,
    valid_val: Sequence[float] = (-1000.0, 1000.0, np.nan),
):
    """Validate and normalize a meteva_base six-dimensional grid field."""
    xr = require_xarray()
    if not isinstance(grid_data, xr.DataArray):
        raise ValueError("griddata must be xr.DataArray")
    if set(grid_data.dims) != set(REQUIRED_DIMS):
        raise ValueError(f"griddata dims must be {set(REQUIRED_DIMS)}, got {set(grid_data.dims)}")
    if is_single and len(grid_data.values.squeeze().shape) > 2:
        raise ValueError("griddata must be a single effective lat/lon field")

    normalized = grid_data.copy()
    if normalized.dims != REQUIRED_DIMS:
        normalized = normalized.transpose(*REQUIRED_DIMS)
    if normalized.values.dtype != np.float32:
        normalized.values = normalized.values.astype(np.float32)

    lower, upper, fill_value = valid_val
    invalid = (normalized.values < lower) | (normalized.values > upper)
    if invalid.any():
        print("WARNING: griddata values exceed valid range; replacing with fill value")
        normalized.values[invalid] = fill_value
    return normalized


def check_for_xy_coordinates(grd_list: Sequence, is_time_match: bool = False) -> bool:
    """Check whether grid fields have matching member/level/lat/lon coordinates."""
    ref = grd_list[0]
    match = True
    for grd in grd_list[1:]:
        base_match = (
            (grd.member.values == ref.member.values).all()
            and (grd.level.values == ref.level.values).all()
            and np.allclose(grd.lat.values, ref.lat.values, atol=0.001)
            and np.allclose(grd.lon.values, ref.lon.values, atol=0.001)
        )
        if not is_time_match:
            match = base_match and match
            continue
        time_match = (
            (
                (grd.time.values == ref.time.values).all()
                and (grd.dtime.values == ref.dtime.values).all()
            )
            or _check_time_dtime_same(
                grd.time.values,
                grd.dtime.values,
                ref.time.values,
                ref.dtime.values,
            )
        )
        match = base_match and time_match and match
    return match


def _check_time_dtime_same(times0, dtimes0, times1, dtimes1) -> bool:
    """Check whether two time+dtime combinations describe the same valid times."""
    try:
        len(times0)
    except TypeError:
        times0 = [times0]
    try:
        len(dtimes0)
    except TypeError:
        dtimes0 = [dtimes0]
    try:
        len(times1)
    except TypeError:
        times1 = [times1]
    try:
        len(dtimes1)
    except TypeError:
        dtimes1 = [dtimes1]

    meb_mod = require_meteva_base()
    times0 = [meb_mod.tool.all_type_time_to_datetime(item) for item in times0]
    times1 = [meb_mod.tool.all_type_time_to_datetime(item) for item in times1]

    alltimes0 = {time + timedelta(hours=int(dtime)) for time in times0 for dtime in dtimes0}
    alltimes1 = {time + timedelta(hours=int(dtime)) for time in times1 for dtime in dtimes1}
    return alltimes0 & alltimes1 == alltimes0


def forecast_observation_difference(fcst: np.ndarray, obs: np.ndarray, absolute: bool = True):
    """Return forecast minus observation, optionally as absolute error."""
    if fcst.shape != obs.shape:
        raise ValueError("OBS and FCST shapes must be same")
    if absolute:
        return np.abs(fcst - obs)
    return fcst - obs


def decaying_me(
    fcst_minus_obs: np.ndarray,
    me_before: np.ndarray | None = None,
    alpha: float = 0.1,
    is_mae: bool = False,
) -> np.ndarray:
    """Update mean error or mean absolute error with exponential decay."""
    if me_before is None:
        me_before = fcst_minus_obs.copy()
    if is_mae:
        return (1 - alpha) * np.abs(me_before) + alpha * np.abs(fcst_minus_obs)
    return (1 - alpha) * me_before + alpha * fcst_minus_obs


def decaying_fcst(fcst: np.ndarray, me_before: np.ndarray | None = None) -> np.ndarray:
    """Apply the latest Kalman mean-error field to a forecast field."""
    if me_before is None:
        me_before = np.zeros_like(fcst)
    return fcst - me_before


def kalman_fix(fcst, me_before=None):
    """Calculate the Kalman-corrected forecast field."""
    fcst = check_for_meb_griddata(fcst, is_single=True, valid_val=(-1000, 1000, np.nan))
    fcst_np = fcst.values
    if me_before is not None:
        me_before = check_for_meb_griddata(me_before, is_single=True, valid_val=(-1000, 1000, np.nan))
        if not check_for_xy_coordinates([fcst, me_before]):
            raise ValueError("kalman_fix input grid coordinates must be same")
        me_before_np = me_before.values
    else:
        me_before_np = None

    fixed_np = decaying_fcst(fcst_np, me_before_np)
    fixed_np[np.isnan(fixed_np)] = fcst_np[np.isnan(fixed_np)]
    meb_mod = require_meteva_base()
    return meb_mod.grid_data(grid=meb_mod.get_grid_of_data(fcst), data=fixed_np)


def kalman_me(
    fcst,
    obs,
    me_before=None,
    *,
    time_new=None,
    dtime_new=None,
    alpha: float = 0.1,
    is_mae: bool = False,
):
    """Update the Kalman mean-error field."""
    if fcst.values.shape != obs.values.shape:
        raise ValueError("Fcst and OBS coordinates must be same")
    if me_before is not None and fcst.values.shape != me_before.values.shape:
        raise ValueError("Fcst and Kalman ME coordinates must be same")

    fob_np = forecast_observation_difference(fcst.values, obs.values, absolute=is_mae)
    if me_before is not None:
        kalman_me_np = decaying_me(fob_np, me_before=me_before.values, alpha=alpha, is_mae=is_mae)
    else:
        kalman_me_np = decaying_me(fob_np, me_before=None, alpha=alpha, is_mae=is_mae)

    meb_mod = require_meteva_base()
    result = meb_mod.grid_data(grid=meb_mod.get_grid_of_data(fcst), data=kalman_me_np)
    if time_new is not None:
        try:
            len(time_new)
        except TypeError:
            time_new = [time_new]
        time_new = [meb_mod.all_type_time_to_datetime(item) for item in time_new]
        meb_mod.set_griddata_coords(result, gtime=time_new)
    if dtime_new is not None:
        try:
            len(dtime_new)
        except TypeError:
            dtime_new = [dtime_new]
        meb_mod.set_griddata_coords(result, dtime_list=[int(item) for item in dtime_new])
    return result
