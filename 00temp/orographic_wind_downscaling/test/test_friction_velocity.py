import numpy as np
import pytest

from orographic_wind_downscaling.src.wind_downscaling import FrictionVelocity, RMDI, VONKARMAN


def create_dummy_friction_data(n_lat=3, n_lon=4):
    """生成模拟的摩擦速度计算数据。"""
    np.random.seed(42)
    
    # 参考高度处的风速
    u_href = np.random.rand(n_lat, n_lon).astype(np.float32) * 10  # 5-15 m/s
    
    # 参考高度
    h_ref = np.random.rand(n_lat, n_lon).astype(np.float32) * 10 + 5  # 5-15 m
    
    # 植被粗糙度长度
    z_0 = np.random.rand(n_lat, n_lon).astype(np.float32) * 0.1  # 0-0.1 m
    
    # 计算掩码（部分点为 False）
    mask = np.ones((n_lat, n_lon), dtype=bool)
    mask[0, 0] = False  # 一个点不计算
    mask[-1, -1] = False  # 另一个点不计算
    
    return {
        'u_href': u_href,
        'h_ref': h_ref,
        'z_0': z_0,
        'mask': mask,
        'n_lat': n_lat,
        'n_lon': n_lon,
    }


class TestFrictionVelocity:
    """测试 FrictionVelocity 类的功能"""
    
    @pytest.fixture
    def friction_data(self):
        """生成模拟数据的 fixture"""
        return create_dummy_friction_data()
    
    @pytest.fixture
    def friction_velocity(self, friction_data):
        """创建 FrictionVelocity 实例的 fixture"""
        return FrictionVelocity(
            u_href=friction_data['u_href'],
            h_ref=friction_data['h_ref'],
            z_0=friction_data['z_0'],
            mask=friction_data['mask']
        )
    
    def test_init(self, friction_velocity, friction_data):
        """测试初始化方法"""
        # 验证属性是否正确设置
        assert np.array_equal(friction_velocity.u_href, friction_data['u_href'])
        assert np.array_equal(friction_velocity.h_ref, friction_data['h_ref'])
        assert np.array_equal(friction_velocity.z_0, friction_data['z_0'])
        assert np.array_equal(friction_velocity.mask, friction_data['mask'])
    
    def test_init_with_mismatched_sizes(self, friction_data):
        """测试初始化时输入数组大小不匹配的情况"""
        # 创建大小不匹配的数据
        u_href = friction_data['u_href']
        h_ref = friction_data['h_ref']
        z_0 = friction_data['z_0']
        mask = np.ones((friction_data['n_lat'] + 1, friction_data['n_lon']), dtype=bool)  # 不同大小
        
        # 验证是否抛出异常
        with pytest.raises(ValueError, match="输入数组 u_href, h_ref, z_0, mask 的大小不一致"):
            FrictionVelocity(u_href, h_ref, z_0, mask)
    
    def test_call_method(self, friction_velocity, friction_data):
        """测试 __call__ 方法"""
        # 直接调用实例
        result_call = friction_velocity()
        # 调用 process 方法
        result_process = friction_velocity.process()
        
        # 验证两种方法的结果一致
        assert np.array_equal(result_call, result_process)
    
    def test_process(self, friction_velocity, friction_data):
        """测试 process 方法"""
        result = friction_velocity.process()
        
        # 验证输出形状
        assert result.shape == friction_data['u_href'].shape
        
        # 验证输出值类型
        assert result.dtype == np.float32
        
        # 验证掩码为 False 的点值为 RMDI
        assert result[0, 0] == RMDI
        assert result[-1, -1] == RMDI
        
        # 验证掩码为 True 的点值有效
        for i in range(friction_data['n_lat']):
            for j in range(friction_data['n_lon']):
                if friction_data['mask'][i, j]:
                    assert result[i, j] != RMDI
                    assert result[i, j] >= 0
    
    def test_manual_calculation(self, friction_data):
        """手动计算摩擦速度并验证结果"""
        # 创建实例
        fv = FrictionVelocity(
            u_href=friction_data['u_href'],
            h_ref=friction_data['h_ref'],
            z_0=friction_data['z_0'],
            mask=friction_data['mask']
        )
        
        # 计算结果
        result = fv.process()
        
        # 手动计算几个点
        for i in range(friction_data['n_lat']):
            for j in range(friction_data['n_lon']):
                if friction_data['mask'][i, j]:
                    u_href = friction_data['u_href'][i, j]
                    h_ref = friction_data['h_ref'][i, j]
                    z_0 = friction_data['z_0'][i, j]
                    expected = VONKARMAN * (u_href / np.log(h_ref / z_0))
                    assert np.isclose(result[i, j], expected)
    
    def test_edge_cases(self):
        """测试边界情况"""
        # 测试 h_ref 接近 z_0 的情况（会产生大的摩擦速度）
        u_href = np.array([[10.0]], dtype=np.float32)
        h_ref = np.array([[1.01]], dtype=np.float32)  # 仅比 z_0 大一点
        z_0 = np.array([[1.0]], dtype=np.float32)
        mask = np.array([[True]], dtype=bool)
        
        fv = FrictionVelocity(u_href, h_ref, z_0, mask)
        result = fv.process()
        assert not np.isnan(result[0, 0])
        
        # 测试 u_href 为 0 的情况
        u_href = np.array([[0.0]], dtype=np.float32)
        h_ref = np.array([[10.0]], dtype=np.float32)
        z_0 = np.array([[0.1]], dtype=np.float32)
        mask = np.array([[True]], dtype=bool)
        
        fv = FrictionVelocity(u_href, h_ref, z_0, mask)
        result = fv.process()
        assert result[0, 0] == 0.0
    
    def test_all_masked(self, friction_data):
        """测试所有点都被掩码的情况"""
        # 创建全为 False 的掩码
        mask = np.zeros_like(friction_data['mask'], dtype=bool)
        
        fv = FrictionVelocity(
            u_href=friction_data['u_href'],
            h_ref=friction_data['h_ref'],
            z_0=friction_data['z_0'],
            mask=mask
        )
        
        result = fv.process()
        # 验证所有点都是 RMDI
        assert np.all(result == RMDI)


if __name__ == '__main__':
    pytest.main(['-v', __file__])
