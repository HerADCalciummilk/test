# kalman_element_forecast_correction

## 算法概述

`kalman_element_forecast_correction` 用于基于 Kalman 平均误差场的要素预报订正。原始算法包默认服务 `SWVL` 土壤湿度和 `STL` 土壤温度，也可以作为符合 `meteva_base` 六维网格结构的单要素预报订正流程使用。

核心能力包括：

- 使用最新预报和实况网格更新 Kalman 平均误差场或平均绝对误差场。
- 使用已有 Kalman 误差场对当前预报场进行偏差订正。
- 按变量、层级、起报时次和预报时效循环处理业务路径模板。
- 支持源数据复制、误差场输出和订正产品输出。

## 算法分类

- 分类：`04single_calibration`
- 分类依据：算法面向单要素/单模式预报偏差订正，核心为 Kalman 误差更新和预报场订正；不属于多模式融合。

## 主要文件

| 类型 | 文件 | 说明 |
| --- | --- | --- |
| 核心源码 | `src/kalman_me_plugin.py` | `KalmanME`，根据预报和实况更新误差场 |
| 核心源码 | `src/kalman_fix_plugin.py` | `KalmanFix`，使用误差场订正预报 |
| 调度源码 | `src/kalman_cli.py` | Kalman 更新和订正业务流程 |
| 数据复制 | `src/data_transfer.py` | SWVL/STL 源数据复制流程 |
| 工具源码 | `utils/grid_utils.py` | `meteva_base` 网格校验、坐标匹配和 Kalman 数值计算 |
| CLI | `cli/kalman_data.py` | 运行 Kalman 订正流程 |
| CLI | `cli/trans_data.py` | 复制源数据到处理目录 |
| 文档 | `docs/kalman_algorithm.md` | 原始算法说明文档 |
| 示例 | `nbs/kalman_tutorial.ipynb` | notebook 示例 |
| 测试 | `test/test_grid_utils.py` | 网格工具最小单元测试 |

## 输入输出

插件层输入输出为内存中的 `xarray.DataArray`，要求符合 `meteva_base` 六维网格结构：

```text
member, level, time, dtime, lat, lon
```

主要输入：

- `fcst_new`：最新模式预报场。
- `obs_new`：对应实况场。
- `me_before`：上一时次 Kalman 平均误差场，可选。

主要输出：

- `KalmanME` 输出更新后的 Kalman 误差场。
- `KalmanFix` 输出订正后的预报场。

## 当前整理状态

当前阶段为原始算法整理至中间目录，尚未补充到正式算法仓库目录。

已完成：

- 原始 `src/`、`cli/`、`docs/`、`nbs/`、`resource/`、`test/`、`utils/` 已复制到 `00temp/kalman_element_forecast_correction/`。
- 已复制根目录配置与包装脚本：`pyproject.toml`、`setup.py`、`setup.cfg`、`pytest.ini`、`kalman_data.sh`、`trans_data.sh`。
- 已补齐 `test_data/` 目录，并添加说明文件。
- 已排除 `__pycache__` 和 `.pyc` 编译缓存。

待处理：

- 导入包名已与目录名一致，为 `kalman_element_forecast_correction`。
- 默认路径指向生产数据目录，正式测试需准备可复现的小样例数据。
- 完整业务流程依赖 `meteva_base`、`xarray`、`numpy` 和真实网格数据文件。

