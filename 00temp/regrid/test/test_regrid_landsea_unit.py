#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""RegridLandSea 合成单元测试（对齐上游 test_RegridLandSea 行为）。"""

from __future__ import annotations

import numpy as np
import pytest
import xarray as xr

from regrid import RegridLandSea
from regrid.test.helpers import make_meb6d, to_compare_array


def _latlon_source_target(*, fine: bool = False):
    """构造粗/细经纬源场与目标场（常数场便于断言）。

    fine=True 时格距更小，便于海陆 vicinity（米）换算到至少 1 个格点。
    """
    if fine:
        src_lats = np.linspace(50.0, 52.0, 21, dtype=np.float32)
        src_lons = np.linspace(-2.0, 2.0, 21, dtype=np.float32)
        tgt_lats = np.linspace(50.2, 51.8, 17, dtype=np.float32)
        tgt_lons = np.linspace(-1.8, 1.8, 17, dtype=np.float32)
        src_shape = (21, 21)
        tgt_shape = (17, 17)
    else:
        src_lats = np.linspace(40.0, 60.0, 11, dtype=np.float32)
        src_lons = np.linspace(-10.0, 10.0, 11, dtype=np.float32)
        tgt_lats = np.linspace(42.0, 58.0, 9, dtype=np.float32)
        tgt_lons = np.linspace(-8.0, 8.0, 9, dtype=np.float32)
        src_shape = (11, 11)
        tgt_shape = (9, 9)

    src = make_meb6d(
        np.full(src_shape, 282.0, dtype=np.float32),
        lats=src_lats,
        lons=src_lons,
        name="air_temperature",
        attrs={
            "mosg__grid_type": "standard",
            "mosg__grid_version": "1.0.0",
            "mosg__grid_domain": "gl_det",
        },
    )
    tgt = make_meb6d(
        np.zeros(tgt_shape, dtype=np.float32),
        lats=tgt_lats,
        lons=tgt_lons,
        name="land_binary_mask",
        units="1",
        attrs={
            "mosg__grid_type": "standard",
            "mosg__grid_version": "1.2.0",
            "mosg__grid_domain": "uk_det",
        },
    )
    landmask = make_meb6d(
        np.zeros(src_shape, dtype=np.float32),
        lats=src_lats,
        lons=src_lons,
        name="land_binary_mask",
        units="1",
    )
    return src, tgt, landmask


class TestInit:
    def test_error_unrecognised_regrid_mode(self):
        with pytest.raises(ValueError, match="Unrecognised regrid mode"):
            RegridLandSea(regrid_mode="kludge")

    def test_error_missing_landmask(self):
        with pytest.raises(ValueError, match="requires an input landmask"):
            RegridLandSea(regrid_mode="nearest-with-mask")

    def test_error_unrecognised_extrapolation_mode(self):
        """非法 extrapolation_mode 在真正插值时（regrid_rectilinear）才校验。"""
        src, tgt, _ = _latlon_source_target()
        plugin = RegridLandSea(extrapolation_mode="not-a-mode")
        with pytest.raises(ValueError, match="Unrecognised extrapolation_mode"):
            plugin(src, tgt)


class TestProcess:
    def test_basic_regrid_shape_and_value(self):
        src, tgt, _ = _latlon_source_target()
        result = RegridLandSea(regrid_mode="bilinear")(src, tgt)
        out = to_compare_array(result)
        assert out.shape == (9, 9)
        np.testing.assert_allclose(out, 282.0, atol=1e-4)
        np.testing.assert_allclose(result.coords["lat"].values, tgt.coords["lat"].values)
        np.testing.assert_allclose(result.coords["lon"].values, tgt.coords["lon"].values)

    def test_extrapolation_error_raises_when_target_outside_source(self):
        """error：目标点越出源域时应抛错（对齐 Iris）。"""
        src, _, _ = _latlon_source_target()
        # 目标网格整体落在源域之外
        outside = make_meb6d(
            np.zeros((5, 5), dtype=np.float32),
            lats=np.linspace(70.0, 75.0, 5, dtype=np.float32),
            lons=np.linspace(20.0, 25.0, 5, dtype=np.float32),
            name="land_binary_mask",
            units="1",
        )
        plugin = RegridLandSea(regrid_mode="nearest", extrapolation_mode="error")
        with pytest.raises(ValueError):
            plugin(src, outside)

    def test_extrapolation_nanmask_fills_outside_with_nan(self):
        """nanmask：域外填 NaN。"""
        src, _, _ = _latlon_source_target()
        outside = make_meb6d(
            np.zeros((5, 5), dtype=np.float32),
            lats=np.linspace(70.0, 75.0, 5, dtype=np.float32),
            lons=np.linspace(20.0, 25.0, 5, dtype=np.float32),
            name="land_binary_mask",
            units="1",
        )
        result = RegridLandSea(regrid_mode="nearest", extrapolation_mode="nanmask")(
            src, outside
        )
        assert np.all(np.isnan(to_compare_array(result)))

    def test_extrapolation_extrapolate_fills_outside(self):
        """extrapolate：域外外推为有限值。"""
        src, _, _ = _latlon_source_target()
        outside = make_meb6d(
            np.zeros((5, 5), dtype=np.float32),
            lats=np.linspace(70.0, 75.0, 5, dtype=np.float32),
            lons=np.linspace(20.0, 25.0, 5, dtype=np.float32),
            name="land_binary_mask",
            units="1",
        )
        result = RegridLandSea(regrid_mode="nearest", extrapolation_mode="extrapolate")(
            src, outside
        )
        out = to_compare_array(result)
        assert np.all(np.isfinite(out))
        np.testing.assert_allclose(out, 282.0, atol=1e-4)

    def test_title_default_and_custom(self):
        src, tgt, _ = _latlon_source_target()
        default = RegridLandSea()(src, tgt)
        assert default.attrs.get("title") == "unknown"

        custom = RegridLandSea()(src, tgt, regridded_title="demo title")
        # PostProcessingPlugin 会在 title 前加 Post-Processed 前缀
        assert custom.attrs.get("title") == "Post-Processed demo title"

    def test_mosg_grid_attributes_inherited_from_target(self):
        src, tgt, _ = _latlon_source_target()
        result = RegridLandSea()(src, tgt)
        assert result.attrs.get("mosg__grid_domain") == "uk_det"
        assert result.attrs.get("mosg__grid_version") == "1.2.0"
        assert result.attrs.get("mosg__grid_type") == "standard"

    def test_mosg_attribute_removed_if_absent_on_target(self):
        src, tgt, _ = _latlon_source_target()
        tgt = tgt.copy(deep=True)
        tgt.attrs.pop("mosg__grid_domain", None)
        result = RegridLandSea()(src, tgt)
        assert "mosg__grid_domain" not in result.attrs

    def test_error_landmask_grid_mismatch(self):
        src, tgt, _ = _latlon_source_target(fine=True)
        wrong_mask = tgt.copy(deep=True)
        wrong_mask.name = "land_binary_mask"
        plugin = RegridLandSea(
            regrid_mode="nearest-with-mask",
            landmask=wrong_mask,
            landmask_vicinity=90000,
        )
        with pytest.raises(ValueError, match="Source landmask does not match input grid"):
            plugin(src, tgt)

    def test_zero_vicinity_cells_raises(self):
        """粗经纬网格上过小 vicinity 换算格点数为 0，应报错。"""
        src, tgt, landmask = _latlon_source_target()
        with pytest.raises(ValueError, match="gives zero cell extent"):
            RegridLandSea(
                regrid_mode="nearest-with-mask",
                landmask=landmask,
                landmask_vicinity=1000,
            )(src, tgt)

    def test_nearest_with_mask_constant_field(self):
        src, tgt, landmask = _latlon_source_target(fine=True)
        result = RegridLandSea(
            regrid_mode="nearest-with-mask",
            landmask=landmask,
            landmask_vicinity=90000,
        )(src, tgt)
        np.testing.assert_allclose(to_compare_array(result), 282.0, atol=1e-4)

    def test_warning_source_not_landmask_name(self):
        src, tgt, landmask = _latlon_source_target(fine=True)
        landmask = landmask.copy(deep=True)
        landmask.name = "not_a_landmask"
        with pytest.warns(UserWarning, match="Expected land_binary_mask in input_landmask"):
            result = RegridLandSea(
                regrid_mode="nearest-with-mask",
                landmask=landmask,
                landmask_vicinity=90000,
            )(src, tgt)
        np.testing.assert_allclose(to_compare_array(result), 282.0, atol=1e-4)

    def test_warning_target_not_landmask_name(self):
        src, tgt, landmask = _latlon_source_target(fine=True)
        tgt = tgt.copy(deep=True)
        tgt.name = "not_a_landmask"
        with pytest.warns(UserWarning, match="Expected land_binary_mask in target_grid"):
            result = RegridLandSea(
                regrid_mode="nearest-with-mask",
                landmask=landmask,
                landmask_vicinity=90000,
            )(src, tgt)
        np.testing.assert_allclose(to_compare_array(result), 282.0, atol=1e-4)

    def test_multi_member_preserved(self):
        src, tgt, _ = _latlon_source_target()
        values = np.stack(
            [
                np.full((11, 11), 280.0, dtype=np.float32),
                np.full((11, 11), 282.0, dtype=np.float32),
                np.full((11, 11), 284.0, dtype=np.float32),
            ],
            axis=0,
        )[:, np.newaxis, np.newaxis, np.newaxis, :, :]
        src_multi = xr_like_replace(src, values, member=np.array([0, 1, 2], dtype=np.int32))

        result = RegridLandSea(regrid_mode="nearest")(src_multi, tgt)
        assert result.sizes["member"] == 3
        out = np.asarray(result.values)
        np.testing.assert_allclose(out[0, 0, 0, 0], 280.0, atol=1e-4)
        np.testing.assert_allclose(out[1, 0, 0, 0], 282.0, atol=1e-4)
        np.testing.assert_allclose(out[2, 0, 0, 0], 284.0, atol=1e-4)


def xr_like_replace(template, values, member):
    """按模板坐标重建带多 member 的场。"""
    return xr.DataArray(
        values,
        dims=("member", "level", "time", "dtime", "lat", "lon"),
        coords={
            "member": member,
            "level": template.coords["level"],
            "time": template.coords["time"],
            "dtime": template.coords["dtime"],
            "lat": template.coords["lat"],
            "lon": template.coords["lon"],
        },
        name=template.name,
        attrs=dict(template.attrs),
    )
