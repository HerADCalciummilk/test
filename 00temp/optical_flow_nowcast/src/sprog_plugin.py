# -*- coding: utf-8 -*-
"""
Created on Wed Jul 12 09:52:07 2023

@author: cheny
"""

from .utils import *
from .base_plugin import PostProcessingPlugin
from typing import Optional, Tuple
import meteva_base as meb
import xarray as xr


@deprecate_args({"R": "precip", "V": "velocity", "R_thr": "precip_thr"}, "1.8.0")
def forecast(
    precip,
    velocity,
    timesteps,
    precip_thr=None,
    n_cascade_levels=6,
    extrap_method="semilagrangian",
    decomp_method="fft",
    bandpass_filter_method="gaussian",
    ar_order=2,
    conditional=False,
    probmatching_method="cdf",
    num_workers=1,
    fft_method="numpy",
    domain="spatial",
    extrap_kwargs=None,
    filter_kwargs=None,
    measure_time=False,
):
    """
    Generate a nowcast by using the Spectral Prognosis (S-PROG) method.

    Parameters
    ----------
    precip: array-like
        Array of shape (ar_order+1,m,n) containing the input precipitation fields
        ordered by timestamp from oldest to newest. The time steps between
        the inputs are assumed to be regular.
    velocity: array-like
        Array of shape (2,m,n) containing the x- and y-components of the
        advection field.
        The velocities are assumed to represent one time step between the
        inputs. All values are required to be finite.
    timesteps: int or list of floats
        Number of time steps to forecast or a list of time steps for which the
        forecasts are computed (relative to the input time step). The elements
        of the list are required to be in ascending order.
    precip_thr: float, required
        The threshold value for minimum observable precipitation intensity.
    n_cascade_levels: int, optional
        The number of cascade levels to use.
    extrap_method: str, optional
        Name of the extrapolation method to use. See the documentation of
        pysteps.extrapolation.interface.
    decomp_method: {'fft'}, optional
        Name of the cascade decomposition method to use. See the documentation
        of pysteps.cascade.interface.
    bandpass_filter_method: {'gaussian', 'uniform'}, optional
        Name of the bandpass filter method to use with the cascade decomposition.
        See the documentation of pysteps.cascade.interface.
    ar_order: int, optional
        The order of the autoregressive model to use. Must be >= 1.
    conditional: bool, optional
        If set to True, compute the statistics of the precipitation field
        conditionally by excluding pixels where the values are
        below the threshold precip_thr.
    probmatching_method: {'cdf','mean',None}, optional
        Method for matching the conditional statistics of the forecast field
        (areas with precipitation intensity above the threshold precip_thr) with
        those of the most recently observed one. 'cdf'=map the forecast CDF to the
        observed one, 'mean'=adjust only the mean value,
        None=no matching applied.
    num_workers: int, optional
        The number of workers to use for parallel computation. Applicable if dask
        is enabled or pyFFTW is used for computing the FFT.
        When num_workers>1, it is advisable to disable OpenMP by setting
        the environment variable OMP_NUM_THREADS to 1.
        This avoids slowdown caused by too many simultaneous threads.
    fft_method: str, optional
        A string defining the FFT method to use (see utils.fft.get_method).
        Defaults to 'numpy' for compatibility reasons. If pyFFTW is installed,
        the recommended method is 'pyfftw'.
    domain: {"spatial", "spectral"}
        If "spatial", all computations are done in the spatial domain (the
        classical S-PROG model). If "spectral", the AR(2) models are applied
        directly in the spectral domain to reduce memory footprint and improve
        performance :cite:`PCH2019a`.
    extrap_kwargs: dict, optional
        Optional dictionary containing keyword arguments for the extrapolation
        method. See the documentation of pysteps.extrapolation.
    filter_kwargs: dict, optional
        Optional dictionary containing keyword arguments for the filter method.
        See the documentation of pysteps.cascade.bandpass_filters.py.
    measure_time: bool
        If set to True, measure, print and return the computation time.

    Returns
    -------
    out: ndarray
        A three-dimensional array of shape (num_timesteps,m,n) containing a time
        series of forecast precipitation fields. The time series starts from
        t0+timestep, where timestep is taken from the input precipitation fields
        precip. If measure_time is True, the return value is a three-element
        tuple containing the nowcast array, the initialization time of the
        nowcast generator and the time used in the main loop (seconds).

    See also
    --------
    pysteps.extrapolation.interface, pysteps.cascade.interface

    References
    ----------
    :cite:`Seed2003`, :cite:`PCH2019a`
    """

    _check_inputs(precip, velocity, timesteps, ar_order)

    if extrap_kwargs is None:
        extrap_kwargs = dict()

    if filter_kwargs is None:
        filter_kwargs = dict()

    if np.any(~np.isfinite(velocity)):
        raise ValueError("velocity contains non-finite values")

    if precip_thr is None:
        raise ValueError("precip_thr required but not specified")

    print("Computing S-PROG nowcast")
    print("------------------------")
    print("")

    print("Inputs")
    print("------")
    print(f"input dimensions: {precip.shape[1]}x{precip.shape[2]}")
    print("")

    print("Methods")
    print("-------")
    print(f"extrapolation:          {extrap_method}")
    print(f"bandpass filter:        {bandpass_filter_method}")
    print(f"decomposition:          {decomp_method}")
    print("conditional statistics: {}".format("yes" if conditional else "no"))
    print(f"probability matching:   {probmatching_method}")
    print(f"FFT method:             {fft_method}")
    print(f"domain:                 {domain}")
    print("")

    print("Parameters")
    print("----------")
    if isinstance(timesteps, int):
        print(f"number of time steps:     {timesteps}")
    else:
        print(f"time steps:               {timesteps}")
    print(f"parallel threads:         {num_workers}")
    print(f"number of cascade levels: {n_cascade_levels}")
    print(f"order of the AR(p) model: {ar_order}")
    print(f"precip. intensity threshold: {precip_thr}")

    if measure_time:
        starttime_init = time.time()

    fft = get_fft_method(fft_method, shape=precip.shape[1:], n_threads=num_workers)

    m, n = precip.shape[1:]

    # initialize the band-pass filter
    filter_method = cascade_get_method(bandpass_filter_method)
    bp_filter = filter_method((m, n), n_cascade_levels, **filter_kwargs)

    decomp_method, recomp_method = cascade_get_method(decomp_method)

    extrapolator_method = extrapolation_get_method(extrap_method)

    precip = precip[-(ar_order + 1):, :, :].copy()
    precip_min = np.nanmin(precip)

    # determine the domain mask from non-finite values
    domain_mask = np.logical_or.reduce(
        [~np.isfinite(precip[i, :]) for i in range(precip.shape[0])]
    )

    # determine the precipitation threshold mask
    if conditional:
        mask_thr = np.logical_and.reduce(
            [precip[i, :, :] >= precip_thr for i in range(precip.shape[0])]
        )
    else:
        mask_thr = None

    # initialize the extrapolator
    x_values, y_values = np.meshgrid(
        np.arange(precip.shape[2]), np.arange(precip.shape[1])
    )

    xy_coords = np.stack([x_values, y_values])

    extrap_kwargs = extrap_kwargs.copy()
    extrap_kwargs["xy_coords"] = xy_coords
    extrap_kwargs["allow_nonfinite_values"] = (
        True if np.any(~np.isfinite(precip)) else False
    )

    # advect the previous precipitation fields to the same position with the
    # most recent one (i.e. transform them into the Lagrangian coordinates)
    res = list()

    def f(precip, i):
        return extrapolator_method(
            precip[i, :], velocity, ar_order - i, "min", **extrap_kwargs
        )[-1]

    for i in range(ar_order):
        if not DASK_IMPORTED:
            precip[i, :, :] = f(precip, i)
        else:
            res.append(dask.delayed(f)(precip, i))

    if DASK_IMPORTED:
        num_workers_ = len(res) if num_workers > len(res) else num_workers
        precip = np.stack(
            list(dask.compute(*res, num_workers=num_workers_)) + [precip[-1, :, :]]
        )

    # replace non-finite values with the minimum value
    precip = precip.copy()
    for i in range(precip.shape[0]):
        precip[i, ~np.isfinite(precip[i, :])] = np.nanmin(precip[i, :])

    # compute the cascade decompositions of the input precipitation fields
    precip_decomp = []
    for i in range(ar_order + 1):
        precip_ = decomp_method(
            precip[i, :, :],
            bp_filter,
            mask=mask_thr,
            fft_method=fft,
            output_domain=domain,
            normalize=True,
            compute_stats=True,
            compact_output=True,
        )
        precip_decomp.append(precip_)

    # rearrange the cascade levels into a four-dimensional array of shape
    # (n_cascade_levels,ar_order+1,m,n) for the autoregressive model
    precip_cascades = stack_cascades(
        precip_decomp, n_cascade_levels, convert_to_full_arrays=True
    )

    # compute lag-l temporal autocorrelation coefficients for each cascade level
    gamma = np.empty((n_cascade_levels, ar_order))
    for i in range(n_cascade_levels):
        if domain == "spatial":
            gamma[i, :] = temporal_autocorrelation(
                precip_cascades[i], mask=mask_thr
            )
        else:
            gamma[i, :] = correlation.temporal_autocorrelation(
                precip_cascades[i], domain="spectral", x_shape=precip.shape[1:]
            )

    precip_cascades = stack_cascades(
        precip_decomp, n_cascade_levels, convert_to_full_arrays=False
    )

    precip_decomp = precip_decomp[-1]

    print_corrcoefs(gamma)

    if ar_order == 2:
        # adjust the lag-2 correlation coefficient to ensure that the AR(p)
        # process is stationary
        for i in range(n_cascade_levels):
            gamma[i, 1] = adjust_lag2_corrcoef2(gamma[i, 0], gamma[i, 1])

    # estimate the parameters of the AR(p) model from the autocorrelation
    # coefficients
    phi = np.empty((n_cascade_levels, ar_order + 1))
    for i in range(n_cascade_levels):
        phi[i, :] = estimate_ar_params_yw(gamma[i, :])

    print_ar_params(phi)

    # discard all except the p-1 last cascades because they are not needed for
    # the AR(p) model
    precip_cascades = [precip_cascades[i][-ar_order:] for i in range(n_cascade_levels)]

    if probmatching_method == "mean":
        mu_0 = np.mean(precip[-1, :, :][precip[-1, :, :] >= precip_thr])
    else:
        mu_0 = None

    # compute precipitation mask and wet area ratio
    mask_p = precip[-1, :, :] >= precip_thr
    war = 1.0 * np.sum(mask_p) / (precip.shape[1] * precip.shape[2])

    if measure_time:
        init_time = time.time() - starttime_init

    precip = precip[-1, :, :]

    print("Starting nowcast computation.")

    precip_forecast = []

    state = {"precip_cascades": precip_cascades, "precip_decomp": precip_decomp}
    params = {
        "domain": domain,
        "domain_mask": domain_mask,
        "fft": fft,
        "mu_0": mu_0,
        "n_cascade_levels": n_cascade_levels,
        "phi": phi,
        "precip_0": precip,
        "precip_min": precip_min,
        "probmatching_method": probmatching_method,
        "recomp_method": recomp_method,
        "war": war,
    }

    precip_forecast = nowcast_main_loop(
        precip,
        velocity,
        state,
        timesteps,
        extrap_method,
        _update,
        extrap_kwargs=extrap_kwargs,
        params=params,
        measure_time=measure_time,
    )
    if measure_time:
        precip_forecast, mainloop_time = precip_forecast

    precip_forecast = np.stack(precip_forecast)

    if measure_time:
        return precip_forecast, init_time, mainloop_time
    else:
        return precip_forecast


def _check_inputs(precip, velocity, timesteps, ar_order):
    if precip.ndim != 3:
        raise ValueError("precip must be a three-dimensional array")
    if precip.shape[0] < ar_order + 1:
        raise ValueError("precip.shape[0] < ar_order+1")
    if velocity.ndim != 3:
        raise ValueError("velocity must be a three-dimensional array")
    if precip.shape[1:3] != velocity.shape[1:3]:
        raise ValueError(
            "dimension mismatch between precip and velocity: shape(precip)=%s, shape(velocity)=%s"
            % (str(precip.shape), str(velocity.shape))
        )
    if isinstance(timesteps, list) and not sorted(timesteps) == timesteps:
        raise ValueError("timesteps is not in ascending order")


def _update(state, params):
    for i in range(params["n_cascade_levels"]):
        state["precip_cascades"][i] = autoregression_iterate_ar_model(
            state["precip_cascades"][i], params["phi"][i, :]
        )

    state["precip_decomp"]["cascade_levels"] = [
        state["precip_cascades"][i][-1, :] for i in range(params["n_cascade_levels"])
    ]
    if params["domain"] == "spatial":
        state["precip_decomp"]["cascade_levels"] = np.stack(
            state["precip_decomp"]["cascade_levels"]
        )

    precip_forecast_recomp = params["recomp_method"](state["precip_decomp"])

    if params["domain"] == "spectral":
        precip_forecast_recomp = params["fft"].irfft2(precip_forecast_recomp)

    mask = compute_percentile_mask(precip_forecast_recomp, params["war"])
    precip_forecast_recomp[~mask] = params["precip_min"]

    if params["probmatching_method"] == "cdf":
        # adjust the CDF of the forecast to match the most recently
        # observed precipitation field
        precip_forecast_recomp = nonparam_match_empirical_cdf(
            precip_forecast_recomp, params["precip_0"]
        )
    elif params["probmatching_method"] == "mean":
        mu_fct = np.mean(precip_forecast_recomp[mask])
        precip_forecast_recomp[mask] = (
            precip_forecast_recomp[mask] - mu_fct + params["mu_0"]
        )

    precip_forecast_recomp[params["domain_mask"]] = np.nan

    return precip_forecast_recomp, state


class Sprog(PostProcessingPlugin):

    def __init__(self,
                 model_id_attr: Optional[str] = None,
                 precip_thr: Optional[float] = -5,
                 n_cascade_levels: Optional[int] = 6,
                 extrap_method: Optional[str] = "semilagrangian",
                 decomp_method: Optional[str] = "fft",
                 bandpass_filter_method: Optional[str] = "gaussian",
                 ar_order: Optional[int] = 2,
                 conditional: Optional[bool] = False,
                 probmatching_method: Optional[str] = "cdf",
                 num_workers: Optional[int] = 1,
                 fft_method: Optional[str] = "numpy",
                 domain: Optional[str] = "spatial",
                 extrap_kwargs: Optional[dict] = None,
                 filter_kwargs: Optional[dict] = None,
                 measure_time: Optional[bool] = False,) -> None:
        """
        Initialise the class

        Args:
        model_id_attr:
            Name of the attribute used to identify the source model for
            blending.
        precip_thr: float, required
            The threshold value for minimum observable precipitation intensity.
        n_cascade_levels: int, optional
            The number of cascade levels to use.
        extrap_method: str, optional
            Name of the extrapolation method to use. See the documentation of
            pysteps.extrapolation.interface.
        decomp_method: {'fft'}, optional
            Name of the cascade decomposition method to use. See the documentation
            of pysteps.cascade.interface.
        bandpass_filter_method: {'gaussian', 'uniform'}, optional
            Name of the bandpass filter method to use with the cascade decomposition.
            See the documentation of pysteps.cascade.interface.
        ar_order: int, optional
            The order of the autoregressive model to use. Must be >= 1.
        conditional: bool, optional
            If set to True, compute the statistics of the precipitation field
            conditionally by excluding pixels where the values are
            below the threshold precip_thr.
        probmatching_method: {'cdf','mean',None}, optional
            Method for matching the conditional statistics of the forecast field
            (areas with precipitation intensity above the threshold precip_thr) with
            those of the most recently observed one. 'cdf'=map the forecast CDF to the
            observed one, 'mean'=adjust only the mean value,
            None=no matching applied.
        num_workers: int, optional
            The number of workers to use for parallel computation. Applicable if dask
            is enabled or pyFFTW is used for computing the FFT.
            When num_workers>1, it is advisable to disable OpenMP by setting
            the environment variable OMP_NUM_THREADS to 1.
            This avoids slowdown caused by too many simultaneous threads.
        fft_method: str, optional
            A string defining the FFT method to use (see utils.fft.get_method).
            Defaults to 'numpy' for compatibility reasons. If pyFFTW is installed,
            the recommended method is 'pyfftw'.
        domain: {"spatial", "spectral"}
            If "spatial", all computations are done in the spatial domain (the
            classical S-PROG model). If "spectral", the AR(2) models are applied
            directly in the spectral domain to reduce memory footprint and improve
            performance :cite:`PCH2019a`.
        extrap_kwargs: dict, optional
            Optional dictionary containing keyword arguments for the extrapolation
            method. See the documentation of pysteps.extrapolation.
        filter_kwargs: dict, optional
            Optional dictionary containing keyword arguments for the filter method.
            See the documentation of pysteps.cascade.bandpass_filters.py.
        measure_time: bool
            If set to True, measure, print and return the computation time.
        """
        self.model_id_attr = model_id_attr
        self.precip_thr = precip_thr
        self.n_cascade_levels = n_cascade_levels
        self.extrap_method = extrap_method
        self.decomp_method = decomp_method
        self.bandpass_filter_method = bandpass_filter_method
        self.ar_order = ar_order
        self.conditional = conditional
        self.probmatching_method = probmatching_method
        self.num_workers = num_workers
        self.fft_method = fft_method
        self.domain = domain
        self.extrap_kwargs = extrap_kwargs
        self.filter_kwargs = filter_kwargs
        self.measure_time = measure_time

    from datetime import timedelta

    @deprecate_args({"R": "precip", "V": "velocity", "R_thr": "precip_thr"}, "1.8.0")
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

        if velocity_griddata.values.squeeze(
        ).ndim != 3 and velocity_griddata.values.squeeze().shape[0] != 2:
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
        precip_np_array = np.array(precip_np_array)
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
                             precip_thr=self.precip_thr,
                             n_cascade_levels=self.n_cascade_levels,
                             extrap_method=self.extrap_method,
                             decomp_method=self.decomp_method,
                             bandpass_filter_method=self.bandpass_filter_method,
                             ar_order=self.ar_order,
                             conditional=self.conditional,
                             probmatching_method=self.probmatching_method,
                             num_workers=self.num_workers,
                             fft_method=self.fft_method,
                             domain=self.domain,
                             extrap_kwargs=self.extrap_kwargs,
                             filter_kwargs=self.filter_kwargs,
                             measure_time=self.measure_time,
                             )

        # 重构meb.griddata
        nlat = result_np.shape[1]
        nlon = result_np.shape[2]
        result_np = result_np.reshape(1, 1, 1, timesteps, nlat, nlon)
        result_griddata = meb.grid_data(grid, result_np)
        return result_griddata
