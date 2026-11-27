# resource（最小运行资源）

本目录随包上传，供容器内直接试跑 CLI。

| 路径 | 说明 |
|------|------|
| `cli_input/*.nc` | **经纬坐标** meb 六维样例（气温/风速/相对湿度/气压），来自 `test_data/.../latlon/cli_input` |
| `cli_output/` | `main()` 默认写出目录 |

业务约定：输入为 meb 六维网格，空间维为 `lat`/`lon`（非投影米制坐标）。

用样例数据试跑（在 `00temp` 目录下运行；路径写**绝对路径**，把 `<本包目录>` 换成 `00temp\feels_like_temperature` 的完整路径）::

    python -m feels_like_temperature temperature_path=<本包目录>\resource\cli_input\20181121T1200Z-PT0012H00M-temperature_at_screen_level.nc wind_speed_path=<本包目录>\resource\cli_input\20181121T1200Z-PT0012H00M-wind_speed_at_10m.nc relative_humidity_path=<本包目录>\resource\cli_input\20181121T1200Z-PT0012H00M-relative_humidity_at_screen_level.nc pressure_path=<本包目录>\resource\cli_input\20181121T1200Z-PT0012H00M-pressure_at_mean_sea_level.nc output_path=<本包目录>\resource\cli_output\feels_like_temp_result.nc
