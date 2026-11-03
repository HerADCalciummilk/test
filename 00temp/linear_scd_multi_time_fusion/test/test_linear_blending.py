"""Unit tests for SCD linear blending."""

from __future__ import annotations

import configparser

import numpy as np

from linear_scd_multi_time_fusion.src.conf_overrides import CONF_KEYS, apply_conf_overrides
from linear_scd_multi_time_fusion.src.linear_blending import linear_blending_forecast


def test_linear_blending_with_per_frame_weights() -> None:
    nowcast = np.ones((2, 2, 2), dtype=np.float32) * 10.0
    model = np.ones((2, 2, 2), dtype=np.float32) * 2.0

    blended = linear_blending_forecast(
        precomputed_nowcast=nowcast,
        precip_model=model,
        weights_now_list=[1.0, 0.25],
    )

    np.testing.assert_allclose(blended[0], np.ones((2, 2), dtype=np.float32) * 10.0)
    np.testing.assert_allclose(blended[1], np.ones((2, 2), dtype=np.float32) * 4.0)


def test_conf_overrides_skip_none_and_keep_empty_string() -> None:
    cfg = configparser.ConfigParser()
    cfg.read_dict({"run": {"dry_run": "false", "max_files": "9"}, "fusion": {"lon_min": "1"}})
    apply_conf_overrides(
        cfg,
        dry_run=False,
        max_files="",
        lon_min=None,
        allowed_realtime_minutes=[0, 30],
        enabled=True,
    )
    assert cfg.get("run", "dry_run") == "false"
    assert cfg.get("run", "max_files") == ""
    assert cfg.get("fusion", "lon_min") == "1"
    assert cfg.get("run", "allowed_realtime_minutes") == "0,30"
    assert cfg.get("padding", "enabled") == "true"
    assert set(CONF_KEYS) >= {
        "source1_dir",
        "output_dir",
        "keyframe_weights",
        "output_source",
        "overwrite",
    }
