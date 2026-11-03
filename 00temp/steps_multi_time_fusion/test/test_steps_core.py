"""Core tests for steps_multi_time_fusion."""

from __future__ import annotations

import numpy as np

from steps_multi_time_fusion.src.climatological_skill_plugin import ClimatologicalSkillPlugin
from steps_multi_time_fusion.src.noise_plugin import StepsNoisePlugin
from steps_multi_time_fusion.src.steps_blending_plugin import StepsBlendingPlugin


def test_climatological_skill_plugin() -> None:
    nowcast = np.ones((3, 8, 8), dtype=np.float32)
    obs = np.ones((8, 8), dtype=np.float32)
    plugin = ClimatologicalSkillPlugin(n_cascade_levels=3)
    skill, raw = plugin.process(nowcast, obs)
    clim = plugin.climatological_skill([skill])
    assert skill.shape == (3, 3)
    assert raw.shape == (3, 3)
    assert clim.shape == (3, 3)
    assert np.isfinite(clim).all()


def test_steps_blending_plugin() -> None:
    nowcast = np.ones((16, 16), dtype=np.float64) * 2.0
    nwp = np.ones((16, 16), dtype=np.float64)
    plugin = StepsBlendingPlugin(n_cascade_levels=4)
    result = plugin.process(nowcast, nwp, lead_index=1)
    assert result.shape == nowcast.shape
    assert np.isfinite(result).all()
    assert result.min() >= 0.0


def test_noise_plugin_train_and_generate(tmp_path) -> None:
    fields = [np.ones((8, 8), dtype=np.float32) * value for value in (1.0, 2.0, 3.0)]
    plugin = StepsNoisePlugin(
        output_dir=tmp_path,
        issue_time="202601010000",
        n_levels=3,
        n_ens_members=2,
        timesteps=2,
    )
    filter_path = plugin.train(fields)
    assert filter_path is not None
    noise_path = plugin.generate(filter_path)
    assert np.load(filter_path).shape == (3, 8, 8)
    assert np.load(noise_path).shape == (2, 2, 3, 8, 8)
