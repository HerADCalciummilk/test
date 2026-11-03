# -*- coding: utf-8 -*-
"""ini 补齐与 CLI 缺省参数。"""
from __future__ import annotations

import pytest

from steps_multi_time_fusion.cli import parse_args
from steps_multi_time_fusion.utils.util_env import (
    clear_ini_cache,
    resolve_blending,
    resolve_climatological_skill,
    resolve_module,
    resolve_noise,
)


def setup_module() -> None:
    clear_ini_cache()


def test_noise_requires_issue_time_and_keeps_preset() -> None:
    with pytest.raises(ValueError, match="issue_time"):
        resolve_noise()
    got = resolve_noise(issue_time="202508191600", n_levels=4)
    assert got["mode"] == "generate"
    assert got["issue_time"] == "202508191600"
    assert got["n_levels"] == 4
    assert got["phi1"] == 0.9
    assert got["phi2"] == -0.15
    assert got["n_ens_members"] == 5
    assert got["timesteps"] == 18
    assert got["output_dir"].endswith("noise")


def test_skill_and_blending_required_paths() -> None:
    with pytest.raises(ValueError, match="input_dir"):
        resolve_climatological_skill()
    skill = resolve_climatological_skill(input_dir="daily")
    assert skill["input_dir"] == "daily"
    assert skill["output"].endswith("climatological_skill.npy")

    with pytest.raises(ValueError, match="nowcast"):
        resolve_blending()
    blended = resolve_blending(nowcast="a.npy", nwp="b.npy", tau_min=30.0)
    assert blended["nowcast"] == "a.npy"
    assert blended["nwp"] == "b.npy"
    assert blended["lead_index"] == 1
    assert blended["n_cascade_levels"] == 8
    assert blended["tau_min"] == 30.0
    assert blended["clim_skill"] is None
    assert blended["output"].endswith("blended.npy")


def test_module_selection() -> None:
    with pytest.raises(ValueError, match="module"):
        resolve_module()
    assert resolve_module("blending") == "blending"
    assert resolve_module("skill") == "climatological_skill"
    args = parse_args([])
    assert args.module is None
    assert args.nowcast is None
    assert args.issue_time is None
    chosen = parse_args(["--module", "blending", "--nowcast", "a.npy", "--nwp", "b.npy"])
    assert chosen.module == "blending"
    assert chosen.nowcast == "a.npy"
    assert chosen.nwp == "b.npy"
