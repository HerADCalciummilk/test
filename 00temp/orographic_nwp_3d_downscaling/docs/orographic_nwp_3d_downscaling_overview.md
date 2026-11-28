# 地形精细化插值

把模式粗网格上的近地面要素订正到细网格或站点。当前业务入口是 `cli/orographic_nwp_3d_downscaling_cli.py` 的 `process`。

## 算法实现原理

目标点落在源格点的四个角之间。每个角先按高度差修正，再做双线性插值：

修正量 = (目标海拔 − 源格点海拔) × 垂直变率 × eta

eta 为 1 时用满垂直变率。求参时在 0.1 到 1.0、步长 0.1 上选取与实况最接近的 eta。风速结果小于 0 记为 0，相对湿度限制在 0 到 100，气压低于 200 记为 200。

公式在 `src/fast_refine_interp_util_plugin.py` 的 `dem_interp_scalar`。`Class_Interp_dem.dDEM_3d_interp_scalar` 调用这一份。源程序没有附参考文献。

`process` 的顺序是：读配置、地形和目标点；`SpatialInterpPlugin` 按时效插值；把格点产品写成 NetCDF；需要时再做 `MaxMinPlugin`、`TimeInterpPlugin`；`operation` 含 `p` 时由 `BestEtaPlugin` 算出 eta，再写成 `{时效}_{要素}_eta.h5`。

## 算法参数说明

| 参数 | 预设 | 含义 |
| --- | --- | --- |
| `operation` | `i` | `i` 插值，`p` 求参，`ip` 两者 |
| `begin_date` | 运行时刻 | 北京时业务时间，`YYYYMMDDHH` |
| `resolution` | `5km` | `site`、`1km` 或 `5km` |
| `model_region` | `EC_12P5KM` | 模式区域 |
| `para_file` | `Fast_refine_interp_5km.ini` | 要素、时效和开关，放在 `work_dir` |
| `work_dir` | 本包 `resource` | 参数文件所在目录 |
| `root_path` | 本包目录 | 项目根 |
| `pro_count` | `1` | 大于 1 时打开时效并行，并作为进程数 |
| `update` | `0` | `1` 表示已有结果也重算 |
| `debug` | `0` | 大于等于 1 时打印耗时 |
| `s3_method` | `g_interp` | 结果目录中的方法名 |
| `site_name` | `Station1` | 站点文件名 |

要素、时效范围和 NetCDF 开关在 `resource/Fast_refine_interp_5km.ini`，不在 `resource/conf.ini`。

## 算法调用示例

在本包目录：

```bash
python -m cli begin_date=2026111813 operation=i debug=1 update=1
```

在 `00temp`：

```bash
python -m orographic_nwp_3d_downscaling begin_date=2026111813 operation=i debug=1 update=1
```

Python：

```python
from cli.orographic_nwp_3d_downscaling_cli import process

process(begin_date="2026111813", operation="i", debug=1, update=1)
```

完整业务还要有模式场、地形和 `resource/config` 里的路径。下面的标量示例只调用订正公式，用来看高度差对气温的影响。
