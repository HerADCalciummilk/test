"""Minimal tests for the archived optical-flow nowcast package."""

from __future__ import annotations

import numpy as np
import pytest

from optical_flow_nowcast.src.extrapolation_plugin import _check_inputs


def test_extrapolation_input_validation() -> None:
    precip = np.ones((4, 4), dtype=float)
    velocity = np.zeros((2, 4, 4), dtype=float)
    _check_inputs(precip, velocity, 2)


def test_extrapolation_rejects_mismatched_shape() -> None:
    precip = np.ones((4, 4), dtype=float)
    velocity = np.zeros((2, 3, 4), dtype=float)
    with pytest.raises(ValueError):
        _check_inputs(precip, velocity, 2)

