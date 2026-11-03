# 简单加性偏差订正

## 基本信息

- 算法名称：`simple_bias_correction`
- 原始路径：`D:\workspace\improver\simple_bias_correction`
- 算法类型：`04single_calibration`
- 贡献人：郭云谦、王亭波

## 算法功能

迁移自 Met Office IMPROVER `improver/calibration/simple_bias_correction.py`：由历史预报与实况估计空间偏差场（沿历史起报时间平均），再对当前预报做加性订正。面向 `xarray.DataArray` / `numpy.ndarray`，适配 `meteva_base` 六维网格（`member, level, time, dtime, lat, lon`），缺测统一用 `NaN` 表示。

核心计算：

```text
error     = forecast - truth
bias      = mean_over_time(error)     # CalculateForecastBias
corrected = forecast - bias           # ApplyBiasCorrection
```

## 主要方法

| 方法 | 功能 |
| --- | --- |
| `evaluate_additive_error` | 计算平均加性误差（预报减实况），两侧缺测取并集 |
| `apply_additive_correction` | 订正量 = 预报减偏差，偏差单位对齐预报 |
| `CalculateForecastBias` | 历史样本按有效时刻配对后沿 `time` 求平均，输出偏差场 |
| `ApplyBiasCorrection` | 拆分预报/偏差、多偏差平均、可选上下界裁剪与偏差缺测填 0 |
| `cli/cal_calculate_forecast_bias.py` | 偏差计算 CLI |
| `cli/prb_bias_correction.py` | 偏差订正 CLI |

## 目录说明

| 类型 | 路径 | 说明 |
| --- | --- | --- |
| 核心源码 | `src/simple_bias_correction.py` | 偏差计算与订正插件 |
| 内部工具 | `src/utils/_calibration_utilities.py` | 时间配对、单位换算、`time_bounds` 处理等 |
| CLI | `cli/cal_*.py`、`cli/prb_*.py` | 示例入口 |
| 预处理 | `cli/preprocess_test_data.py` | 官方投影样例预处理（仅中间目录） |
| 公共工具 | `utils/base_plugin.py` | 本地 `BasePlugin` |
| 测试 | `test/` | 合成单测与 CLI 写出-读回保真度测试 |
| 文档 | `docs/simple_bias_correction.md` | 详细算法说明 |
| notebook | `nbs/simple_bias_correction.ipynb` | 与 IMPROVER 原方法及 KGO 对照 |

## 当前整理状态

- 已从原目录完整同步源码、CLI、测试、文档与 notebook；包名保留原名 `simple_bias_correction`，源码导入已使用包名，无需调整导入路径。
- 2026-08-27 首次整理；核心算法使用 `meb.checkout_griddata()` 进行网格数据校验。
- `test_data/` 约 6.10MB，中间目录未同步；正式入库前筛选必要样例至 `NIMM_pip_testdata`。
- 原目录与中间目录 pytest 均 195 passed（2026-08-27）。
- 补充至 `NIMM/04single_calibration/` 时需调整为仓库正式包路径，并评估 `BasePlugin` 是否改为仓库统一基类。
