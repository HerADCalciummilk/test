#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2019 NMC Developers.
# Distributed under the terms of the GPL V3 License.

"""
Official Met Office test data validation for feels_like_temperature algorithm.
This test validates against Known Good Output (KGO) from the original Improver library.
"""

import os
import numpy as np
import pytest
import xarray as xr

from feels_like_temperature.src.feels_like_temperature import calculate_feels_like_temperature


def get_test_data_path():
    """Get the path to the official test data."""
    # Use project test_data directory for official KGO inputs.
    base_path = os.path.join(
        os.path.dirname(__file__),
        '..',
        'test_data',
        'feels_like_temp_data',
    )
    if not os.path.exists(base_path):
        pytest.skip("Official test data not available")
    return base_path


def get_cli_input_data_path(base_path: str) -> str:
    """Get CLI input data path."""
    return os.path.join(base_path, "cli_input")


class TestOfficialDataValidation:
    """Validate against official Met Office test data."""

    def test_official_data_xarray_input(self):
        """Test with official Met Office data using xarray.DataArray inputs."""
        base_path = get_test_data_path()
        cli_input_path = get_cli_input_data_path(base_path)
        if not os.path.isdir(cli_input_path):
            pytest.skip("cli_input data not available for strict xarray meb6d validation")

        temp_file = os.path.join(
            cli_input_path, "20181121T1200Z-PT0012H00M-temperature_at_screen_level.nc"
        )
        wind_file = os.path.join(
            cli_input_path, "20181121T1200Z-PT0012H00M-wind_speed_at_10m.nc"
        )
        rh_file = os.path.join(
            cli_input_path, "20181121T1200Z-PT0012H00M-relative_humidity_at_screen_level.nc"
        )
        pressure_file = os.path.join(
            cli_input_path, "20181121T1200Z-PT0012H00M-pressure_at_mean_sea_level.nc"
        )
        kgo_file = os.path.join(base_path, "kgo.nc")

        required_files = [temp_file, wind_file, rh_file, pressure_file, kgo_file]
        missing = [f for f in required_files if not os.path.exists(f)]
        if missing:
            pytest.skip(f"cli_input / reference files missing: {missing}")

        temp_ds = xr.open_dataset(temp_file, decode_timedelta=False)
        wind_ds = xr.open_dataset(wind_file, decode_timedelta=False)
        rh_ds = xr.open_dataset(rh_file, decode_timedelta=False)
        pressure_ds = xr.open_dataset(pressure_file, decode_timedelta=False)
        kgo_ds = xr.open_dataset(kgo_file, decode_timedelta=False)

        # Extract data variables and set correct unit attributes
        temperature = temp_ds.air_temperature.copy()
        temperature.attrs['units'] = temp_ds.air_temperature.attrs.get('units', 'K')

        wind_speed = wind_ds.wind_speed.copy()
        wind_speed.attrs['units'] = wind_ds.wind_speed.attrs.get('units', 'm s-1')

        relative_humidity = rh_ds.relative_humidity.copy()
        relative_humidity.attrs['units'] = rh_ds.relative_humidity.attrs.get('units', '1')

        pressure = pressure_ds.air_pressure_at_sea_level.copy()
        pressure.attrs['units'] = pressure_ds.air_pressure_at_sea_level.attrs.get('units', 'Pa')

        kgo_result = kgo_ds.feels_like_temperature.values

        # Calculate feels like temperature
        calculated_flt = calculate_feels_like_temperature(
            temperature,
            wind_speed,
            relative_humidity,
            pressure,
        )
        if isinstance(calculated_flt, xr.DataArray):
            calculated_flt = calculated_flt.values

        # Validate results against KGO
        abs_diff = np.abs(calculated_flt - kgo_result)
        rel_diff = abs_diff / np.maximum(np.abs(kgo_result), 1e-8)

        # Check that results are within tolerance.
        # 预处理到 meb6d 后与官方 KGO 可能存在小幅差异，采用覆盖率+最大误差双约束。
        tolerance_abs = 0.01
        tolerance_rel = 0.001

        within_tolerance = (abs_diff <= tolerance_abs) | (rel_diff <= tolerance_rel)
        accuracy = np.mean(within_tolerance)
        max_abs_diff = float(np.max(abs_diff))

        assert accuracy >= 0.995, f"Accuracy {accuracy*100:.4f}% below threshold"
        assert max_abs_diff <= 0.5, f"Max absolute error too large: {max_abs_diff:.6f} K"

    def test_official_data_numpy_input(self):
        """Test with official Met Office data using numpy array inputs."""
        base_path = get_test_data_path()

        # Load official test data
        temp_file = os.path.join(base_path, "20181121T1200Z-PT0012H00M-temperature_at_screen_level.nc")
        wind_file = os.path.join(base_path, "20181121T1200Z-PT0012H00M-wind_speed_at_10m.nc")
        rh_file = os.path.join(base_path, "20181121T1200Z-PT0012H00M-relative_humidity_at_screen_level.nc")
        pressure_file = os.path.join(base_path, "20181121T1200Z-PT0012H00M-pressure_at_mean_sea_level.nc")
        kgo_file = os.path.join(base_path, "kgo.nc")

        temp_ds = xr.open_dataset(temp_file, decode_timedelta=False)
        wind_ds = xr.open_dataset(wind_file, decode_timedelta=False)
        rh_ds = xr.open_dataset(rh_file, decode_timedelta=False)
        pressure_ds = xr.open_dataset(pressure_file, decode_timedelta=False)
        kgo_ds = xr.open_dataset(kgo_file, decode_timedelta=False)

        # Extract numpy arrays and convert to expected units for numpy input
        # For numpy arrays, the function assumes: degC, m/s, fraction, Pa
        temperature = (temp_ds.air_temperature.values - 273.15)  # Convert K to degC
        wind_speed = wind_ds.wind_speed.values                   # m/s (already correct)
        relative_humidity = rh_ds.relative_humidity.values       # fraction (already correct)
        pressure = pressure_ds.air_pressure_at_sea_level.values  # Pa (already correct)

        kgo_result = kgo_ds.feels_like_temperature.values

        # Calculate feels like temperature with numpy arrays
        calculated_flt_c = calculate_feels_like_temperature(
            temperature,
            wind_speed,
            relative_humidity,
            pressure,
        )

        # Convert result from Celsius to Kelvin for comparison with KGO
        calculated_flt = calculated_flt_c + 273.15

        # Validate consistency between xarray and numpy results should be identical
        # Since both use the same underlying algorithm
        abs_diff = np.abs(calculated_flt - kgo_result)
        rel_diff = abs_diff / np.maximum(np.abs(kgo_result), 1e-8)

        tolerance_abs = 0.01
        tolerance_rel = 0.001

        within_tolerance = (abs_diff <= tolerance_abs) | (rel_diff <= tolerance_rel)
        accuracy = np.mean(within_tolerance)

        assert accuracy >= 0.9999, f"Numpy input accuracy {accuracy*100:.4f}% below threshold"
