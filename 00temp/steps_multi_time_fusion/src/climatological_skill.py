"""Climatological skill calculation for STEPS cascade levels."""

from __future__ import annotations

import numpy as np
from scipy.ndimage import gaussian_filter
from scipy.stats import spearmanr


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
