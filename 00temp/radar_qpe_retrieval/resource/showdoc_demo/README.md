# ShowDoc 示例数据

已质控的 meteva 网格（Z9010），供插件 / CLI 的 QPE 使用示例直接读取。

质控链路：**基数据 → Py-ART 极坐标质控（`PolarRadarQCPlugin`）→ `grid_2d` 经纬网格**，由 `_prep_showdoc_qc_nc.py` 生成。

| 路径 | 说明 |
| --- | --- |
| `single/refl_qc_048.nc` | 单时次 0.48° 反射率（2025-07-24 19:24） |
| `single/kdp_qc_048.nc` | 同上一时次 KDP |
| `batch/<YYYYMMDDHHMMSS>/refl_qc.nc` | 19:00–20:00 各体扫质控后反射率 |
| `batch/<YYYYMMDDHHMMSS>/kdp_qc.nc` | 同窗各体扫质控后 KDP |

QPE 使用示例不包含质控代码，只读本目录网格。
