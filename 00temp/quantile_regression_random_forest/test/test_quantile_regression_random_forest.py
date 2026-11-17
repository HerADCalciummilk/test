"""分位数回归随机森林测试。"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from quantile_regression_random_forest.src.features import (  # noqa: E402
    apply_transformation,
    prep_feature,
    prep_features_from_config,
    reverse_transformation,
)
from quantile_regression_random_forest.src.quantile_regression_random_forest import apply_qrf, train_qrf
from quantile_regression_random_forest.src.quantile_forest import QuantileForestRegressor
from quantile_regression_random_forest.util.demo_data import make_grid_case, make_station_case
from quantile_regression_random_forest.util.meteva_data import load_grid, load_station, save_grid, save_station

PYTHON = sys.executable


class QuantileForestTests(unittest.TestCase):
    def test_constant_target_quantiles_stay_constant(self):
        features = np.linspace(0, 1, 40).reshape(-1, 1)
        target = np.full(40, 3.5)
        model = QuantileForestRegressor(n_estimators=8, random_state=1)
        model.fit(features, target)
        predicted = model.predict(features[:5], quantiles=[0.1, 0.5, 0.9])
        self.assertTrue(np.allclose(predicted, 3.5))

    def test_quantiles_are_ordered_for_noisy_line(self):
        rng = np.random.default_rng(2)
        features = np.linspace(0, 10, 80).reshape(-1, 1)
        target = features.ravel() * 2.0 + rng.normal(0, 0.4, size=80)
        model = QuantileForestRegressor(n_estimators=20, max_depth=6, random_state=2)
        model.fit(features, target)
        predicted = model.predict(features, quantiles=[0.1, 0.5, 0.9])
        self.assertTrue(np.all(predicted[:, 0] <= predicted[:, 1] + 1e-8))
        self.assertTrue(np.all(predicted[:, 1] <= predicted[:, 2] + 1e-8))


class FeatureTests(unittest.TestCase):
    def _frame(self):
        return pd.DataFrame(
            {
                "forecast_reference_time": pd.to_datetime(["2024-01-01 00:00"] * 4),
                "forecast_period": [6, 6, 6, 6],
                "valid_time": pd.to_datetime(["2024-01-01 06:00"] * 4),
                "level": [0, 0, 0, 0],
                "id": [1, 1, 1, 1],
                "member": [0, 1, 2, 3],
                "air_temperature": [1.0, 2.0, 3.0, 4.0],
                "altitude": [10.0, 10.0, 10.0, 10.0],
            }
        )

    def test_members_below_and_mean(self):
        frame = self._frame()
        keys = ["forecast_reference_time", "forecast_period", "level", "id"]
        frame = prep_feature(frame, "air_temperature", "members_below_2.5", keys)
        frame = prep_feature(frame, "air_temperature", "mean", keys)
        self.assertTrue((frame["air_temperature_members_below_2.5"] == 2).all())
        self.assertTrue(np.allclose(frame["air_temperature_mean"], 2.5))

    def test_single_member_std_is_zero(self):
        frame = self._frame().iloc[:1].copy()
        keys = ["forecast_reference_time", "forecast_period", "level", "id"]
        result = prep_feature(frame, "air_temperature", "std", keys)
        self.assertEqual(result["air_temperature_std"].iloc[0], 0)

    def test_unknown_feature_raises(self):
        frame = self._frame()
        keys = ["forecast_reference_time", "forecast_period", "level", "id"]
        with self.assertRaises(ValueError):
            prep_features_from_config(frame, {"air_temperature": ["interquartile_range"]}, keys)

    def test_uneven_percentiles_raise(self):
        frame = self._frame()
        frame = frame.drop(columns=["member"])
        frame["percentile"] = [10, 20, 90, 90]
        keys = ["forecast_reference_time", "forecast_period", "level", "id"]
        with self.assertRaises(ValueError):
            prep_feature(frame, "air_temperature", "mean", keys)

    def test_log_transform_roundtrip(self):
        values = np.array([1.0, np.e, 10.0])
        transformed = apply_transformation(values, "log", 0)
        restored = reverse_transformation(transformed, "log", 0)
        self.assertTrue(np.allclose(restored, values))


class CalibrationTests(unittest.TestCase):
    def test_station_median_removes_bias(self):
        forecast, truth = make_station_case()
        bundle = train_qrf(
            forecast,
            truth,
            {"air_temperature": ["mean"]},
            "air_temperature",
            n_estimators=30,
            random_state=0,
        )
        calibrated = apply_qrf(bundle, forecast, quantiles=[0.1, 0.5, 0.9])
        self.assertIn("member", calibrated.columns)
        median = calibrated[np.isclose(calibrated["member"], 0.5)]
        merged = median.merge(truth, on=["id", "level", "lon", "lat"], suffixes=("_fcst", "_truth"))
        merged = merged[merged["time_truth"] == merged["time_fcst"] + pd.to_timedelta(merged["dtime_fcst"], unit="h")]
        self.assertFalse(merged.empty)
        corrected = np.abs(merged["air_temperature"] - merged["ob_value"])
        self.assertLess(float(corrected.mean()), 0.5)
        ordered = calibrated.pivot_table(
            index=["id", "time", "dtime"], columns="member", values="air_temperature"
        )
        quantile_columns = sorted(ordered.columns)
        values = ordered[quantile_columns].to_numpy()
        self.assertTrue(np.all(values[:, 0] <= values[:, 1] + 1e-5))
        self.assertTrue(np.all(values[:, 1] <= values[:, 2] + 1e-5))

    def test_grid_output_uses_quantile_members(self):
        forecast, truth = make_grid_case()
        bundle = train_qrf(
            forecast,
            truth,
            {"air_temperature": ["mean", "std"]},
            "air_temperature",
            n_estimators=20,
            random_state=0,
        )
        calibrated = apply_qrf(bundle, forecast, quantiles=[0.1, 0.5, 0.9])
        self.assertEqual(calibrated.dims, ("member", "level", "time", "dtime", "lat", "lon"))
        self.assertEqual(list(calibrated.member.values), ["0.1", "0.5", "0.9"])
        self.assertEqual(calibrated.attrs["dtime_units"], "hour")
        self.assertTrue(np.isfinite(calibrated.values).all())
        ordered = calibrated.transpose("member", ...)
        self.assertTrue(np.all(ordered.sel(member="0.1").values <= ordered.sel(member="0.5").values + 1e-5))
        self.assertTrue(np.all(ordered.sel(member="0.5").values <= ordered.sel(member="0.9").values + 1e-5))
        median = calibrated.sel(member="0.5")
        truth_aligned = truth.isel(member=0).assign_coords(
            time=median.time.values,
            dtime=median.dtime.values,
        )
        corrected = np.abs(median.values - truth_aligned.values)
        raw_mean = forecast.mean("member")
        raw_error = np.abs(raw_mean.values - truth_aligned.values)
        self.assertLess(float(corrected.mean()), float(raw_error.mean()))
        self.assertLess(float(corrected.mean()), 0.5)

    def test_too_many_missing_values_raise(self):
        forecast, truth = make_station_case()
        forecast = forecast.copy()
        forecast.loc[forecast["id"] != 54511, "altitude"] = np.nan
        with self.assertRaises(ValueError):
            train_qrf(
                forecast,
                truth,
                {"air_temperature": ["mean"], "altitude": ["static"]},
                "air_temperature",
                n_estimators=5,
                random_state=0,
            )

    def test_log_calibration_returns_positive_values(self):
        forecast, truth = make_station_case()
        forecast = forecast.copy()
        truth = truth.copy()
        forecast["air_temperature"] = np.exp(forecast["air_temperature"] / 20.0)
        truth["ob_value"] = np.exp((truth["ob_value"] + 2.0) / 20.0)
        bundle = train_qrf(
            forecast,
            truth,
            {"air_temperature": ["mean"]},
            "air_temperature",
            n_estimators=10,
            random_state=0,
            transformation="log",
        )
        calibrated = apply_qrf(bundle, forecast, quantiles=[0.5])
        self.assertTrue(np.all(calibrated["air_temperature"] > 0))


class IoAndCliTests(unittest.TestCase):
    def test_meteva_roundtrip_keeps_lead_unit_and_hour(self):
        forecast, truth = make_station_case()
        grid, _ = make_grid_case()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            save_station(forecast, root / "forecast.csv")
            save_grid(grid, root / "forecast.nc")
            loaded_station = load_station(root / "forecast.csv")
            loaded_grid = load_grid(root / "forecast.nc")
        self.assertEqual(loaded_station.attrs["dtime_units"], "hour")
        self.assertEqual(loaded_grid.attrs["dtime_units"], "hour")
        self.assertIn(12, set(pd.to_datetime(loaded_station["time"]).dt.hour))
        self.assertEqual(loaded_grid.sizes["member"], 4)
        self.assertEqual(loaded_grid.name, "air_temperature")
        self.assertEqual(len(truth), 24)

    def test_cli_train_and_apply(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = {
                "air_temperature": ["mean", "std"],
                "altitude": ["static"],
            }
            config_path = root / "features.json"
            config_path.write_text(json.dumps(config), encoding="utf-8")
            model_path = root / "model.pkl"
            output_path = root / "calibrated.csv"
            forecast = REPO / "quantile_regression_random_forest" / "testdata" / "forecast_sta.csv"
            truth = REPO / "quantile_regression_random_forest" / "testdata" / "truth_sta.csv"
            train = subprocess.run(
                [
                    PYTHON,
                    "-m",
                    "quantile_regression_random_forest.cli",
                    "train",
                    "--forecast",
                    str(forecast),
                    "--truth",
                    str(truth),
                    "--feature-config",
                    str(config_path),
                    "--output",
                    str(model_path),
                    "--n-estimators",
                    "20",
                    "--random-state",
                    "0",
                ],
                cwd=REPO,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
            self.assertEqual(train.returncode, 0, train.stderr)
            apply = subprocess.run(
                [
                    PYTHON,
                    "-m",
                    "quantile_regression_random_forest",
                    "apply",
                    "--forecast",
                    str(forecast),
                    "--model",
                    str(model_path),
                    "--output",
                    str(output_path),
                    "--quantiles",
                    "0.5",
                    "--feature-config",
                    str(config_path),
                ],
                cwd=REPO,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
            self.assertEqual(apply.returncode, 0, apply.stderr)
            calibrated = load_station(output_path)
        self.assertTrue(np.allclose(calibrated["member"], 0.5))
        self.assertEqual(calibrated.attrs["dtime_units"], "hour")

    def test_cli_train_and_apply_grid(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            model_path = root / "grid_model.pkl"
            output_path = root / "calibrated.nc"
            forecast = REPO / "quantile_regression_random_forest" / "testdata" / "forecast_grid.nc"
            truth = REPO / "quantile_regression_random_forest" / "testdata" / "truth_grid.nc"
            config = REPO / "quantile_regression_random_forest" / "testdata" / "feature_config_grid.json"
            train = subprocess.run(
                [
                    PYTHON,
                    "-m",
                    "quantile_regression_random_forest",
                    "train",
                    "--forecast",
                    str(forecast),
                    "--truth",
                    str(truth),
                    "--feature-config",
                    str(config),
                    "--output",
                    str(model_path),
                    "--n-estimators",
                    "20",
                    "--random-state",
                    "0",
                ],
                cwd=REPO,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
            self.assertEqual(train.returncode, 0, train.stderr)
            apply = subprocess.run(
                [
                    PYTHON,
                    "-m",
                    "quantile_regression_random_forest.cli",
                    "apply",
                    "--forecast",
                    str(forecast),
                    "--model",
                    str(model_path),
                    "--output",
                    str(output_path),
                    "--quantiles",
                    "0.1,0.5,0.9",
                ],
                cwd=REPO,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
            self.assertEqual(apply.returncode, 0, apply.stderr)
            calibrated = load_grid(output_path)
        self.assertEqual(calibrated.dims, ("member", "level", "time", "dtime", "lat", "lon"))
        self.assertEqual(list(calibrated.member.values), ["0.1", "0.5", "0.9"])
        self.assertEqual(calibrated.attrs["dtime_units"], "hour")
        self.assertEqual(calibrated.name, "air_temperature")
        self.assertEqual(calibrated.sizes["lat"], 12)
        self.assertEqual(calibrated.sizes["lon"], 12)
        self.assertTrue(np.isfinite(calibrated.values).all())
        self.assertTrue(
            np.all(calibrated.sel(member="0.1").values <= calibrated.sel(member="0.5").values + 1e-5)
        )
        self.assertTrue(
            np.all(calibrated.sel(member="0.5").values <= calibrated.sel(member="0.9").values + 1e-5)
        )


if __name__ == "__main__":
    unittest.main()
