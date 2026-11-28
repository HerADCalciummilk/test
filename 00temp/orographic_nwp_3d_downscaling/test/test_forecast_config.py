"""Forecast bounds tests runnable without the full algorithm environment."""

import configparser
import importlib.util
from pathlib import Path
import unittest


path = Path(__file__).resolve().parents[1] / "src/core/forecast_config.py"
spec = importlib.util.spec_from_file_location("forecast_config", path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ForecastRangeTests(unittest.TestCase):
    def bounds(self, text, model="EC_12P5KM", hours=(0, 3, 6, 57, 60, 240)):
        config = configparser.ConfigParser()
        config.read_string(text)
        return module.forecast_hour_range(config, model, hours)

    def test_ec_extended(self):
        self.assertEqual(self.bounds("[ForecastHourRange]\nEC_12P5KM=0,240"), (0, 240))

    def test_different_models(self):
        text = "[ForecastHourRange]\nEC_12P5KM=6,240\nGRAPES_12P5KM=3,48"
        self.assertEqual(self.bounds(text), (6, 240))
        self.assertEqual(self.bounds(text, "GRAPES_12P5KM"), (3, 48))

    def test_old_config_uses_full_list(self):
        self.assertEqual(self.bounds(""), (0, 240))
        self.assertEqual(self.bounds("[ForecastHourRange]\nCMA_MESO=5,36"), (0, 240))

    def test_single_hour(self):
        self.assertEqual(self.bounds("[ForecastHourRange]\nEC_12P5KM=6,6"), (6, 6))

    def test_invalid_bounds(self):
        for value in ("-1,240", "60,6", "abc", "0,6,12", "7,8"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.bounds("[ForecastHourRange]\nEC_12P5KM=" + value)

    def test_empty_model_hours(self):
        with self.assertRaises(ValueError):
            self.bounds("", hours=())


if __name__ == "__main__":
    unittest.main()
