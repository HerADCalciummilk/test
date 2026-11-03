"""Unit tests for SCD linear blending."""

from __future__ import annotations

import numpy as np

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
