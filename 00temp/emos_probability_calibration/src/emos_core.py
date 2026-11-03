"""Merged EMOS calibration modules (base, utilities, ECC, calibration)."""

from __future__ import annotations

import warnings
from abc import ABC, abstractmethod
from collections.abc import Iterable
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple, Union

import numpy as np
import scipy.special as sc
import xarray as xr
from numpy import ndarray
from numpy.ma.core import MaskedArray
from scipy import stats
from scipy.optimize import OptimizeResult, minimize
from scipy.stats import norm
from scipy.stats._distn_infrastructure import rv_continuous

from emos_xr_utils import (
    LAT_DIM,
    LON_DIM,
    REALIZATION_DIM,
    SPOT_DIM,
    TIME_DIM,
    CoordinateNotFoundError,
    as_dataarray,
    as_dataset,
    collapsed,
    convert_data_to_2d,
    create_new_diagnostic_dataarray,
    enforce_coordinate_ordering,
    extract_coefficient,
    find_percentile_coordinate,
    find_threshold_coordinate,
    generate_mandatory_attributes,
    get_diagnostic_cube_name_from_probability_name,
    get_diagnostic_name,
    get_forecast_type,
    get_frt_hours,
    get_threshold_coord_name_from_probability_name,
    has_spatial_points,
    is_gridded_data,
    is_spot_data,
    iter_spatial_selections,
    mask_dataarray,
    merge_land_and_sea as _merge_land_and_sea_core,
    pd_timestamp_to_datetime,
    probability_is_above_or_below,
    reshape_pointwise_coefficients,
    spatial_point_count,
    time_value_to_datetime,
    to_output_dataset,
    choose,
    choose_set_of_percentiles,
    concatenate_2d_array_with_2d_array_endpoints,
    create_dataarray_with_percentiles,
    get_bounds_of_distribution,
    insert_lower_and_upper_endpoint_to_1d_array,
    interpolate_multiple_rows_same_x,
    interpolate_multiple_rows_same_y,
    manipulate_n_realizations,
    restore_non_percentile_dimensions,
)

# --- base_init ---

import xarray as xr

try:
    from importlib.metadata import PackageNotFoundError, version

    try:
        __version__ = version("improver")
    except PackageNotFoundError:
        pass
except ImportError:
    pass


class BasePlugin(ABC):
    """IMPROVER 插件的抽象基类。"""

    def __call__(self, *args, **kwargs) -> Any:
        return self.process(*args, **kwargs)

    @abstractmethod
    def process(self, *args, **kwargs) -> Any:
        pass


class PostProcessingPlugin(BasePlugin):
    """后处理插件，为 xarray 输出更新 title 属性。"""

    def __call__(self, *args, **kwargs) -> Any:
        MANDATORY_ATTRIBUTE_DEFAULTS = {
            "title": "unknown",
            "source": "IMPROVER",
            "institution": "unknown",
        }

        result = super().__call__(*args, **kwargs)
        default_title = MANDATORY_ATTRIBUTE_DEFAULTS["title"]

        def _update_title(obj):
            if "title" not in obj.attrs:
                return
            title = obj.attrs["title"]
            if title != default_title and "Post-Processed" not in title:
                obj.attrs["title"] = f"Post-Processed {title}"

        if isinstance(result, xr.Dataset):
            _update_title(result)
            for var in result.data_vars:
                _update_title(result[var])
        elif isinstance(result, xr.DataArray):
            _update_title(result)
        elif isinstance(result, Iterable) and not isinstance(result, str):
            for item in result:
                if isinstance(item, (xr.Dataset, xr.DataArray)):
                    if isinstance(item, xr.Dataset):
                        _update_title(item)
                    else:
                        _update_title(item)
        return result
# --- calibration_utilities ---

import numpy as np
import xarray as xr
from numpy import ndarray
from numpy.ma.core import MaskedArray


# 供 emos_calibration 导入的向后兼容别名
convert_cube_data_to_2d = convert_data_to_2d


def flatten_ignoring_masked_data(
    data_array: Union[MaskedArray, ndarray], preserve_leading_dimension: bool = False
) -> ndarray:
    """展平数组，忽略掩码元素；可选保留首维。"""
    if np.ma.is_masked(data_array):
        if data_array.ndim > 2:
            first_slice_mask = data_array[0].mask
            for i in range(1, data_array.shape[0]):
                if not np.all(first_slice_mask == data_array[i].mask):
                    raise ValueError(
                        "The mask on the input array is not the same for "
                        "every slice along the leading dimension."
                    )
        result = data_array[~data_array.mask]
    else:
        result = data_array.flatten()
    if preserve_leading_dimension:
        result = result.reshape((data_array.shape[0], -1))
    return result


def check_predictor(predictor: str) -> str:
    """校验预测因子名称，返回小写形式。"""
    if predictor.lower() not in ["mean", "realizations"]:
        raise ValueError(
            f"The requested value for the predictor {predictor.lower()} is not an "
            "accepted value. Accepted values are 'mean' or 'realizations'"
        )
    return predictor.lower()


def _time_match_key(t, units: Optional[str] = None) -> datetime:
    """将时间值转换为用于匹配的 datetime 键。"""
    return time_value_to_datetime(t, units)


def filter_non_matching_cubes(
    historic_forecast: Union[xr.DataArray, xr.Dataset],
    truth: Union[xr.DataArray, xr.Dataset],
) -> Tuple[xr.DataArray, xr.DataArray]:
    """按有效时间对齐历史预报与实况。"""
    hf = as_dataarray(historic_forecast)
    tr = as_dataarray(truth)
    if TIME_DIM not in hf.dims:
        raise ValueError("historic_forecast must have a time dimension")

    hf_time_units = hf[TIME_DIM].attrs.get("units")
    tr_time_units = tr[TIME_DIM].attrs.get("units")

    hf_slices = []
    tr_slices = []
    truth_times = []

    for t in hf[TIME_DIM].values:
        t_key = _time_match_key(t, hf_time_units)
        if TIME_DIM not in tr.dims:
            raise ValueError("truth must have a time dimension")
        tr_time_keys = [_time_match_key(v, tr_time_units) for v in tr[TIME_DIM].values]
        if t not in tr[TIME_DIM].values and t_key not in tr_time_keys:
            continue
        tr_at_t = tr.sel({TIME_DIM: t}, drop=False)
        if tr_at_t.sizes.get(TIME_DIM, 0) == 0:
            tr_at_t = tr.sel(
                {TIME_DIM: tr[TIME_DIM].values[tr_time_keys.index(t_key)]},
                drop=False,
            )
        hf_at_t = hf.sel({TIME_DIM: t}, drop=False)
        if np.isnan(hf_at_t.values).all():
            continue
        if t_key in truth_times:
            continue
        truth_times.append(t_key)
        hf_slices.append(hf_at_t)
        tr_slices.append(tr_at_t)

    if not hf_slices:
        raise ValueError(
            "The filtering has found no matches in validity time "
            "between the historic forecasts and the truths."
        )

    hf_out = xr.concat(hf_slices, dim=TIME_DIM)
    tr_out = xr.concat(
        [s.expand_dims(TIME_DIM) if TIME_DIM not in s.dims else s for s in tr_slices],
        dim=TIME_DIM,
    )
    hf_out = enforce_coordinate_ordering(hf_out, list(hf.dims))
    tr_out = enforce_coordinate_ordering(tr_out, list(tr.dims))
    return hf_out, tr_out


def create_unified_frt_coord(historic_forecasts: xr.DataArray) -> xr.DataArray:
    """为系数元数据创建标量 forecast_reference_time 坐标。"""
    frt = historic_forecasts["forecast_reference_time"]
    points = np.atleast_1d(frt.values)
    frt_point = np.max(points)
    return xr.DataArray(
        frt_point,
        attrs=frt.attrs,
        name="forecast_reference_time",
    )


def merge_land_and_sea(
    calibrated_land_only: Union[xr.DataArray, xr.Dataset],
    uncalibrated: Union[xr.DataArray, xr.Dataset],
) -> None:
    """将已校准的陆地数据与未校准的完整场合并。"""
    # _merge imported as _merge_land_and_sea_core at module level

    _merge_land_and_sea_core(as_dataarray(calibrated_land_only), as_dataarray(uncalibrated))


def _ceiling_fp(da: xr.DataArray) -> np.ndarray:
    """将 forecast_period 转为向上取整的小时数。"""
    fp = da["forecast_period"]
    values = fp.values

    if not np.issubdtype(values.dtype, np.timedelta64):
        # 探测它代表的是小时还是纳秒。若数值很大（如时间戳级纳秒），先转为纳秒再转小时。
        if values.size == 1 and values > 10000:
            values = np.array(values, dtype="timedelta64[ns]")
        else:
            # 若数值较小（如 12、15、24），说明本身即为小时整数，直接打包为 [h]。
            values = np.array(values, dtype="timedelta64[h]")

        # 此时执行除法，两边均为时间序列，可安全运算。
    if hasattr(values, "astype"):
        hours = values / np.timedelta64(1, "h")
        return np.ceil(hours.astype(float))

    return np.ceil(np.atleast_1d(values).astype(float))


def forecast_coords_match(first: Union[xr.DataArray, xr.Dataset], second: Union[xr.DataArray, xr.Dataset]) -> None:
    """校验两个输入的 forecast_period 与 forecast_reference_time 是否一致。"""
    a = as_dataarray(first)
    b = as_dataarray(second)
    mismatches = []
    if not np.array_equal(_ceiling_fp(a), _ceiling_fp(b)):
        mismatches.append("rounded forecast_period hours")
    if get_frt_hours(a) != get_frt_hours(b):
        mismatches.append("forecast_reference_time hours")
    if mismatches:
        raise ValueError(
            f"The following coordinates of the two inputs do not match: {', '.join(mismatches)}"
        )


def check_forecast_consistency(forecasts: Union[xr.DataArray, xr.Dataset]) -> None:
    """校验预报是否具有唯一的起报时间与预报时效。"""
    fc = as_dataarray(forecasts)
    frt_hours = get_frt_hours(fc)
    if len(frt_hours) != 1:
        raise ValueError(
            f"Forecasts have been provided with differing hours for the "
            f"forecast reference time {frt_hours}"
        )
    fp = fc["forecast_period"]
    fp_vals = np.atleast_1d(fp.values)
    if len(fp_vals) != 1:
        raise ValueError(
            f"Forecasts have been provided with differing forecast periods {fp_vals}"
        )


def broadcast_data_to_time_coord(
    predictors: List[xr.DataArray],
) -> List[ndarray]:
    """将静态预测因子沿 time 维广播。"""
    num_times = [
        p.sizes[TIME_DIM]
        for p in predictors
        if TIME_DIM in p.dims
    ]
    broadcasted = []
    for p in predictors:
        data = p.values
        if TIME_DIM not in p.dims and num_times:
            data = np.broadcast_to(data, (num_times[0],) + data.shape)
        broadcasted.append(data)
    return broadcasted


def check_data_sufficiency(
    historic_forecasts: Union[xr.DataArray, xr.Dataset],
    truths: Union[xr.DataArray, xr.Dataset],
    point_by_point: bool,
    proportion_of_nans: float,
) -> None:
    """检查历史预报与实况配对中的 NaN 比例是否超过允许阈值。"""
    hf = as_dataarray(historic_forecasts)
    tr = as_dataarray(truths)
    if not has_spatial_points(hf):
        return

    truths_data = np.broadcast_to(tr.values, hf.shape)
    index = np.isnan(hf.values) & np.isnan(truths_data)

    if point_by_point:
        if is_gridded_data(hf):
            lat_axis = hf.dims.index(LAT_DIM)
            lon_axis = hf.dims.index(LON_DIM)
            non_spatial_axes = [
                i for i in range(hf.ndim) if i not in (lat_axis, lon_axis)
            ]
        else:
            spot_axis = hf.dims.index(SPOT_DIM)
            non_spatial_axes = [i for i in range(hf.ndim) if i != spot_axis]
        detected_proportion = np.count_nonzero(index, axis=tuple(non_spatial_axes)) / np.prod(
            np.array(index.shape)[non_spatial_axes]
        )
        if np.any(detected_proportion > proportion_of_nans):
            number_of_sites = np.sum(detected_proportion > proportion_of_nans)
            raise ValueError(
                f"{number_of_sites} sites have a proportion of NaNs that is "
                f"higher than the allowable proportion of NaNs within the "
                f"historic forecasts and truth pairs. The allowable proportion is "
                f"{proportion_of_nans}. The maximum proportion of NaNs is "
                f"{np.amax(detected_proportion)}."
            )
    else:
        detected_proportion = np.count_nonzero(index) / index.size
        if detected_proportion > proportion_of_nans:
            raise ValueError(
                f"The proportion of NaNs detected is {detected_proportion}. "
                f"This is higher than the allowable proportion of NaNs within the "
                f"historic forecasts and truth pairs: {proportion_of_nans}."
            )
# --- scipy continuous distns ---

# ============================================================================
# |                        Copyright SciPy                                   |
# | Code from this point unto the termination banner is copyright SciPy.     |
# |                                                                          |
# | Copyright © 2001, 2002 Enthought, Inc.                                   |
# | All rights reserved.                                                     |
# |                                                                          |
# | Copyright © 2003-2019 SciPy Developers.                                  |
# | All rights reserved.                                                     |
# |                                                                          |
# | Redistribution and use in source and binary forms, with or without       |
# | modification, are permitted provided that the following conditions are   |
# | met:                                                                     |
# |                                                                          |
# | Redistributions of source code must retain the above copyright notice,   |
# | this list of conditions and the following disclaimer.                    |
# |                                                                          |
# | - Redistributions in binary form must reproduce the above copyright      |
# |   notice, this list of conditions and the following disclaimer in the    |
# |   documentation and/or other materials provided with the distribution.   |
# | - Neither the name of Enthought nor the names of the SciPy Developers    |
# |   may be used to endorse or promote products derived from this software  |
# |   without specific prior written permission.                             |
# |                                                                          |
# | THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS      |
# | “AS IS” AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT        |
# | LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A  |
# | PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE REGENTS OR      |
# | CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL,    |
# | EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO,      |
# | PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR       |
# | PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF   |
# | LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING     |
# | NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS       |
# | SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.             |
# |                                                                          |
# | Further details can be found at scipy.org/scipylib/license.html          |
# ============================================================================

# Source: https://github.com/scipy/scipy/blob/v1.3.3/scipy/stats/_continuous_\
# distns.py


_norm_pdf_C = np.sqrt(2 * np.pi)
_norm_pdf_logC = np.log(_norm_pdf_C)


def _norm_pdf(x):
    return np.exp(-(x**2) / 2.0) / _norm_pdf_C


def _norm_logpdf(x):
    return -(x**2) / 2.0 - _norm_pdf_logC


def _norm_cdf(x):
    return sc.ndtr(x)


def _norm_ppf(q):
    return sc.ndtri(q)


def _norm_sf(x):
    return _norm_cdf(-x)


def _norm_isf(q):
    return -_norm_ppf(q)


class truncnorm_gen(rv_continuous):
    r"""A truncated normal continuous random variable.

    %(before_notes)s

    Notes
    -----
    The standard form of this distribution is a standard normal truncated to
    the range [a, b] --- notice that a and b are defined over the domain of the
    standard normal.  To convert clip values for a specific mean and standard
    deviation, use::

        a, b = (myclip_a - my_mean) / my_std, (myclip_b - my_mean) / my_std

    `truncnorm` takes :math:`a` and :math:`b` as shape parameters.

    %(after_notes)s

    %(example)s

    """

    def _argcheck(self, a, b):
        return a < b

    def _get_support(self, a, b):
        return a, b

    def _get_norms(self, a, b):
        _nb = _norm_cdf(b)
        _na = _norm_cdf(a)
        _sb = _norm_sf(b)
        _sa = _norm_sf(a)
        _delta = np.where(a > 0, _sa - _sb, _nb - _na)
        with np.errstate(divide="ignore"):
            return _na, _nb, _sa, _sb, _delta, np.log(_delta)

    def _pdf(self, x, a, b):
        ans = self._get_norms(a, b)
        _delta = ans[4]
        return _norm_pdf(x) / _delta

    def _logpdf(self, x, a, b):
        ans = self._get_norms(a, b)
        _logdelta = ans[5]
        return _norm_logpdf(x) - _logdelta

    def _cdf(self, x, a, b):
        ans = self._get_norms(a, b)
        _na, _delta = ans[0], ans[4]
        return (_norm_cdf(x) - _na) / _delta

    def _ppf(self, q, a, b):
        # XXX Use _lazywhere...
        ans = self._get_norms(a, b)
        _na, _nb, _sa, _sb = ans[:4]
        ppf = np.where(
            a > 0,
            _norm_isf(q * _sb + _sa * (1.0 - q)),
            _norm_ppf(q * _nb + _na * (1.0 - q)),
        )
        return ppf


truncnorm = truncnorm_gen(name="truncnorm")


# ============================================================================
# |                        END SciPy copyright                               |
# ============================================================================
# --- xarray_ecc ---

import numpy as np
import xarray as xr
from numpy import ndarray
from scipy import stats



def _align_distribution_parameters_to_template(
    location_parameter: Union[xr.DataArray, xr.Dataset],
    scale_parameter: Union[xr.DataArray, xr.Dataset],
    template: Union[xr.DataArray, xr.Dataset],
):
    """去掉 location/scale 上输出模板中不存在的单例维度。"""
    loc = as_dataarray(location_parameter)
    scale = as_dataarray(scale_parameter)
    tmpl = as_dataarray(template)
    for dim in list(loc.dims):
        if dim not in tmpl.dims and loc.sizes[dim] == 1:
            loc = loc.squeeze(dim, drop=True)
            scale = scale.squeeze(dim, drop=True)
    return loc, scale


class RebadgePercentilesAsRealizations(BasePlugin):
    """将百分位坐标重标记为集合成员 realization 坐标。"""

    @staticmethod
    def process(
        da: Union[xr.DataArray, xr.Dataset],
        ensemble_realization_numbers: Optional[ndarray] = None,
    ) -> xr.DataArray:
        """将等间距百分位数据重标记为 realization 维。"""
        cube = as_dataarray(da)
        perc_name = find_percentile_coordinate(cube)
        if "realization" in cube.coords or "realization" in cube.dims:
            raise ValueError(
                "Cannot rebadge percentile coordinate to realization "
                "because a realization coordinate already exists."
            )
        percentiles = np.sort(np.unique(np.append(cube[perc_name].values, [0, 100])))
        diffs = np.diff(percentiles)
        if not np.isclose(np.max(diffs), np.min(diffs)):
            raise ValueError(
                "The percentile array cannot be rebadged as ensemble realizations. "
                f"The percentiles provided were {cube[perc_name].values}"
            )
        if ensemble_realization_numbers is None:
            ensemble_realization_numbers = np.arange(
                cube.sizes[perc_name], dtype=np.int32
            )
        out = cube.rename({perc_name: "realization"})
        out = out.assign_coords(
            realization=("realization", ensemble_realization_numbers.astype(np.int32))
        )
        out["realization"].attrs["units"] = "1"
        return out


class ResamplePercentiles(BasePlugin):
    """对百分位预报进行重采样或插值到新的百分位集合。"""

    def __init__(self, ecc_bounds_warning: bool = False, skip_ecc_bounds: bool = False):
        self.ecc_bounds_warning = ecc_bounds_warning
        self.skip_ecc_bounds = skip_ecc_bounds

    def _add_bounds_to_percentiles_and_forecast_at_percentiles(
        self, percentiles, forecast_at_percentiles, bounds_pairing
    ):
        """在百分位轴与预报值两端追加分布边界。"""
        lower_bound, upper_bound = bounds_pairing
        percentiles = insert_lower_and_upper_endpoint_to_1d_array(percentiles, 0, 100)
        forecast = concatenate_2d_array_with_2d_array_endpoints(
            forecast_at_percentiles, lower_bound, upper_bound
        )
        if np.any(np.diff(forecast) < 0):
            msg = (
                "Forecast values exist that fall outside the expected extrema "
                f"values {bounds_pairing}."
            )
            if self.ecc_bounds_warning:
                warnings.warn(msg + " Exceeded values will be used as new bounds.")
                if upper_bound < forecast.max():
                    upper_bound = forecast.max()
                if lower_bound > forecast.min():
                    lower_bound = forecast.min()
                forecast = concatenate_2d_array_with_2d_array_endpoints(
                    forecast_at_percentiles, lower_bound, upper_bound
                )
            else:
                raise ValueError(msg)
        if np.any(np.diff(percentiles) < 0):
            raise ValueError(f"Percentiles must be ascending. Got {percentiles}")
        return percentiles, forecast

    def _interpolate_percentiles(self, forecast_at_percentiles, desired_percentiles, perc_name):
        """将预报插值到目标百分位坐标。"""
        original_percentiles = forecast_at_percentiles[perc_name].values
        forecast_at_reshaped = convert_data_to_2d(
            enforce_coordinate_ordering(forecast_at_percentiles, perc_name), perc_name
        )
        if not self.skip_ecc_bounds:
            bounds = get_bounds_of_distribution(
                get_diagnostic_name(forecast_at_percentiles),
                forecast_at_percentiles.attrs.get("units", "1"),
            )
            original_percentiles, forecast_at_reshaped = (
                self._add_bounds_to_percentiles_and_forecast_at_percentiles(
                    original_percentiles, forecast_at_reshaped, bounds
                )
            )
        interpolated = interpolate_multiple_rows_same_x(
            np.array(desired_percentiles, dtype=np.float64),
            original_percentiles.astype(np.float64),
            forecast_at_reshaped.astype(np.float64),
        )
        interpolated = np.transpose(interpolated)
        template = forecast_at_percentiles.isel({perc_name: 0}, drop=True)
        data = restore_non_percentile_dimensions(
            interpolated, template, len(desired_percentiles)
        )
        return create_dataarray_with_percentiles(
            desired_percentiles, template, data, forecast_at_percentiles.attrs.get("units")
        )

    def process(
        self,
        forecast_at_percentiles: Union[xr.DataArray, xr.Dataset],
        no_of_percentiles: Optional[int] = None,
        sampling: Optional[str] = "quantile",
        percentiles: Optional[List] = None,
    ) -> xr.DataArray:
        """将百分位预报重采样到指定数量或百分位列表。"""
        fc = as_dataarray(forecast_at_percentiles)
        perc_name = find_percentile_coordinate(fc)
        if percentiles is None:
            if no_of_percentiles is None:
                no_of_percentiles = fc.sizes[perc_name]
            percentiles = choose_set_of_percentiles(no_of_percentiles, sampling=sampling)
        return self._interpolate_percentiles(fc, percentiles, perc_name)


class ConvertProbabilitiesToPercentiles(BasePlugin):
    """将阈值概率预报转换为百分位预报。"""

    def __init__(
        self,
        ecc_bounds_warning: bool = False,
        mask_percentiles: bool = False,
        skip_ecc_bounds: bool = False,
    ):
        self.ecc_bounds_warning = ecc_bounds_warning
        self.mask_percentiles = mask_percentiles
        self.skip_ecc_bounds = skip_ecc_bounds

    def _add_threshold_endpoints(self, threshold_points, probabilities_for_cdf, bounds_pairing):
        """在阈值轴与 CDF 概率两端追加分布边界。"""
        lower_bound, upper_bound = bounds_pairing
        tp = insert_lower_and_upper_endpoint_to_1d_array(
            threshold_points, lower_bound, upper_bound
        )
        probs = concatenate_2d_array_with_2d_array_endpoints(probabilities_for_cdf, 0, 1)
        if np.any(np.diff(tp) < 0):
            msg = f"Threshold values {tp} not ascending relative to bounds {bounds_pairing}"
            if self.ecc_bounds_warning:
                warnings.warn(msg)
            else:
                raise ValueError(msg)
        return tp, probs

    def _probabilities_to_percentiles(self, forecast_probabilities, percentiles):
        """沿阈值维插值，得到目标百分位上的预报值。"""
        thresh_name = find_threshold_coordinate(forecast_probabilities)
        threshold_points = forecast_probabilities[thresh_name].values
        enforce_coordinate_ordering(forecast_probabilities, thresh_name)
        prob_slices = convert_data_to_2d(forecast_probabilities, coord=thresh_name)
        prob_slices = np.around(prob_slices, 9)
        relation = probability_is_above_or_below(forecast_probabilities)
        if relation == "above":
            probabilities_for_cdf = 1 - prob_slices
        elif relation == "below":
            probabilities_for_cdf = prob_slices
        else:
            raise NotImplementedError(f"Unsupported threshold relation {relation}")
        if not self.skip_ecc_bounds:
            phenom = get_threshold_coord_name_from_probability_name(
                get_diagnostic_name(forecast_probabilities)
            )
            bounds = get_bounds_of_distribution(
                phenom, forecast_probabilities.attrs.get("units", "1")
            )
            threshold_points, probabilities_for_cdf = self._add_threshold_endpoints(
                threshold_points, probabilities_for_cdf, bounds
            )
        result_slices = interpolate_multiple_rows_same_y(
            np.array(percentiles, dtype=np.float64) / 100.0,
            probabilities_for_cdf.astype(np.float64),
            threshold_points.astype(np.float64),
        )
        template = forecast_probabilities.isel({thresh_name: 0}, drop=True)
        data = restore_non_percentile_dimensions(
            np.transpose(result_slices), template, len(percentiles)
        )
        diag_name = get_diagnostic_cube_name_from_probability_name(
            get_diagnostic_name(forecast_probabilities)
        )
        out = create_dataarray_with_percentiles(
            percentiles, template, data, forecast_probabilities.attrs.get("units")
        )
        out.attrs["standard_name"] = diag_name
        out.name = diag_name
        return out

    def process(
        self,
        forecast_probabilities: Union[xr.DataArray, xr.Dataset],
        no_of_percentiles: Optional[int] = None,
        percentiles: Optional[List[float]] = None,
    ) -> xr.DataArray:
        """将概率预报转换为百分位预报。"""
        fc = as_dataarray(forecast_probabilities)
        if percentiles is None:
            if no_of_percentiles is None:
                raise ValueError("Provide no_of_percentiles or percentiles")
            percentiles = choose_set_of_percentiles(no_of_percentiles)
        return self._probabilities_to_percentiles(fc, percentiles)


class ConvertLocationAndScaleParameters:
    """位置-尺度参数与 scipy 分布之间的公共基类。"""

    def __init__(self, distribution: str = "norm", shape_parameters: Optional[ndarray] = None):
        """初始化分布类型与形状参数。"""
        if distribution == "truncnorm":
            self.distribution = truncnorm
        else:
            self.distribution = getattr(stats, distribution)
        if shape_parameters is None:
            if self.distribution.name == "truncnorm":
                raise ValueError("truncnorm requires shape_parameters")
            shape_parameters = []
        self.shape_parameters = list(shape_parameters)

    def _rescale_shape_parameters(self, location_parameter, scale_parameter):
        """将 truncnorm 形状参数重标度到标准化坐标。"""
        if self.distribution.name == "truncnorm":
            self.shape_parameters = [
                (v - location_parameter) / scale_parameter for v in self.shape_parameters
            ]


class ConvertLocationAndScaleParametersToPercentiles(
    BasePlugin, ConvertLocationAndScaleParameters
):
    """由位置/尺度参数计算百分位预报。"""

    def _location_and_scale_parameters_to_percentiles(
        self, location_parameter, scale_parameter, template, percentiles
    ):
        """对每个空间点用分布 ppf 计算指定百分位值。"""
        loc = as_dataarray(location_parameter)
        scale = as_dataarray(scale_parameter)
        tmpl = as_dataarray(template)
        loc, scale = _align_distribution_parameters_to_template(loc, scale, tmpl)
        location_data = np.ma.filled(loc.values, 1).flatten()
        scale_data = np.ma.filled(scale.values, 1).flatten()
        fractions = np.array([x / 100.0 for x in percentiles], dtype=np.float32)
        result = np.zeros((len(fractions), location_data.shape[0]), dtype=np.float32)
        self._rescale_shape_parameters(location_data, scale_data)
        dist = self.distribution(*self.shape_parameters, loc=location_data, scale=scale_data)
        for index, percentile in enumerate(fractions):
            result[index, :] = dist.ppf(np.repeat(percentile, len(location_data)))
            if np.any(scale_data <= 0):
                nan_index = np.argwhere(np.isnan(result[index, :]))
                result[index, nan_index] = location_data[nan_index]
            if np.any(np.isnan(result)):
                raise ValueError(f"NaNs in result for percentile index {index}")
        result = result.reshape((len(percentiles),) + loc.shape)
        tmpl_slice = tmpl
        for d in ("realization", "percentile"):
            if d in tmpl_slice.dims:
                tmpl_slice = tmpl_slice.isel({d: 0}, drop=True)
        mask = np.logical_or(np.ma.getmaskarray(loc.values), np.ma.getmaskarray(scale.values))
        out = create_dataarray_with_percentiles(
            percentiles, tmpl_slice, result, loc.attrs.get("units")
        )
        if np.any(mask):
            mask_array = np.stack([mask] * len(percentiles))
            out = out.where(~mask_array)
        return out

    def process(
        self,
        location_parameter,
        scale_parameter,
        template_cube,
        no_of_percentiles: Optional[int] = None,
        percentiles: Optional[List[float]] = None,
    ) -> xr.DataArray:
        """由位置/尺度参数生成百分位 DataArray。"""
        if no_of_percentiles and percentiles:
            raise ValueError("Specify either no_of_percentiles or percentiles, not both")
        if no_of_percentiles:
            percentiles = choose_set_of_percentiles(no_of_percentiles)
        return self._location_and_scale_parameters_to_percentiles(
            location_parameter, scale_parameter, template_cube, percentiles
        )


class ConvertLocationAndScaleParametersToProbabilities(
    BasePlugin, ConvertLocationAndScaleParameters
):
    """由位置/尺度参数计算阈值概率预报。"""

    def process(self, location_parameter, scale_parameter, probability_template):
        """对每个阈值计算超越或低于概率，并组装概率 DataArray。"""
        loc = as_dataarray(location_parameter)
        scale = as_dataarray(scale_parameter)
        tmpl = as_dataarray(probability_template)
        loc, scale = _align_distribution_parameters_to_template(loc, scale, tmpl)
        thresh_name = find_threshold_coordinate(tmpl)
        thresholds = tmpl[thresh_name].values
        location_data = np.ma.filled(loc.values, 0).flatten()
        scale_data = np.ma.filled(scale.values, 1).flatten()
        self._rescale_shape_parameters(location_data, scale_data)
        dist = self.distribution(*self.shape_parameters, loc=location_data, scale=scale_data)
        relation = probability_is_above_or_below(tmpl)
        probs = []
        for t in thresholds:
            if relation == "above":
                # 超越概率：用 sf() 计算大于阈值的概率（即 1 - cdf）
                probs.append(dist.sf(np.full_like(location_data, t)))
            elif relation == "below":
                # 低于/等于概率：仍使用 cdf()
                probs.append(dist.cdf(np.full_like(location_data, t)))
            else:
                raise NotImplementedError(f"Unsupported threshold relation {relation}")
            # probs.append(dist.cdf(np.full_like(location_data, t)))
        data = np.array(probs, dtype=np.float32).reshape((len(thresholds),) + loc.shape)
        tmpl_slice = tmpl.isel({thresh_name: 0}, drop=True)
        for dim in list(tmpl_slice.dims):
            if dim not in loc.dims:
                tmpl_slice = tmpl_slice.squeeze(dim, drop=True)
        coords = dict(tmpl_slice.coords)
        coords[thresh_name] = ("threshold", thresholds)
        dims = ["threshold"] + list(tmpl_slice.dims)
        out = xr.DataArray(
            data,
            dims=dims,
            coords={k: v for k, v in coords.items() if k in dims},
            attrs=tmpl.attrs,
            name=get_diagnostic_name(tmpl),
        )
        return out


class EnsembleReordering(BasePlugin):
    """集合 Copula 耦合：按原始集合秩对后处理百分位重排。"""

    @staticmethod
    def _recycle_raw_ensemble_realizations(post_processed, raw_forecast, percentile_coord_name):
        """将原始集合成员数调整为与后处理百分位数一致。"""
        plen = post_processed.sizes[percentile_coord_name]
        raw = as_dataarray(raw_forecast)
        if raw.sizes["realization"] == plen:
            return raw
        return manipulate_n_realizations(raw, plen)

    @staticmethod
    def _rank_slice(cal, raw, perc_name, random_ordering, rng, tie_break):
        """对单个切片执行秩匹配重排。"""
        cal = enforce_coordinate_ordering(cal, perc_name)
        raw = enforce_coordinate_ordering(raw, "realization")
        if random_ordering:
            ranking = np.argsort(rng.rand(*raw.values.shape), axis=0)
        else:
            if tie_break == "random":
                tie_data = rng.rand(*raw.values.shape)
            elif tie_break == "realization":
                reals = raw["realization"].values
                tie_data = np.broadcast_to(
                    reals.reshape(-1, *([1] * (raw.ndim - 1))), raw.values.shape
                )
            else:
                raise ValueError(f'tie_break must be "random" or "realization", not {tie_break}')
            sorting_index = np.lexsort((tie_data, raw.values), axis=0)
            ranking = np.argsort(sorting_index, axis=0)
        mask = np.ma.getmask(cal.values)
        reordered = choose(ranking, cal.values)
        if mask is not np.ma.nomask:
            reordered = np.ma.MaskedArray(reordered, mask, dtype=np.float32)
        return cal.copy(data=reordered)

    @staticmethod
    def rank_ecc(
        post_processed_forecast_percentiles,
        raw_forecast_realizations,
        random_ordering=False,
        random_seed=None,
        tie_break="random",
    ):
        """对后处理百分位与原始集合执行秩 ECC 重排。"""
        if random_seed is not None:
            random_seed = int(random_seed)
        rng = np.random.RandomState(random_seed)
        cal = as_dataarray(post_processed_forecast_percentiles)
        raw = as_dataarray(raw_forecast_realizations)
        perc_name = find_percentile_coordinate(cal)
        if "time" in cal.dims and "time" in raw.dims:
            results = []
            for t in cal["time"].values:
                cal_t = cal.sel(time=t)
                raw_t = raw.sel(time=t) if t in raw["time"].values else raw.isel(time=0)
                results.append(
                    EnsembleReordering._rank_slice(
                        cal_t, raw_t, perc_name, random_ordering, rng, tie_break
                    )
                )
            return xr.concat(results, dim="time")
        return EnsembleReordering._rank_slice(
            cal, raw, perc_name, random_ordering, rng, tie_break
        )

    def process(
        self,
        post_processed_forecast,
        raw_forecast,
        random_ordering=False,
        random_seed=None,
        tie_break="random",
    ) -> xr.DataArray:
        """完整 ECC 流程：重排百分位并重标记为 realization。"""
        cal = as_dataarray(post_processed_forecast)
        raw = as_dataarray(raw_forecast)
        perc_name = find_percentile_coordinate(cal)
        raw = self._recycle_raw_ensemble_realizations(cal, raw, perc_name)
        reordered = self.rank_ecc(cal, raw, random_ordering, random_seed, tie_break)
        return RebadgePercentilesAsRealizations.process(
            reordered, ensemble_realization_numbers=raw["realization"].values
        )
# --- emos_calibration ---

import numpy as np
import xarray as xr
from numpy import ndarray
from scipy.optimize import OptimizeResult, minimize
from scipy.stats import norm


PredictorList = List[xr.DataArray]
InputField = Union[xr.DataArray, xr.Dataset]
AdditionalFields = Optional[List[InputField]]


def _as_list_of_dataarrays(fields: AdditionalFields) -> PredictorList:
    if not fields:
        return []
    return [as_dataarray(f) for f in fields]


def _predictor_name(da: xr.DataArray) -> str:
    return get_diagnostic_name(da)


def _normalize_spatial_fields(fields: AdditionalFields) -> PredictorList:
    return [as_dataarray(f) for f in _as_list_of_dataarrays(fields)]


class ContinuousRankedProbabilityScoreMinimisers(BasePlugin):
    """通过最小化 CRPS 估计 EMOS 系数的优化器。"""

    TOLERATED_PERCENTAGE_CHANGE = 5
    BAD_VALUE = np.float64(999999)

    def __init__(
        self,
        predictor: str,
        tolerance: float = 0.02,
        max_iterations: int = 1000,
        point_by_point: bool = False,
    ) -> None:
        self.minimisation_dict = {
            "norm": self.calculate_normal_crps,
            "truncnorm": self.calculate_truncated_normal_crps,
        }
        self.predictor = check_predictor(predictor)
        self.tolerance = tolerance
        self.max_iterations = max_iterations
        self.point_by_point = point_by_point

    def _normal_crps_preparation(
        self, initial_guess, forecast_predictor, truth, forecast_var
    ):
        aa, bb, gamma, delta = (
            initial_guess[0],
            initial_guess[1:-2],
            initial_guess[-2],
            initial_guess[-1],
        )
        if self.predictor == "mean":
            a_b = np.array([aa, *np.atleast_1d(bb)], dtype=np.float64)
        else:
            bb = bb * bb
            a_b = np.array([aa] + bb.tolist(), dtype=np.float64)
        new_col = np.ones(truth.shape, dtype=np.float32)
        all_data = np.column_stack((new_col, forecast_predictor))
        mu = np.dot(all_data, a_b)
        sigma = np.sqrt(gamma * gamma + delta * delta * forecast_var)
        xz = (truth - mu) / sigma
        return mu, sigma, xz, norm.cdf(xz), norm.pdf(xz)

    def calculate_normal_crps(self, initial_guess, forecast_predictor, truth, forecast_var, sqrt_pi):
        mu, sigma, xz, normal_cdf, normal_pdf = self._normal_crps_preparation(
            initial_guess, forecast_predictor, truth, forecast_var
        )
        if np.isfinite(np.min(mu / sigma)):
            return np.nanmean(
                sigma * (xz * (2 * normal_cdf - 1) + 2 * normal_pdf - 1 / sqrt_pi)
            )
        return self.BAD_VALUE

    def calculate_truncated_normal_crps(
        self, initial_guess, forecast_predictor, truth, forecast_var, sqrt_pi
    ):
        mu, sigma, xz, normal_cdf, normal_pdf = self._normal_crps_preparation(
            initial_guess, forecast_predictor, truth, forecast_var
        )
        x0 = mu / sigma
        normal_cdf_0 = norm.cdf(x0)
        normal_cdf_root_two = norm.cdf(np.sqrt(2) * x0)
        if np.isfinite(np.min(mu / sigma)) or (np.min(mu / sigma) >= -3):
            return np.nanmean(
                (sigma / (normal_cdf_0 * normal_cdf_0))
                * (
                    xz * normal_cdf_0 * (2 * normal_cdf + normal_cdf_0 - 2)
                    + 2 * normal_pdf * normal_cdf_0
                    - normal_cdf_root_two / sqrt_pi
                )
            )
        return self.BAD_VALUE

    def _calculate_percentage_change_in_last_iteration(self, allvecs):
        last_iteration_percentage_change = (
            np.absolute((allvecs[-1] - allvecs[-2]) / allvecs[-2]) * 100
        )
        if np.any(last_iteration_percentage_change > self.TOLERATED_PERCENTAGE_CHANGE):
            warnings.warn(
                f"Final iteration change {last_iteration_percentage_change} exceeds "
                f"{self.TOLERATED_PERCENTAGE_CHANGE}% threshold."
            )

    def _minimise_caller(
        self, minimisation_function, initial_guess, forecast_predictor_data, truth_data, forecast_var_data, sqrt_pi
    ):
        return minimize(
            minimisation_function,
            initial_guess,
            args=(forecast_predictor_data, truth_data, forecast_var_data, sqrt_pi),
            method="Nelder-Mead",
            tol=self.tolerance,
            options={"maxiter": self.max_iterations, "return_all": True},
        )

    def _prepare_forecasts(self, forecast_predictors: PredictorList) -> ndarray:
        preserve = self.predictor == "realizations"
        broadcasted = broadcast_data_to_time_coord(forecast_predictors)
        flattened = [
            flatten_ignoring_masked_data(d, preserve_leading_dimension=preserve)
            for d in broadcasted
        ]
        if len(flattened) > 1:
            return np.ma.vstack(flattened)
        return flattened[0]

    def _process_points_independently(
        self, minimisation_function, initial_guess, forecast_predictors, truth, forecast_var, sqrt_pi
    ):
        if not has_spatial_points(truth):
            raise ValueError(
                "point_by_point requires spot_index or lat/lon spatial dimensions"
            )
        optimised_coeffs = []
        for point_idx, selection in enumerate(iter_spatial_selections(truth)):
            truth_slice = truth.sel(selection)
            fv_slice = forecast_var.sel(selection)
            fp_slice = [fp.sel(selection) for fp in forecast_predictors]
            fp_data = self._prepare_forecasts(fp_slice)
            ig = initial_guess[point_idx] if initial_guess.ndim > 1 else initial_guess
            if np.all(np.isnan(truth_slice.values)):
                optimised_coeffs.append(np.array(ig, dtype=np.float32))
            else:
                optimised_coeffs.append(
                    self._minimise_caller(
                        minimisation_function, ig, fp_data.T, truth_slice.values, fv_slice.values, sqrt_pi
                    ).x.astype(np.float32)
                )
        return reshape_pointwise_coefficients(optimised_coeffs, truth)

    def _process_points_together(
        self, minimisation_function, initial_guess, forecast_predictors, truth, forecast_var, sqrt_pi
    ):
        truth_data = flatten_ignoring_masked_data(truth.values)
        forecast_var_data = flatten_ignoring_masked_data(forecast_var.values)
        forecast_predictor_data = self._prepare_forecasts(forecast_predictors)
        optimised_coeffs = self._minimise_caller(
            minimisation_function,
            initial_guess,
            forecast_predictor_data.T,
            truth_data,
            forecast_var_data,
            sqrt_pi,
        )
        if not optimised_coeffs.success:
            warnings.warn(
                f"Minimisation did not converge after {self.max_iterations} iterations."
            )
        self._calculate_percentage_change_in_last_iteration(optimised_coeffs.allvecs)
        return optimised_coeffs.x.astype(np.float32)

    def process(
        self,
        initial_guess: ndarray,
        forecast_predictors: PredictorList,
        truth: xr.DataArray,
        forecast_var: xr.DataArray,
        distribution: str,
    ) -> ndarray:
        """对给定初始猜测执行 CRPS 最小化，返回优化后的系数数组。"""
        minimisation_function = self.minimisation_dict[distribution]
        if self.predictor == "realizations":
            forecast_predictors = [
                enforce_coordinate_ordering(fp, REALIZATION_DIM) for fp in forecast_predictors
            ]
        initial_guess = np.array(initial_guess, dtype=np.float64)
        forecast_predictors = [fp.astype(np.float64) for fp in forecast_predictors]
        forecast_var = forecast_var.astype(np.float64)
        truth = truth.astype(np.float64)
        sqrt_pi = np.sqrt(np.pi)
        if self.point_by_point:
            return self._process_points_independently(
                minimisation_function, initial_guess, forecast_predictors, truth, forecast_var, sqrt_pi
            )
        return self._process_points_together(
            minimisation_function, initial_guess, forecast_predictors, truth, forecast_var, sqrt_pi
        )


class EstimateCoefficientsForEnsembleCalibration(BasePlugin):
    """从历史预报与实况训练 EMOS 校准系数。"""

    coeff_names = ["alpha", "beta", "gamma", "delta"]

    def __init__(
        self,
        distribution: str,
        point_by_point: bool = False,
        use_default_initial_guess: bool = False,
        desired_units: Optional[Any] = None,
        predictor: str = "mean",
        tolerance: float = 0.02,
        max_iterations: int = 1000,
        proportion_of_nans: float = 0.5,
    ) -> None:
        if desired_units is not None:
            raise ValueError(
                "desired_units is not supported in the xarray implementation. "
                "Convert historic forecasts and truths to the same units before calling."
            )
        self.distribution = distribution
        self.point_by_point = point_by_point
        self.use_default_initial_guess = use_default_initial_guess
        self.predictor = check_predictor(predictor)
        self._validate_distribution()
        self.tolerance = tolerance
        self.max_iterations = max_iterations
        self.proportion_of_nans = proportion_of_nans
        self.minimiser = ContinuousRankedProbabilityScoreMinimisers(
            self.predictor, tolerance, max_iterations, point_by_point
        )

    def _validate_distribution(self):
        valid = ContinuousRankedProbabilityScoreMinimisers(self.predictor).minimisation_dict
        if self.distribution not in valid:
            raise ValueError(f"Distribution {self.distribution} not in {list(valid)}")

    def _set_attributes(self, historic_forecasts: xr.DataArray) -> Dict[str, Any]:
        attrs = {
            "diagnostic_standard_name": get_diagnostic_name(historic_forecasts),
            "distribution": self.distribution,
            "title": "Ensemble Model Output Statistics coefficients",
        }
        if self.distribution == "truncnorm":
            attrs["shape_parameters"] = np.array([0, np.inf], dtype=np.float32)
        return attrs

    def _template_for_coefficients(self, historic_forecasts: xr.DataArray) -> xr.DataArray:
        drop = [REALIZATION_DIM, TIME_DIM]
        tmpl = historic_forecasts
        for d in drop:
            if d in tmpl.dims:
                tmpl = tmpl.isel({d: 0}, drop=True)
        if not self.point_by_point and has_spatial_points(tmpl):
            # 全场共用系数：去掉全部空间维（站点 spot_index 或格点 lat/lon）
            for d in (SPOT_DIM, LAT_DIM, LON_DIM):
                if d in tmpl.dims:
                    tmpl = tmpl.isel({d: 0}, drop=True)
        return tmpl

    def _add_predictor_coords(
        self, template: xr.DataArray, forecast_predictors: PredictorList
    ) -> Tuple[List[str], List[str]]:
        names = [_predictor_name(fp) for fp in forecast_predictors]
        return list(range(len(names))), names

    def _build_coefficient_array(
        self,
        coeff_name: str,
        coeff_data: ndarray,
        template: xr.DataArray,
        historic_forecasts: xr.DataArray,
        forecast_predictors: PredictorList,
    ) -> xr.DataArray:
        if self.point_by_point and has_spatial_points(historic_forecasts):
            tmpl = historic_forecasts.isel({TIME_DIM: 0, REALIZATION_DIM: 0}, drop=True)
        else:
            tmpl = self._template_for_coefficients(historic_forecasts)
        units = historic_forecasts.attrs.get("units", "1")
        if coeff_name not in ("alpha", "gamma"):
            units = "1"
        data = np.array(coeff_data, dtype=np.float32)
        dims = list(tmpl.dims)
        coords = {d: tmpl[d] for d in dims}
        for c in tmpl.coords:
            if c not in dims:
                coords[c] = tmpl[c]
        if coeff_name == "beta":
            pidx, pnames = self._add_predictor_coords(tmpl, forecast_predictors)
            if self.predictor == "realizations":
                dims = [REALIZATION_DIM] + dims
                coords[REALIZATION_DIM] = historic_forecasts[REALIZATION_DIM]
            dims = ["predictor_index"] + dims
            coords["predictor_index"] = ("predictor_index", np.array(pidx, dtype=np.int8))
            coords["predictor_name"] = ("predictor_index", np.array(pnames, dtype=object))
            shape = [len(pidx)] + [tmpl.sizes[d] for d in tmpl.dims]
            data = np.reshape(data, shape)
        frt = create_unified_frt_coord(historic_forecasts)
        coords["forecast_reference_time"] = frt
        if "forecast_period" in historic_forecasts.coords:
            coords["forecast_period"] = historic_forecasts["forecast_period"]
        attrs = generate_mandatory_attributes([historic_forecasts])
        attrs.update(self._set_attributes(historic_forecasts))
        return xr.DataArray(
            data,
            dims=dims,
            coords=coords,
            attrs=attrs,
            name=f"emos_coefficient_{coeff_name}",
        )

    def create_coefficients_dataset(
        self,
        optimised_coeffs: Union[List[float], ndarray],
        historic_forecasts: InputField,
        forecast_predictors: PredictorList,
    ) -> xr.Dataset:
        hf = as_dataarray(historic_forecasts)
        if self.predictor == "realizations" or len(forecast_predictors) > 1:
            optimised_coeffs = [
                optimised_coeffs[0],
                optimised_coeffs[1:-2],
                optimised_coeffs[-2],
                optimised_coeffs[-1],
            ]
        if len(optimised_coeffs) != len(self.coeff_names):
            raise ValueError("Coefficient count mismatch")
        data_vars = {}
        for coeff, name in zip(optimised_coeffs, self.coeff_names):
            data_vars[f"emos_coefficient_{name}"] = self._build_coefficient_array(
                name, coeff, self._template_for_coefficients(hf), hf, forecast_predictors
            )
        ds = xr.Dataset(data_vars)
        ds.attrs.update(self._set_attributes(hf))
        return ds

    def compute_initial_guess(
        self, truths, forecast_predictor, predictor, number_of_realizations
    ):
        default = (
            self.use_default_initial_guess
            or np.any(np.isnan(truths))
            or np.any(np.isnan(forecast_predictor))
        )
        if predictor == "mean" and default:
            initial_beta = np.repeat(1.0 / forecast_predictor.shape[0], forecast_predictor.shape[0]).tolist()
            initial_guess = [0] + initial_beta + [0, 1]
        elif predictor == "realizations" and default:
            initial_beta = np.repeat(
                np.sqrt(1.0 / number_of_realizations), number_of_realizations
            ).tolist()
            initial_guess = [0] + initial_beta + [0, 1]
        elif not self.use_default_initial_guess:
            import statsmodels.api as sm

            truths_flat = flatten_ignoring_masked_data(truths)
            fp_flat = flatten_ignoring_masked_data(
                forecast_predictor, preserve_leading_dimension=True
            )
            val = sm.add_constant(fp_flat.T, has_constant="add").astype(np.float64)
            est = sm.OLS(truths_flat.astype(np.float64), val).fit()
            initial_guess = [est.params[0].astype(np.float32)] + est.params[1:].astype(np.float32).tolist() + [0, 1]
        else:
            initial_guess = [0, 1, 0, 1]
        return np.array(initial_guess, dtype=np.float32)

    def guess_and_minimise(
        self, truths, historic_forecasts, forecast_predictors, forecast_var, number_of_realizations
    ) -> xr.Dataset:
        """计算初始猜测并执行 CRPS 最小化，返回系数 Dataset。"""
        if self.point_by_point and not self.use_default_initial_guess:
            initial_guess = []
            for selection in iter_spatial_selections(truths):
                t_slice = truths.sel(selection)
                fp_slice = [fp.sel(selection) for fp in forecast_predictors]
                if self.predictor == "realizations":
                    fp_data = fp_slice[0].values
                else:
                    fp_data = np.ma.stack(broadcast_data_to_time_coord(fp_slice))
                initial_guess.append(
                    self.compute_initial_guess(
                        t_slice.values, fp_data, self.predictor, number_of_realizations
                    )
                )
            initial_guess = np.array(initial_guess)
        else:
            if self.predictor == "realizations":
                fp_data = forecast_predictors[0].values
            else:
                fp_data = np.ma.stack(broadcast_data_to_time_coord(forecast_predictors))
            initial_guess = self.compute_initial_guess(
                truths.values, fp_data, self.predictor, number_of_realizations
            )
            if self.point_by_point:
                n_points = spatial_point_count(truths)
                initial_guess = np.broadcast_to(
                    initial_guess,
                    (n_points, len(initial_guess)),
                )
        optimised = self.minimiser(
            initial_guess, forecast_predictors, truths, forecast_var, self.distribution.lower()
        )
        return self.create_coefficients_dataset(
            optimised, historic_forecasts, forecast_predictors
        )

    def process(
        self,
        historic_forecasts: InputField,
        truths: InputField,
        additional_fields: AdditionalFields = None,
        landsea_mask: Optional[InputField] = None,
    ) -> xr.Dataset:
        """校验输入、构建预测因子并训练 EMOS 系数。"""
        if landsea_mask and self.point_by_point:
            raise NotImplementedError("landsea_mask with point_by_point is not implemented")
        hf = as_dataarray(historic_forecasts)
        tr = as_dataarray(truths)
        if hf is None or tr is None:
            raise ValueError("historic_forecasts and truths must be provided")
        hf, tr = filter_non_matching_cubes(hf, tr)
        check_forecast_consistency(hf)
        check_data_sufficiency(hf, tr, self.point_by_point, self.proportion_of_nans)
        add_fields = _normalize_spatial_fields(additional_fields)
        if add_fields:
            if self.predictor == "realizations":
                raise NotImplementedError("additional_fields with realizations predictor unsupported")
            for af in add_fields:
                for c in ("forecast_period", "forecast_reference_time", REALIZATION_DIM, TIME_DIM):
                    if c in af.dims:
                        raise ValueError(f"Static predictor {get_diagnostic_name(af)} contains {c}")
        if hf.attrs.get("units") != tr.attrs.get("units"):
            raise ValueError("Historic forecast and truth units must match")
        number_of_realizations = None
        if self.predictor == "mean":
            forecast_predictors = [collapsed(hf, REALIZATION_DIM, "mean")]
        else:
            number_of_realizations = hf.sizes[REALIZATION_DIM]
            hf = enforce_coordinate_ordering(hf, REALIZATION_DIM)
            forecast_predictors = [hf]
        forecast_predictors.extend(add_fields)
        forecast_var = collapsed(hf, REALIZATION_DIM, "var")
        if landsea_mask:
            mask = as_dataarray(landsea_mask)
            forecast_predictors = [mask_dataarray(fp, mask) for fp in forecast_predictors]
            forecast_var = mask_dataarray(forecast_var, mask)
            tr = mask_dataarray(tr, mask)
        return self.guess_and_minimise(tr, hf, forecast_predictors, forecast_var, number_of_realizations)


class CalibratedForecastDistributionParameters(BasePlugin):
    """从 EMOS 系数计算校准预报分布的位置与尺度参数。"""

    def __init__(self, predictor: str = "mean") -> None:
        self.predictor = check_predictor(predictor)
        self.coefficients = None
        self.current_forecast = None
        self.additional_fields = None

    def _diagnostic_match(self):
        diag = self.coefficients.attrs.get(
            "diagnostic_standard_name",
            list(self.coefficients.data_vars.values())[0].attrs.get("diagnostic_standard_name"),
        )
        if get_diagnostic_name(self.current_forecast) != diag:
            raise ValueError(
                f"Forecast diagnostic {get_diagnostic_name(self.current_forecast)} "
                f"!= coefficients diagnostic {diag}"
            )

    def _spatial_domain_match(self):
        if not has_spatial_points(self.current_forecast):
            return
        for var in self.coefficients.data_vars:
            coeff = self.coefficients[var]
            if is_gridded_data(self.current_forecast) and is_gridded_data(coeff):
                if not np.array_equal(
                    self.current_forecast[LAT_DIM].values, coeff[LAT_DIM].values
                ) or not np.array_equal(
                    self.current_forecast[LON_DIM].values, coeff[LON_DIM].values
                ):
                    raise ValueError("lat/lon on forecast and coefficients do not match")
                continue
            if SPOT_DIM not in coeff.dims:
                continue
            if SPOT_DIM not in self.current_forecast.dims:
                continue
            if not np.array_equal(
                self.current_forecast[SPOT_DIM].values, coeff[SPOT_DIM].values
            ):
                raise ValueError(
                    "Spatial index on forecast and coefficients do not match"
                )
            if "wmo_id" in self.current_forecast.coords and "wmo_id" in coeff.coords:
                if not np.array_equal(
                    self.current_forecast["wmo_id"].values, coeff["wmo_id"].values
                ):
                    raise ValueError("wmo_id on forecast and coefficients do not match")

    def _calculate_location_parameter_from_mean(self) -> ndarray:
        fps = [collapsed(self.current_forecast, REALIZATION_DIM, "mean")]
        if self.additional_fields:
            fps.extend(self.additional_fields)
        beta = extract_coefficient(self.coefficients, "emos_coefficient_beta")
        alpha = extract_coefficient(self.coefficients, "emos_coefficient_alpha").values
        if len(fps) != beta.sizes.get("predictor_index", len(fps)):
            raise ValueError("Predictor count must match beta coefficients")
        location = np.zeros(fps[0].shape, dtype=np.float32)
        pnames = list(beta.coords.get("predictor_name", beta["predictor_index"]).values)
        for i, fp in enumerate(fps):
            pname = _predictor_name(fp)
            idx = pnames.index(pname) if pname in pnames else i
            b = beta.isel(predictor_index=idx).values
            while b.ndim < fp.values.ndim:
                b = np.expand_dims(b, axis=0)
            location += b * fp.values
        return (location + alpha).astype(np.float32)

    def _calculate_location_parameter_from_realizations(self) -> ndarray:
        beta = extract_coefficient(self.coefficients, "emos_coefficient_beta")
        alpha = extract_coefficient(self.coefficients, "emos_coefficient_alpha").values
        beta_values = np.atleast_2d(beta.values * beta.values)
        if beta.values.ndim != 1:
            beta_values = np.atleast_2d(np.squeeze(beta_values.T))
        a_and_b = np.hstack((np.atleast_2d(alpha).T, beta_values))
        fp_flat = convert_data_to_2d(self.current_forecast)
        xy_shape = self.current_forecast.isel({REALIZATION_DIM: 0}).shape
        ones_and_pred = np.column_stack(
            (np.ones(np.prod(xy_shape), dtype=np.float32), fp_flat)
        )
        return (
            np.sum(ones_and_pred * a_and_b, axis=-1).reshape(xy_shape).astype(np.float32)
        )

    def _calculate_scale_parameter(self) -> ndarray:
        forecast_var = collapsed(self.current_forecast, REALIZATION_DIM, "var")
        gamma = extract_coefficient(self.coefficients, "emos_coefficient_gamma").values
        delta = extract_coefficient(self.coefficients, "emos_coefficient_delta").values
        return np.sqrt(gamma * gamma + delta * delta * forecast_var.values).astype(np.float32)

    def _create_output_dataset(self, location, scale) -> xr.Dataset:
        tmpl = self.current_forecast.isel({REALIZATION_DIM: 0}, drop=True)
        mandatory = generate_mandatory_attributes([self.current_forecast])
        loc = create_new_diagnostic_dataarray(
            "location_parameter",
            tmpl.attrs.get("units", "1"),
            tmpl,
            mandatory,
            data=location,
        )
        sc = create_new_diagnostic_dataarray(
            "scale_parameter",
            tmpl.attrs.get("units", "1"),
            tmpl,
            mandatory,
            data=scale,
        )
        return xr.Dataset({"location_parameter": loc, "scale_parameter": sc})

    def process(
        self,
        current_forecast: InputField,
        coefficients: Union[xr.Dataset, InputField],
        additional_fields: AdditionalFields = None,
        landsea_mask: Optional[InputField] = None,
        tolerate_time_mismatch: bool = False,
    ) -> xr.Dataset:
        """对当前预报应用系数，返回位置与尺度参数 Dataset。"""
        self.current_forecast = as_dataarray(current_forecast)
        self.coefficients = (
            coefficients if isinstance(coefficients, xr.Dataset) else as_dataset(coefficients)
        )
        self.additional_fields = _normalize_spatial_fields(additional_fields)
        self._diagnostic_match()
        if not tolerate_time_mismatch:
            for var in self.coefficients.data_vars:
                forecast_coords_match(self.coefficients[var], self.current_forecast)
        self._spatial_domain_match()
        if self.predictor == "mean":
            location = self._calculate_location_parameter_from_mean()
        else:
            location = self._calculate_location_parameter_from_realizations()
        scale = self._calculate_scale_parameter()
        out = self._create_output_dataset(location, scale)
        if landsea_mask:
            flip = np.logical_not(as_dataarray(landsea_mask).values.astype(bool))
            for v in out.data_vars:
                out[v].values = np.ma.masked_where(flip, out[v].values)
        return out


class ApplyEMOS(PostProcessingPlugin):
    """将 EMOS 校准应用于集合预报，输出概率、百分位或成员预报。"""

    def __init__(self, percentiles: Optional[Sequence] = None):
        self.percentiles = [np.float32(p) for p in percentiles] if percentiles is not None else None

    def _check_additional_field_sites(self, forecast, additional_fields):
        if not additional_fields or SPOT_DIM not in forecast.dims:
            return
        if "wmo_id" not in forecast.coords:
            return
        for ap in additional_fields:
            if not np.array_equal(ap["wmo_id"].values, forecast["wmo_id"].values):
                raise ValueError("Forecast and additional predictors have mismatching wmo_id")

    def process(
        self,
        forecast: InputField,
        coefficients: xr.Dataset,
        additional_fields: AdditionalFields = None,
        land_sea_mask: Optional[InputField] = None,
        prob_template: Optional[InputField] = None,
        realizations_count: Optional[int] = None,
        ignore_ecc_bounds: bool = True,
        tolerate_time_mismatch: bool = False,
        predictor: str = "mean",
        randomise: bool = False,
        random_seed: Optional[int] = None,
        return_parameters: bool = False,
    ) -> xr.Dataset:
        """应用 EMOS 校准并生成与输入类型匹配的校准预报。"""
        fc = as_dataarray(forecast)
        self.input_forecast_type = get_forecast_type(fc)
        self.output_forecast_type = "probabilities" if prob_template is not None else self.input_forecast_type
        if land_sea_mask and self.input_forecast_type != self.output_forecast_type:
            raise ValueError("land_sea_mask requires input and output forecast types to match")
        add = _normalize_spatial_fields(additional_fields)
        self._check_additional_field_sites(fc, add)
        fc_real = fc.copy(deep=True)
        if self.input_forecast_type != "realizations":
            fc_real = convert_to_realizations(fc_real, realizations_count, ignore_ecc_bounds)
        params = CalibratedForecastDistributionParameters(predictor=predictor)(
            fc_real,
            coefficients,
            additional_fields=add,
            landsea_mask=land_sea_mask,
            tolerate_time_mismatch=tolerate_time_mismatch,
        )
        if return_parameters:
            return params
        distribution = {
            "name": get_attribute_from_coefficients(coefficients, "distribution"),
            "location": params["location_parameter"],
            "scale": params["scale_parameter"],
            "shape": get_attribute_from_coefficients(
                coefficients, "shape_parameters", optional=True
            ),
        }
        template = as_dataarray(prob_template) if prob_template is not None else fc
        result = generate_forecast_from_distribution(
            distribution, template, self.percentiles, randomise, random_seed
        )
        if land_sea_mask:
            merge_land_and_sea(result, fc)
        return to_output_dataset(result)


def convert_to_realizations(forecast, realizations_count, ignore_ecc_bounds):
    ftype = get_forecast_type(forecast)
    if not realizations_count:
        raise ValueError(f"realizations_count required for {ftype} input")
    if ftype == "probabilities":
        plugin = ConvertProbabilitiesToPercentiles(ecc_bounds_warning=ignore_ecc_bounds)
    elif ftype == "percentiles":
        plugin = ResamplePercentiles(ecc_bounds_warning=ignore_ecc_bounds)
    else:
        return forecast
    pct = plugin(forecast, no_of_percentiles=realizations_count)
    return RebadgePercentilesAsRealizations.process(pct)


def get_attribute_from_coefficients(coefficients, attribute_name, optional=False):
    attrs = []
    for var in coefficients.data_vars:
        if attribute_name in coefficients[var].attrs:
            attrs.append(str(coefficients[var].attrs[attribute_name]))
    if attribute_name in coefficients.attrs:
        attrs.append(str(coefficients.attrs[attribute_name]))
    if not attrs and optional:
        return None
    if not attrs:
        raise AttributeError(f"{attribute_name} must be on all coefficient variables")
    if len(set(attrs)) == 1:
        val = coefficients.attrs.get(attribute_name, coefficients[list(coefficients.data_vars)[0]].attrs[attribute_name])
        return val
    raise AttributeError(f"Inconsistent {attribute_name}: {attrs}")


def generate_forecast_from_distribution(distribution, template, percentiles, randomise, random_seed):
    template = as_dataarray(template)
    output_type = get_forecast_type(template)
    if output_type == "probabilities":
        plugin = ConvertLocationAndScaleParametersToProbabilities(
            distribution=distribution["name"], shape_parameters=distribution["shape"]
        )
        return plugin(distribution["location"], distribution["scale"], template)
    plugin = ConvertLocationAndScaleParametersToPercentiles(
        distribution=distribution["name"], shape_parameters=distribution["shape"]
    )
    if output_type == "percentiles":
        perc_coord = find_percentile_coordinate(template)
        perc = percentiles if percentiles else template[perc_coord].values
        result = plugin(distribution["location"], distribution["scale"], template, percentiles=list(perc))
    else:
        n = template.sizes[REALIZATION_DIM]
        pct = plugin(
            distribution["location"], distribution["scale"], template, no_of_percentiles=n
        )
        result = EnsembleReordering().process(
            pct, template, random_ordering=randomise, random_seed=random_seed
        )
    return result
