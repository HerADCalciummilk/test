"""Run directly to test exports without importing the meteorological engine."""

from datetime import datetime
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

import h5py
import numpy as np
from netCDF4 import Dataset

spec = importlib.util.spec_from_file_location(
    "grid_netcdf", Path(__file__).resolve().parents[1] / "src/core/grid_netcdf.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class NetCDFTests(unittest.TestCase):
    def test_paths(self):
        p = module.product_path("out", "TMP", datetime(2026, 11, 18), 6, level=900)
        self.assertEqual(p.as_posix(), "out/TMP/900/2026/20261118/2026111800.006.nc")
        with self.assertRaises(ValueError):
            module.product_path("out", "../TMP", datetime(2026, 11, 18), 6)

    def test_multi_element_roundtrip_and_skip(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "006_006.h5"
            fixture_path = Path(__file__).resolve().parents[1] / "resource/sample/合成温度样例.json"
            fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
            values = np.array(fixture["2t"])
            with h5py.File(source, "w") as h:
                h["lon_lat"] = fixture["lon_lat"]
                h["2t"] = values
                h["sp"] = np.where(values == -32766, -32766, 1000.)
                h["gamma_2t"] = np.zeros((1, 1))
            mapping = {"2t": "TMP_2M", "sp": "PRES"}
            products = module.export_grid_file(source, root, "2026111808", 6, mapping)
            self.assertEqual(len(products), 2)
            temperature = root / "TMP_2M/2026/20261118/2026111800.006.nc"
            with Dataset(temperature) as ds:
                self.assertEqual(ds.variables["data0"].shape, (1, 1, 1, 1, 2, 3))
                actual = ds.variables["data0"][:].filled(-32766).reshape(2, 3)
                np.testing.assert_array_equal(actual, values)
                np.testing.assert_allclose(ds.variables["lat"][:], [0, .05])
                np.testing.assert_allclose(ds.variables["lon"][:], [70, 70.05, 70.1])
                self.assertEqual(ds.valid_time, "2026-11-18T06:00:00")
            with Dataset(root / "PRES/2026/20261118/2026111800.006.nc") as ds:
                self.assertEqual(ds.variables["data0"].units, "Pa")
                self.assertEqual(ds.variables["data0"][0, 0, 0, 0, 0, 0], 100000.)
                self.assertTrue(ds.variables["data0"][0, 0, 0, 0, 1, 2].mask)
            timestamp = temperature.stat().st_mtime_ns
            module.export_grid_file(source, root, "2026111808", 6, mapping)
            self.assertEqual(temperature.stat().st_mtime_ns, timestamp)
            module.export_grid_file(source, root, "2026111808", 6, mapping, update=True)
            self.assertFalse(list(root.rglob("*.tmp")))

    def test_cross_day(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "test.h5"
            with h5py.File(source, "w") as h:
                h["lon_lat"] = [70, 70, 0, 0, .05, .05]
                h["2t"] = [[1.]]
            paths = module.export_grid_file(source, root, "2026010100", 240, {"2t": "TMP_2M"})
            self.assertIn("2025/20251231/2025123116.240.nc", Path(paths[0]).as_posix())


if __name__ == "__main__":
    unittest.main()
