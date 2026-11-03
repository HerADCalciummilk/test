# -*- coding: utf-8 -*-
"""
Created on Tue Jul 11 16:28:57 2023

@author: cheny
"""
import inspect
from collections import defaultdict
import uuid
from scipy import ndimage
import numpy as np
from numpy.ma.core import MaskedArray
import time
import warnings
import scipy.ndimage.interpolation as ip
from scipy.special import binom
from types import SimpleNamespace
from scipy.integrate import nquad
from scipy.interpolate import interp1d
from scipy import optimize as opt
from scipy.signal import convolve
from scipy import stats
from scipy.ndimage import gaussian_laplace
from functools import wraps
import scipy.ndimage
from scipy import linalg
import scipy.ndimage as ndi
import skimage.measure as skime
import skimage.morphology as skim
import skimage.segmentation as skis
from scipy import optimize
import re
from datetime import timedelta
try:
    from skimage import feature as ski_feature
    SKIMAGE_IMPORTED = True
except ImportError:
    SKIMAGE_IMPORTED = False
try:
    import dask
    DASK_IMPORTED = True
except ImportError:
    DASK_IMPORTED = False
try:
    import pandas as pd
    PANDAS_IMPORTED = True
except ImportError:
    PANDAS_IMPORTED = False
try:
    import cv2
    CV2_IMPORTED = True
except ImportError:
    CV2_IMPORTED = False

def deprecate_args(old_new_args, deprecation_release):
    def _deprecate(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            kwargs_names = list(kwargs.keys())
            for key_old in kwargs_names:
                if key_old in old_new_args:
                    key_new = old_new_args[key_old]
                    kwargs[key_new] = kwargs.pop(key_old)
                    warnings.warn(
                        f"Argument '{key_old}' has been renamed to '{key_new}'. "
                        f"This will raise a TypeError in pysteps {deprecation_release}.",
                        FutureWarning,
                    )
            return func(*args, **kwargs)

        return wrapper

    return _deprecate

def extrapolate(
    precip,
    velocity,
    timesteps,
    outval=np.nan,
    xy_coords=None,
    allow_nonfinite_values=False,
    vel_timestep=1,
    **kwargs,
):

    if precip is not None and precip.ndim != 2:
        raise ValueError("precip must be a two-dimensional array")

    if velocity.ndim != 3:
        raise ValueError("velocity must be a three-dimensional array")

    if not allow_nonfinite_values:
        if precip is not None and np.any(~np.isfinite(precip)):
            raise ValueError("precip contains non-finite values")

        if np.any(~np.isfinite(velocity)):
            raise ValueError("velocity contains non-finite values")

    if precip is not None and np.all(~np.isfinite(precip)):
        raise ValueError("precip contains only non-finite values")

    if np.all(~np.isfinite(velocity)):
        raise ValueError("velocity contains only non-finite values")

    if isinstance(timesteps, list) and not sorted(timesteps) == timesteps:
        raise ValueError("timesteps is not in ascending order")

    # defaults
    verbose = kwargs.get("verbose", False)
    displacement_prev = kwargs.get("displacement_prev", None)
    n_iter = kwargs.get("n_iter", 1)
    return_displacement = kwargs.get("return_displacement", False)
    interp_order = kwargs.get("interp_order", 1)
    map_coordinates_mode = kwargs.get("map_coordinates_mode", "constant")

    if precip is None and not return_displacement:
        raise ValueError("precip is None but return_displacement is False")

    if "D_prev" in kwargs.keys():
        warnings.warn(
            "deprecated argument D_prev is ignored, use displacement_prev instead",
        )

    # if interp_order > 1, apply separate masking to preserve nan and
    # non-precipitation values
    if precip is not None and interp_order > 1:
        minval = np.nanmin(precip)
        mask_min = (precip > minval).astype(float)
        if allow_nonfinite_values:
            mask_finite = np.isfinite(precip)
            precip = precip.copy()
            precip[~mask_finite] = 0.0
            mask_finite = mask_finite.astype(float)
        else:
            mask_finite = np.ones(precip.shape)

    prefilter = True if interp_order > 1 else False

    if isinstance(timesteps, int):
        timesteps = np.arange(1, timesteps + 1)
        vel_timestep = 1.0
    elif np.any(np.diff(timesteps) <= 0.0):
        raise ValueError("the given timestep sequence is not monotonously increasing")

    timestep_diff = np.hstack([[timesteps[0]], np.diff(timesteps)])

    if verbose:
        print("Computing the advection with the semi-lagrangian scheme.")
        t0 = time.time()

    if precip is not None and outval == "min":
        outval = np.nanmin(precip)

    if xy_coords is None:
        x_values, y_values = np.meshgrid(
            np.arange(velocity.shape[2]), np.arange(velocity.shape[1])
        )

        xy_coords = np.stack([x_values, y_values])

    def interpolate_motion(displacement, velocity_inc, td):
        coords_warped = xy_coords + displacement
        coords_warped = [coords_warped[1, :, :], coords_warped[0, :, :]]

        velocity_inc_x = ip.map_coordinates(
            velocity[0, :, :], coords_warped, mode="nearest", order=1, prefilter=False
        )
        velocity_inc_y = ip.map_coordinates(
            velocity[1, :, :], coords_warped, mode="nearest", order=1, prefilter=False
        )

        velocity_inc[0, :, :] = velocity_inc_x
        velocity_inc[1, :, :] = velocity_inc_y

        if n_iter > 1:
            velocity_inc /= n_iter

        velocity_inc *= td / vel_timestep

    precip_extrap = []
    if displacement_prev is None:
        displacement = np.zeros((2, velocity.shape[1], velocity.shape[2]))
        velocity_inc = velocity.copy() * timestep_diff[0] / vel_timestep
    else:
        displacement = displacement_prev.copy()
        velocity_inc = np.empty(velocity.shape)
        interpolate_motion(displacement, velocity_inc, timestep_diff[0])

    for ti, td in enumerate(timestep_diff):
        if n_iter > 0:
            for k in range(n_iter):
                interpolate_motion(displacement - velocity_inc / 2.0, velocity_inc, td)
                displacement -= velocity_inc
                interpolate_motion(displacement, velocity_inc, td)
        else:
            if ti > 0 or displacement_prev is not None:
                interpolate_motion(displacement, velocity_inc, td)

            displacement -= velocity_inc

        coords_warped = xy_coords + displacement
        coords_warped = [coords_warped[1, :, :], coords_warped[0, :, :]]

        if precip is not None:
            precip_warped = ip.map_coordinates(
                precip,
                coords_warped,
                mode=map_coordinates_mode,
                cval=outval,
                order=interp_order,
                prefilter=prefilter,
            )

            if interp_order > 1:
                mask_warped = ip.map_coordinates(
                    mask_min,
                    coords_warped,
                    mode=map_coordinates_mode,
                    cval=0,
                    order=1,
                    prefilter=False,
                )
                precip_warped[mask_warped < 0.5] = minval

                mask_warped = ip.map_coordinates(
                    mask_finite,
                    coords_warped,
                    mode=map_coordinates_mode,
                    cval=0,
                    order=1,
                    prefilter=False,
                )
                precip_warped[mask_warped < 0.5] = np.nan

            precip_extrap.append(np.reshape(precip_warped, precip.shape))

    if verbose:
        print("--- %s seconds ---" % (time.time() - t0))

    if precip is not None:
        if not return_displacement:
            return np.stack(precip_extrap)
        else:
            return np.stack(precip_extrap), displacement
    else:
        return None, displacement

def extrapolation_forecast(
    precip,
    velocity,
    timesteps,
    extrap_method="semilagrangian",
    extrap_kwargs=None,
    measure_time=False,
):

    extrapolation_check_inputs(precip, velocity, timesteps)

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

    extrapolation_method = extrapolate

    precip_forecast = extrapolation_method(precip, velocity, timesteps, **extrap_kwargs)

    if measure_time:
        computation_time = time.time() - start_time
        print(f"{computation_time:.2f} seconds.")

    if measure_time:
        return precip_forecast, computation_time
    else:
        return precip_forecast


def extrapolation_check_inputs(precip, velocity, timesteps):
    if precip.ndim != 2:
        raise ValueError("The input precipitation must be a " "two-dimensional array")
    if velocity.ndim != 3:
        raise ValueError("Input velocity must be a three-dimensional array")
    if precip.shape != velocity.shape[1:3]:
        raise ValueError(
            "Dimension mismatch between "
            "input precipitation and velocity: "
            + "shape(precip)=%s, shape(velocity)=%s"
            % (str(precip.shape), str(velocity.shape))
        )
    if isinstance(timesteps, list) and not sorted(timesteps) == timesteps:
        raise ValueError("timesteps is not in ascending order")

class MissingOptionalDependency(Exception):
    """Raised when an optional dependency is needed but not found."""
    
def spectral_std(X, shape, use_full_fft=False):
    res = np.sum(np.abs(X) ** 2) - np.real(X[0, 0]) ** 2
    if not use_full_fft:
        if shape[1] % 2 == 1:
            res += np.sum(np.abs(X[:, 1:]) ** 2)
        else:
            res += np.sum(np.abs(X[:, 1:-1]) ** 2)

def spectral_mean(X, shape):
    return np.real(X[0, 0]) / (shape[0] * shape[1])

def get_numpy(shape, fftn_shape=None, **kwargs):
    import numpy.fft as numpy_fft

    f = {
        "fft2": numpy_fft.fft2,
        "ifft2": numpy_fft.ifft2,
        "rfft2": numpy_fft.rfft2,
        "irfft2": lambda X: numpy_fft.irfft2(X, s=shape),
        "fftshift": numpy_fft.fftshift,
        "ifftshift": numpy_fft.ifftshift,
        "fftfreq": numpy_fft.fftfreq,
    }
    if fftn_shape is not None:
        f["fftn"] = numpy_fft.fftn
    fft = SimpleNamespace(**f)

    return fft


def get_scipy(shape, fftn_shape=None, **kwargs):
    import numpy.fft as numpy_fft
    import scipy.fftpack as scipy_fft

    # use numpy implementation of rfft2/irfft2 because they have not been
    # implemented in scipy.fftpack
    f = {
        "fft2": scipy_fft.fft2,
        "ifft2": scipy_fft.ifft2,
        "rfft2": numpy_fft.rfft2,
        "irfft2": lambda X: numpy_fft.irfft2(X, s=shape),
        "fftshift": scipy_fft.fftshift,
        "ifftshift": scipy_fft.ifftshift,
        "fftfreq": scipy_fft.fftfreq,
    }
    if fftn_shape is not None:
        f["fftn"] = scipy_fft.fftn
    fft = SimpleNamespace(**f)

    return fft

def get_pyfftw(shape, fftn_shape=None, n_threads=1, **kwargs):
    try:
        import pyfftw.interfaces.numpy_fft as pyfftw_fft
        import pyfftw

        pyfftw.interfaces.cache.enable()
    except ImportError:
        raise MissingOptionalDependency("pyfftw is required but not installed")

    X = pyfftw.empty_aligned(shape, dtype="complex128")
    F = pyfftw.empty_aligned(shape, dtype="complex128")

    fft_obj = pyfftw.FFTW(
        X,
        F,
        flags=["FFTW_ESTIMATE"],
        direction="FFTW_FORWARD",
        axes=(0, 1),
        threads=n_threads,
    )
    ifft_obj = pyfftw.FFTW(
        F,
        X,
        flags=["FFTW_ESTIMATE"],
        direction="FFTW_BACKWARD",
        axes=(0, 1),
        threads=n_threads,
    )

    if fftn_shape is not None:
        X = pyfftw.empty_aligned(fftn_shape, dtype="complex128")
        F = pyfftw.empty_aligned(fftn_shape, dtype="complex128")

        fftn_obj = pyfftw.FFTW(
            X,
            F,
            flags=["FFTW_ESTIMATE"],
            direction="FFTW_FORWARD",
            axes=list(range(len(fftn_shape))),
            threads=n_threads,
        )

    X = pyfftw.empty_aligned(shape, dtype="float64")
    output_shape = list(shape[:-1])
    output_shape.append(int(shape[-1] / 2) + 1)
    output_shape = tuple(output_shape)
    F = pyfftw.empty_aligned(output_shape, dtype="complex128")

    rfft_obj = pyfftw.FFTW(
        X,
        F,
        flags=["FFTW_ESTIMATE"],
        direction="FFTW_FORWARD",
        axes=(0, 1),
        threads=n_threads,
    )
    irfft_obj = pyfftw.FFTW(
        F,
        X,
        flags=["FFTW_ESTIMATE"],
        direction="FFTW_BACKWARD",
        axes=(0, 1),
        threads=n_threads,
    )

    f = {
        "fft2": lambda X: fft_obj(input_array=X.copy()).copy(),
        "ifft2": lambda X: ifft_obj(input_array=X.copy()).copy(),
        "rfft2": lambda X: rfft_obj(input_array=X.copy()).copy(),
        "irfft2": lambda X: irfft_obj(input_array=X.copy()).copy(),
        "fftshift": pyfftw_fft.fftshift,
        "ifftshift": pyfftw_fft.ifftshift,
        "fftfreq": pyfftw_fft.fftfreq,
    }

    if fftn_shape is not None:
        f["fftn"] = lambda X: fftn_obj(input_array=X).copy()
    fft = SimpleNamespace(**f)

    return fft

def get_fft_method(name, **kwargs):
    kwargs = kwargs.copy()
    shape = kwargs["shape"]
    kwargs.pop("shape")

    if name == "numpy":
        return get_numpy(shape, **kwargs)
    elif name == "scipy":
        return get_scipy(shape, **kwargs)
    elif name == "pyfftw":
        return get_pyfftw(shape, **kwargs)
    else:
        raise ValueError(
            "Unknown method {}\n".format(name)
            + "The available methods are:"
            + str(["numpy", "pyfftw", "scipy"])
        ) from None
        
def decomposition_fft(field, bp_filter, **kwargs):
    fft = kwargs.get("fft_method", "numpy")
    if isinstance(fft, str):
        fft = get_fft_method(fft, shape=field.shape)
    normalize = kwargs.get("normalize", False)
    mask = kwargs.get("mask", None)
    input_domain = kwargs.get("input_domain", "spatial")
    output_domain = kwargs.get("output_domain", "spatial")
    compute_stats = kwargs.get("compute_stats", True)
    compact_output = kwargs.get("compact_output", False)
    subtract_mean = kwargs.get("subtract_mean", False)

    if normalize and not compute_stats:
        compute_stats = True

    if len(field.shape) != 2:
        raise ValueError("The input is not two-dimensional array")

    if mask is not None and mask.shape != field.shape:
        raise ValueError(
            "Dimension mismatch between field and mask:"
            + "field.shape="
            + str(field.shape)
            + ",mask.shape"
            + str(mask.shape)
        )

    if field.shape[0] != bp_filter["weights_2d"].shape[1]:
        raise ValueError(
            "dimension mismatch between field and bp_filter: "
            + "field.shape[0]=%d , " % field.shape[0]
            + "bp_filter['weights_2d'].shape[1]"
            "=%d" % bp_filter["weights_2d"].shape[1]
        )

    if (
        input_domain == "spatial"
        and int(field.shape[1] / 2) + 1 != bp_filter["weights_2d"].shape[2]
    ):
        raise ValueError(
            "Dimension mismatch between field and bp_filter: "
            "int(field.shape[1]/2)+1=%d , " % (int(field.shape[1] / 2) + 1)
            + "bp_filter['weights_2d'].shape[2]"
            "=%d" % bp_filter["weights_2d"].shape[2]
        )

    if (
        input_domain == "spectral"
        and field.shape[1] != bp_filter["weights_2d"].shape[2]
    ):
        raise ValueError(
            "Dimension mismatch between field and bp_filter: "
            "field.shape[1]=%d , " % (field.shape[1] + 1)
            + "bp_filter['weights_2d'].shape[2]"
            "=%d" % bp_filter["weights_2d"].shape[2]
        )

    if output_domain != "spectral":
        compact_output = False

    if np.any(~np.isfinite(field)):
        raise ValueError("field contains non-finite values")

    result = {}
    means = []
    stds = []

    if subtract_mean and input_domain == "spatial":
        field_mean = np.mean(field)
        field = field - field_mean
        result["field_mean"] = field_mean

    if input_domain == "spatial":
        field_fft = fft.rfft2(field)
    else:
        field_fft = field
    if output_domain == "spectral" and compact_output:
        weight_masks = []
    field_decomp = []

    for k in range(len(bp_filter["weights_1d"])):
        field_ = field_fft * bp_filter["weights_2d"][k, :, :]

        if output_domain == "spatial" or (compute_stats and mask is not None):
            field__ = fft.irfft2(field_)
        else:
            field__ = field_

        if compute_stats:
            if output_domain == "spatial" or (compute_stats and mask is not None):
                if mask is not None:
                    masked_field = field__[mask]
                else:
                    masked_field = field__
                mean = np.mean(masked_field)
                std = np.std(masked_field)
            else:
                mean = spectral_mean(field_, bp_filter["shape"])
                std = spectral_std(field_, bp_filter["shape"])

            means.append(mean)
            stds.append(std)

        if output_domain == "spatial":
            field_ = field__
        if normalize:
            field_ = (field_ - mean) / std
        if output_domain == "spectral" and compact_output:
            weight_mask = bp_filter["weights_2d"][k, :, :] > 1e-12
            field_ = field_[weight_mask]
            weight_masks.append(weight_mask)
        field_decomp.append(field_)

    result["domain"] = output_domain
    result["normalized"] = normalize
    result["compact_output"] = compact_output

    if output_domain == "spatial" or not compact_output:
        field_decomp = np.stack(field_decomp)

    result["cascade_levels"] = field_decomp
    if output_domain == "spectral" and compact_output:
        result["weight_masks"] = np.stack(weight_masks)

    if compute_stats:
        result["means"] = means
        result["stds"] = stds

    return result


def recompose_fft(decomp, **kwargs):
    levels = decomp["cascade_levels"]
    if decomp["normalized"]:
        mu = decomp["means"]
        sigma = decomp["stds"]

    if not decomp["normalized"] and not (
        decomp["domain"] == "spectral" and decomp["compact_output"]
    ):
        result = np.sum(levels, axis=0)
    else:
        if decomp["compact_output"]:
            weight_masks = decomp["weight_masks"]
            result = np.zeros(weight_masks.shape[1:], dtype=complex)

            for i in range(len(levels)):
                if decomp["normalized"]:
                    result[weight_masks[i]] += levels[i] * sigma[i] + mu[i]
                else:
                    result[weight_masks[i]] += levels[i]
        else:
            result = [levels[i] * sigma[i] + mu[i] for i in range(len(levels))]
            result = np.sum(np.stack(result), axis=0)

    if "field_mean" in decomp:
        result += decomp["field_mean"]

    return result

def filter_uniform(shape, n):
    del n  # Unused

    out = {}

    try:
        height, width = shape
    except TypeError:
        height, width = (shape, shape)

    r_max = int(max(width, height) / 2) + 1

    out["weights_1d"] = np.ones((1, r_max))
    out["weights_2d"] = np.ones((1, height, int(width / 2) + 1))
    out["central_freqs"] = None
    out["central_wavenumbers"] = None
    out["shape"] = shape

    return out

def filter_gaussian(
    shape,
    n,
    gauss_scale=0.5,
    d=1.0,
    normalize=True,
    return_weight_funcs=False,
    include_mean=True,
):
    if n < 3:
        raise ValueError("n must be greater than 2")

    try:
        height, width = shape
    except TypeError:
        height, width = (shape, shape)

    max_length = max(width, height)

    rx = np.s_[: int(width / 2) + 1]

    if (height % 2) == 1:
        ry = np.s_[-int(height / 2) : int(height / 2) + 1]
    else:
        ry = np.s_[-int(height / 2) : int(height / 2)]

    y_grid, x_grid = np.ogrid[ry, rx]
    dy = int(height / 2) if height % 2 == 0 else int(height / 2) + 1

    r_2d = np.roll(np.sqrt(x_grid * x_grid + y_grid * y_grid), dy, axis=0)

    r_max = int(max_length / 2) + 1
    r_1d = np.arange(r_max)

    wfs, central_wavenumbers = gaussweights_1d(
        max_length,
        n,
        gauss_scale=gauss_scale,
    )

    weights_1d = np.empty((n, r_max))
    weights_2d = np.empty((n, height, int(width / 2) + 1))

    for i, wf in enumerate(wfs):
        weights_1d[i, :] = wf(r_1d)
        weights_2d[i, :, :] = wf(r_2d)

    if normalize:
        weights_1d_sum = np.sum(weights_1d, axis=0)
        weights_2d_sum = np.sum(weights_2d, axis=0)
        for k in range(weights_2d.shape[0]):
            weights_1d[k, :] /= weights_1d_sum
            weights_2d[k, :, :] /= weights_2d_sum

    for i in range(len(wfs)):
        if i == 0 and include_mean:
            weights_1d[i, 0] = 1.0
            weights_2d[i, 0, 0] = 1.0
        else:
            weights_1d[i, 0] = 0.0
            weights_2d[i, 0, 0] = 0.0

    out = {"weights_1d": weights_1d, "weights_2d": weights_2d}
    out["shape"] = shape

    central_wavenumbers = np.array(central_wavenumbers)
    out["central_wavenumbers"] = central_wavenumbers

    # Compute frequencies
    central_freqs = 1.0 * central_wavenumbers / max_length
    central_freqs[0] = 1.0 / max_length
    central_freqs[-1] = 0.5  # Nyquist freq
    central_freqs = 1.0 * d * central_freqs
    out["central_freqs"] = central_freqs

    if return_weight_funcs:
        out["weight_funcs"] = wfs

    return out

def gaussweights_1d(l, n, gauss_scale=0.5):
    q = pow(0.5 * l, 1.0 / n)
    r = [(pow(q, k - 1), pow(q, k)) for k in range(1, n + 1)]
    r = [0.5 * (r_[0] + r_[1]) for r_ in r]

    def log_e(x):
        if len(np.shape(x)) > 0:
            res = np.empty(x.shape)
            res[x == 0] = 0.0
            res[x > 0] = np.log(x[x > 0]) / np.log(q)
        else:
            if x == 0.0:
                res = 0.0
            else:
                res = np.log(x) / np.log(q)

        return res

    class GaussFunc:
        def __init__(self, c, s):
            self.c = c
            self.s = s

        def __call__(self, x):
            x = log_e(x) - self.c
            return np.exp(-(x**2.0) / (2.0 * self.s**2.0))

    weight_funcs = []
    central_wavenumbers = []

    for i, ri in enumerate(r):
        rc = log_e(ri)
        weight_funcs.append(GaussFunc(rc, gauss_scale))
        central_wavenumbers.append(ri)

    return weight_funcs, central_wavenumbers


def check_input_frames(
    minimum_input_frames=2, maximum_input_frames=np.inf, just_ndim=False):
    def _check_input_frames(motion_method_func):
        @wraps(motion_method_func)
        def new_function(*args, **kwargs):
            """
            Return new function with the checks prepended to the
            target motion_method_func function.
            """

            input_images = args[1]
            # print(args[1])
            if input_images.ndim != 3:
                raise ValueError(
                    "input_images dimension mismatch.\n"
                    f"input_images.shape: {str(input_images.shape)}\n"
                    "(t, x, y ) dimensions expected"
                )

            if not just_ndim:
                num_of_frames = input_images.shape[0]

                if minimum_input_frames < num_of_frames > maximum_input_frames:
                    raise ValueError(
                        f"input_images frames {num_of_frames} mismatch.\n"
                        f"Minimum frames: {minimum_input_frames}\n"
                        f"Maximum frames: {maximum_input_frames}\n"
                    )

            return motion_method_func(*args, **kwargs)

        return new_function

    return _check_input_frames

def stack_cascades(precip_decomp, n_levels, convert_to_full_arrays=False):
    out = []

    n_inputs = len(precip_decomp)

    for i in range(n_levels):
        precip_cur_level = []
        for j in range(n_inputs):
            precip_cur_input = precip_decomp[j]["cascade_levels"][i]
            if precip_decomp[j]["compact_output"] and convert_to_full_arrays:
                precip_tmp = np.zeros(
                    precip_decomp[j]["weight_masks"].shape[1:], dtype=complex
                )
                precip_tmp[precip_decomp[j]["weight_masks"][i]] = precip_cur_input
                precip_cur_input = precip_tmp
            precip_cur_level.append(precip_cur_input)
        out.append(np.stack(precip_cur_level))

    if not np.any(
        [precip_decomp[i]["compact_output"] for i in range(len(precip_decomp))]
    ):
        out = np.stack(out)

    return out  

def print_corrcoefs(gamma):
    print("************************************************")
    print("* Correlation coefficients for cascade levels: *")
    print("************************************************")

    m = gamma.shape[0]
    n = gamma.shape[1]

    hline_str = "---------"
    for _ in range(n):
        hline_str += "----------------"

    title_str = "| Level |"
    for i in range(n):
        title_str += "     Lag-%d     |" % (i + 1)

    print(hline_str)
    print(title_str)
    print(hline_str)

    fmt_str = "| %-5d |"
    for _ in range(n):
        fmt_str += " %-13.6f |"

    for i in range(m):
        print(fmt_str % ((i + 1,) + tuple(gamma[i, :])))
        print(hline_str)

def print_ar_params(phi):
    print("****************************************")
    print("* AR(p) parameters for cascade levels: *")
    print("****************************************")

    n = phi.shape[1]

    hline_str = "---------"
    for _ in range(n):
        hline_str += "---------------"

    title_str = "| Level |"
    for i in range(n - 1):
        title_str += "    Phi-%d     |" % (i + 1)
    title_str += "    Phi-0     |"

    print(hline_str)
    print(title_str)
    print(hline_str)

    fmt_str = "| %-5d |"
    for _ in range(n):
        fmt_str += " %-12.6f |"

    for i in range(phi.shape[0]):
        print(fmt_str % ((i + 1,) + tuple(phi[i, :])))
        print(hline_str)

def nonparam_match_empirical_cdf(initial_array, target_array):

    if np.any(~np.isfinite(initial_array)):
        raise ValueError("initial array contains non-finite values")
    if np.any(~np.isfinite(target_array)):
        raise ValueError("target array contains non-finite values")
    if initial_array.size != target_array.size:
        raise ValueError(
            "dimension mismatch between initial_array and target_array: "
            f"initial_array.shape={initial_array.shape}, target_array.shape={target_array.shape}"
        )

    initial_array = np.array(initial_array)
    target_array = np.array(target_array)

    # zeros in initial array
    zvalue = initial_array.min()
    idxzeros = initial_array == zvalue

    # zeros in the target array
    zvalue_trg = target_array.min()

    # adjust the fraction of rain in target distribution if the number of
    # nonzeros is greater than in the initial array
    if np.sum(target_array > zvalue_trg) > np.sum(initial_array > zvalue):
        war = np.sum(initial_array > zvalue) / initial_array.size
        p = np.percentile(target_array, 100 * (1 - war))
        target_array = target_array.copy()
        target_array[target_array < p] = zvalue_trg

    # flatten the arrays
    arrayshape = initial_array.shape
    target_array = target_array.flatten()
    initial_array = initial_array.flatten()

    # rank target values
    order = target_array.argsort()
    ranked = target_array[order]

    # rank initial values order
    orderin = initial_array.argsort()
    ranks = np.empty(len(initial_array), int)
    ranks[orderin] = np.arange(len(initial_array))

    # get ranked values from target and rearrange with the initial order
    output_array = ranked[ranks]

    # reshape to the original array dimensions
    output_array = output_array.reshape(arrayshape)

    # read original zeros
    output_array[idxzeros] = zvalue_trg

    return output_array

def temporal_autocorrelation(
    x,
    d=0,
    domain="spatial",
    x_shape=None,
    mask=None,
    use_full_fft=False,
    window="gaussian",
    window_radius=np.inf,
):
    if len(x.shape) < 2:
        raise ValueError("the dimension of x must be >= 2")
    if len(x.shape) != 3 and domain == "spectral":
        raise NotImplementedError(
            "len(x.shape[1:]) = %d, but with domain == 'spectral', this function has only been implemented for two-dimensional fields"
            % len(x.shape[1:])
        )
    if mask is not None and mask.shape != x.shape[1:]:
        raise ValueError(
            "dimension mismatch between x and mask: x.shape[1:]=%s, mask.shape=%s"
            % (str(x.shape[1:]), str(mask.shape))
        )
    if np.any(~np.isfinite(x)):
        raise ValueError("x contains non-finite values")

    if d == 1:
        x = np.diff(x, axis=0)

    if domain == "spatial" and mask is None:
        mask = np.ones(x.shape[1:], dtype=bool)

    gamma = []
    for k in range(x.shape[0] - 1):
        if domain == "spatial":
            if window_radius == np.inf:
                cc = np.corrcoef(x[-1, :][mask], x[-(k + 2), :][mask])[0, 1]
            else:
                cc = moving_window_corrcoef(
                    x[-1, :], x[-(k + 2), :], window_radius, mask=mask
                )
        else:
            cc = corrcoef(
                x[-1, :, :], x[-(k + 2), :], x_shape, use_full_fft=use_full_fft
            )
        gamma.append(cc)

    return gamma

def corrcoef(X, Y, shape, use_full_fft=False):
    if len(X.shape) != 2:
        raise ValueError("X is not a two-dimensional array")

    if len(Y.shape) != 2:
        raise ValueError("Y is not a two-dimensional array")

    if X.shape != Y.shape:
        raise ValueError(
            "dimension mismatch between X and Y: "
            + "X.shape=%d,%d , " % (X.shape[0], X.shape[1])
            + "Y.shape=%d,%d" % (Y.shape[0], Y.shape[1])
        )

    n = np.real(np.sum(X * np.conj(Y))) - np.real(X[0, 0] * Y[0, 0])
    d1 = np.sum(np.abs(X) ** 2) - np.real(X[0, 0]) ** 2
    d2 = np.sum(np.abs(Y) ** 2) - np.real(Y[0, 0]) ** 2

    if not use_full_fft:
        if shape[1] % 2 == 1:
            n += np.real(np.sum(X[:, 1:] * np.conj(Y[:, 1:])))
            d1 += np.sum(np.abs(X[:, 1:]) ** 2)
            d2 += np.sum(np.abs(Y[:, 1:]) ** 2)
        else:
            n += np.real(np.sum(X[:, 1:-1] * np.conj(Y[:, 1:-1])))
            d1 += np.sum(np.abs(X[:, 1:-1]) ** 2)
            d2 += np.sum(np.abs(Y[:, 1:-1]) ** 2)

    return n / np.sqrt(d1 * d2)

def moving_window_corrcoef(x, y, window_radius, window="gaussian", mask=None):
    if window not in ["gaussian", "uniform"]:
        raise ValueError(
            "unknown window type %s, the available options are 'gaussian' and 'uniform'"
            % window
        )

    if mask is None:
        mask = np.ones(x.shape)
    else:
        x = x.copy()
        x[~mask] = 0.0
        y = y.copy()
        y[~mask] = 0.0
        mask = mask.astype(float)

    if window == "gaussian":
        convol_filter = ndimage.gaussian_filter
    else:
        convol_filter = ndimage.uniform_filter

    if window == "uniform":
        window_size = 2 * window_radius + 1
    else:
        window_size = window_radius

    n = convol_filter(mask, window_size, mode="constant") * window_size**2

    sx = convol_filter(x, window_size, mode="constant") * window_size**2
    sy = convol_filter(y, window_size, mode="constant") * window_size**2

    ssx = convol_filter(x**2, window_size, mode="constant") * window_size**2
    ssy = convol_filter(y**2, window_size, mode="constant") * window_size**2
    sxy = convol_filter(x * y, window_size, mode="constant") * window_size**2

    mux = sx / n
    muy = sy / n

    stdx = np.sqrt(ssx - 2 * mux * sx + n * mux**2)
    stdy = np.sqrt(ssy - 2 * muy * sy + n * muy**2)
    cov = sxy - muy * sx - mux * sy + n * mux * muy

    mask = np.logical_and(stdx > 1e-8, stdy > 1e-8)
    mask = np.logical_and(mask, stdx * stdy > 1e-8)
    mask = np.logical_and(mask, n >= 3)
    corr = np.empty(x.shape)
    corr[mask] = cov[mask] / (stdx[mask] * stdy[mask])
    corr[~mask] = np.nan

    return corr

def adjust_lag2_corrcoef2(gamma_1, gamma_2):
    gamma_2 = np.maximum(gamma_2, 2 * gamma_1 * gamma_2 - 1)
    gamma_2 = np.maximum(
        gamma_2, (3 * gamma_1**2 - 2 + 2 * (1 - gamma_1**2) ** 1.5) / gamma_1**2
    )

    return gamma_2


def test_ar_stationarity(phi):
    r = np.array(
        [
            np.abs(r_)
            for r_ in np.roots([1.0 if i == 0 else -phi[i] for i in range(len(phi))])
        ]
    )

    return False if np.any(r >= 1) else True



def compute_differenced_model_params(phi, p, q, d):
    phi_out = []
    for i in range(p + d):
        if q > 1:
            if len(phi[0].shape) == 2:
                phi_out.append(np.zeros((q, q)))
            else:
                phi_out.append(np.zeros(phi[0].shape))
        else:
            phi_out.append(0.0)

    for i in range(1, d + 1):
        if q > 1:
            phi_out[i - 1] -= binom(d, i) * (-1) ** i * np.eye(q)
        else:
            phi_out[i - 1] -= binom(d, i) * (-1) ** i
    for i in range(1, p + 1):
        phi_out[i - 1] += phi[i - 1]
    for i in range(1, p + 1):
        for j in range(1, d + 1):
            phi_out[i + j - 1] += phi[i - 1] * binom(d, j) * (-1) ** j

    return phi_out

def estimate_ar_params_yw(gamma, d=0, check_stationarity=True):
    if d not in [0, 1]:
        raise ValueError("d = %d, but 0 or 1 required" % d)

    p = len(gamma)

    g = np.hstack([[1.0], gamma])
    G = []
    for j in range(p):
        G.append(np.roll(g[:-1], j))
    G = np.array(G)
    phi = np.linalg.solve(G, g[1:].flatten())

    # Check that the absolute values of the roots of the characteristic
    # polynomial are less than one.
    # Otherwise the AR(p) model is not stationary.
    if check_stationarity:
        if not test_ar_stationarity(phi):
            raise RuntimeError(
                "Error in estimate_ar_params_yw: " "nonstationary AR(p) process"
            )

    c = 1.0
    for j in range(p):
        c -= gamma[j] * phi[j]
    phi_pert = np.sqrt(c)

    # If the expression inside the square root is negative, phi_pert cannot
    # be computed and it is set to zero instead.
    if not np.isfinite(phi_pert):
        phi_pert = 0.0

    if d == 1:
        phi = compute_differenced_model_params(phi, p, 1, 1)

    phi_out = np.empty(len(phi) + 1)
    phi_out[: len(phi)] = phi
    phi_out[-1] = phi_pert

    return phi_out

def iterate_ar_model(x, phi, eps=None):
    if x.shape[0] < len(phi) - 1:
        raise ValueError(
            "dimension mismatch between x and phi: x.shape[0]=%d, len(phi)=%d"
            % (x.shape[0], len(phi))
        )

    if len(x.shape) == 1:
        x_simple_shape = True
        x = x[:, np.newaxis]
    else:
        x_simple_shape = False

    if eps is not None and eps.shape != x.shape[1:]:
        raise ValueError(
            "dimension mismatch between x and eps: x.shape=%s, eps.shape[1:]=%s"
            % (str(x.shape), str(eps.shape[1:]))
        )

    x_new = 0.0

    p = len(phi) - 1

    for i in range(p):
        x_new += phi[i] * x[-(i + 1), :]

    if eps is not None:
        x_new += phi[-1] * eps

    if x_simple_shape:
        return np.hstack([x[1:], [x_new]])
    else:
        return np.concatenate([x[1:, :], x_new[np.newaxis, :]])

def binned_timesteps(timesteps):
    timesteps = list(timesteps)
    if not sorted(timesteps) == timesteps:
        raise ValueError("timesteps is not in ascending order")

    if np.any(np.array(timesteps) < 0):
        raise ValueError("negative time steps are not allowed")

    num_bins = int(np.ceil(timesteps[-1]))
    timestep_range = np.arange(num_bins + 1)
    bin_idx = np.digitize(timesteps, timestep_range, right=False)

    out = [[] for _ in range(num_bins + 1)]
    for i, bi in enumerate(bin_idx):
        out[bi - 1].append(i)

    return out

def nowcast_main_loop(
    precip,
    velocity,
    state,
    timesteps,
    extrap_method,
    func,
    extrap_kwargs=None,
    velocity_pert_gen=None,
    params=None,
    ensemble=False,
    num_ensemble_members=1,
    callback=None,
    return_output=True,
    num_workers=1,
    measure_time=False,
):
    precip_forecast_out = None

    # create a range of time steps
    # if an integer time step is given, create a simple range iterator
    # otherwise, assing the time steps to integer bins so that each bin
    # contains a list of time steps belonging to that bin
    if isinstance(timesteps, int):
        timesteps = range(timesteps + 1)
        timestep_type = "int"
    else:
        original_timesteps = [0] + list(timesteps)
        timesteps = binned_timesteps(original_timesteps)
        timestep_type = "list"

    state_cur = state
    if not ensemble:
        precip_forecast_prev = precip[np.newaxis, :]
    else:
        precip_forecast_prev = np.stack([precip for _ in range(num_ensemble_members)])
    displacement = None
    t_prev = 0.0
    t_total = 0.0

    # initialize the extrapolator
    extrapolator = extrapolate

    x_values, y_values = np.meshgrid(
        np.arange(precip.shape[1]), np.arange(precip.shape[0])
    )

    xy_coords = np.stack([x_values, y_values])

    if extrap_kwargs is None:
        extrap_kwargs = dict()
    else:
        extrap_kwargs = extrap_kwargs.copy()
    extrap_kwargs["xy_coords"] = xy_coords
    extrap_kwargs["return_displacement"] = True

    if measure_time:
        starttime_total = time.time()

    # loop through the integer time steps or bins if non-integer time steps
    # were given
    for t, subtimestep_idx in enumerate(timesteps):
        if timestep_type == "list":
            subtimesteps = [original_timesteps[t_] for t_ in subtimestep_idx]
        else:
            subtimesteps = [t]

        if (timestep_type == "list" and subtimesteps) or (
            timestep_type == "int" and t > 0
        ):
            is_nowcast_time_step = True
        else:
            is_nowcast_time_step = False

        # print a message if nowcasts are computed for the current integer time
        # step (this is not necessarily the case, since the current bin might
        # not contain any time steps)
        if is_nowcast_time_step:
            print(
                f"Computing nowcast for time step {t}... ",
                end="",
                flush=True,
            )

            if measure_time:
                starttime = time.time()

        # call the function to iterate the integer-timestep part of the model
        # for one time step
        precip_forecast_new, state_new = func(state_cur, params)

        if not ensemble:
            precip_forecast_new = precip_forecast_new[np.newaxis, :]

        # advect the currect forecast field to the subtimesteps in the current
        # timestep bin and append the results to the output list
        # apply temporal interpolation to the forecasts made between the
        # previous and the next integer time steps
        for t_sub in subtimesteps:
            if t_sub > 0:
                t_diff_prev_int = t_sub - int(t_sub)
                if t_diff_prev_int > 0.0:
                    precip_forecast_ip = (
                        1.0 - t_diff_prev_int
                    ) * precip_forecast_prev + t_diff_prev_int * precip_forecast_new
                else:
                    precip_forecast_ip = precip_forecast_prev

                t_diff_prev = t_sub - t_prev
                t_total += t_diff_prev

                if displacement is None:
                    displacement = [None for _ in range(precip_forecast_ip.shape[0])]

                if precip_forecast_out is None and return_output:
                    precip_forecast_out = [
                        [] for _ in range(precip_forecast_ip.shape[0])
                    ]

                precip_forecast_out_cur = [
                    None for _ in range(precip_forecast_ip.shape[0])
                ]

                def worker1(i):
                    extrap_kwargs_ = extrap_kwargs.copy()
                    extrap_kwargs_["displacement_prev"] = displacement[i]
                    extrap_kwargs_["allow_nonfinite_values"] = (
                        True if np.any(~np.isfinite(precip_forecast_ip[i])) else False
                    )

                    if velocity_pert_gen is not None:
                        velocity_ = velocity + velocity_pert_gen[i](t_total)
                    else:
                        velocity_ = velocity

                    precip_forecast_ep, displacement[i] = extrapolator(
                        precip_forecast_ip[i],
                        velocity_,
                        [t_diff_prev],
                        **extrap_kwargs_,
                    )

                    precip_forecast_out_cur[i] = precip_forecast_ep[0]
                    if return_output:
                        precip_forecast_out[i].append(precip_forecast_ep[0])

                if DASK_IMPORTED and ensemble and num_ensemble_members > 1:
                    res = []
                    for i in range(precip_forecast_ip.shape[0]):
                        res.append(dask.delayed(worker1)(i))
                    dask.compute(*res, num_workers=num_workers)
                else:
                    for i in range(precip_forecast_ip.shape[0]):
                        worker1(i)

                if callback is not None:
                    precip_forecast_out_cur = np.stack(precip_forecast_out_cur)
                    callback(precip_forecast_out_cur)

                precip_forecast_out_cur = None
                t_prev = t_sub

        # advect the forecast field by one time step if no subtimesteps in the
        # current interval were found
        if not subtimesteps:
            t_diff_prev = t + 1 - t_prev
            t_total += t_diff_prev

            if displacement is None:
                displacement = [None for _ in range(precip_forecast_new.shape[0])]

            def worker2(i):
                extrap_kwargs_ = extrap_kwargs.copy()
                extrap_kwargs_["displacement_prev"] = displacement[i]

                if velocity_pert_gen is not None:
                    velocity_ = velocity + velocity_pert_gen[i](t_total)
                else:
                    velocity_ = velocity

                _, displacement[i] = extrapolator(
                    None,
                    velocity_,
                    [t_diff_prev],
                    **extrap_kwargs_,
                )

            if DASK_IMPORTED and ensemble and num_ensemble_members > 1:
                res = []
                for i in range(precip_forecast_new.shape[0]):
                    res.append(dask.delayed(worker2)(i))
                dask.compute(*res, num_workers=num_workers)
            else:
                for i in range(precip_forecast_new.shape[0]):
                    worker2(i)

            t_prev = t + 1

        precip_forecast_prev = precip_forecast_new
        state_cur = state_new

        if is_nowcast_time_step:
            if measure_time:
                print(f"{time.time() - starttime:.2f} seconds.")
            else:
                print("done.")

    if return_output:
        precip_forecast_out = np.stack(precip_forecast_out)
        if not ensemble:
            precip_forecast_out = precip_forecast_out[0, :]

    if measure_time:
        return precip_forecast_out, time.time() - starttime_total
    else:
        return precip_forecast_out

def compute_percentile_mask(precip, pct):
    # obtain the CDF from the input precipitation field
    precip_s = precip.flatten()

    # compute the precipitation intensity threshold corresponding to the given
    # percentile
    precip_s.sort(kind="quicksort")
    x = 1.0 * np.arange(1, len(precip_s) + 1)[::-1] / len(precip_s)
    i = np.argmin(np.abs(x - pct))
    # handle ties
    if precip_s[i] == precip_s[i + 1]:
        i = np.where(precip_s == precip_s[i])[0][-1]
    precip_pct_thr = precip_s[i]

    # determine the mask using the above threshold value
    return precip >= precip_pct_thr

def get_default_params_bps_par():
    """Return a tuple containing the default velocity perturbation parameters
    given in :cite:`BPS2006` for the parallel component."""
    return (10.88, 0.23, -7.68)

def get_default_params_bps_perp():
    """Return a tuple containing the default velocity perturbation parameters
    given in :cite:`BPS2006` for the perpendicular component."""
    return (5.76, 0.31, -2.72)

def composite_convolution(field, kernels, weights):
    """
    Compute a localized convolution by applying a set of kernels with the
    given spatial weights. The weights are assumed to be normalized.
    """
    n = len(kernels)
    field_c = 0.0

    for i in range(n):
        field_c += weights[i] * masked_convolution(field, kernels[i])

    return field_c


def compute_ellipse_bbox(phi, sigma1, sigma2, cutoff):
    """Compute the bounding box of an ellipse."""
    r1 = cutoff * sigma1
    r2 = cutoff * sigma2
    phi_r = phi / 180.0 * np.pi

    if np.abs(phi_r - np.pi / 2) > 1e-6 and np.abs(phi_r - 3 * np.pi / 2) > 1e-6:
        alpha = np.arctan(-r2 * np.sin(phi_r) / (r1 * np.cos(phi_r)))
        w = r1 * np.cos(alpha) * np.cos(phi_r) - r2 * np.sin(alpha) * np.sin(phi_r)

        alpha = np.arctan(r2 * np.cos(phi_r) / (r1 * np.sin(phi_r)))
        h = r1 * np.cos(alpha) * np.sin(phi_r) + r2 * np.sin(alpha) * np.cos(phi_r)
    else:
        w = sigma2 * cutoff
        h = sigma1 * cutoff

    return -abs(h), -abs(w), abs(h), abs(w)


def compute_inverse_acf_mapping(target_dist, target_dist_params, n_intervals=10):
    """Compute the inverse ACF mapping between two distributions."""
    phi = (
        lambda x1, x2, rho: 1.0
        / (2 * np.pi * np.sqrt(1 - rho**2))
        * np.exp(-(x1**2 + x2**2 - 2 * rho * x1 * x2) / (2 * (1 - rho**2)))
    )

    rho_1 = np.linspace(-0.9, 0.9, n_intervals)
    rho_2 = np.empty(len(rho_1))

    mu = target_dist.mean(*target_dist_params)
    sigma = target_dist.std(*target_dist_params)

    cdf_trans = lambda x: target_dist.ppf(stats.norm.cdf(x), *target_dist_params)
    int_range = (-6, 6)

    for i, rho_1_ in enumerate(rho_1):
        f = (
            lambda x1, x2: (cdf_trans(x1) - mu)
            * (cdf_trans(x2) - mu)
            * phi(x1, x2, rho_1_)
        )
        opts = {"epsabs": 1e-8, "epsrel": 1e-8, "limit": 1}
        rho_2[i] = nquad(f, (int_range, int_range), opts=opts)[0] / (sigma * sigma)

    return interp1d(rho_2, rho_1, fill_value="extrapolate")


def compute_kernel_anisotropic(params, cutoff=6.0):
    """Compute anisotropic Gaussian convolution kernel."""
    phi, sigma1, sigma2 = params

    phi_r = phi / 180.0 * np.pi
    rot_inv = np.array(
        [[np.cos(phi_r), np.sin(phi_r)], [-np.sin(phi_r), np.cos(phi_r)]]
    )

    bb_y1, bb_x1, bb_y2, bb_x2 = compute_ellipse_bbox(phi, sigma1, sigma2, cutoff)

    x = np.arange(int(bb_x1), int(bb_x2) + 1).astype(float)
    if len(x) % 2 == 0:
        x = np.arange(int(bb_x1) - 1, int(bb_x2) + 1).astype(float)
    y = np.arange(int(bb_y1), int(bb_y2) + 1).astype(float)
    if len(y) % 2 == 0:
        y = np.arange(int(bb_y1) - 1, int(bb_y2) + 1).astype(float)

    x_grid, y_grid = np.meshgrid(x, y)
    xy_grid = np.vstack([x_grid.flatten(), y_grid.flatten()])
    xy_grid = np.dot(rot_inv, xy_grid)

    x2 = xy_grid[0, :] * xy_grid[0, :]
    y2 = xy_grid[1, :] * xy_grid[1, :]
    result = np.exp(-(x2 / sigma1**2 + y2 / sigma2**2))

    return np.reshape(result / np.sum(result), x_grid.shape)


def compute_kernel_isotropic(sigma, cutoff=6.0):
    """Compute isotropic Gaussian convolution kernel."""
    bb_y1, bb_x1, bb_y2, bb_x2 = (
        -sigma * cutoff,
        -sigma * cutoff,
        sigma * cutoff,
        sigma * cutoff,
    )

    x = np.arange(int(bb_x1), int(bb_x2) + 1).astype(float)
    if len(x) % 2 == 0:
        x = np.arange(int(bb_x1) - 1, int(bb_x2) + 1).astype(float)
    y = np.arange(int(bb_y1), int(bb_y2) + 1).astype(float)
    if len(y) % 2 == 0:
        y = np.arange(int(bb_y1) - 1, int(bb_y2) + 1).astype(float)

    x_grid, y_grid = np.meshgrid(x / sigma, y / sigma)

    r2 = x_grid * x_grid + y_grid * y_grid
    result = np.exp(-0.5 * r2)

    return result / np.sum(result)


def compute_parametric_acf(params, m, n):
    """Compute parametric ACF."""
    c, phi, sigma1, sigma2 = params

    phi_r = phi / 180.0 * np.pi
    rot_inv = np.array(
        [[np.cos(phi_r), np.sin(phi_r)], [-np.sin(phi_r), np.cos(phi_r)]]
    )

    if n % 2 == 0:
        n_max = int(n / 2)
    else:
        n_max = int(n / 2) + 1
    x = np.fft.ifftshift(np.arange(-int(n / 2), n_max))
    if m % 2 == 0:
        m_max = int(m / 2)
    else:
        m_max = int(m / 2) + 1
    y = np.fft.ifftshift(np.arange(-int(m / 2), m_max))

    grid_x, grid_y = np.meshgrid(x, y)
    grid_xy = np.vstack([grid_x.flatten(), grid_y.flatten()])
    grid_xy = np.dot(rot_inv, grid_xy)

    grid_xy[0, :] = grid_xy[0, :] / sigma1
    grid_xy[1, :] = grid_xy[1, :] / sigma2

    r2 = np.reshape(
        grid_xy[0, :] * grid_xy[0, :] + grid_xy[1, :] * grid_xy[1, :], grid_x.shape
    )
    result = np.exp(-np.sqrt(r2))

    return c * result

def compute_sample_acf(field):
    """Compute sample ACF from FFT."""
    field_fft = np.fft.rfft2((field - np.mean(field)) / np.std(field))
    fft_abs = np.abs(field_fft * np.conj(field_fft))

    return np.fft.irfft2(fft_abs, s=field.shape) / (field.shape[0] * field.shape[1])


def compute_window_weights(coords, grid_height, grid_width, window_radius):
    """Compute interpolation weights."""
    coords = coords.astype(float).copy()
    num_features = coords.shape[0]

    coords[:, 0] /= grid_height
    coords[:, 1] /= grid_width

    window_radius_1 = window_radius / grid_height
    window_radius_2 = window_radius / grid_width

    grid_x = (np.arange(grid_width) + 0.5) / grid_width
    grid_y = (np.arange(grid_height) + 0.5) / grid_height

    grid_x, grid_y = np.meshgrid(grid_x, grid_y)

    w = np.empty((num_features, grid_x.shape[0], grid_x.shape[1]))

    if coords.shape[0] > 1:
        for i, c in enumerate(coords):
            dy = c[0] - grid_y
            dx = c[1] - grid_x

            w[i, :] = np.exp(
                -dy * dy / (2 * window_radius_1**2)
                - dx * dx / (2 * window_radius_2**2)
            )
    else:
        w[0, :] = np.ones((grid_height, grid_width))

    return w


def estimate_ar1_params(
    field_src, field_dst, estim_weights, interp_weights, num_workers=1
):
    """Constrained optimization of AR(1) parameters."""

    def objf(p, *args):
        i = args[0]
        field_ar = p * field_src
        return np.nansum(estim_weights[i] * (field_dst - field_ar) ** 2.0)

    bounds = (-0.98, 0.98)

    def worker(i):
        return opt.minimize_scalar(objf, method="bounded", bounds=bounds, args=(i,)).x

    if DASK_IMPORTED and num_workers > 1:
        res = []
        for i in range(len(estim_weights)):
            res.append(dask.delayed(worker)(i))

        psi = dask.compute(*res, num_workers=num_workers, scheduler="threads")
    else:
        psi = []
        for i in range(len(estim_weights)):
            psi.append(worker(i))

    return [np.sum([psi_ * interp_weights[i] for i, psi_ in enumerate(psi)], axis=0)]


def estimate_ar2_params(
    field_src, field_dst, estim_weights, interp_weights, num_workers=1
):
    """Constrained optimization of AR(2) parameters."""

    def objf(p, *args):
        i = args[0]
        field_ar = p[0] * field_src[1] + p[1] * field_src[0]
        return np.nansum(estim_weights[i] * (field_dst - field_ar) ** 2.0)

    bounds = [(-1.98, 1.98), (-0.98, 0.98)]
    constraints = [
        opt.LinearConstraint(
            np.array([(1, 1), (-1, 1)]),
            (-np.inf, -np.inf),
            (0.98, 0.98),
            keep_feasible=True,
        )
    ]

    def worker(i):
        return opt.minimize(
            objf,
            (0.8, 0.0),
            method="trust-constr",
            bounds=bounds,
            constraints=constraints,
            args=(i,),
        ).x

    if DASK_IMPORTED and num_workers > 1:
        res = []
        for i in range(len(estim_weights)):
            res.append(dask.delayed(worker)(i))

        psi = dask.compute(*res, num_workers=num_workers, scheduler="threads")
    else:
        psi = []
        for i in range(len(estim_weights)):
            psi.append(worker(i))

    psi_out = []
    for i in range(2):
        psi_out.append(
            np.sum([psi[j][i] * interp_weights[j] for j in range(len(psi))], axis=0)
        )

    return psi_out


def estimate_convol_params(
    field_src,
    field_dst,
    weights,
    mask,
    kernel_type="anisotropic",
    kernel_params=None,
    num_workers=1,
):
    """Estimation of convolution kernel."""
    if kernel_params is None:
        kernel_params = {}
    masks = []
    for weight in weights:
        masks.append(np.logical_and(mask, weight > 1e-3))

    def objf_aniso(p, *args):
        i = args[0]
        p = get_anisotropic_kernel_params(p)
        kernel = compute_kernel_anisotropic(p, **kernel_params)

        field_src_c = masked_convolution(field_src, kernel)
        fval = np.sqrt(weights[i][masks[i]]) * (
            field_dst[masks[i]] - field_src_c[masks[i]]
        )

        return fval

    def objf_iso(p, *args):
        i = args[0]
        kernel = compute_kernel_isotropic(p, **kernel_params)

        field_src_c = masked_convolution(field_src, kernel)
        fval = np.sum(
            weights[i][masks[i]] * (field_dst[masks[i]] - field_src_c[masks[i]]) ** 2
        )

        return fval

    def worker(i):
        if kernel_type == "anisotropic":
            bounds = ((-np.inf, 0.1, 0.2), (np.inf, 10.0, 5.0))
            p_opt = opt.least_squares(
                objf_aniso,
                np.array((0.0, 1.0, 1.0)),
                bounds=bounds,
                method="trf",
                ftol=1e-6,
                xtol=1e-4,
                gtol=1e-6,
                args=(i,),
            )
            p_opt = get_anisotropic_kernel_params(p_opt.x)

            return compute_kernel_anisotropic(p_opt, **kernel_params)
        else:
            p_opt = opt.minimize_scalar(
                objf_iso, bounds=[0.01, 10.0], method="bounded", args=(i,)
            )
            p_opt = p_opt.x

            return compute_kernel_isotropic(p_opt, **kernel_params)

    if DASK_IMPORTED and num_workers > 1:
        res = []
        for i in range(len(weights)):
            res.append(dask.delayed(worker)(i))
        kernels = dask.compute(*res, num_workers=num_workers, scheduler="threads")
    else:
        kernels = []
        for i in range(len(weights)):
            kernels.append(worker(i))

    return kernels


def estimate_perturbation_params(
    forecast_err,
    forecast_gen,
    errdist_window_radius,
    acf_window_radius,
    interp_window_radius,
    measure_time,
    num_workers,
    use_multiprocessing,
):
    """
    Estimate perturbation generator parameters from forecast errors."""
    pert_gen = {}
    pert_gen["m"] = forecast_err.shape[0]
    pert_gen["n"] = forecast_err.shape[1]

    feature_coords = forecast_gen["feature_coords"]

    print("Estimating perturbation parameters... ", end="", flush=True)

    if measure_time:
        starttime = time.time()

    mask_finite = np.isfinite(forecast_err)

    forecast_err = forecast_err.copy()
    forecast_err[~mask_finite] = 1.0

    weights_dist = compute_window_weights(
        feature_coords,
        forecast_err.shape[0],
        forecast_err.shape[1],
        errdist_window_radius,
    )

    acf_winfunc = window_tukey if feature_coords.shape[0] > 1 else window_uniform

    def worker(i):
        weights_acf = acf_winfunc(
            forecast_err.shape[0],
            forecast_err.shape[1],
            feature_coords[i, 0],
            feature_coords[i, 1],
            acf_window_radius,
            acf_window_radius,
        )

        mask = np.logical_and(mask_finite, weights_dist[i] > 0.1)
        if np.sum(mask) > 10 and np.sum(np.abs(forecast_err[mask] - 1.0) >= 1e-3) > 10:
            distpar = fit_dist(forecast_err, stats.lognorm, weights_dist[i], mask)
            inv_acf_mapping = compute_inverse_acf_mapping(stats.lognorm, distpar)
            mask_acf = weights_acf > 1e-4
            std = weighted_std(forecast_err[mask_acf], weights_dist[i][mask_acf])
            if np.isfinite(std):
                acf = inv_acf_mapping(
                    compute_sample_acf(weights_acf * (forecast_err - 1.0) / std)
                )
                acf = fit_acf(acf)
            else:
                distpar = None
                std = None
                acf = None
        else:
            distpar = None
            std = None
            acf = None

        return distpar, std, np.sqrt(np.abs(np.fft.rfft2(acf)))

    dist_params = []
    stds = []
    acf_fft_ampl = []

    if DASK_IMPORTED and num_workers > 1:
        res = []
        for i in range(feature_coords.shape[0]):
            res.append(dask.delayed(worker)(i))
        scheduler = "threads" if not use_multiprocessing else "multiprocessing"
        res = dask.compute(*res, num_workers=num_workers, scheduler=scheduler)
        for r in res:
            dist_params.append(r[0])
            stds.append(r[1])
            acf_fft_ampl.append(r[2])
    else:
        for i in range(feature_coords.shape[0]):
            r = worker(i)
            dist_params.append(r[0])
            stds.append(r[1])
            acf_fft_ampl.append(r[2])

    pert_gen["dist_param"] = dist_params
    pert_gen["std"] = stds
    pert_gen["acf_fft_ampl"] = acf_fft_ampl

    weights = compute_window_weights(
        feature_coords,
        forecast_err.shape[0],
        forecast_err.shape[1],
        interp_window_radius,
    )
    pert_gen["weights"] = weights / np.sum(weights, axis=0)

    if measure_time:
        print(f"{time.time() - starttime:.2f} seconds.")
    else:
        print("done.")

    return pert_gen


def fit_acf(acf):
    """
    Fit a parametric ACF to the given sample estimate."""

    def objf(p, *args):
        p = get_acf_params(p)
        fitted_acf = compute_parametric_acf(p, acf.shape[0], acf.shape[1])

        return (acf - fitted_acf).flatten()

    bounds = ((0.01, -np.inf, 0.1, 0.2), (10.0, np.inf, 10.0, 5.0))
    p_opt = opt.least_squares(
        objf,
        np.array((1.0, 0.0, 1.0, 1.0)),
        bounds=bounds,
        method="trf",
        ftol=1e-6,
        xtol=1e-4,
        gtol=1e-6,
    )

    return compute_parametric_acf(get_acf_params(p_opt.x), acf.shape[0], acf.shape[1])


def fit_dist(err, dist, wf, mask):
    """
    Fit a lognormal distribution by maximizing the log-likelihood function
    with the constraint that the mean value is one."""
    func = lambda p: -np.sum(np.log(stats.lognorm.pdf(err[mask], p, -0.5 * p**2)))
    p_opt = opt.minimize_scalar(func, bounds=(1e-3, 20.0), method="Bounded")

    return (p_opt.x, -0.5 * p_opt.x**2)

def generate_perturbations(pert_gen, num_workers, seed):
    """Generate perturbations based on the estimated forecast error statistics."""
    m, n = pert_gen["m"], pert_gen["n"]
    dist_param = pert_gen["dist_param"]
    std = pert_gen["std"]
    acf_fft_ampl = pert_gen["acf_fft_ampl"]
    weights = pert_gen["weights"]

    perturb = stats.norm.rvs(size=(m, n), random_state=seed)
    perturb_fft = np.fft.rfft2(perturb)

    out = np.zeros((m, n))

    def worker(i):
        if std[i] > 0.0:
            filtered_noise = np.fft.irfft2(acf_fft_ampl[i] * perturb_fft, s=(m, n))
            filtered_noise /= np.std(filtered_noise)
            filtered_noise = stats.lognorm.ppf(
                stats.norm.cdf(filtered_noise), *dist_param[i]
            )
        else:
            filtered_noise = np.ones(weights[i].shape)

        return weights[i] * filtered_noise

    if DASK_IMPORTED and num_workers > 1:
        res = []
        for i in range(weights.shape[0]):
            res.append(dask.delayed(worker)(i))
        res = dask.compute(*res, num_workers=num_workers, scheduler="threads")
        for r in res:
            out += r
    else:
        for i in range(weights.shape[0]):
            out += worker(i)

    return out


def get_acf_params(p):
    """Get ACF parameters from the given parameter vector."""
    return p[0], p[1], p[2], p[3] * p[2]


def get_anisotropic_kernel_params(p):
    """Get anisotropic convolution kernel parameters from the given parameter
    vector."""
    return p[0], p[1], p[2] * p[1]

def iterate_ar_model(input_fields, psi):
    """Iterate autoregressive process."""
    input_field_new = 0.0

    for i, psi_ in enumerate(psi):
        input_field_new += psi_ * input_fields[-(i + 1), :]

    return np.concatenate([input_fields[1:, :], input_field_new[np.newaxis, :]])

def autoregression_iterate_ar_model(x, phi, eps=None):
    if x.shape[0] < len(phi) - 1:
        raise ValueError(
            "dimension mismatch between x and phi: x.shape[0]=%d, len(phi)=%d"
            % (x.shape[0], len(phi))
        )

    if len(x.shape) == 1:
        x_simple_shape = True
        x = x[:, np.newaxis]
    else:
        x_simple_shape = False

    if eps is not None and eps.shape != x.shape[1:]:
        raise ValueError(
            "dimension mismatch between x and eps: x.shape=%s, eps.shape[1:]=%s"
            % (str(x.shape), str(eps.shape[1:]))
        )

    x_new = 0.0

    p = len(phi) - 1

    for i in range(p):
        x_new += phi[i] * x[-(i + 1), :]

    if eps is not None:
        x_new += phi[-1] * eps

    if x_simple_shape:
        return np.hstack([x[1:], [x_new]])
    else:
        return np.concatenate([x[1:, :], x_new[np.newaxis, :]])

def blob_detection(
    input_image,
    max_num_features=None,
    method="log",
    threshold=0.5,
    min_sigma=3,
    max_sigma=20,
    overlap=0.5,
    return_sigmas=False,
    **kwargs,
):
    if method not in ["log", "dog", "doh"]:
        raise ValueError("unknown method %s, must be 'log', 'dog' or 'doh'" % method)

    if not SKIMAGE_IMPORTED:
        raise MissingOptionalDependency(
            "skimage is required for the blob_detection routine but it is not installed"
        )

    if method == "log":
        detector = ski_feature.blob_log
    elif method == "dog":
        detector = ski_feature.blob_dog
    else:
        detector = ski_feature.blob_doh

    blobs = detector(
        input_image,
        min_sigma=min_sigma,
        max_sigma=max_sigma,
        threshold=threshold,
        overlap=overlap,
        **kwargs,
    )

    if max_num_features is not None and blobs.shape[0] > max_num_features:
        blob_intensities = []
        for i in range(blobs.shape[0]):
            gl_image = -gaussian_laplace(input_image, blobs[i, 2]) * blobs[i, 2] ** 2
            blob_intensities.append(gl_image[int(blobs[i, 0]), int(blobs[i, 1])])
        idx = np.argsort(blob_intensities)[::-1]
        blobs = blobs[idx[:max_num_features], :]

    if not return_sigmas:
        return np.column_stack([blobs[:, 1], blobs[:, 0]])
    else:
        return np.column_stack([blobs[:, 1], blobs[:, 0], blobs[:, 2]])

def longdistance(loc_max, mindis):
    """
    This function computes the distance between all maxima and rejects maxima that are
    less than a minimum distance apart.
    """
    x_max = loc_max[1]
    y_max = loc_max[0]
    n = 0
    while n < len(y_max):
        disx = x_max[n] - x_max
        disy = y_max[n] - y_max
        dis = np.sqrt(disx * disx + disy * disy)
        close = np.where(dis < mindis)[0]
        close = np.delete(close, np.where(close <= n))
        if len(close) > 0:
            x_max = np.delete(x_max, close)
            y_max = np.delete(y_max, close)
        n += 1

    new_max = y_max, x_max

    return new_max

def breakup(ref, minval, maxima):
    """
    This function segments the entire 2-D array into areas belonging to each identified
    maximum according to a watershed algorithm.
    """
    ref_t = np.zeros(ref.shape)
    ref_t[:] = minval
    ref_t[ref > minval] = ref[ref > minval]
    markers = ndi.label(maxima)[0]
    areas = skis.watershed(-ref_t, markers=markers)
    lines = skis.watershed(-ref_t, markers=markers, watershed_line=True)

    return areas, lines

def get_profile(areas, binary, ref, loc_max, time, minref):
    """
    This function returns the identified cells in a dataframe including their x,y
    locations, location of their maxima, maximum reflectivity and contours.
    """
    cells = areas * binary
    cell_labels = cells[loc_max]
    labels = np.zeros(cells.shape)
    cells_id = pd.DataFrame(
        data=None,
        index=range(len(cell_labels)),
        columns=["ID", "time", "x", "y", "cen_x", "cen_y", "max_ref", "cont", "area"],
    )
    cells_id.time = time
    for n in range(len(cell_labels)):
        ID = n + 1
        cells_id.ID.iloc[n] = ID
        cells_id.x.iloc[n] = np.where(cells == cell_labels[n])[1]
        cells_id.y.iloc[n] = np.where(cells == cell_labels[n])[0]
        cell_unique = np.zeros(cells.shape)
        cell_unique[cells == cell_labels[n]] = 1
        maxref = np.nanmax(ref[cells_id.y[n], cells_id.x[n]])
        contours = skime.find_contours(cell_unique, 0.8)
        cells_id.cont.iloc[n] = contours
        cells_id.cen_x.iloc[n] = np.round(np.nanmean(cells_id.x[n])).astype(int)
        cells_id.cen_y.iloc[n] = np.round(np.nanmean(cells_id.y[n])).astype(int)
        cells_id.max_ref.iloc[n] = maxref
        cells_id.area.iloc[n] = len(cells_id.x.iloc[n])
        labels[cells == cell_labels[n]] = ID

    return cells_id, labels

def tstorm_detection(
    input_image,
    max_num_features=None,
    minref=35,
    maxref=48,
    mindiff=6,
    minsize=50,
    minmax=41,
    mindis=10,
    output_feat=False,
    time="000000000",
):
    if not SKIMAGE_IMPORTED:
        raise MissingOptionalDependency(
            "skimage is required for thunderstorm DATing " "but it is not installed"
        )
    if not PANDAS_IMPORTED:
        raise MissingOptionalDependency(
            "pandas is required for thunderstorm DATing " "but it is not installed"
        )
    filt_image = np.zeros(input_image.shape)
    filt_image[input_image >= minref] = input_image[input_image >= minref]
    filt_image[input_image > maxref] = maxref
    max_image = np.zeros(filt_image.shape)
    max_image[filt_image == maxref] = 1
    labels, n_groups = ndi.label(max_image)
    for n in range(1, n_groups + 1):
        indx, indy = np.where(labels == n)
        if len(indx) > 3:
            max_image[indx[0], indy[0]] = 2
    filt_image[max_image == 2] = maxref + 1
    binary = np.zeros(filt_image.shape)
    binary[filt_image > 0] = 1
    labels, n_groups = ndi.label(binary)
    for n in range(1, n_groups + 1):
        ind = np.where(labels == n)
        size = len(ind[0])
        maxval = np.nanmax(input_image[ind])
        if size < minsize:  # removing too small areas
            binary[labels == n] = 0
            labels[labels == n] = 0
        if maxval < minmax:  # removing areas with too low max value
            binary[labels == n] = 0
            labels[labels == n] = 0
    filt_image = filt_image * binary
    if mindis % 2 == 0:
        elem = mindis - 1
    else:
        elem = mindis
    struct = np.ones([elem, elem])
    if np.nanmax(filt_image.flatten()) < minref:
        maxima = np.zeros(filt_image.shape)
    else:
        maxima = skim.h_maxima(filt_image, h=mindiff, footprint=struct)
    loc_max = np.where(maxima > 0)

    loc_max = longdistance(loc_max, mindis)
    i_cell = labels[loc_max]
    n_cell = np.unique(labels)[1:]
    for n in n_cell:
        if n not in i_cell:
            binary[labels == n] = 0
            labels[labels == n] = 0

    maxima_dis = np.zeros(maxima.shape)
    maxima_dis[loc_max] = 1

    areas, lines = breakup(input_image, np.nanmin(input_image.flatten()), maxima_dis)

    cells_id, labels = get_profile(areas, binary, input_image, loc_max, time, minref)

    if max_num_features is not None:
        idx = np.argsort(cells_id.area.to_numpy())[::-1]

    if not output_feat:
        if max_num_features is None:
            return cells_id, labels
        else:
            for i in idx[max_num_features:]:
                labels[labels == cells_id.ID[i]] = 0
            return cells_id.loc[idx[:max_num_features]], labels
    if output_feat:
        out = np.column_stack([np.array(cells_id.cen_x), np.array(cells_id.cen_y)])
        if max_num_features is not None:
            out = out[idx[:max_num_features], :]

        return out

def shitomasi_detection(
    input_image,
    max_corners=1000,
    max_num_features=None,
    quality_level=0.01,
    min_distance=10,
    block_size=5,
    buffer_mask=5,
    use_harris=False,
    k=0.04,
    verbose=False,
    **kwargs,
):
    if not CV2_IMPORTED:
        raise MissingOptionalDependency(
        )

    input_image = input_image.copy()

    if input_image.ndim != 2:
        raise ValueError("input_image must be a two-dimensional array")

    # Check if a MaskedArray is used. If not, mask the ndarray
    if not isinstance(input_image, MaskedArray):
        input_image = np.ma.masked_invalid(input_image)

    np.ma.set_fill_value(input_image, input_image.min())

    # buffer the quality mask to ensure that no vectors are computed nearby
    # the edges of the radar mask
    mask = np.ma.getmaskarray(input_image).astype("uint8")
    if buffer_mask > 0:
        mask = cv2.dilate(
            mask, np.ones((int(buffer_mask), int(buffer_mask)), np.uint8), 1
        )
        input_image[mask] = np.ma.masked

    # scale image between 0 and 255
    im_min = input_image.min()
    im_max = input_image.max()
    if im_max - im_min > 1e-8:
        input_image = (input_image.filled() - im_min) / (im_max - im_min) * 255
    else:
        input_image = input_image.filled() - im_min

    # convert to 8-bit
    input_image = np.ndarray.astype(input_image, "uint8")
    mask = (-1 * mask + 1).astype("uint8")

    params = dict(
        maxCorners=max_num_features if max_num_features is not None else max_corners,
        qualityLevel=quality_level,
        minDistance=min_distance,
        blockSize=block_size,
        useHarrisDetector=use_harris,
        k=k,
    )
    points = cv2.goodFeaturesToTrack(input_image, mask=mask, **params)
    if points is None:
        points = np.empty(shape=(0, 2))
    else:
        points = points[:, 0, :]

    if verbose:
        print(f"--- {points.shape[0]} good features to track detected ---")

    return points

def initialize_bps(
    V, pixelsperkm, timestep, p_par=None, p_perp=None, randstate=None, seed=None
):

    if len(V.shape) != 3:
        raise ValueError("V is not a three-dimensional array")
    if V.shape[0] != 2:
        raise ValueError("the first dimension of V is not 2")

    if p_par is None:
        p_par = get_default_params_bps_par()
    if p_perp is None:
        p_perp = get_default_params_bps_perp()

    if len(p_par) != 3:
        raise ValueError("the length of p_par is not 3")
    if len(p_perp) != 3:
        raise ValueError("the length of p_perp is not 3")

    perturbator = {}
    if randstate is None:
        randstate = np.random

    if seed is not None:
        randstate.seed(seed)

    eps_par = randstate.laplace(scale=1.0 / np.sqrt(2))
    eps_perp = randstate.laplace(scale=1.0 / np.sqrt(2))

    # scale factor for converting the unit of the advection velocities
    # into km/h
    vsf = 60.0 / (timestep * pixelsperkm)

    N = linalg.norm(V, axis=0)
    mask = N > 1e-12
    V_n = np.empty(V.shape)
    V_n[:, mask] = V[:, mask] / np.stack([N[mask], N[mask]])
    V_n[:, ~mask] = 0.0

    perturbator["randstate"] = randstate
    perturbator["vsf"] = vsf
    perturbator["p_par"] = p_par
    perturbator["p_perp"] = p_perp
    perturbator["eps_par"] = eps_par
    perturbator["eps_perp"] = eps_perp
    perturbator["V_par"] = V_n
    perturbator["V_perp"] = np.stack([-V_n[1, :, :], V_n[0, :, :]])

    return perturbator

def generate_bps(perturbator, t):
    """
    Generate a motion perturbation field by using the method described in
    :cite:`BPS2006`.

    Parameters
    ----------
    perturbator: dict
      A dictionary returned by initialize_motion_perturbations_bps.
    t: float
      Lead time for the perturbation field (minutes).

    Returns
    -------
    out: ndarray
      Array of shape (2,m,n) containing the x- and y-components of the motion
      vector perturbations, where m and n are determined from the perturbator.

    See also
    --------
    pysteps.noise.motion.initialize_bps

    """
    vsf = perturbator["vsf"]
    p_par = perturbator["p_par"]
    p_perp = perturbator["p_perp"]
    eps_par = perturbator["eps_par"]
    eps_perp = perturbator["eps_perp"]
    V_par = perturbator["V_par"]
    V_perp = perturbator["V_perp"]

    g_par = p_par[0] * pow(t, p_par[1]) + p_par[2]
    g_perp = p_perp[0] * pow(t, p_perp[1]) + p_perp[2]

    return (g_par * eps_par * V_par + g_perp * eps_perp * V_perp) / vsf

def masked_convolution(field, kernel):
    """Compute "masked" convolution where non-finite values are ignored."""
    mask = np.isfinite(field)

    field = field.copy()
    field[~mask] = 0.0

    field_c = np.ones(field.shape) * np.nan
    field_c[mask] = convolve(field, kernel, mode="same")[mask]
    field_c[mask] /= convolve(mask.astype(float), kernel, mode="same")[mask]

    return field_c

def weighted_std(f, w):
    """
    Compute standard deviation of forecast errors with spatially varying weights.
    Values close to zero are omitted.
    """
    mask = np.abs(f - 1.0) > 1e-4
    n = np.count_nonzero(mask)
    if n > 0:
        c = (w[mask].size - 1.0) / n
        return np.sqrt(np.sum(w[mask] * (f[mask] - 1.0) ** 2.0) / (c * np.sum(w[mask])))
    else:
        return np.nan


def window_tukey(m, n, ci, cj, ri, rj, alpha=0.5):
    """Tukey window function centered at the given coordinates."""
    j, i = np.meshgrid(np.arange(n), np.arange(m))

    di = np.abs(i - ci)
    dj = np.abs(j - cj)

    mask1 = np.logical_and(di <= ri, dj <= rj)

    w1 = np.zeros(di.shape)
    mask2 = di <= alpha * ri
    mask12 = np.logical_and(mask1, ~mask2)
    w1[mask12] = 0.5 * (
        1.0 + np.cos(np.pi * (di[mask12] - alpha * ri) / ((1.0 - alpha) * ri))
    )
    w1[np.logical_and(mask1, mask2)] = 1.0

    w2 = np.zeros(dj.shape)
    mask2 = dj <= alpha * rj
    mask12 = np.logical_and(mask1, ~mask2)
    w2[mask12] = 0.5 * (
        1.0 + np.cos(np.pi * (dj[mask12] - alpha * rj) / ((1.0 - alpha) * rj))
    )
    w2[np.logical_and(mask1, mask2)] = 1.0

    weights = np.zeros((m, n))
    weights[mask1] = w1[mask1] * w2[mask1]

    return weights


def window_uniform(m, n, ci, cj, ri, rj):
    """Uniform window function with all values set to one."""
    return np.ones((m, n))



def hann(R):
    W = np.ones_like(R)
    N = min(R.shape[0], R.shape[1])
    mask = R > int(N / 2)

    W[mask] = 0.0
    W[~mask] = 0.5 * (1.0 - np.cos(2.0 * np.pi * (R[~mask] + int(N / 2)) / N))

    return W

def tukey(R, alpha):
    W = np.ones_like(R)
    N = min(R.shape[0], R.shape[1])

    mask1 = R < int(N / 2)
    mask2 = R > int(N / 2) * (1.0 - alpha)
    mask = np.logical_and(mask1, mask2)
    W[mask] = 0.5 * (
        1.0 + np.cos(np.pi * (R[mask] / (alpha * 0.5 * N) - 1.0 / alpha + 1.0))
    )
    mask = R >= int(N / 2)
    W[mask] = 0.0

    return W

def compute_window_function(m, n, func, **kwargs):
    X, Y = np.meshgrid(np.arange(n), np.arange(m))
    R = np.sqrt((X - int(n / 2)) ** 2 + (Y - int(m / 2)) ** 2)

    if func == "hann":
        return hann(R)
    elif func == "tukey":
        alpha = kwargs.get("alpha", 0.2)

        return tukey(R, alpha)
    else:
        raise ValueError("invalid window function '%s'" % func)

def initialize_nonparam_2d_fft_filter(field, **kwargs):
    if len(field.shape) < 2 or len(field.shape) > 3:
        raise ValueError("the input is not two- or three-dimensional array")
    if np.any(~np.isfinite(field)):
        raise ValueError("field contains non-finite values")

    # defaults
    win_fun = kwargs.get("win_fun", "tukey")
    donorm = kwargs.get("donorm", False)
    rm_rdisc = kwargs.get("rm_rdisc", True)
    use_full_fft = kwargs.get("use_full_fft", False)
    fft = kwargs.get("fft_method", "numpy")
    if type(fft) == str:
        fft_shape = field.shape if len(field.shape) == 2 else field.shape[1:]
        fft = get_numpy(shape=fft_shape)

    field = field.copy()

    # remove rain/no-rain discontinuity
    if rm_rdisc:
        field[field > field.min()] -= field[field > field.min()].min() - field.min()

    # dims
    if len(field.shape) == 2:
        field = field[None, :, :]
    nr_fields = field.shape[0]
    field_shape = field.shape[1:]
    if use_full_fft:
        fft_shape = (field.shape[1], field.shape[2])
    else:
        fft_shape = (field.shape[1], int(field.shape[2] / 2) + 1)

    # make sure non-rainy pixels are set to zero
    field -= field.min(axis=(1, 2))[:, None, None]

    if win_fun is not None:
        tapering = compute_window_function(
            field_shape[0], field_shape[1], win_fun
        )
    else:
        tapering = np.ones(field_shape)

    F = np.zeros(fft_shape, dtype=complex)
    for i in range(nr_fields):
        if use_full_fft:
            F += fft.fft2(field[i, :, :] * tapering)
        else:
            F += fft.rfft2(field[i, :, :] * tapering)
    F /= nr_fields

    # normalize the real and imaginary parts
    if donorm:
        if np.std(F.imag) > 0:
            F.imag = (F.imag - np.mean(F.imag)) / np.std(F.imag)
        if np.std(F.real) > 0:
            F.real = (F.real - np.mean(F.real)) / np.std(F.real)

    return {
        "field": np.abs(F),
        "input_shape": field.shape[1:],
        "use_full_fft": use_full_fft,
    }

def generate_noise_2d_fft_filter(
    F, randstate=None, seed=None, fft_method=None, domain="spatial"
):
    if domain not in ["spatial", "spectral"]:
        raise ValueError(
            "invalid value %s for the 'domain' argument: must be 'spatial' or 'spectral'"
            % str(domain)
        )

    input_shape = F["input_shape"]
    use_full_fft = F["use_full_fft"]
    F = F["field"]

    if len(F.shape) != 2:
        raise ValueError("field is not two-dimensional array")
    if np.any(~np.isfinite(F)):
        raise ValueError("field contains non-finite values")

    if randstate is None:
        randstate = np.random

    # set the seed
    if seed is not None:
        randstate.seed(seed)

    if fft_method is None:
        fft = get_numpy(shape=input_shape)
    else:
        if type(fft_method) == str:
            fft = get_numpy(shape=input_shape)
        else:
            fft = fft_method

    # produce fields of white noise
    if domain == "spatial":
        N = randstate.randn(input_shape[0], input_shape[1])
    else:
        if use_full_fft:
            size = (input_shape[0], input_shape[1])
        else:
            size = (input_shape[0], int(input_shape[1] / 2) + 1)
        theta = randstate.uniform(low=0.0, high=2.0 * np.pi, size=size)
        if input_shape[0] % 2 == 0:
            theta[int(input_shape[0] / 2) + 1 :, 0] = -theta[
                1 : int(input_shape[0] / 2), 0
            ][::-1]
        else:
            theta[int(input_shape[0] / 2) + 1 :, 0] = -theta[
                1 : int(input_shape[0] / 2) + 1, 0
            ][::-1]
        N = np.cos(theta) + 1.0j * np.sin(theta)

    # apply the global Fourier filter to impose a correlation structure
    if domain == "spatial":
        if use_full_fft:
            fN = fft.fft2(N)
        else:
            fN = fft.rfft2(N)
    else:
        fN = N
    fN *= F
    if domain == "spatial":
        if use_full_fft:
            N = np.array(fft.ifft2(fN).real)
        else:
            N = np.array(fft.irfft2(fN))
        N = (N - N.mean()) / N.std()
    else:
        N = fN
        N[0, 0] = 0.0
        N /= spectral_std(N, input_shape, use_full_fft=use_full_fft)

    return N

def compute_noise_stddev_adjs(
    R,
    R_thr_1,
    R_thr_2,
    F,
    decomp_method,
    noise_filter,
    noise_generator,
    num_iter,
    conditional=True,
    num_workers=1,
    seed=None,
):

    MASK = R >= R_thr_1

    R = R.copy()
    R[~np.isfinite(R)] = R_thr_2
    R[~MASK] = R_thr_2
    if not conditional:
        mu, sigma = np.mean(R), np.std(R)
    else:
        mu, sigma = np.mean(R[MASK]), np.std(R[MASK])
    R -= mu

    MASK_ = MASK if conditional else None
    decomp_R = decomp_method(R, F, mask=MASK_)

    if DASK_IMPORTED and num_workers > 1:
        res = []
    else:
        N_stds = []

    randstates = []
    seed = None
    for k in range(num_iter):
        randstates.append(np.random.RandomState(seed=seed))
        seed = np.random.randint(0, high=1e9)

    for k in range(num_iter):

        def worker():
            # generate Gaussian white noise field, filter it using the chosen
            # method, multiply it with the standard deviation of the observed
            # field and apply the precipitation mask
            N = noise_generator(noise_filter, randstate=randstates[k], seed=seed)
            N = N / np.std(N) * sigma + mu
            N[~MASK] = R_thr_2

            # subtract the mean and decompose the masked noise field into a
            # cascade
            N -= mu
            decomp_N = decomp_method(N, F, mask=MASK_)

            return decomp_N["stds"]

        if DASK_IMPORTED and num_workers > 1:
            res.append(dask.delayed(worker)())
        else:
            N_stds.append(worker())

    if DASK_IMPORTED and num_workers > 1:
        N_stds = dask.compute(*res, num_workers=num_workers)

    # for each cascade level, compare the standard deviations between the
    # observed field and the masked noise field, which gives the correction
    # factors
    return decomp_R["stds"] / np.mean(np.vstack(N_stds), axis=0)


def compute_dilated_mask(input_mask, kr, r):
    # buffer the input mask
    input_mask = np.ndarray.astype(input_mask.copy(), "uint8")
    mask_dilated = scipy.ndimage.morphology.binary_dilation(input_mask, kr)

    # add grayscale rim
    kr1 = scipy.ndimage.generate_binary_structure(2, 1)
    mask = mask_dilated.astype(float)
    for _ in range(r):
        mask_dilated = scipy.ndimage.morphology.binary_dilation(mask_dilated, kr1)
        mask += mask_dilated

    # normalize between 0 and 1
    return mask / mask.max()


def semi_extrapolate(
    precip,
    velocity,
    timesteps,
    outval=np.nan,
    xy_coords=None,
    allow_nonfinite_values=False,
    vel_timestep=1,
    **kwargs,
):
    if precip is not None and precip.ndim != 2:
        raise ValueError("precip must be a two-dimensional array")

    if velocity.ndim != 3:
        raise ValueError("velocity must be a three-dimensional array")

    if not allow_nonfinite_values:
        if precip is not None and np.any(~np.isfinite(precip)):
            raise ValueError("precip contains non-finite values")

        if np.any(~np.isfinite(velocity)):
            raise ValueError("velocity contains non-finite values")

    if precip is not None and np.all(~np.isfinite(precip)):
        raise ValueError("precip contains only non-finite values")

    if np.all(~np.isfinite(velocity)):
        raise ValueError("velocity contains only non-finite values")

    if isinstance(timesteps, list) and not sorted(timesteps) == timesteps:
        raise ValueError("timesteps is not in ascending order")

    # defaults
    verbose = kwargs.get("verbose", False)
    displacement_prev = kwargs.get("displacement_prev", None)
    n_iter = kwargs.get("n_iter", 1)
    return_displacement = kwargs.get("return_displacement", False)
    interp_order = kwargs.get("interp_order", 1)
    map_coordinates_mode = kwargs.get("map_coordinates_mode", "constant")

    if precip is None and not return_displacement:
        raise ValueError("precip is None but return_displacement is False")

    if "D_prev" in kwargs.keys():
        warnings.warn(
            "deprecated argument D_prev is ignored, use displacement_prev instead",
        )

    # if interp_order > 1, apply separate masking to preserve nan and
    # non-precipitation values
    if precip is not None and interp_order > 1:
        minval = np.nanmin(precip)
        mask_min = (precip > minval).astype(float)
        if allow_nonfinite_values:
            mask_finite = np.isfinite(precip)
            precip = precip.copy()
            precip[~mask_finite] = 0.0
            mask_finite = mask_finite.astype(float)
        else:
            mask_finite = np.ones(precip.shape)

    prefilter = True if interp_order > 1 else False

    if isinstance(timesteps, int):
        timesteps = np.arange(1, timesteps + 1)
        vel_timestep = 1.0
    elif np.any(np.diff(timesteps) <= 0.0):
        raise ValueError("the given timestep sequence is not monotonously increasing")

    timestep_diff = np.hstack([[timesteps[0]], np.diff(timesteps)])

    if verbose:
        print("Computing the advection with the semi-lagrangian scheme.")
        t0 = time.time()

    if precip is not None and outval == "min":
        outval = np.nanmin(precip)

    if xy_coords is None:
        x_values, y_values = np.meshgrid(
            np.arange(velocity.shape[2]), np.arange(velocity.shape[1])
        )

        xy_coords = np.stack([x_values, y_values])

    def interpolate_motion(displacement, velocity_inc, td):
        coords_warped = xy_coords + displacement
        coords_warped = [coords_warped[1, :, :], coords_warped[0, :, :]]

        velocity_inc_x = ip.map_coordinates(
            velocity[0, :, :], coords_warped, mode="nearest", order=1, prefilter=False
        )
        velocity_inc_y = ip.map_coordinates(
            velocity[1, :, :], coords_warped, mode="nearest", order=1, prefilter=False
        )

        velocity_inc[0, :, :] = velocity_inc_x
        velocity_inc[1, :, :] = velocity_inc_y

        if n_iter > 1:
            velocity_inc /= n_iter

        velocity_inc *= td / vel_timestep

    precip_extrap = []
    if displacement_prev is None:
        displacement = np.zeros((2, velocity.shape[1], velocity.shape[2]))
        velocity_inc = velocity.copy() * timestep_diff[0] / vel_timestep
    else:
        displacement = displacement_prev.copy()
        velocity_inc = np.empty(velocity.shape)
        interpolate_motion(displacement, velocity_inc, timestep_diff[0])

    for ti, td in enumerate(timestep_diff):
        if n_iter > 0:
            for k in range(n_iter):
                interpolate_motion(displacement - velocity_inc / 2.0, velocity_inc, td)
                displacement -= velocity_inc
                interpolate_motion(displacement, velocity_inc, td)
        else:
            if ti > 0 or displacement_prev is not None:
                interpolate_motion(displacement, velocity_inc, td)

            displacement -= velocity_inc

        coords_warped = xy_coords + displacement
        coords_warped = [coords_warped[1, :, :], coords_warped[0, :, :]]

        if precip is not None:
            precip_warped = ip.map_coordinates(
                precip,
                coords_warped,
                mode=map_coordinates_mode,
                cval=outval,
                order=interp_order,
                prefilter=prefilter,
            )

            if interp_order > 1:
                mask_warped = ip.map_coordinates(
                    mask_min,
                    coords_warped,
                    mode=map_coordinates_mode,
                    cval=0,
                    order=1,
                    prefilter=False,
                )
                precip_warped[mask_warped < 0.5] = minval

                mask_warped = ip.map_coordinates(
                    mask_finite,
                    coords_warped,
                    mode=map_coordinates_mode,
                    cval=0,
                    order=1,
                    prefilter=False,
                )
                precip_warped[mask_warped < 0.5] = np.nan

            precip_extrap.append(np.reshape(precip_warped, precip.shape))

    if verbose:
        print("--- %s seconds ---" % (time.time() - t0))

    if precip is not None:
        if not return_displacement:
            return np.stack(precip_extrap)
        else:
            return np.stack(precip_extrap), displacement
    else:
        return None, displacement
    
_cascade_methods = dict()
_cascade_methods["fft"] = (decomposition_fft, recompose_fft)
_cascade_methods["gaussian"] = filter_gaussian
_cascade_methods["uniform"] = filter_uniform

def cascade_get_method(name):
    """
    Return a callable function for the bandpass filter or cascade decomposition
    method corresponding to the given name. For the latter, two functions are
    returned: the first is for the decomposing and the second is for recomposing
    the cascade.

    Filter methods:

    +-------------------+------------------------------------------------------+
    |     Name          |              Description                             |
    +===================+======================================================+
    |  gaussian         | implementation of bandpass filter using Gaussian     |
    |                   | weights                                              |
    +-------------------+------------------------------------------------------+
    |  uniform          | implementation of a filter where all weights are set |
    |                   | to one                                               |
    +-------------------+------------------------------------------------------+

    Decomposition/recomposition methods:

    +-------------------+------------------------------------------------------+
    |     Name          |              Description                             |
    +===================+======================================================+
    |  fft              | decomposition into multiple spatial scales based on  |
    |                   | the fast Fourier Transform (FFT) and a set of        |
    |                   | bandpass filters                                     |
    +-------------------+------------------------------------------------------+

    """

    if isinstance(name, str):
        name = name.lower()
    else:
        raise TypeError(
            "Only strings supported for the method's names.\n"
            + "Available names:"
            + str(list(_cascade_methods.keys()))
        ) from None
    try:
        return _cascade_methods[name]
    except KeyError:
        raise ValueError(
            "Unknown method {}\n".format(name)
            + "The available methods are:"
            + str(list(_cascade_methods.keys()))
        ) from None

def eulerian_persistence(precip, velocity, timesteps, outval=np.nan, **kwargs):
    del velocity, outval  # Unused by _eulerian_persistence

    if isinstance(timesteps, int):
        num_timesteps = timesteps
    else:
        num_timesteps = len(timesteps)

    return_displacement = kwargs.get("return_displacement", False)

    extrapolated_precip = np.repeat(precip[np.newaxis, :, :], num_timesteps, axis=0)

    if not return_displacement:
        return extrapolated_precip
    else:
        return extrapolated_precip, np.zeros((2,) + extrapolated_precip.shape)

def do_nothing(precip, velocity, timesteps, outval=np.nan, **kwargs):
    """Return None."""
    del precip, velocity, timesteps, outval, kwargs  # Unused
    return None


_extrapolation_methods = dict()
_extrapolation_methods["eulerian"] = eulerian_persistence
_extrapolation_methods["semilagrangian"] = extrapolate
_extrapolation_methods[None] = do_nothing
_extrapolation_methods["none"] = do_nothing


def extrapolation_get_method(name):
    """
    Return two-element tuple for the extrapolation method corresponding to
    the given name. The elements of the tuple are callable functions for the
    initializer of the extrapolator and the extrapolation method, respectively.
    The available options are:\n

    +-----------------+--------------------------------------------------------+
    |     Name        |              Description                               |
    +=================+========================================================+
    |  None           | returns None                                           |
    +-----------------+--------------------------------------------------------+
    |  eulerian       | this methods does not apply any advection to the input |
    |                 | precipitation field (Eulerian persistence)             |
    +-----------------+--------------------------------------------------------+
    | semilagrangian  | implementation of the semi-Lagrangian method described |
    |                 | in :cite:`GZ2002`                                      |
    +-----------------+--------------------------------------------------------+

    """
    if isinstance(name, str):
        name = name.lower()

    try:
        return _extrapolation_methods[name]

    except KeyError:
        raise ValueError(
            "Unknown method {}\n".format(name)
            + "The available methods are:"
            + str(list(_extrapolation_methods.keys()))
        ) from None


_detection_methods = dict()
_detection_methods["blob"] = blob_detection
_detection_methods["tstorm"] = tstorm_detection
_detection_methods["shitomasi"] = shitomasi_detection

def feature_get_method(name):
    """
    Return a callable function for feature detection.

    Implemented methods:

    +-----------------+-------------------------------------------------------+
    |     Name        |              Description                              |
    +=================+=======================================================+
    |  blob           | blob detection in scale space                         |
    +-----------------+-------------------------------------------------------+
    |  tstorm         | Thunderstorm cell detection                           |
    +-----------------+-------------------------------------------------------+
    |  shitomasi      | Shi-Tomasi corner detection                           |
    +-----------------+-------------------------------------------------------+
    """
    if isinstance(name, str):
        name = name.lower()
    else:
        raise TypeError(
            "Only strings supported for the method's names.\n"
            + "Available names:"
            + str(list(_detection_methods.keys()))
        ) from None

    try:
        return _detection_methods[name]
    except KeyError:
        raise ValueError(
            "Unknown detection method {}\n".format(name)
            + "The available methods are:"
            + str(list(_detection_methods.keys()))
        ) from None

def get_fft_method(name, **kwargs):
    kwargs = kwargs.copy()
    shape = kwargs["shape"]
    kwargs.pop("shape")

    if name == "numpy":
        return get_numpy(shape, **kwargs)
    elif name == "scipy":
        return get_scipy(shape, **kwargs)
    elif name == "pyfftw":
        return get_pyfftw(shape, **kwargs)
    else:
        raise ValueError(
            "Unknown method {}\n".format(name)
            + "The available methods are:"
            + str(["numpy", "pyfftw", "scipy"])
        ) from None

def compute_centred_coord_array(M, N):
    if M % 2 == 1:
        s1 = np.s_[-int(M / 2) : int(M / 2) + 1]
    else:
        s1 = np.s_[-int(M / 2) : int(M / 2)]

    if N % 2 == 1:
        s2 = np.s_[-int(N / 2) : int(N / 2) + 1]
    else:
        s2 = np.s_[-int(N / 2) : int(N / 2)]

    YC, XC = np.ogrid[s1, s2]

    return YC, XC

def rapsd(
    field, fft_method=None, return_freq=False, d=1.0, normalize=False, **fft_kwargs
):

    if len(field.shape) != 2:
        raise ValueError(
            f"{len(field.shape)} dimensions are found, but the number "
            "of dimensions should be 2"
        )

    if np.sum(np.isnan(field)) > 0:
        raise ValueError("input field should not contain nans")

    m, n = field.shape

    yc, xc = compute_centred_coord_array(m, n)
    r_grid = np.sqrt(xc * xc + yc * yc).round()
    l = max(field.shape[0], field.shape[1])

    if l % 2 == 1:
        r_range = np.arange(0, int(l / 2) + 1)
    else:
        r_range = np.arange(0, int(l / 2))

    if fft_method is not None:
        psd = fft_method.fftshift(fft_method.fft2(field, **fft_kwargs))
        psd = np.abs(psd) ** 2 / psd.size
    else:
        psd = field

    result = []
    for r in r_range:
        mask = r_grid == r
        psd_vals = psd[mask]
        result.append(np.mean(psd_vals))

    result = np.array(result)

    if normalize:
        result /= np.sum(result)

    if return_freq:
        freq = np.fft.fftfreq(l, d=d)
        freq = freq[r_range]
        return result, freq
    else:
        return result


def initialize_param_2d_fft_filter(field, **kwargs):   
    if len(field.shape) < 2 or len(field.shape) > 3:
        raise ValueError("the input is not two- or three-dimensional array")
    if np.any(~np.isfinite(field)):
        raise ValueError("field contains non-finite values")

    # defaults
    win_fun = kwargs.get("win_fun", None)
    model = kwargs.get("model", "power-law")
    weighted = kwargs.get("weighted", False)
    rm_rdisc = kwargs.get("rm_rdisc", False)
    fft = kwargs.get("fft_method", "numpy")
    if type(fft) == str:
        fft_shape = field.shape if len(field.shape) == 2 else field.shape[1:]
        fft = get_fft_method(fft, shape=fft_shape)

    field = field.copy()

    # remove rain/no-rain discontinuity
    if rm_rdisc:
        field[field > field.min()] -= field[field > field.min()].min() - field.min()

    # dims
    if len(field.shape) == 2:
        field = field[None, :, :]
    nr_fields = field.shape[0]
    M, N = field.shape[1:]

    if win_fun is not None:
        tapering = compute_window_function(M, N, win_fun)

        # make sure non-rainy pixels are set to zero
        field -= field.min(axis=(1, 2))[:, None, None]
    else:
        tapering = np.ones((M, N))

    if model.lower() == "power-law":

        # compute average 2D PSD
        F = np.zeros((M, N), dtype=complex)
        for i in range(nr_fields):
            F += fft.fftshift(fft.fft2(field[i, :, :] * tapering))
        F /= nr_fields
        F = abs(F) ** 2 / F.size

        # compute radially averaged 1D PSD
        psd = rapsd(F)
        L = max(M, N)

        # wavenumbers
        if L % 2 == 1:
            wn = np.arange(0, int(L / 2) + 1)
        else:
            wn = np.arange(0, int(L / 2))

        # compute single spectral slope beta as first guess
        if weighted:
            p0 = np.polyfit(np.log(wn[1:]), np.log(psd[1:]), 1, w=np.sqrt(psd[1:]))
        else:
            p0 = np.polyfit(np.log(wn[1:]), np.log(psd[1:]), 1)
        beta = p0[0]

        # create the piecewise function with two spectral slopes beta1 and beta2
        # and scaling break x0
        def piecewise_linear(x, x0, y0, beta1, beta2):
            return np.piecewise(
                x,
                [x < x0, x >= x0],
                [
                    lambda x: beta1 * x + y0 - beta1 * x0,
                    lambda x: beta2 * x + y0 - beta2 * x0,
                ],
            )

        # fit the two betas and the scaling break
        p0 = [2.0, 0, beta, beta]  # first guess
        bounds = (
            [2.0, 0, -4, -4],
            [5.0, 20, -1.0, -1.0],
        )  # TODO: provide better bounds
        if weighted:
            p, e = optimize.curve_fit(
                piecewise_linear,
                np.log(wn[1:]),
                np.log(psd[1:]),
                p0=p0,
                bounds=bounds,
                sigma=1 / np.sqrt(psd[1:]),
            )
        else:
            p, e = optimize.curve_fit(
                piecewise_linear, np.log(wn[1:]), np.log(psd[1:]), p0=p0, bounds=bounds
            )

        # compute 2d filter
        YC, XC = compute_centred_coord_array(M, N)
        R = np.sqrt(XC * XC + YC * YC)
        R = fft.fftshift(R)
        pf = p.copy()
        pf[2:] = pf[2:] / 2
        F = np.exp(piecewise_linear(np.log(R), *pf))
        F[~np.isfinite(F)] = 1

        f = piecewise_linear

    else:
        raise ValueError("unknown parametric model %s" % model)

    return {
        "field": F,
        "input_shape": field.shape[1:],
        "use_full_fft": True,
        "model": f,
        "pars": p,
    }

def _get_mask(Size, idxi, idxj, win_fun):
    """Compute a mask of zeros with a window at a given position."""

    idxi = np.array(idxi).astype(int)
    idxj = np.array(idxj).astype(int)

    win_size = (idxi[1] - idxi[0], idxj[1] - idxj[0])
    if win_fun is not None:
        wind = compute_window_function(win_size[0], win_size[1], win_fun)
        wind += 1e-6  # avoid zero values

    else:
        wind = np.ones(win_size)

    mask = np.zeros(Size)
    mask[idxi.item(0) : idxi.item(1), idxj.item(0) : idxj.item(1)] = wind

    return mask

def _split_field(idxi, idxj, Segments):
    """Split domain field into a number of equally sapced segments."""

    sizei = idxi[1] - idxi[0]
    sizej = idxj[1] - idxj[0]

    winsizei = int(sizei / Segments)
    winsizej = int(sizej / Segments)

    Idxi = np.zeros((Segments**2, 2))
    Idxj = np.zeros((Segments**2, 2))

    count = -1
    for i in range(Segments):
        for j in range(Segments):
            count += 1
            Idxi[count, 0] = idxi[0] + i * winsizei
            Idxi[count, 1] = np.min((Idxi[count, 0] + winsizei, idxi[1]))
            Idxj[count, 0] = idxj[0] + j * winsizej
            Idxj[count, 1] = np.min((Idxj[count, 0] + winsizej, idxj[1]))

    Idxi = np.array(Idxi).astype(int)
    Idxj = np.array(Idxj).astype(int)

    return Idxi, Idxj

def initialize_nonparam_2d_ssft_filter(field, **kwargs):   

    if len(field.shape) < 2 or len(field.shape) > 3:
        raise ValueError("the input is not two- or three-dimensional array")
    if np.any(np.isnan(field)):
        raise ValueError("field must not contain NaNs")

    # defaults
    win_size = kwargs.get("win_size", (128, 128))
    if type(win_size) == int:
        win_size = (win_size, win_size)
    win_fun = kwargs.get("win_fun", "tukey")
    overlap = kwargs.get("overlap", 0.3)
    war_thr = kwargs.get("war_thr", 0.1)
    rm_rdisc = kwargs.get("rm_disc", True)
    fft = kwargs.get("fft_method", "numpy")
    if type(fft) == str:
        fft_shape = field.shape if len(field.shape) == 2 else field.shape[1:]
        fft = get_fft_method(fft, shape=fft_shape)

    field = field.copy()

    # remove rain/no-rain discontinuity
    if rm_rdisc:
        field[field > field.min()] -= field[field > field.min()].min() - field.min()

    # dims
    if len(field.shape) == 2:
        field = field[None, :, :]
    nr_fields = field.shape[0]
    dim = field.shape[1:]
    dim_x = dim[1]
    dim_y = dim[0]

    # make sure non-rainy pixels are set to zero
    field -= field.min(axis=(1, 2))[:, None, None]

    # SSFT algorithm

    # prepare indices
    idxi = np.zeros(2, dtype=int)
    idxj = np.zeros(2, dtype=int)

    # number of windows
    num_windows_y = np.ceil(float(dim_y) / win_size[0]).astype(int)
    num_windows_x = np.ceil(float(dim_x) / win_size[1]).astype(int)

    # domain fourier filter
    F0 = initialize_nonparam_2d_fft_filter(
        field, win_fun=win_fun, donorm=True, use_full_fft=True, fft_method=fft
    )["field"]
    # and allocate it to the final grid
    F = np.zeros((num_windows_y, num_windows_x, F0.shape[0], F0.shape[1]))
    F += F0[np.newaxis, np.newaxis, :, :]

    # loop rows
    for i in range(F.shape[0]):
        # loop columns
        for j in range(F.shape[1]):

            # compute indices of local window
            idxi[0] = int(np.max((i * win_size[0] - overlap * win_size[0], 0)))
            idxi[1] = int(
                np.min((idxi[0] + win_size[0] + overlap * win_size[0], dim_y))
            )
            idxj[0] = int(np.max((j * win_size[1] - overlap * win_size[1], 0)))
            idxj[1] = int(
                np.min((idxj[0] + win_size[1] + overlap * win_size[1], dim_x))
            )

            # build localization mask
            # TODO: the 0.01 rain threshold must be improved
            mask = _get_mask(dim, idxi, idxj, win_fun)
            war = float(np.sum((field * mask[None, :, :]) > 0.01)) / (
                (idxi[1] - idxi[0]) * (idxj[1] - idxj[0]) * nr_fields
            )

            if war > war_thr:
                # the new filter
                F[i, j, :, :] = initialize_nonparam_2d_fft_filter(
                    field * mask[None, :, :],
                    win_fun=None,
                    donorm=True,
                    use_full_fft=True,
                    fft_method=fft,
                )["field"]

    return {"field": F, "input_shape": field.shape[1:], "use_full_fft": True}

def generate_noise_2d_ssft_filter(F, randstate=None, seed=None, **kwargs):
    input_shape = F["input_shape"]
    use_full_fft = F["use_full_fft"]
    F = F["field"]

    if len(F.shape) != 4:
        raise ValueError("the input is not four-dimensional array")
    if np.any(~np.isfinite(F)):
        raise ValueError("field contains non-finite values")

    if "domain" in kwargs.keys() and kwargs["domain"] == "spectral":
        raise NotImplementedError(
            "SSFT-based noise generator is not implemented in the spectral domain"
        )

    # defaults
    overlap = kwargs.get("overlap", 0.2)
    win_fun = kwargs.get("win_fun", "tukey")
    fft = kwargs.get("fft_method", "numpy")
    if type(fft) == str:
        fft = get_fft_method(fft, shape=input_shape)

    if randstate is None:
        randstate = np.random

    # set the seed
    if seed is not None:
        randstate.seed(seed)

    dim_y = F.shape[2]
    dim_x = F.shape[3]
    dim = (dim_y, dim_x)

    # produce fields of white noise
    N = randstate.randn(dim_y, dim_x)
    fN = fft.fft2(N)

    # initialize variables
    cN = np.zeros(dim)
    sM = np.zeros(dim)

    idxi = np.zeros(2, dtype=int)
    idxj = np.zeros(2, dtype=int)

    # get the window size
    win_size = (float(dim_y) / F.shape[0], float(dim_x) / F.shape[1])

    # loop the windows and build composite image of correlated noise

    # loop rows
    for i in range(F.shape[0]):
        # loop columns
        for j in range(F.shape[1]):

            # apply fourier filtering with local filter
            lF = F[i, j, :, :]
            flN = fN * lF
            flN = np.array(fft.ifft2(flN).real)

            # compute indices of local window
            idxi[0] = int(np.max((i * win_size[0] - overlap * win_size[0], 0)))
            idxi[1] = int(
                np.min((idxi[0] + win_size[0] + overlap * win_size[0], dim_y))
            )
            idxj[0] = int(np.max((j * win_size[1] - overlap * win_size[1], 0)))
            idxj[1] = int(
                np.min((idxj[0] + win_size[1] + overlap * win_size[1], dim_x))
            )

            # build mask and add local noise field to the composite image
            M = _get_mask(dim, idxi, idxj, win_fun)
            cN += flN * M
            sM += M

    # normalize the field
    cN[sM > 0] /= sM[sM > 0]
    cN = (cN - cN.mean()) / cN.std()

    return cN

def initialize_nonparam_2d_nested_filter(field, gridres=1.0, **kwargs):
    if len(field.shape) < 2 or len(field.shape) > 3:
        raise ValueError("the input is not two- or three-dimensional array")
    if np.any(np.isnan(field)):
        raise ValueError("field must not contain NaNs")

    # defaults
    max_level = kwargs.get("max_level", 3)
    win_fun = kwargs.get("win_fun", "tukey")
    war_thr = kwargs.get("war_thr", 0.1)
    rm_rdisc = kwargs.get("rm_disc", True)
    fft = kwargs.get("fft_method", "numpy")
    if type(fft) == str:
        fft_shape = field.shape if len(field.shape) == 2 else field.shape[1:]
        fft = get_fft_method(fft, shape=fft_shape)

    field = field.copy()

    # remove rain/no-rain discontinuity
    if rm_rdisc:
        field[field > field.min()] -= field[field > field.min()].min() - field.min()

    # dims
    if len(field.shape) == 2:
        field = field[None, :, :]
    nr_fields = field.shape[0]
    dim = field.shape[1:]
    dim_x = dim[1]
    dim_y = dim[0]

    # make sure non-rainy pixels are set to zero
    field -= field.min(axis=(1, 2))[:, None, None]

    # Nested algorithm

    # prepare indices
    Idxi = np.array([[0, dim_y]])
    Idxj = np.array([[0, dim_x]])
    Idxipsd = np.array([[0, 2**max_level]])
    Idxjpsd = np.array([[0, 2**max_level]])

    # generate the FFT sample frequencies
    freqx = fft.fftfreq(dim_x, gridres)
    freqy = fft.fftfreq(dim_y, gridres)
    fx, fy = np.meshgrid(freqx, freqy)
    freq_grid = np.sqrt(fx**2 + fy**2)

    # domain fourier filter
    F0 = initialize_nonparam_2d_fft_filter(
        field, win_fun=win_fun, donorm=True, use_full_fft=True, fft_method=fft
    )["field"]
    # and allocate it to the final grid
    F = np.zeros((2**max_level, 2**max_level, F0.shape[0], F0.shape[1]))
    F += F0[np.newaxis, np.newaxis, :, :]

    # now loop levels and build composite spectra
    level = 0
    while level < max_level:

        for m in range(len(Idxi)):

            # the indices of rainfall field
            Idxinext, Idxjnext = _split_field(Idxi[m, :], Idxj[m, :], 2)
            # the indices of the field of fourier filters
            Idxipsdnext, Idxjpsdnext = _split_field(Idxipsd[m, :], Idxjpsd[m, :], 2)

            for n in range(len(Idxinext)):

                mask = _get_mask(dim, Idxinext[n, :], Idxjnext[n, :], win_fun)
                war = np.sum((field * mask[None, :, :]) > 0.01) / float(
                    (Idxinext[n, 1] - Idxinext[n, 0])
                    * (Idxjnext[n, 1] - Idxjnext[n, 0])
                    * nr_fields
                )

                if war > war_thr:
                    # the new filter
                    newfilter = initialize_nonparam_2d_fft_filter(
                        field * mask[None, :, :],
                        win_fun=None,
                        donorm=True,
                        use_full_fft=True,
                        fft_method=fft,
                    )["field"]

                    # compute logistic function to define weights as function of frequency
                    # k controls the shape of the weighting function
                    # TODO: optimize parameters
                    k = 0.05
                    x0 = (
                        Idxinext[n, 1] - Idxinext[n, 0]
                    ) / 2.0  # TODO: consider y dimension, too
                    merge_weights = 1 / (
                        1 + np.exp(-k * (1 / freq_grid - x0 * gridres))
                    )
                    newfilter *= 1 - merge_weights

                    # perform the weighted average of previous and new fourier filters
                    F[
                        Idxipsdnext[n, 0] : Idxipsdnext[n, 1],
                        Idxjpsdnext[n, 0] : Idxjpsdnext[n, 1],
                        :,
                        :,
                    ] *= merge_weights[np.newaxis, np.newaxis, :, :]
                    F[
                        Idxipsdnext[n, 0] : Idxipsdnext[n, 1],
                        Idxjpsdnext[n, 0] : Idxjpsdnext[n, 1],
                        :,
                        :,
                    ] += newfilter[np.newaxis, np.newaxis, :, :]

        # update indices
        level += 1
        Idxi, Idxj = _split_field((0, dim[0]), (0, dim[1]), 2**level)
        Idxipsd, Idxjpsd = _split_field(
            (0, 2**max_level), (0, 2**max_level), 2**level
        )

    return {"field": F, "input_shape": field.shape[1:], "use_full_fft": True}
       
_noise_methods = dict()
_noise_methods["parametric"] = (
    initialize_param_2d_fft_filter,
    generate_noise_2d_fft_filter,
)

_noise_methods["nonparametric"] = (
    initialize_nonparam_2d_fft_filter,
    generate_noise_2d_fft_filter,
)
_noise_methods["ssft"] = (
    initialize_nonparam_2d_ssft_filter,
    generate_noise_2d_ssft_filter,
)

_noise_methods["nested"] = (
    initialize_nonparam_2d_nested_filter,
    generate_noise_2d_ssft_filter,
)

_noise_methods["bps"] = (initialize_bps, generate_bps)


def noise_get_method(name):
    """
    Return two callable functions to initialize and generate 2d perturbations
    of precipitation or velocity fields.\n

    Methods for precipitation fields:

    +-------------------+------------------------------------------------------+
    |     Name          |              Description                             |
    +===================+======================================================+
    |  parametric       | this global generator uses parametric Fourier        |
    |                   | filtering (power-law model)                          |
    +-------------------+------------------------------------------------------+
    |  nonparametric    | this global generator uses nonparametric Fourier     |
    |                   | filtering                                            |
    +-------------------+------------------------------------------------------+
    |  ssft             | this local generator uses the short-space Fourier    |
    |                   | filtering                                            |
    +-------------------+------------------------------------------------------+
    |  nested           | this local generator uses a nested Fourier filtering |
    +-------------------+------------------------------------------------------+

    Methods for velocity fields:

    +-------------------+------------------------------------------------------+
    |     Name          |              Description                             |
    +===================+======================================================+
    |  bps              | The method described in :cite:`BPS2006`, where       |
    |                   | time-dependent velocity perturbations are sampled    |
    |                   | from the exponential distribution                    |
    +-------------------+------------------------------------------------------+

    """
    if isinstance(name, str):
        name = name.lower()
    else:
        raise TypeError(
            "Only strings supported for the method's names.\n"
            + "Available names:"
            + str(list(_noise_methods.keys()))
        ) from None

    try:
        return _noise_methods[name]
    except KeyError:
        raise ValueError(
            "Unknown method {}\n".format(name)
            + "The available methods are:"
            + str(list(_noise_methods.keys()))
        ) from None

def dB_transform(R, metadata=None, threshold=None, zerovalue=None, inverse=False):

    R = R.copy()

    if metadata is None:
        if inverse:
            metadata = {"transform": "dB"}
        else:
            metadata = {"transform": None}

    else:
        metadata = metadata.copy()

    # to dB units
    if not inverse:

        if metadata["transform"] == "dB":
            return R, metadata

        if threshold is None:
            threshold = metadata.get("threshold", 0.1)

        zeros = R < threshold

        # Convert to dB
        R[~zeros] = 10.0 * np.log10(R[~zeros])
        threshold = 10.0 * np.log10(threshold)

        # Set value for zeros
        if zerovalue is None:
            zerovalue = threshold - 5  # TODO: set to a more meaningful value
        R[zeros] = zerovalue

        metadata["transform"] = "dB"
        metadata["zerovalue"] = zerovalue
        metadata["threshold"] = threshold

        return R, metadata

def memoize(maxsize=10):
    """
    Add a Least Recently Used (LRU) cache to any function.
    Caching is purely based on the optional keyword argument 'hkey', which needs
    to be a hashable.

    Parameters
    ----------
    maxsize: int, optional
        The maximum number of elements stored in the LRU cache.
    """

    def _memoize(func):
        cache = dict()
        hkeys = []

        @wraps(func)
        def _func_with_cache(*args, **kwargs):
            hkey = kwargs.pop("hkey", None)
            if hkey in cache:
                return cache[hkey]
            result = func(*args, **kwargs)
            if hkey is not None:
                cache[hkey] = result
                hkeys.append(hkey)
                if len(hkeys) > maxsize:
                    cache.pop(hkeys.pop(0))

            return result

        return _func_with_cache

    return _memoize

def _add_extra_kwrds_to_docstrings(target_func, extra_kwargs_doc_text):
    """
    Update the functions docstrings by replacing the `{extra_kwargs_doc}` occurences in
    the docstring by the `extra_kwargs_doc_text` value.
    """
    # Clean up indentation from docstrings for the
    # docstrings to be merged correctly.
    extra_kwargs_doc = inspect.cleandoc(extra_kwargs_doc_text)
    target_func.__doc__ = inspect.cleandoc(target_func.__doc__)

    # Add extra kwargs docstrings
    target_func.__doc__ = target_func.__doc__.format_map(
        defaultdict(str, extra_kwargs_doc=extra_kwargs_doc)
    )
    return target_func

def prepare_interpolator(nchunks=4):
    """
    Check that all the inputs have the correct shape, and that all values are
    finite. It also split the destination grid in  `nchunks` parts, and process each
    part independently.
    """

    def _preamble_interpolation(interpolator):
        @wraps(interpolator)
        def _interpolator_with_preamble(xy_coord, values, xgrid, ygrid, **kwargs):
            nonlocal nchunks  # https://stackoverflow.com/questions/5630409/

            values = values.copy()
            xy_coord = xy_coord.copy()

            input_ndims = values.ndim
            input_nvars = 1 if input_ndims == 1 else values.shape[1]
            input_nsamples = values.shape[0]

            coord_ndims = xy_coord.ndim
            coord_nsamples = xy_coord.shape[0]

            grid_shape = (ygrid.size, xgrid.size)

            if np.any(~np.isfinite(values)):
                raise ValueError("argument 'values' contains non-finite values")
            if np.any(~np.isfinite(xy_coord)):
                raise ValueError("argument 'xy_coord' contains non-finite values")

            if input_ndims > 2:
                raise ValueError(
                    "argument 'values' must have 1 (n) or 2 dimensions (n, m), "
                    f"but it has {input_ndims}"
                )
            if not coord_ndims == 2:
                raise ValueError(
                    "argument 'xy_coord' must have 2 dimensions (n, 2), "
                    f"but it has {coord_ndims}"
                )

            if not input_nsamples == coord_nsamples:
                raise ValueError(
                    "the number of samples in argument 'values' does not match the "
                    f"number of coordinates {input_nsamples}!={coord_nsamples}"
                )

            # only one sample, return uniform output
            if input_nsamples == 1:
                output_array = np.ones((input_nvars,) + grid_shape)
                for n, v in enumerate(values[0, ...]):
                    output_array[n, ...] *= v
                return output_array.squeeze()

            # all equal elements, return uniform output
            if values.max() == values.min():
                return np.ones((input_nvars,) + grid_shape) * values.ravel()[0]

            # split grid in n chunks
            nchunks = int(kwargs.get("nchunks", nchunks) ** 0.5)
            if nchunks > 1:
                subxgrids = np.array_split(xgrid, nchunks)
                subxgrids = [x for x in subxgrids if x.size > 0]
                subygrids = np.array_split(ygrid, nchunks)
                subygrids = [y for y in subygrids if y.size > 0]

                # generate a unique identifier to be used for caching
                # intermediate results
                kwargs["hkey"] = uuid.uuid1().int
            else:
                subxgrids = [xgrid]
                subygrids = [ygrid]

            interpolated = np.zeros((input_nvars,) + grid_shape)
            indx = 0
            for subxgrid in subxgrids:
                deltax = subxgrid.size
                indy = 0
                for subygrid in subygrids:
                    deltay = subygrid.size
                    interpolated[
                        :, indy : (indy + deltay), indx : (indx + deltax)
                    ] = interpolator(xy_coord, values, subxgrid, subygrid, **kwargs)
                    indy += deltay
                indx += deltax

            return interpolated.squeeze()

        extra_kwargs_doc = """
            nchunks: int, optional
                Split and process the destination grid in nchunks.
                Useful for large grids to limit the memory footprint.
            """

        _add_extra_kwrds_to_docstrings(_interpolator_with_preamble, extra_kwargs_doc)

        return _interpolator_with_preamble

    return _preamble_interpolation

class MissingOptionalDependency(Exception):
    """Raised when an optional dependency is needed but not found."""

    pass



#用于对meb list中的griddata按时间排序的函数
def sort_meb_griddata_list_along_time(meb_griddata_list):

    result = sorted(meb_griddata_list, key=_get_time)

    return result

def _get_time(grd_data):

    t=pd.to_datetime(grd_data.time).to_pydatetime()[0]

    return t

#用于对meb griddata list时间间隔是否一致的检查
def check_meb_griddata_time_interval(grid_list):
    delta_t_array=[]
    for i in range(len(grid_list)):
        if i == 0 :
            continue
        else:
            dt=grid_list[i].time.squeeze()-grid_list[i-1].time.squeeze()
            delta_t_array.append(dt.values)
    if len(delta_t_array) == 0:
        return True
    delta_t_array=np.array(delta_t_array).squeeze()
    # 仅两帧时 squeeze 成 0 维标量，视为间隔一致
    if np.ndim(delta_t_array) == 0:
        return True
    ref = delta_t_array[0]
    try:
        atol = ref * 0.05
    except TypeError:
        # numpy timedelta64 等
        atol = np.abs(ref) * 0.05
    result=np.allclose(delta_t_array, ref, atol=atol)

    return result


def _split_numeric_alpha(s):
    
    match = re.match(r"(\d+)([a-zA-Z]+)", s)
    
    if match:
        numeric_part = int(match.group(1))
        alpha_part = match.group(2)
        return numeric_part, alpha_part
    else:
        raise ValueError("String does not match the expected format.")
        
        
def get_timedelta_interval(dt_units):
    numeric_part, alpha_part = _split_numeric_alpha(dt_units)
    units_mapping={'min':'minute',
                   'mins':'minute',
                   'minutes':'minute',
                   'minute':'minute',
                   
                   'h':'hour',
                   'hour':'hour',
                   'hours':'hour',
                   
                   'd':'day',
                   'day':'day',
                   'days':'day',
                   }
    try:
        units=units_mapping[alpha_part]
    except:
        raise ValueError("time units should be in [min,mins,minute,minutes h,hour,hours d,day,days ")   
    if units=='minute':
        result=timedelta(minutes=numeric_part)
    elif units=='hour':
        result=timedelta(hours=numeric_part)
    elif units=='day':
        result=timedelta(days=numeric_part)
    return result


def get_dt_units(dt_units):
    
    numeric_part, alpha_part = _split_numeric_alpha(dt_units)
    
    units_mapping={'min':'minute',
                   'mins':'minute',
                   'minutes':'minute',
                   'minute':'minute',
                   
                   'h':'hour',
                   'hour':'hour',
                   'hours':'hour',
                   
                   'd':'day',
                   'day':'day',
                   'days':'day',
                   }
    try:
        units=units_mapping[alpha_part]
    except:
        raise ValueError("time units should be in [min,mins,minute,minutes h,hour,hours d,day,days]")
    
    return units


