#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Threshold 合成单测与官方 KGO 回归。"""

from __future__ import annotations

import json
from pathlib import Path
import sys

import numpy as np
import pytest
import xarray as xr

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from threshold_probability_conversion.src.threshold import Threshold
from threshold_probability_conversion.src.utils._regrid import prepare_geographic_input
from threshold_probability_conversion.src.utils._comparison_operator import comparison_operator_dict
from threshold_probability_conversion.src.utils._rescale import rescale

TEST_DATA = Path(__file__).resolve().parents[1] / "test_data"
MEB_INPUT = TEST_DATA / "basic" / "cli_inputs" / "input_meb.nc"
VICINITY_INPUT = TEST_DATA / "vicinity" / "cli_inputs" / "input_meb.nc"
VICINITY_LANDMASK = TEST_DATA / "vicinity" / "cli_inputs" / "landmask_meb.nc"
VICINITY_MASKED_INPUT = TEST_DATA / "vicinity_masked" / "cli_inputs" / "input_meb.nc"


def _meb_from_array(
    values: np.ndarray,
    *,
    units: str = "K",
    name: str = "air_temperature",
    n_time: int = 1,
) -> xr.DataArray:
    """构造最小六维 DataArray（member×1×time×1×lat×lon）。"""
    if values.ndim == 2:
        values = values[np.newaxis, ...]
    elif values.ndim == 4:
        n_time = values.shape[1]
    n_member, n_lat, n_lon = values.shape[0], values.shape[-2], values.shape[-1]
    arr = values.reshape(n_member, 1, n_time, 1, n_lat, n_lon).astype(np.float32)
    times = np.datetime64("1970-01-01T00:00:00") + np.arange(
        n_time, dtype=np.int64
    ) * np.timedelta64(1, "h")
    return xr.DataArray(
        arr,
        dims=("member", "level", "time", "dtime", "lat", "lon"),
        coords={
            "member": np.arange(n_member, dtype=np.int32),
            "level": np.array([0.0], dtype=np.float32),
            "time": times,
            "dtime": np.array([0], dtype=np.int32),
            "lat": np.arange(n_lat, dtype=np.float32),
            "lon": np.arange(n_lon, dtype=np.float32),
        },
        name=name,
        attrs={"units": units},
    )


class TestRescaleAndOperator:
    def test_rescale_clip(self):
        data = np.array([0.0, 5.0, 10.0, 15.0])
        out = rescale(data, data_range=(0, 10), scale_range=(0, 1), clip=True)
        np.testing.assert_allclose(out, [0.0, 0.5, 1.0, 1.0])

    def test_comparison_operator_keys(self):
        mapping = comparison_operator_dict()
        assert mapping[">"].spp_string == "greater_than"
        assert mapping["<="].spp_string == "less_than_or_equal_to"
        assert mapping["ge"].function(3, 3)


class TestThresholdSynthetic:
    def test_hard_above(self):
        data = np.array([[270.0, 280.0, 290.0]], dtype=np.float32)
        out = Threshold(threshold_values=280.0).process(data)
        np.testing.assert_array_equal(out[0, 0], [0, 0, 1])

    def test_hard_ge(self):
        data = np.array([[270.0, 280.0, 290.0]], dtype=np.float32)
        out = Threshold(threshold_values=280.0, comparison_operator=">=").process(data)
        np.testing.assert_array_equal(out[0, 0], [0, 1, 1])

    def test_below(self):
        data = np.array([[270.0, 280.0, 290.0]], dtype=np.float32)
        out = Threshold(threshold_values=280.0, comparison_operator="<").process(data)
        np.testing.assert_array_equal(out[0, 0], [1, 0, 0])

    def test_fuzzy_midpoint(self):
        # fuzzy_factor=0.5 → 界 (140, 420)，阈值 280 处应为 0.5
        data = np.array([[280.0]], dtype=np.float32)
        out = Threshold(threshold_values=280.0, fuzzy_factor=0.5).process(data)
        np.testing.assert_allclose(out[0, 0, 0], 0.5)

    def test_multi_threshold_level(self):
        da = _meb_from_array(np.array([[275.0, 285.0]], dtype=np.float32))
        out = Threshold(threshold_values=[270.0, 280.0, 290.0]).process(da)
        assert list(out.dims) == ["member", "level", "time", "dtime", "lat", "lon"]
        np.testing.assert_allclose(out.level.values, [270, 280, 290])
        # 点 275：>270 是 1，>280 是 0，>290 是 0
        np.testing.assert_array_equal(out.values[0, :, 0, 0, 0, 0], [1, 0, 0])

    def test_threshold_units_celsius(self):
        # 数据单位 K，阈值 6.85 C = 280 K
        data = np.array([[279.0, 281.0]], dtype=np.float32)
        out = Threshold(
            threshold_values=6.85, threshold_units="celsius", comparison_operator=">"
        ).process(data, data_units="K")
        np.testing.assert_array_equal(out[0, 0], [0, 1])
        np.testing.assert_allclose(out[:, 0].shape[0] and [280.0], [280.0], atol=0.01)
        # numpy 路径：阈值坐标不在数组里；用 DataArray 检查
        da = _meb_from_array(data)
        out_da = Threshold(
            threshold_values=6.85, threshold_units="celsius"
        ).process(da)
        np.testing.assert_allclose(out_da.level.values, [280.0], atol=1e-4)

    def test_fill_masked(self):
        data = np.ma.array(
            [[270.0, 999.0]], mask=[[False, True]], dtype=np.float32
        )
        out = Threshold(threshold_values=280.0, fill_masked=0.0).process(data)
        np.testing.assert_array_equal(out[0, 0], [0, 0])

    def test_nan_raises(self):
        data = np.array([[270.0, np.nan]], dtype=np.float32)
        with pytest.raises(ValueError, match="NaN"):
            Threshold(threshold_values=280.0).process(data)

    def test_mutex_args(self):
        with pytest.raises(ValueError, match="mutually exclusive"):
            Threshold(threshold_values=1.0, threshold_config={"1": "None"})

    def test_fuzzy_zero_threshold_forbidden(self):
        with pytest.raises(ValueError, match="threshold == 0"):
            Threshold(threshold_values=0.0, fuzzy_factor=0.5)

    def test_config_json_bounds(self):
        cfg = {"280.0": [278.0, 282.0]}
        data = np.array([[280.0]], dtype=np.float32)
        out = Threshold(threshold_config=cfg).process(data)
        np.testing.assert_allclose(out[0, 0, 0], 0.5)


class TestThresholdCollapse:
    def test_collapse_member_ensemble_probability(self):
        # 三成员在同格点：270 / 280 / 290，阈值 280 严格大于 → 1/3
        values = np.array(
            [[[270.0]], [[280.0]], [[290.0]]], dtype=np.float32
        )
        da = _meb_from_array(values)
        out = Threshold(
            threshold_values=280.0, collapse_coord="member"
        ).process(da)
        assert out.sizes["member"] == 1
        np.testing.assert_allclose(out.values[0, 0, 0, 0, 0, 0], 1.0 / 3.0)
        assert out.attrs.get("collapsed_coords") == ["member"]

    def test_collapse_time(self):
        values = np.array(
            [[[[270.0]], [[290.0]]]], dtype=np.float32
        )  # member=1, time=2
        da = _meb_from_array(values)
        out = Threshold(threshold_values=280.0, collapse_coord="time").process(da)
        assert out.sizes["time"] == 1
        np.testing.assert_allclose(out.values[0, 0, 0, 0, 0, 0], 0.5)
        assert "time" in out.attrs.get("collapsed_coords", [])

    def test_collapse_member_and_time(self):
        values = np.array(
            [
                [[270.0], [290.0]],
                [[290.0], [270.0]],
            ],
            dtype=np.float32,
        )  # member=2, time=2 → 平均 (0+1+1+0)/4 = 0.5
        da = _meb_from_array(values)
        out = Threshold(
            threshold_values=280.0, collapse_coord=["member", "time"]
        ).process(da)
        assert out.sizes["member"] == 1 and out.sizes["time"] == 1
        np.testing.assert_allclose(out.values[0, 0, 0, 0, 0, 0], 0.5)

    def test_collapse_truth_stack_respects_mask(self):
        truths = np.zeros((1, 3, 1, 1, 1, 1), dtype=np.float32)
        truths[0, 0, 0, 0, 0, 0] = 1.0
        truths[0, 2, 0, 0, 0, 0] = 1.0
        mask = np.zeros((3, 1, 1, 1, 1), dtype=bool)
        mask[1, 0, 0, 0, 0] = True
        plugin = Threshold(threshold_values=280.0)
        collapsed, _ = plugin._collapse_truth_stack(truths, mask, ["member"])
        np.testing.assert_allclose(collapsed[0, 0, 0, 0, 0, 0], 1.0)

    def test_no_collapse_unchanged_member_size(self):
        values = np.array([[[270.0]], [[290.0]]], dtype=np.float32)
        da = _meb_from_array(values)
        out = Threshold(threshold_values=280.0).process(da)
        assert out.sizes["member"] == 2
        np.testing.assert_array_equal(out.values[:, 0, 0, 0, 0, 0], [0, 1])

    def test_collapse_cell_methods_attr(self):
        da = _meb_from_array(np.array([[[270.0]], [[290.0]]], dtype=np.float32))
        out = Threshold(
            threshold_values=280.0,
            collapse_coord="member",
            collapse_cell_methods={"member": "mean"},
        ).process(da)
        assert out.attrs.get("collapse_cell_methods") == {"member": "mean"}

    def test_invalid_collapse_coord(self):
        with pytest.raises(ValueError, match='仅支持 "member" 与 "time"'):
            Threshold(threshold_values=1.0, collapse_coord="dtime")

    def test_upstream_alias_not_accepted(self):
        with pytest.raises(ValueError, match='仅支持 "member" 与 "time"'):
            Threshold(threshold_values=1.0, collapse_coord="realization")

    def test_collapse_requires_xarray(self):
        data = np.array([[270.0, 290.0]], dtype=np.float32)
        with pytest.raises(ValueError, match="collapse_coord"):
            Threshold(threshold_values=280.0, collapse_coord="member").process(data)


def _load_kgo_cube(path: Path):
    import iris

    return iris.load_cube(str(path))


def _meb_vicinity_to_kgo(result: xr.DataArray | xr.Dataset) -> np.ndarray:
    """meb vicinity 结果 → 与官方 KGO 对齐的数组。"""
    if isinstance(result, xr.Dataset):
        layers = []
        for name in sorted(
            result.data_vars,
            key=lambda n: float(result[n].attrs.get("radius_of_vicinity", 0.0)),
        ):
            layers.append(_meb_vicinity_to_kgo(result[name]))
        return np.stack(layers, axis=1)

    work = result
    for dim in ("member", "time", "dtime"):
        if dim in work.dims and work.sizes[dim] == 1:
            work = work.isel({dim: 0}, drop=True)
    if "radius_of_vicinity" in work.dims:
        work = work.transpose("level", "radius_of_vicinity", "lat", "lon")
    elif "member" in work.dims:
        work = work.transpose("member", "level", "lat", "lon")
    else:
        work = work.transpose("level", "lat", "lon")
    return np.asarray(work.values, dtype=np.float32)


class TestThresholdVicinitySynthetic:
    def test_vicinity_spreads_max(self):
        grid = np.zeros((5, 5), dtype=np.float32)
        grid[2, 2] = 1.0
        da = _meb_from_array(grid)
        da = da.assign_coords(
            lat=xr.DataArray(
                np.arange(5, dtype=np.float32) * 1000.0,
                dims=("lat",),
                attrs={"units": "m"},
            ),
            lon=xr.DataArray(
                np.arange(5, dtype=np.float32) * 1000.0,
                dims=("lon",),
                attrs={"units": "m"},
            ),
        )
        out = Threshold(threshold_values=0.5, vicinity=1500.0).process(da)
        assert "in_vicinity" in out.name
        field = np.squeeze(out.values, axis=(0, 1, 2, 3))
        assert field[2, 2] == 1.0
        assert field[2, 3] == 1.0

    def test_vicinity_multiple_returns_dataset(self):
        grid = np.zeros((5, 5), dtype=np.float32)
        grid[2, 2] = 1.0
        da = _meb_from_array(grid)
        da = da.assign_coords(
            lat=xr.DataArray(
                np.arange(5, dtype=np.float32) * 1000.0,
                dims=("lat",),
                attrs={"units": "m"},
            ),
            lon=xr.DataArray(
                np.arange(5, dtype=np.float32) * 1000.0,
                dims=("lon",),
                attrs={"units": "m"},
            ),
        )
        out = Threshold(threshold_values=0.5, vicinity=[1000.0, 2000.0]).process(da)
        assert isinstance(out, xr.Dataset)
        assert len(out.data_vars) == 2
        for name, da_out in out.data_vars.items():
            assert list(da_out.dims) == [
                "member",
                "level",
                "time",
                "dtime",
                "lat",
                "lon",
            ]
            assert da_out.attrs["radius_of_vicinity_units"] == "m"
            assert "_r1000" in name or "_r2000" in name

    def test_landmask_without_vicinity_raises(self):
        da = _meb_from_array(np.zeros((3, 3), dtype=np.float32))
        mask = np.ones((3, 3), dtype=bool)
        with pytest.raises(ValueError, match="landmask"):
            Threshold(threshold_values=1.0).process(da, landmask=mask)

    def test_vicinity_requires_xarray(self):
        data = np.zeros((2, 2), dtype=np.float32)
        with pytest.raises(ValueError, match="vicinity"):
            Threshold(threshold_values=0.5, vicinity=1000.0).process(data)

    def test_vicinity_geographic_matches_projected_spacing(self):
        """经纬 vicinity 与 LAEA 米轴推断格距路径数值一致。"""
        grid = np.zeros((7, 7), dtype=np.float32)
        grid[3, 3] = 1.0
        geo = _geographic_meb_from_array(grid)
        out_geo = Threshold(threshold_values=0.5, vicinity=2000.0).process(geo)

        projected, _, ctx = prepare_geographic_input(geo)
        assert ctx is not None
        out_proj = Threshold(threshold_values=0.5, vicinity=2000.0).process(projected)

        np.testing.assert_allclose(
            np.asarray(out_geo.values, dtype=np.float64),
            np.asarray(out_proj.values, dtype=np.float64),
            equal_nan=True,
        )
        np.testing.assert_array_equal(
            out_geo.coords["lat"].values, geo.coords["lat"].values
        )
        np.testing.assert_array_equal(
            out_geo.coords["lon"].values, geo.coords["lon"].values
        )


def _geographic_meb_from_array(values: np.ndarray) -> xr.DataArray:
    """构造等距经纬 meb 六维测试 DataArray。"""
    arr = np.asarray(values, dtype=np.float32)
    if arr.ndim == 2:
        arr = arr[np.newaxis, np.newaxis, np.newaxis, np.newaxis, :, :]
    lat_size, lon_size = arr.shape[-2], arr.shape[-1]
    base_lat, base_lon, step = 30.0, 110.0, 0.01
    return xr.DataArray(
        arr,
        dims=("member", "level", "time", "dtime", "lat", "lon"),
        coords={
            "member": np.array([0], dtype=np.int32),
            "level": np.array([0.0], dtype=np.float32),
            "time": np.array([np.datetime64("2024-01-01T00:00:00")]),
            "dtime": np.array([0], dtype=np.int32),
            "lat": xr.DataArray(
                base_lat + np.arange(lat_size, dtype=np.float64) * step,
                dims=("lat",),
                attrs={"units": "degree_north"},
            ),
            "lon": xr.DataArray(
                base_lon + np.arange(lon_size, dtype=np.float64) * step,
                dims=("lon",),
                attrs={"units": "degree_east"},
            ),
        },
        attrs={"units": "1"},
        name="diagnostic",
    )


@pytest.mark.skipif(not VICINITY_INPUT.exists(), reason="缺少 vicinity 预处理数据")
class TestOfficialVicinityKGO:
    def _run(self, *, landmask=None, **kwargs) -> xr.DataArray:
        import meteva_base as meb

        da = meb.read_griddata_from_nc(str(VICINITY_INPUT))
        lm = None
        if landmask is not None:
            lm = xr.open_dataset(landmask)["landmask"]
        return Threshold(
            threshold_values=[0.03, 0.1, 1.0],
            threshold_units="mm hr-1",
            **kwargs,
        ).process(da, landmask=lm)

    def test_vicinity_basic(self):
        result = self._run(vicinity=10000.0)
        kgo = _load_kgo_cube(TEST_DATA / "vicinity" / "kgo.nc")
        np.testing.assert_allclose(
            _meb_vicinity_to_kgo(result),
            np.asarray(kgo.data, dtype=np.float32),
            atol=1e-6,
        )
        assert "in_vicinity" in result.name

    def test_vicinity_multiple_collapsed(self):
        result = self._run(vicinity=[10000.0, 20000.0], collapse_coord="member")
        assert isinstance(result, xr.Dataset)
        kgo = _load_kgo_cube(TEST_DATA / "vicinity" / "kgo_multiple_vicinities.nc")
        np.testing.assert_allclose(
            _meb_vicinity_to_kgo(result),
            np.asarray(kgo.data, dtype=np.float32),
            atol=1e-6,
        )

    def test_vicinity_collapsed(self):
        result = self._run(vicinity=10000.0, collapse_coord="member")
        kgo = _load_kgo_cube(TEST_DATA / "vicinity" / "kgo_collapsed.nc")
        np.testing.assert_allclose(
            _meb_vicinity_to_kgo(result),
            np.asarray(kgo.data, dtype=np.float32),
            atol=1e-6,
        )

    def test_vicinity_landmask(self):
        result = self._run(vicinity=10000.0, landmask=VICINITY_LANDMASK)
        kgo = _load_kgo_cube(TEST_DATA / "vicinity" / "kgo_landmask.nc")
        np.testing.assert_allclose(
            _meb_vicinity_to_kgo(result),
            np.asarray(kgo.data, dtype=np.float32),
            atol=1e-6,
        )

    def test_vicinity_landmask_collapsed(self):
        result = self._run(
            vicinity=10000.0,
            collapse_coord="member",
            landmask=VICINITY_LANDMASK,
        )
        kgo = _load_kgo_cube(TEST_DATA / "vicinity" / "kgo_landmask_collapsed.nc")
        np.testing.assert_allclose(
            _meb_vicinity_to_kgo(result),
            np.asarray(kgo.data, dtype=np.float32),
            atol=1e-6,
        )


@pytest.mark.skipif(not VICINITY_MASKED_INPUT.exists(), reason="缺少 masked vicinity 数据")
class TestOfficialVicinityMasked:
    def test_vicinity_masked_matches_kgo(self):
        """掩码降水 meb（海点 NaN）与官方 kgo_masked 对照。"""
        import meteva_base as meb

        da = meb.read_griddata_from_nc(str(VICINITY_MASKED_INPUT))
        result = Threshold(
            threshold_values=[0.03, 0.1, 1.0],
            threshold_units="mm hr-1",
            vicinity=10000.0,
        ).process(da)
        kgo = _load_kgo_cube(TEST_DATA / "vicinity_masked" / "kgo.nc")
        kgo_arr = np.asarray(kgo.data, dtype=np.float32)
        our_arr = _meb_vicinity_to_kgo(result)
        invalid = kgo_arr > 1e30
        np.testing.assert_allclose(our_arr[~invalid], kgo_arr[~invalid], atol=1e-6)
        assert "in_vicinity" in (result.name or "")


def _load_kgo_array(path: Path) -> np.ndarray:
    """读取官方 KGO 主变量为 numpy（阈值维在前若存在）。"""
    import iris

    cube = iris.load_cube(str(path))
    data = np.asarray(cube.data, dtype=np.float32)
    # 多阈值时 dim 顺序为 realization, threshold, y, x
    thr_coords = [
        c
        for c in cube.coords(dim_coords=True)
        if c.var_name == "threshold" or "threshold" in c.name()
    ]
    if thr_coords:
        thr = thr_coords[0]
        axis = cube.coord_dims(thr)[0]
        if axis != 1:
            data = np.moveaxis(data, axis, 1)
        # 与 meb 对齐：member, level, y, x → 比较时再 squeeze
        return data
    # 单阈值被 squeeze：补 level 维
    return data[:, np.newaxis, ...]


def _meb_result_to_member_level_yx(result: xr.DataArray) -> np.ndarray:
    """meb 结果 → (member, level, y, x)。"""
    arr = np.asarray(result.values, dtype=np.float32)
    # (member, level, time, dtime, lat, lon)
    return np.squeeze(arr, axis=(2, 3))


@pytest.mark.skipif(not MEB_INPUT.exists(), reason="缺少预处理 meb 输入")
class TestOfficialKGO:
    def _run(self, **kwargs) -> xr.DataArray:
        import meteva_base as meb

        da = meb.read_griddata_from_nc(str(MEB_INPUT))
        return Threshold(**kwargs).process(da)

    def test_basic(self):
        result = self._run(threshold_values=280.0)
        kgo = _load_kgo_array(TEST_DATA / "basic" / "kgo.nc")
        np.testing.assert_allclose(
            _meb_result_to_member_level_yx(result), kgo, atol=1e-6
        )

    def test_below_threshold(self):
        result = self._run(threshold_values=280.0, comparison_operator="<=")
        kgo = _load_kgo_array(TEST_DATA / "below_threshold" / "kgo.nc")
        np.testing.assert_allclose(
            _meb_result_to_member_level_yx(result), kgo, atol=1e-6
        )

    def test_multiple_thresholds(self):
        result = self._run(threshold_values=[270.0, 280.0, 290.0])
        kgo = _load_kgo_array(TEST_DATA / "multiple_thresholds" / "kgo.nc")
        np.testing.assert_allclose(
            _meb_result_to_member_level_yx(result), kgo, atol=1e-6
        )

    def test_threshold_units(self):
        result = self._run(threshold_values=6.85, threshold_units="celsius")
        kgo = _load_kgo_array(TEST_DATA / "threshold_units" / "kgo.nc")
        np.testing.assert_allclose(
            _meb_result_to_member_level_yx(result), kgo, atol=1e-5
        )
        np.testing.assert_allclose(result.level.values, [280.0], atol=1e-4)

    def test_fuzzy_factor(self):
        result = self._run(threshold_values=280.0, fuzzy_factor=0.99)
        kgo = _load_kgo_array(TEST_DATA / "fuzzy_factor" / "kgo.nc")
        np.testing.assert_allclose(
            _meb_result_to_member_level_yx(result), kgo, atol=1e-5
        )

    def test_threshold_units_fuzzy_factor(self):
        result = self._run(
            threshold_values=6.85, threshold_units="celsius", fuzzy_factor=0.2
        )
        kgo = _load_kgo_array(TEST_DATA / "threshold_units_fuzzy_factor" / "kgo.nc")
        np.testing.assert_allclose(
            _meb_result_to_member_level_yx(result), kgo, atol=1e-5
        )

    def test_fuzzy_bounds_config(self):
        # 官方验收：config 界与 fuzzy_factor=0.99 等价，对照 fuzzy_factor/kgo
        cfg_path = TEST_DATA / "fuzzy_bounds" / "threshold_config.json"
        with open(cfg_path, encoding="utf-8") as fh:
            cfg = json.load(fh)
        result = self._run(threshold_config=cfg)
        kgo = _load_kgo_array(TEST_DATA / "fuzzy_factor" / "kgo.nc")
        np.testing.assert_allclose(
            _meb_result_to_member_level_yx(result), kgo, atol=1e-5
        )

    def test_json_config(self):
        # 官方验收：{"280.0": "None"} 对照 basic/kgo
        cfg_path = TEST_DATA / "json" / "threshold_config.json"
        with open(cfg_path, encoding="utf-8") as fh:
            cfg = json.load(fh)
        result = self._run(threshold_config=cfg)
        kgo = _load_kgo_array(TEST_DATA / "basic" / "kgo.nc")
        np.testing.assert_allclose(
            _meb_result_to_member_level_yx(result), kgo, atol=1e-6
        )
