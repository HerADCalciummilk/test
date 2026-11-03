"""Unit tests for Kalman numeric helpers."""

from __future__ import annotations

import numpy as np

from kalman_element_forecast_correction.utils.grid_utils import decaying_fcst, decaying_me, forecast_observation_difference


def test_forecast_observation_difference() -> None:
    fcst = np.array([3.0, 5.0], dtype=np.float32)
    obs = np.array([1.0, 7.0], dtype=np.float32)
    np.testing.assert_allclose(forecast_observation_difference(fcst, obs, absolute=False), [2.0, -2.0])
    np.testing.assert_allclose(forecast_observation_difference(fcst, obs, absolute=True), [2.0, 2.0])


def test_decaying_me() -> None:
    previous = np.array([1.0, 3.0], dtype=np.float32)
    latest = np.array([3.0, 5.0], dtype=np.float32)
    np.testing.assert_allclose(decaying_me(latest, previous, alpha=0.25), [1.5, 3.5])


def test_decaying_fcst() -> None:
    fcst = np.array([10.0, 20.0], dtype=np.float32)
    me = np.array([1.5, -2.0], dtype=np.float32)
    np.testing.assert_allclose(decaying_fcst(fcst, me), [8.5, 22.0])
