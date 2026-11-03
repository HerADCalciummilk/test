import numpy as np
import pytest

from orographic_wind_downscaling.src.wind_downscaling import (
    RoughnessCorrectionUtilities,
    RMDI,
    Z0M_SEA,
)


def create_dummy_utilities_data(n_lat=3, n_lon=4):
    """生成模拟的辅助数据，用于测试 RoughnessCorrectionUtilities 类。"""
    np.random.seed(42)
    
    # 辅助数据（2D）
    a_over_s = np.random.rand(n_lat, n_lon).astype(np.float32)
    sigma = np.random.rand(n_lat, n_lon).astype(np.float32) * 100  # 米
    pporo = np.random.rand(n_lat, n_lon).astype(np.float32) * 500  # 米
    modoro = np.random.rand(n_lat, n_lon).astype(np.float32) * 500  # 米
    z0 = np.random.rand(n_lat, n_lon).astype(np.float32) * 0.5      # 米

    # 为模拟海陆区分：将部分点设为海洋（sigma=0，a_over_s=0）
    a_over_s[0, 0] = 0.0
    sigma[0, 0] = 0.0
    # 另一个海洋点
    a_over_s[-1, -1] = 0.0
    sigma[-1, -1] = 0.0

    modres = 4000.0   # 模型分辨率 4km
    ppres = 1000.0    # 后处理分辨率 1km

    return {
        'a_over_s': a_over_s,
        'sigma': sigma,
        'pporo': pporo,
        'modoro': modoro,
        'z0': z0,
        'modres': modres,
        'ppres': ppres,
        'n_lat': n_lat,
        'n_lon': n_lon,
    }


def create_dummy_wind_data(n_lat=3, n_lon=4, n_levels=5):
    """生成模拟的风速和高度数据。"""
    # 风速场：形状 (lat, lon, levels)
    base_speed = 5.0
    height_factor = 0.1
    wind_speed = np.zeros((n_lat, n_lon, n_levels), dtype=np.float32)

    for k in range(n_levels):
        wind_speed[:, :, k] = base_speed + k * height_factor
    # 添加小扰动
    wind_speed += np.random.randn(n_lat, n_lon, n_levels).astype(np.float32) * 0.1

    # 高度网格：1D 版本
    height_1d = np.linspace(10, 500, n_levels, dtype=np.float32)  # 米

    # 3D 高度：在 1D 基础上加入空间变化
    height_3d = height_1d[np.newaxis, np.newaxis, :] + np.random.randn(n_lat, n_lon, n_levels).astype(np.float32) * 5

    return {
        'wind_speed': wind_speed,
        'height_1d': height_1d,
        'height_3d': height_3d,
        'n_levels': n_levels,
    }


class TestRoughnessCorrectionUtilities:
    """测试 RoughnessCorrectionUtilities 类的功能"""
    
    @pytest.fixture
    def utilities_data(self):
        """生成模拟数据的 fixture"""
        return create_dummy_utilities_data()
    
    @pytest.fixture
    def wind_data(self):
        """生成模拟风速数据的 fixture"""
        return create_dummy_wind_data()
    
    @pytest.fixture
    def utilities(self, utilities_data):
        """创建 RoughnessCorrectionUtilities 实例的 fixture"""
        return RoughnessCorrectionUtilities(
            a_over_s=utilities_data['a_over_s'],
            sigma=utilities_data['sigma'],
            z_0=utilities_data['z0'],
            pporo=utilities_data['pporo'],
            modoro=utilities_data['modoro'],
            ppres=utilities_data['ppres'],
            modres=utilities_data['modres']
        )
    
    def test_init(self, utilities, utilities_data):
        """测试初始化方法"""
        # 验证属性是否正确设置
        assert np.array_equal(utilities.a_over_s, utilities_data['a_over_s'])
        assert np.array_equal(utilities.z_0, utilities_data['z0'])
        assert np.array_equal(utilities.pporo, utilities_data['pporo'])
        assert np.array_equal(utilities.modoro, utilities_data['modoro'])
        
        # 验证计算的属性
        assert utilities.h_over_2.shape == utilities_data['sigma'].shape
        assert utilities.hcmask.shape == utilities_data['sigma'].shape
        assert utilities.rcmask.shape == utilities_data['sigma'].shape
        assert utilities.wavenum.shape == utilities_data['sigma'].shape
        assert utilities.h_ref.shape == utilities_data['sigma'].shape
        assert utilities.h_at0.shape == utilities_data['sigma'].shape
    
    def test_sigma2hover2(self, utilities):
        """测试 sigma2hover2 静态方法"""
        # 测试正常情况
        sigma = np.array([[1.0, 2.0], [3.0, 0.0]], dtype=np.float32)
        expected = np.array([[np.sqrt(2), 2*np.sqrt(2)], [3*np.sqrt(2), RMDI]], dtype=np.float32)
        result = RoughnessCorrectionUtilities.sigma2hover2(sigma)
        assert np.allclose(result, expected)
    
    def test_setmask(self, utilities):
        """测试 _setmask 方法"""
        # 验证掩码形状
        assert utilities.hcmask.shape == utilities.a_over_s.shape
        assert utilities.rcmask.shape == utilities.a_over_s.shape
        
        # 验证海洋点被正确标记为 False
        assert not utilities.hcmask[0, 0]  # 海洋点
        assert not utilities.hcmask[-1, -1]  # 海洋点
        assert not utilities.rcmask[0, 0]  # 海洋点
        assert not utilities.rcmask[-1, -1]  # 海洋点
    
    def test_refinemask(self, utilities):
        """测试 _refinemask 方法"""
        # 验证方法执行后掩码仍然有效
        assert utilities.hcmask.shape == utilities.a_over_s.shape
    
    def test_calc_wav(self, utilities):
        """测试 _calc_wav 方法"""
        # 验证波数数组形状
        assert utilities.wavenum.shape == utilities.a_over_s.shape
        
        # 验证海洋点的波数为 RMDI
        assert utilities.wavenum[0, 0] == RMDI
        assert utilities.wavenum[-1, -1] == RMDI
    
    def test_calc_h_ref(self, utilities):
        """测试 _calc_h_ref 方法"""
        # 验证参考高度数组形状
        assert utilities.h_ref.shape == utilities.a_over_s.shape
        
        # 验证海洋点的参考高度为 0
        assert utilities.h_ref[0, 0] == 0
        assert utilities.h_ref[-1, -1] == 0
    
    def test_delta_height(self, utilities):
        """测试 _delta_height 方法"""
        # 验证高度差数组形状
        assert utilities.h_at0.shape == utilities.a_over_s.shape
    
    def test_calc_roughness_correction(self, utilities, wind_data):
        """测试 calc_roughness_correction 方法"""
        wind_speed = wind_data['wind_speed']
        height_1d = wind_data['height_1d']
        
        # 使用 1D 高度网格
        result = utilities.calc_roughness_correction(height_1d, wind_speed, utilities.rcmask)
        
        # 验证输出形状
        assert result.shape == wind_speed.shape
        
        # 验证输出值
        assert not np.isnan(result).any()
        assert (result >= 0).all()
    
    def test_do_rc_hc_all(self, utilities, wind_data):
        """测试 do_rc_hc_all 方法"""
        wind_speed = wind_data['wind_speed']
        height_1d = wind_data['height_1d']
        
        # 使用 1D 高度网格
        result = utilities.do_rc_hc_all(height_1d, wind_speed)
        
        # 验证输出形状
        assert result.shape == wind_speed.shape
        
        # 验证输出值
        assert not np.isnan(result).any()
        assert (result >= 0).all()
    
    def test_without_z0(self, utilities_data):
        """测试不提供 z0 参数的情况"""
        # 创建不包含 z0 的实例
        utilities = RoughnessCorrectionUtilities(
            a_over_s=utilities_data['a_over_s'],
            sigma=utilities_data['sigma'],
            z_0=None,  # 不提供 z0
            pporo=utilities_data['pporo'],
            modoro=utilities_data['modoro'],
            ppres=utilities_data['ppres'],
            modres=utilities_data['modres']
        )
        
        # 验证初始化成功
        assert utilities.z_0 is None
    
    def test_edge_cases(self, utilities_data):
        """测试边界情况"""
        # 创建包含无效值的数据
        a_over_s = np.array([[0.0, 0.5], [0.5, 0.5]], dtype=np.float32)
        sigma = np.array([[0.0, 50.0], [50.0, 50.0]], dtype=np.float32)
        z0 = np.array([[0.0, 0.1], [0.1, 0.1]], dtype=np.float32)
        pporo = np.array([[100.0, 200.0], [300.0, np.nan]], dtype=np.float32)  # 包含 NaN
        modoro = np.array([[90.0, 190.0], [290.0, 390.0]], dtype=np.float32)
        
        # 创建实例
        utilities = RoughnessCorrectionUtilities(
            a_over_s=a_over_s,
            sigma=sigma,
            z_0=z0,
            pporo=pporo,
            modoro=modoro,
            ppres=1000.0,
            modres=4000.0
        )
        
        # 验证掩码处理
        assert not utilities.hcmask[0, 0]  # 海洋点
        assert not utilities.hcmask[1, 1]  # 包含 NaN 的点


if __name__ == '__main__':
    pytest.main(['-v', __file__])
