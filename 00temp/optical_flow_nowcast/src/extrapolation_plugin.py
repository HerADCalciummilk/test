# -*- coding: utf-8 -*-
"""
Created on Wed Jul 12 09:52:07 2023

@author: cheny
"""

from .utils import *


from .base_plugin import PostProcessingPlugin
from typing import Optional
import meteva_base as meb
import xarray as xr

def forecast(
    precip,
    velocity,
    timesteps,
    extrap_method="semilagrangian",
    extrap_kwargs=None,
    measure_time=False,
):
    """
    Generate a nowcast by applying a simple advection-based extrapolation to
    the given precipitation field.

    .. _ndarray: http://docs.scipy.org/doc/numpy/reference/generated/numpy.ndarray.html

    Parameters
    ----------
    precip: array-like
        Two-dimensional array of shape (m,n) containing the input precipitation
        field.
    velocity: array-like
        Array of shape (2,m,n) containing the x- and y-components of the
        advection field. The velocities are assumed to represent one time step
        between the inputs.
    timesteps: int or list of floats
        Number of time steps to forecast or a list of time steps for which the
        forecasts are computed (relative to the input time step). The elements
        of the list are required to be in ascending order.
    extrap_method: str, optional
        Name of the extrapolation method to use. See the documentation of
        pysteps.extrapolation.interface.
    extrap_kwargs: dict, optional
        Optional dictionary that is expanded into keyword arguments for the
        extrapolation method.
    measure_time: bool, optional
        If True, measure, print, and return the computation time.

    Returns
    -------
    out: ndarray_
      Three-dimensional array of shape (num_timesteps, m, n) containing a time
      series of nowcast precipitation fields. The time series starts from
      t0 + timestep, where timestep is taken from the advection field velocity.
      If *measure_time* is True, the return value is a two-element tuple
      containing this array and the computation time (seconds).

    See also
    --------
    pysteps.extrapolation.interface
    """

    _check_inputs(precip, velocity, timesteps)

    if extrap_kwargs is None:
        extrap_kwargs = dict()
    else:
        extrap_kwargs = extrap_kwargs.copy()

    extrap_kwargs["allow_nonfinite_values"] = (
        True if np.any(~np.isfinite(precip)) else False
    )

    if measure_time:
        print(
            "Computing extrapolation nowcast from a "
            f"{precip.shape[0]:d}x{precip.shape[1]:d} input grid... ",
            end="",
        )

    if measure_time:
        start_time = time.time()

    extrapolation_method = extrapolation_get_method(extrap_method)

    precip_forecast = extrapolation_method(precip, velocity, timesteps, **extrap_kwargs)

    if measure_time:
        computation_time = time.time() - start_time
        print(f"{computation_time:.2f} seconds.")

    if measure_time:
        return precip_forecast, computation_time
    else:
        return precip_forecast


def _check_inputs(precip, velocity, timesteps):
    if precip.ndim != 2:
        raise ValueError("The input precipitation must be a " "two-dimensional array")
    if velocity.ndim != 3:
        raise ValueError("Input velocity must be a three-dimensional array")
    if precip.shape != velocity.shape[1:3]:
        raise ValueError(
            "Dimension mismatch between "
            "input precipitation and velocity: " +
            "shape(precip)=%s, shape(velocity)=%s"
            % (str(precip.shape), str(velocity.shape))
        )
    if isinstance(timesteps, list) and not sorted(timesteps) == timesteps:
        raise ValueError("timesteps is not in ascending order")


class Extrapolation(PostProcessingPlugin):

    def __init__(self,
                 model_id_attr: Optional[str] = None,
                 extrap_method: Optional[str] = "semilagrangian",
                 extrap_kwargs: Optional[dict] = None,
                 measure_time: Optional[bool] = False,
                 ) -> None:
        """
        Initialise the class

        Args:
        model_id_attr:
            Name of the attribute used to identify the source model for
            blending.
            feature_method: {'blob', 'domain' 'shitomasi'}
        extrap_method: str, optional
            Name of the extrapolation method to use. See the documentation of
            pysteps.extrapolation.interface.
        extrap_kwargs: dict, optional
            Optional dictionary that is expanded into keyword arguments for the
            extrapolation method.
        measure_time: bool, optional
            If True, measure, print, and return the computation time.

        """
        self.model_id_attr = model_id_attr
        self.extrap_method = extrap_method
        self.extrap_kwargs = extrap_kwargs
        self.measure_time = measure_time

    def process(self,
                precip_griddata_list: list,
                velocity_griddata: xr.DataArray,
                timesteps: int,
                delta_t=timedelta(minutes=10)
                ) -> xr.DataArray:
        """
        Args:
            precip_griddata_list: 实况降水列表，meb网格数据，依次从前到后
            velocity_griddata：平流速度
            timesteps： 外推多少个时次
            delta_t： 实况间隔，暨每个时次间隔时间
        """
        # 时间排序
        precip_griddata_list = sort_meb_griddata_list_along_time(precip_griddata_list)
        # 数据维度一致性检查
        for precip_griddata in precip_griddata_list:
            if precip_griddata.values.squeeze().ndim != 2:
                raise ValueError("uncorrect dimension, expect 2 dimensions data like [m,n]")
            else:
                continue

        if velocity_griddata.values.squeeze().ndim != 3 and velocity_griddata.values.squeeze().shape[0] != 2:
            raise ValueError("uncorrect dimension, expect 3 dimensions data like [2,m,n]")

        # 时间间隔一致性检查
        if check_meb_griddata_time_interval(precip_griddata_list):
            pass
        else:
            raise ValueError('unequal time intervals in meb_griddata_list detected!')

        # 数据提取
        precip_np_array = []
        for precip_griddata in precip_griddata_list:
            precip_np_array.append(precip_griddata.values.squeeze())

        velocity_np_array = velocity_griddata.values.squeeze()

        # 构建三维输入
        precip_np_array = np.array(precip_np_array)[-1]
        velocity_np_array = np.array(velocity_np_array)

        # 维度提取
        grid_info = meb.get_grid_of_data(precip_griddata)
        gtime = grid_info.gtime
        glon = [grid_info.slon, grid_info.elon, grid_info.dlon]
        glat = [grid_info.slat, grid_info.elat, grid_info.dlat]

        if delta_t.seconds % 3600 == 0:
            delta_t = delta_t.seconds / 3600
            delta_t_units = 'hours'
        elif delta_t.seconds % 60 == 0:
            delta_t = delta_t.seconds / 60
            delta_t_units = 'minutes'
        elif delta_t.seconds % 1 == 0:
            delta_t = delta_t.seconds
            delta_t_units = 'seconds'

        dtime_list = np.arange(delta_t, timesteps * delta_t + 1, delta_t)
        grid = meb.grid(glon, glat, gtime, dtime_list=dtime_list, dtime_units_attr=delta_t_units)

        result_np = forecast(precip_np_array,
                             velocity_np_array,
                             timesteps,
                             extrap_method=self.extrap_method,
                             extrap_kwargs=self.extrap_kwargs,
                             measure_time=self.measure_time,
                             )

        # 重构meb.griddata
        nlat = result_np.shape[1]
        nlon = result_np.shape[2]
        result_np = result_np.reshape(1, 1, 1, timesteps, nlat, nlon)
        result_griddata = meb.grid_data(grid, result_np)
        return result_griddata
