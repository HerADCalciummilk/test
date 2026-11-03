"""Plugin wrapper for climatological skill calculation."""

from __future__ import annotations

import numpy as np

from steps_multi_time_fusion.src.climatological_skill import calc_climatological_skill, compute_daily_skill


class ClimatologicalSkillPlugin:
    """Calculate daily and climatological cascade skill matrices."""

    def __init__(self, n_cascade_levels: int = 8, use_spearman: bool = False) -> None:
        self.n_cascade_levels = n_cascade_levels
        self.use_spearman = use_spearman

    def process(self, nowcast_stack: np.ndarray, obs: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Calculate one day's skill and raw correlation matrices."""
        return compute_daily_skill(
            nowcast_stack=nowcast_stack,
            obs=obs,
            n_cascade_levels=self.n_cascade_levels,
            use_spearman=self.use_spearman,
        )

    @staticmethod
    def climatological_skill(daily_skills: list[np.ndarray]) -> np.ndarray:
        """Aggregate daily skills into a climatological skill matrix."""
        return calc_climatological_skill(daily_skills)
