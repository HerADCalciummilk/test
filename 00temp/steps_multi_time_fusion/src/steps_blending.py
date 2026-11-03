"""STEPS cascade blending core functions."""

from __future__ import annotations

import os

import numpy as np


def to_db(precip, threshold: float = 0.1):
    """Convert precipitation to dB."""
    precip = np.copy(precip)
    precip[precip < threshold] = threshold
    return 10 * np.log10(precip)


def from_db(db_values):
    """Convert dB precipitation back to linear units."""
    return 10 ** (db_values / 10)


def filter_gaussian(shape, n: int = 8):
    """Create Gaussian band-pass filters used by STEPS cascade decomposition."""
    height, width = shape
    max_length = max(width, height)
    rx = np.s_[: int(width / 2) + 1]
    ry = np.s_[-int(height / 2) : int(height / 2) + 1] if height % 2 == 1 else np.s_[-int(height / 2) : int(height / 2)]
    y_grid, x_grid = np.ogrid[ry, rx]
    dy = int(height / 2) if height % 2 == 0 else int(height / 2) + 1
    r_2d = np.roll(np.sqrt(x_grid**2 + y_grid**2), dy, axis=0)
    r_max = int(max_length / 2) + 1
    r_1d = np.arange(r_max)
    q_value = (0.5 * max_length) ** (1.0 / n)

    def log_e(values):
        values = np.asarray(values)
        result = np.zeros_like(values, dtype=float)
        positive = values > 0
        result[positive] = np.log(values[positive]) / np.log(q_value)
        return result

    class GaussFunc:
        def __init__(self, center, sigma):
            self.center = center
            self.sigma = sigma

        def __call__(self, values):
            return np.exp(-((log_e(values) - self.center) ** 2) / (2 * self.sigma**2))

    radii = [0.5 * (q_value ** (level - 1) + q_value**level) for level in range(1, n + 1)]
    weight_funcs = [GaussFunc(log_e(radius), 0.5) for radius in radii]
    weights_2d = np.array([func(r_2d) for func in weight_funcs])
    weights_2d /= np.sum(weights_2d, axis=0, keepdims=True)
    weights_2d[0, 0, 0] = 1.0
    return {"weights_2d": weights_2d, "shape": (height, width)}


def decomposition_fft(field, bp_filter, normalize: bool = True):
    """Decompose a field into FFT cascade levels."""
    field_fft = np.fft.rfft2(field)
    field_decomp = []
    means = []
    stds = []
    for level in range(bp_filter["weights_2d"].shape[0]):
        spatial = np.fft.irfft2(field_fft * bp_filter["weights_2d"][level], s=field.shape)
        mean_value = np.mean(spatial)
        std_value = np.std(spatial) + 1e-8
        means.append(mean_value)
        stds.append(std_value)
        if normalize:
            spatial = (spatial - mean_value) / std_value
        field_decomp.append(spatial)
    return {"cascade_levels": np.stack(field_decomp), "means": np.array(means), "stds": np.array(stds)}


def blend_with_cascade(
    nowcast_np,
    nwp_np,
    bp_filter,
    lead_index: int,
    noise_np,
    target_shape,
    n_cascade_levels: int,
    use_climatological_skill: bool = False,
    climatological_skill_path: str | None = None,
    tau_min: float = 90.0,
):
    """Blend nowcast, NWP and optional stochastic noise by cascade level."""
    lead_time_min = lead_index * 10
    if use_climatological_skill and climatological_skill_path and os.path.exists(climatological_skill_path):
        try:
            skill_arr = np.load(climatological_skill_path)
            skill = np.maximum(skill_arr[min(lead_index, skill_arr.shape[0] - 1), :], 0.15)
        except Exception:
            skill = np.full(n_cascade_levels, np.exp(-lead_time_min / tau_min))
    else:
        skill = np.full(n_cascade_levels, np.exp(-lead_time_min / tau_min))

    w_nowcast = skill
    w_nwp = 1.0 - skill
    w_noise = np.sqrt(np.maximum(0.0, 1.0 - skill**2))
    nowcast_db = to_db(nowcast_np)
    nwp_db = to_db(nwp_np)
    nowcast_casc = decomposition_fft(nowcast_db, bp_filter)
    nwp_casc = decomposition_fft(nwp_db, bp_filter)
    precip_mask = ((nowcast_np > 0.1) | (nwp_np > 0.1)).astype(float)
    blended_db = np.zeros_like(nowcast_casc["cascade_levels"][0])

    for level in range(n_cascade_levels):
        noise = np.copy(noise_np) if noise_np is not None else np.zeros(target_shape)
        noise *= 0.25**level
        noise *= precip_mask
        blended_level = (
            w_nowcast[level] * nowcast_casc["cascade_levels"][level]
            + w_nwp[level] * nwp_casc["cascade_levels"][level]
            + w_noise[level] * noise
        )
        blended_mean = w_nowcast[level] * nowcast_casc["means"][level] + w_nwp[level] * nwp_casc["means"][level]
        blended_std = w_nowcast[level] * nowcast_casc["stds"][level] + w_nwp[level] * nwp_casc["stds"][level]
        blended_db += blended_level * blended_std + blended_mean

    blended_np = from_db(np.clip(blended_db, -15.0, 35.0))
    blended_np[blended_np < 0.05] = 0.0
    blended_np = np.where(precip_mask > 0, blended_np, 0.0)
    return np.clip(blended_np, 0.0, 50.0)
