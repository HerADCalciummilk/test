#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.
"""Goff-Gratch 公式准确性验证测试。"""

import numpy as np
import pytest

from feels_like_temperature.src.utils._feels_like import (
    _calculate_svp_in_air,
    _svp_pure_water_goff_gratch,
)


class TestGoffGratchValidation:
    """Test Goff-Gratch formula implementation accuracy."""

    def test_goff_gratch_formula_accuracy(self):
        """Test Goff-Gratch formula against reference values from WMO."""
        REFERENCE_VALUES = [
            (250.0, 76.35),
            (273.15, 611.21),
            (273.16, 611.657),
            (293.15, 2338.0),
            (310.0, 6220.0),
        ]

        total_error = 0.0
        for temp_k, ref_svp in REFERENCE_VALUES:
            temp_array = np.array([temp_k], dtype=np.float32)
            base_svp_hpa = _svp_pure_water_goff_gratch(temp_array)
            base_svp_pa = base_svp_hpa * 100.0
            calc_value = base_svp_pa[0]
            rel_error = abs(calc_value - ref_svp) / ref_svp * 100.0
            total_error += rel_error
            assert rel_error < 0.6, (
                f"Relative error {rel_error:.4f}% exceeds 0.6% tolerance at {temp_k}K"
            )

        avg_error = total_error / len(REFERENCE_VALUES)
        assert avg_error < 0.5, (
            f"Average relative error {avg_error:.4f}% exceeds 0.5% tolerance"
        )

    def test_pressure_correction_functionality(self):
        """Test pressure correction functionality."""
        temp_test = 293.15
        pressures = [101325.0, 90000.0, 110000.0]

        for p in pressures:
            temp_arr = np.array([temp_test], dtype=np.float32)
            press_arr = np.array([p], dtype=np.float32)
            svp_corrected = _calculate_svp_in_air(temp_arr, press_arr)
            svp_base = _svp_pure_water_goff_gratch(temp_arr) * 100.0
            correction_factor = svp_corrected[0] / svp_base[0]

            assert correction_factor > 1.0, (
                f"Correction factor {correction_factor:.6f} should be > 1.0 at pressure {p} Pa"
            )
            assert correction_factor < 1.01, (
                f"Correction factor {correction_factor:.6f} should be < 1.01 at pressure {p} Pa"
            )
