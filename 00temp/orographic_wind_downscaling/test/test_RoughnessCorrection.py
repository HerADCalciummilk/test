import numpy as np
import pytest
import meteva_base as meb

from orographic_wind_downscaling.src.wind_downscaling import RoughnessCorrection


def create_dummy_data(n_lat=3, n_lon=4, n_levels=5):
    """生成模拟的辅助数据（粗糙度、地形等）和风速/高度场。"""
    np.random.seed(42)
    # 辅助数据（2D）
    a_over_s = np.random.rand(n_lat, n_lon).astype(np.float32)
    sigma = np.random.rand(n_lat, n_lon).astype(np.float32) * 100  # 米
    pporo = np.random.rand(n_lat, n_lon).astype(np.float32) * 500  # 米
    modoro = np.random.rand(n_lat, n_lon).astype(np.float32) * 500  # 米
    z0 = np.random.rand(n_lat, n_lon).astype(np.float32) * 0.5  # 米

    # 为模拟海陆区分：将部分点设为海洋（sigma=0，a_over_s=0）
    a_over_s[0, 0] = 0.0
    sigma[0, 0] = 0.0
    # 另一个海洋点
    a_over_s[-1, -1] = 0.0
    sigma[-1, -1] = 0.0

    modres = 4000.0  # 模型分辨率 4km
    ppres = 1000.0  # 后处理分辨率 1km

    # 风速场：形状 (batch, levels, lat, lon) 或 (levels, lat, lon)
    # 简单构造：随高度线性增加，再加一些随机扰动
    base_speed = 5.0
    height_factor = 0.1
    wind_speed = np.zeros((6, n_levels, n_lat, n_lon), dtype=np.float32)

    for l in range(6):
        for k in range(n_levels):
            wind_speed[l][k] = base_speed + k * height_factor + l * height_factor
    # 添加小扰动
    wind_speed += np.random.randn(6, n_levels, n_lat, n_lon).astype(np.float32) * 0.1

    # 高度网格：可以返回1D或3D版本
    height_1d = np.linspace(10, 500, n_levels, dtype=np.float32)  # 米

    # 3D高度：在1D基础上加入空间变化
    height_3d = height_1d[:, np.newaxis, np.newaxis] + np.random.randn(n_levels, n_lat, n_lon).astype(np.float32) * 5

    return {
        'a_over_s': a_over_s,
        'sigma': sigma,
        'pporo': pporo,
        'modoro': modoro,
        'z0': z0,
        'modres': modres,
        'ppres': ppres,
        'wind_speed': wind_speed,
        'height_1d': height_1d,
        'height_3d': height_3d,
        'n_lat': n_lat,
        'n_lon': n_lon,
        'n_levels': n_levels,
    }


class TestRoughnessCorrection:
    """测试 RoughnessCorrection 类的功能"""

    @pytest.fixture
    def dummy_data(self):
        """生成模拟数据的 fixture"""
        return create_dummy_data()

    @pytest.fixture
    def roughness_correction(self, dummy_data):
        """创建 RoughnessCorrection 实例的 fixture"""
        # 创建纬度坐标
        lat_points = np.linspace(60, 70, dummy_data['n_lat'])
        # 创建经度坐标
        lon_points = np.linspace(70, 80, dummy_data['n_lon'], endpoint=False)

        xres = (np.diff(lat_points)).mean()
        yres = (np.diff(lon_points)).mean()

        return RoughnessCorrection(
            a_over_s=dummy_data['a_over_s'],
            sigma=dummy_data['sigma'],
            pporo=dummy_data['pporo'],
            modoro=dummy_data['modoro'],
            z0=dummy_data['z0'],
            modres=dummy_data['modres'],
            ppres=(abs(xres) + abs(yres)) / 2.0
        )

    def test_basic_rc_hc(self, dummy_data, roughness_correction):
        """测试基础粗糙度和高度修正，使用默认的level/lat/lon轴。"""
        # 使用1D高度网格
        corrected1 = roughness_correction.process(dummy_data['wind_speed'], dummy_data['height_1d'])

        # 验证输出形状
        assert corrected1.shape == dummy_data[
            'wind_speed'].shape, f"输出形状不匹配: {corrected1.shape} != {dummy_data['wind_speed'].shape}"

        # 验证输出值
        assert not np.isnan(corrected1).any(), "输出包含 NaN 值"
        assert (corrected1 >= 0).all(), "输出包含负值"

    def test_with_grid_data(self, dummy_data, roughness_correction):
        """测试使用 grid_data 作为输入"""
        # 先添加缺失的维度
        wind_speed_reshaped = dummy_data['wind_speed'][np.newaxis, :, np.newaxis, :, :, :]
        # 调整维度顺序到 (member, level, time, dtime, lat, lon)
        wind_speed_reshaped = wind_speed_reshaped.transpose(0, 3, 2, 1, 4, 5)

        # 创建网格对象
        grid0 = meb.grid([70, 77.5, 2.5], [60, 70, 5],
                         dtime_list=[0, 1, 2, 3, 4, 5],
                         level_list=dummy_data['height_1d'])

        # 使用调整好顺序的数据创建 grid_data
        wind_speed_grid = meb.grid_data(grid0, wind_speed_reshaped)

        # 调整维度顺序
        wind_speed_grid = wind_speed_grid.transpose('member', 'time', 'dtime', 'level', 'lat', 'lon')

        # 处理数据
        corrected2 = roughness_correction.process(wind_speed_grid, dummy_data['height_1d'])

        # 验证输出形状：DataArray 输入返回 meteva_base 六维结构
        expected_shape = (1, 5, 1, 6, 3, 4)
        assert corrected2.shape == expected_shape, f"输出形状不匹配: {corrected2.shape} != {expected_shape}"

        # 验证输出值
        assert not np.isnan(corrected2).any(), "输出包含 NaN 值"
        assert (corrected2 >= 0).all(), "输出包含负值"

    def test_with_3d_height(self, dummy_data, roughness_correction):
        """测试使用3D高度网格"""
        # 使用3D高度网格
        corrected = roughness_correction.process(dummy_data['wind_speed'], dummy_data['height_3d'])

        # 验证输出形状
        assert corrected.shape == dummy_data[
            'wind_speed'].shape, f"输出形状不匹配: {corrected.shape} != {dummy_data['wind_speed'].shape}"

        # 验证输出值
        assert not np.isnan(corrected).any(), "输出包含 NaN 值"
        assert (corrected >= 0).all(), "输出包含负值"

    def test_without_z0(self, dummy_data):
        """测试不提供 z0 参数的情况"""
        # 创建纬度坐标
        lat_points = np.linspace(60, 70, dummy_data['n_lat'])
        # 创建经度坐标
        lon_points = np.linspace(70, 80, dummy_data['n_lon'], endpoint=False)

        xres = (np.diff(lat_points)).mean()
        yres = (np.diff(lon_points)).mean()

        # 创建不包含 z0 的实例
        rc = RoughnessCorrection(
            a_over_s=dummy_data['a_over_s'],
            sigma=dummy_data['sigma'],
            pporo=dummy_data['pporo'],
            modoro=dummy_data['modoro'],
            z0=None,  # 不提供 z0
            modres=dummy_data['modres'],
            ppres=(abs(xres) + abs(yres)) / 2.0
        )

        # 处理数据
        corrected = rc.process(dummy_data['wind_speed'], dummy_data['height_1d'])

        # 验证输出形状
        assert corrected.shape == dummy_data[
            'wind_speed'].shape, f"输出形状不匹配: {corrected.shape} != {dummy_data['wind_speed'].shape}"

        # 验证输出值
        assert not np.isnan(corrected).any(), "输出包含 NaN 值"
        assert (corrected >= 0).all(), "输出包含负值"

    def test_edge_case_minimal_grid(self):
        """测试最小格点（1×1×1）可正常处理。"""
        n_lat, n_lon, n_levels = 1, 1, 1

        a_over_s = np.random.rand(n_lat, n_lon).astype(np.float32)
        sigma = np.random.rand(n_lat, n_lon).astype(np.float32) * 100
        pporo = np.random.rand(n_lat, n_lon).astype(np.float32) * 500
        modoro = np.random.rand(n_lat, n_lon).astype(np.float32) * 500
        z0 = np.random.rand(n_lat, n_lon).astype(np.float32) * 0.5

        wind_speed = np.random.rand(1, n_levels, n_lat, n_lon).astype(np.float32)
        height_1d = np.linspace(10, 500, n_levels, dtype=np.float32)

        rc = RoughnessCorrection(
            a_over_s=a_over_s,
            sigma=sigma,
            pporo=pporo,
            modoro=modoro,
            z0=z0,
            modres=4000.0,
            ppres=1000.0,
        )
        corrected = rc.process(wind_speed, height_1d)

        assert corrected.shape == wind_speed.shape
        assert not np.isnan(corrected).any()
        assert (corrected >= 0).all()


if __name__ == '__main__':
    pytest.main(['-v', __file__])
