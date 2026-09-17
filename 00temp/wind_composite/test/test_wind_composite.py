"""风速风向合成插件的单元测试。"""

import numpy as np
import pytest
import meteva_base as meb

from grid_utils import GRID_ATTRS, GRID_DIMS
from wind_composite import (
    ComputeWindDirection,
    ComputeWindSpeed,
    gust_factor,
    wind_direction,
    wind_speed,
)


def make_grid(values, member="ec"):
    """构造一个 2x2 的 meb 标准网格，便于断言具体数值。"""
    grid = meb.grid([100, 101, 1], [30, 31, 1], gtime=["2024010108"],
                    dtime_list=[0], level_list=[850], member_list=[member])
    return meb.grid_data(grid, np.asarray(values, dtype=np.float32))


def test_wind_speed_pythagorean():
    """3、4 分量应合成为 5 m/s。"""
    assert wind_speed(np.array([3.0]), np.array([4.0]))[0] == pytest.approx(5.0)


def test_wind_direction_cardinals():
    """四个基本风向的来向应分别为 0/90/180/270 度。"""
    u = np.array([0.0, -1.0, 0.0, 1.0])
    v = np.array([-1.0, 0.0, 1.0, 0.0])
    assert wind_direction(u, v) == pytest.approx([0.0, 90.0, 180.0, 270.0])


def test_process_returns_standard_griddata():
    """输出应保持 meb 六维结构并补齐六项属性。"""
    u = make_grid([[3.0, 3.0], [3.0, 3.0]])
    v = make_grid([[4.0, 4.0], [4.0, 4.0]])

    out = ComputeWindSpeed().process(u, v)

    assert out.dims == GRID_DIMS
    assert out.shape == u.shape
    assert set(GRID_ATTRS).issubset(out.attrs)
    assert out.attrs["units"] == "m/s"
    assert out.coords["member"].values.tolist() == ["wind_speed"]
    assert np.asarray(out).ravel() == pytest.approx([5.0] * 4)


def test_process_applies_calm_threshold():
    """低于静风阈值的格点应被置 0。"""
    u = make_grid([[0.1, 0.1], [2.0, 2.0]])
    v = make_grid([[0.1, 0.1], [2.0, 2.0]])

    out = ComputeWindSpeed().process(u, v)

    flat = np.asarray(out).ravel()
    assert flat[0] == pytest.approx(0.0)
    assert flat[2] == pytest.approx(np.sqrt(8.0), rel=1e-6)


def test_direction_process_keeps_coords():
    """风向插件应沿用输入坐标，并改写 member 与单位。"""
    u = make_grid([[0.0, 0.0], [0.0, 0.0]])
    v = make_grid([[-1.0, -1.0], [-1.0, -1.0]])

    out = ComputeWindDirection().process(u, v)

    assert out.attrs["units"] == "degree"
    assert out.coords["member"].values.tolist() == ["wind_direction"]
    assert np.asarray(out).ravel() == pytest.approx([0.0] * 4)
    assert out.coords["lon"].values.tolist() == u.coords["lon"].values.tolist()


def test_gust_factor_scales_speed():
    """阵风系数应按比例放大风速。"""
    assert gust_factor(np.array([10.0]))[0] == pytest.approx(13.5)
