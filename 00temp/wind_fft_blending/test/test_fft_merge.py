# -*- coding: utf-8 -*-
"""FFTMergePlugin 核心算法单元测试。"""
import sys
from pathlib import Path

import numpy as np
import pytest

_REPO = Path(__file__).resolve().parents[1]
_SRC = _REPO / "src"
_TEST_DATA = (
    _REPO.parents[1].parent
    / "NIMM_pip_testdata"
    / "multi_wind_fft_blending"
    / "test_data"
)

for _p in (str(_REPO), str(_SRC)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from src import fft_merge  # noqa: E402
from meteva import base as meb  # noqa: E402


def _load_sample_uv(sample: str = "a"):
    uv1_path = _TEST_DATA / f"sample_{sample}1_uv.m11"
    uv2_path = _TEST_DATA / f"sample_{sample}2_uv.m11"
    if not (uv1_path.is_file() and uv2_path.is_file()):
        pytest.skip(f"缺少示例数据: {uv1_path} / {uv2_path}")
    uv1 = meb.read_gridwind_from_micaps11(str(uv1_path))
    uv2 = meb.read_gridwind_from_micaps11(str(uv2_path))
    return uv1, uv2


def _crop_da(da, nlat=32, nlon=32):
    return da.isel(lat=slice(0, nlat), lon=slice(0, nlon))


def test_move_percent_validation():
    plugin = fft_merge.FFTMergePlugin()
    main_da, ass_da = _load_sample_uv("a")
    main_da = _crop_da(main_da)
    ass_da = _crop_da(ass_da)
    with pytest.raises(ValueError):
        plugin(main_da, [ass_da], move_percent=0.0, feature_border=32, max_iterations=16)
    with pytest.raises(ValueError):
        plugin(main_da, [ass_da], move_percent=1.5, feature_border=32, max_iterations=16)


def test_uv_merge_output_shape():
    plugin = fft_merge.FFTMergePlugin()
    main_da, ass_da = _load_sample_uv("a")
    main_da = _crop_da(main_da)
    ass_da = _crop_da(ass_da)
    result = plugin(main_da, [ass_da], feature_border=32, max_iterations=32)
    assert result.shape == main_da.shape
    assert list(result.coords["member"].values) == ["u", "v"]


def test_move_percent_accepts_valid_range():
    plugin = fft_merge.FFTMergePlugin()
    main_da, ass_da = _load_sample_uv("b")
    main_da = _crop_da(main_da, 64, 64)
    ass_da = _crop_da(ass_da, 64, 64)
    result = plugin(main_da, [ass_da], feature_border=64, max_iterations=16, move_percent=0.5)
    assert result.shape == main_da.shape


def test_multiple_assist_fields():
    plugin = fft_merge.FFTMergePlugin()
    main_da, ass1 = _load_sample_uv("a")
    _, ass2 = _load_sample_uv("b")
    main_da = _crop_da(main_da, 64, 64)
    ass1 = _crop_da(ass1, 64, 64)
    ass2 = _crop_da(ass2, 64, 64)
    result = plugin(main_da, [ass1, ass2], feature_border=64, max_iterations=16)
    assert result.shape == main_da.shape


def test_plugin_returns_finite_values():
    plugin = fft_merge.FFTMergePlugin()
    main_da, ass_da = _load_sample_uv("a")
    main_da = _crop_da(main_da, 64, 64)
    ass_da = _crop_da(ass_da, 64, 64)
    result = plugin(main_da, [ass_da], feature_border=64, max_iterations=32)
    values = result.values
    assert np.isfinite(values[np.isfinite(main_da.values)]).all()


if __name__ == "__main__":
    test_move_percent_validation()
    test_uv_merge_output_shape()
    test_move_percent_accepts_valid_range()
    test_multiple_assist_fields()
    test_plugin_returns_finite_values()
    print("all tests passed")
