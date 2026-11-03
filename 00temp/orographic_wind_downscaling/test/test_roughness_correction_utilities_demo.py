import numpy as np

from orographic_wind_downscaling.src.wind_downscaling import RoughnessCorrectionUtilities


def test_roughness_correction_utilities_demo_smoke():
    """演示版冒烟测试：确保核心工具类可初始化并完成一次主流程调用。"""
    n_lat, n_lon, n_levels = 4, 5, 6
    rng = np.random.default_rng(42)

    a_over_s = rng.random((n_lat, n_lon), dtype=np.float32)
    sigma = rng.random((n_lat, n_lon), dtype=np.float32) * 100.0
    z_0 = rng.random((n_lat, n_lon), dtype=np.float32) * 0.3 + 0.01
    pporo = rng.random((n_lat, n_lon), dtype=np.float32) * 400.0
    modoro = rng.random((n_lat, n_lon), dtype=np.float32) * 400.0

    # 构造部分海点，模拟真实场景
    a_over_s[0, 0] = 0.0
    sigma[0, 0] = 0.0

    height_1d = np.linspace(10.0, 600.0, n_levels, dtype=np.float32)
    wind_speed = rng.random((n_lat, n_lon, n_levels), dtype=np.float32) * 20.0

    rc_utils = RoughnessCorrectionUtilities(
        a_over_s=a_over_s,
        sigma=sigma,
        z_0=z_0,
        pporo=pporo,
        modoro=modoro,
        ppres=1000.0,
        modres=4000.0,
    )

    result = rc_utils.do_rc_hc_all(height_1d, wind_speed)

    assert result.shape == wind_speed.shape
    assert np.isfinite(result).all()
    assert (result >= 0.0).all()

