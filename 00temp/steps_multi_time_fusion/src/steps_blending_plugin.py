"""Plugin wrapper for STEPS cascade blending."""

from __future__ import annotations

import numpy as np

from steps_multi_time_fusion.src.steps_blending import blend_with_cascade, filter_gaussian


class StepsBlendingPlugin:
    """Blend nowcast and NWP precipitation fields using STEPS cascade weights."""

    def __init__(
        self,
        n_cascade_levels: int = 8,
        tau_min: float = 90.0,
        use_climatological_skill: bool = False,
        climatological_skill_path: str | None = None,
    ) -> None:
        self.n_cascade_levels = n_cascade_levels
        self.tau_min = tau_min
        self.use_climatological_skill = use_climatological_skill
        self.climatological_skill_path = climatological_skill_path

    def process(
        self,
        nowcast: np.ndarray,
        nwp: np.ndarray,
        lead_index: int,
        noise: np.ndarray | None = None,
    ) -> np.ndarray:
        """Blend one lead frame."""
        nowcast = np.asarray(nowcast, dtype=np.float64)
        nwp = np.asarray(nwp, dtype=np.float64)
        if nowcast.shape != nwp.shape:
            raise ValueError(f"nowcast shape {nowcast.shape} must equal nwp shape {nwp.shape}")
        target_shape = nowcast.shape
        if noise is None:
            noise = np.zeros(target_shape, dtype=np.float64)
        bp_filter = filter_gaussian(target_shape, self.n_cascade_levels)
        return blend_with_cascade(
            nowcast,
            nwp,
            bp_filter,
            lead_index=lead_index,
            noise_np=noise,
            target_shape=target_shape,
            n_cascade_levels=self.n_cascade_levels,
            use_climatological_skill=self.use_climatological_skill,
            climatological_skill_path=self.climatological_skill_path,
            tau_min=self.tau_min,
        )
