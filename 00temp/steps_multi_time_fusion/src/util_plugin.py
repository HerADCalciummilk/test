# -*- coding: utf-8 -*-
"""STEPS 算法步骤。文件路径与 ini 读写仍留在 utils 与各命令入口。"""
from __future__ import annotations

from pathlib import Path

import numpy as np


class AR2NoiseGenerator:
    """Generate cascade-level AR(2) stochastic noise fields."""

    def __init__(self, filter_path: str | Path, phi1: float, phi2: float, n_levels: int):
        self.filters = np.load(filter_path)
        self.m_size, self.n_size = self.filters.shape[1:]
        self.phi1 = phi1
        self.phi2 = phi2
        self.n_levels = n_levels
        self.state_prev = np.zeros((n_levels, self.m_size, self.n_size))
        self.state = np.zeros((n_levels, self.m_size, self.n_size))

    def generate_one_step(self) -> np.ndarray:
        """Generate one AR(2) noise step with shape ``(n_levels, y, x)``."""
        noise_levels = []
        for level in range(self.n_levels):
            white = np.random.normal(0, 1, (self.m_size, self.n_size))
            fft_white = np.fft.fft2(white)
            fft_noise = fft_white * self.filters[level]
            noise = np.fft.ifft2(fft_noise).real
            noise = np.clip(noise, -15, None)
            new_state = self.phi1 * self.state[level] + self.phi2 * self.state_prev[level] + noise
            self.state_prev[level] = self.state[level].copy()
            self.state[level] = new_state.copy()
            noise_levels.append(new_state)
        return np.stack(noise_levels, axis=0)


def noise_to_db(precip: np.ndarray) -> np.ndarray:
    """Convert precipitation to dB units with a 0.1 mm/h floor."""
    precip = np.where(precip < 0.1, 0.1, precip)
    db_values = 10 * np.log10(precip)
    db_values[~np.isfinite(db_values)] = -15.0
    return db_values


def decompose_cascade(field_db: np.ndarray, n_levels: int) -> list[np.ndarray]:
    """Decompose a dB precipitation field into simple FFT cascade levels."""
    cascades = []
    fft_field = np.fft.fft2(field_db)
    m_size, n_size = field_db.shape
    for level in range(n_levels):
        sigma = 2 ** (level + 1)
        fy, fx = np.ogrid[-m_size // 2 : m_size // 2, -n_size // 2 : n_size // 2]
        freq2 = (fx**2 + fy**2) / (sigma**2)
        kernel = np.exp(-freq2 / 2)
        cascades.append(np.fft.ifft2(fft_field * kernel).real)
    return cascades


def train_noise_filter(
    fields_db_list: list[np.ndarray],
    *,
    output_dir: str | Path,
    issue_time: str,
    n_levels: int,
) -> Path | None:
    """Train non-parametric filters from historical dB precipitation fields."""
    if not fields_db_list:
        print("没有有效历史数据，无法训练滤波器。")
        return None

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    total_frames = len(fields_db_list)
    m_size, n_size = fields_db_list[0].shape
    psd_sum = [np.zeros((m_size, n_size)) for _ in range(n_levels)]

    print(f"共收到 {total_frames} 帧历史数据，开始计算非参数滤波器。")
    for field_db in fields_db_list:
        for level, cascade in enumerate(decompose_cascade(field_db, n_levels)):
            fft_cascade = np.fft.fft2(cascade)
            psd_sum[level] += np.fft.fftshift(np.abs(fft_cascade) ** 2 / (m_size * n_size))

    filter_array = np.zeros((n_levels, m_size, n_size))
    y_grid, x_grid = np.ogrid[-m_size // 2 : m_size // 2, -n_size // 2 : n_size // 2]
    freq = np.sqrt(x_grid**2 + y_grid**2)
    freq[freq == 0] = 1e-8

    for level in range(n_levels):
        mean_psd = np.fft.ifftshift(psd_sum[level] / total_frames)
        filter_array[level] = np.sqrt(mean_psd) / (freq ** (-1.0) + 1e-8)

    filter_path = output_dir / f"nonparam_filters_{issue_time}.npy"
    np.save(filter_path, filter_array)
    print(f"非参数滤波器已保存：{filter_path}，形状 {filter_array.shape}")
    return filter_path


def generate_ar2_noise(
    *,
    filter_path: str | Path,
    output_dir: str | Path,
    issue_time: str,
    phi1: float,
    phi2: float,
    n_levels: int,
    n_ens_members: int,
    timesteps: int,
) -> Path:
    """Generate AR(2) noise members using a trained filter file."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    generator = AR2NoiseGenerator(filter_path, phi1, phi2, n_levels)
    noise_array = np.zeros((n_ens_members, timesteps, n_levels, generator.m_size, generator.n_size))

    for member in range(n_ens_members):
        print(f"生成噪声成员 {member + 1}/{n_ens_members}")
        generator.state_prev = np.zeros((n_levels, generator.m_size, generator.n_size))
        generator.state = np.zeros((n_levels, generator.m_size, generator.n_size))
        for step in range(timesteps):
            noise_array[member, step] = generator.generate_one_step()

    noise_path = output_dir / f"ar_noise_{issue_time}.npy"
    np.save(noise_path, noise_array)
    print(f"AR(2) 噪声场已保存：{noise_path}，形状 {noise_array.shape}")
    return noise_path


# 级联融合：dB 变换、高斯带通与按时效加权。
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

import numpy as np
from scipy.ndimage import gaussian_filter
from scipy.stats import spearmanr


# 由逐日级联相关汇总气候态技能。
def decompose_to_cascades(field: np.ndarray, n_levels: int) -> list[np.ndarray]:
    """Decompose one field into low-pass cascade levels plus residual."""
    cascades = []
    current = field.copy().astype(float)
    for level in range(n_levels):
        sigma = 2 ** (level + 1) / 2.0
        lowpass = gaussian_filter(current, sigma=sigma, mode="constant", cval=0.0)
        cascades.append(lowpass)
        current = current - lowpass
    cascades.append(current)
    return cascades


def compute_cascade_skill(
    nowcast_raw: np.ndarray,
    obs: np.ndarray,
    n_cascade_levels: int,
    use_spearman: bool,
) -> tuple[np.ndarray, np.ndarray]:
    """Calculate skill and raw correlation for one lead time."""
    skill = np.full(n_cascade_levels, np.nan)
    raw_corr = np.full(n_cascade_levels, np.nan)
    valid = np.isfinite(obs) & np.isfinite(nowcast_raw) & ((obs > 0.001) | (nowcast_raw > 0.001))
    if not np.any(valid):
        return skill, raw_corr

    nowcast_casc = decompose_to_cascades(nowcast_raw, n_levels=n_cascade_levels)
    obs_casc = decompose_to_cascades(obs, n_levels=n_cascade_levels)

    for level in range(n_cascade_levels):
        n_flat = nowcast_casc[level][valid].ravel()
        o_flat = obs_casc[level][valid].ravel()
        if len(n_flat) < 2 or np.std(n_flat) < 1e-8 or np.std(o_flat) < 1e-8:
            corr = 1.0 if np.allclose(n_flat, o_flat) else 0.0
        elif use_spearman:
            corr, _ = spearmanr(n_flat, o_flat)
        else:
            corr = np.corrcoef(n_flat, o_flat)[0, 1]
        raw_corr[level] = corr
        skill[level] = max(corr, 0.0)
    return skill, raw_corr


def compute_daily_skill(
    nowcast_stack: np.ndarray,
    obs: np.ndarray,
    n_cascade_levels: int,
    use_spearman: bool,
) -> tuple[np.ndarray, np.ndarray]:
    """Calculate skill matrices for all lead times in one day."""
    n_leads = nowcast_stack.shape[0]
    skill_matrix = np.full((n_leads, n_cascade_levels), np.nan)
    raw_corr_matrix = np.full((n_leads, n_cascade_levels), np.nan)
    for index in range(n_leads):
        if index == 0:
            skill_matrix[index, :] = 1.0
            raw_corr_matrix[index, :] = 1.0
            continue
        skill_vec, corr_vec = compute_cascade_skill(
            nowcast_stack[index].copy(),
            obs,
            n_cascade_levels,
            use_spearman,
        )
        skill_matrix[index] = skill_vec
        raw_corr_matrix[index] = corr_vec
    return skill_matrix, raw_corr_matrix


def calc_climatological_skill(daily_skills_list: list[np.ndarray]) -> np.ndarray:
    """Calculate climatological skill by geometric mean."""
    if not daily_skills_list:
        return np.zeros((0, 0))
    daily_skills = np.array(daily_skills_list)
    clim_skill = np.exp(np.nanmean(np.log(np.maximum(daily_skills, 1e-10)), axis=0))
    return np.nan_to_num(clim_skill, nan=0.0)
