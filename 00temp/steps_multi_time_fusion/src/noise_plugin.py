"""Plugin wrapper for STEPS noise training and generation."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from steps_multi_time_fusion.src.noise import generate_ar2_noise, to_db, train_noise_filter


class StepsNoisePlugin:
    """Train non-parametric noise filters and generate AR(2) noise fields."""

    def __init__(
        self,
        output_dir: str | Path,
        issue_time: str,
        n_levels: int = 6,
        phi1: float = 0.9,
        phi2: float = -0.15,
        n_ens_members: int = 5,
        timesteps: int = 18,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.issue_time = issue_time
        self.n_levels = n_levels
        self.phi1 = phi1
        self.phi2 = phi2
        self.n_ens_members = n_ens_members
        self.timesteps = timesteps

    def train(self, fields: list[np.ndarray], already_db: bool = False) -> Path | None:
        """Train filters from precipitation fields or already converted dB fields."""
        fields_db = fields if already_db else [to_db(field) for field in fields]
        return train_noise_filter(
            fields_db,
            output_dir=self.output_dir,
            issue_time=self.issue_time,
            n_levels=self.n_levels,
        )

    def generate(self, filter_path: str | Path | None = None) -> Path:
        """Generate AR(2) noise using an existing filter file."""
        if filter_path is None:
            filter_path = self.output_dir / f"nonparam_filters_{self.issue_time}.npy"
        return generate_ar2_noise(
            filter_path=filter_path,
            output_dir=self.output_dir,
            issue_time=self.issue_time,
            phi1=self.phi1,
            phi2=self.phi2,
            n_levels=self.n_levels,
            n_ens_members=self.n_ens_members,
            timesteps=self.timesteps,
        )

    def process(self, mode: str, fields: list[np.ndarray] | None = None, already_db: bool = False) -> Path | None:
        """Run ``train`` or ``generate`` mode."""
        if mode == "train":
            if fields is None:
                raise ValueError("train mode requires fields")
            return self.train(fields, already_db=already_db)
        if mode == "generate":
            return self.generate()
        raise ValueError("mode must be 'train' or 'generate'")
