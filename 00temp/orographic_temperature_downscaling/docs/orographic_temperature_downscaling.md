# orographic_temperature_downscaling

## 算法概述

`orographic_temperature_downscaling` 用于基于地形高度差进行气温降尺度和地形订正。原始算法主要迁移自 Met Office IMPROVER 的层结递减率相关方法，并适配 `meteva_base` 的 `grid_data` 数据结构，同时保留 `numpy.ndarray` 输入能力。

本次整理的核心能力包括：

- 根据温度、地形高度和陆海掩膜估计网格化层结递减率。
- 将已有层结递减率应用到温度场，实现源地形到目标地形的温度订正。
- 提供 CLI 示例、notebook 示例和单元测试。

## 算法分类

- 分类：`00space_downscale`
- 分类依据：算法以地形高度差为主要物理约束，对气温场进行空间降尺度和地形订正。

## 主要文件

| 类型 | 文件 | 说明 |
| --- | --- | --- |
| 核心源码 | `src/lapse_rate.py` | 层结递减率估计与气温地形订正核心算法 |
| 辅助源码 | `utils/base_plugin.py` | 插件基类与后处理插件基类 |
| 辅助源码 | `utils/utils.py` | `meteva_base` 网格数据单位换算与结果封装工具 |
| CLI | `cli/dsc_temp_lapse_rate.py` | 从温度、地形和陆海掩膜计算层结递减率 |
| CLI | `cli/anc_lapse_rate.py` | 应用层结递减率进行温度地形订正 |
| CLI | `cli/preprocess_test_data.py` | 官方投影样例预处理为 meb 六维及经纬重网格 |
| 测试 | `test/test_lapse_rate.py` | 核心函数与插件单元测试 |
| 测试 | `test/test_official_lapse_rate_actual_orog.py` | 官方样例数据对照测试 |

## 输入输出

### 层结递减率估计

输入：

- `temperature`：气温场，支持 `xarray.DataArray` 或 `numpy.ndarray`。
- `orography`：地形高度场。
- `land_sea_mask`：陆海掩膜，陆地点参与局地梯度拟合，海洋点回退为干绝热递减率。

输出：

- `air_temperature_lapse_rate`：层结递减率场，单位 `K m-1`。

### 气温地形订正

输入：

- `temperature`：待订正温度场。
- `lapse_rate`：层结递减率场。
- `source_orog`：源地形高度场。
- `dest_orog`：目标地形高度场。

输出：

- 地形订正后的温度场，输出单位为 `K`。

## 当前整理状态

当前阶段为原始算法整理至中间目录，尚未补充到正式算法仓库目录。

已完成：

- 原始源码、CLI、文档、notebook、测试脚本复制到 `00temp/orographic_temperature_downscaling/`。
- 2026-07-03 从 `D:\workspace\improver\temperature` 增量同步，导入路径已统一为中间目录模块名 `orographic_temperature_downscaling`。
- 2026-08-17 从 `D:\workspace\improver\temperature` 增量同步：`src/lapse_rate.py` 改用 `meb.checkout_griddata()` / `meb.checkout_griddata_same_coords()` 直接调用；`utils/utils.py` 简化为仅保留 `rebuild_to_meb_griddata()` 和 `convert_units()`；`utils/base_plugin.py` 恢复完整 `PostProcessingPlugin`；补齐 `cli/preprocess_test_data.py`；同步 `nbs/lapse_rate.ipynb`（更完善的演示与验证版本）；文档同步更新。
- 体感温度相关内容已拆出，中间目录仅保留层结递减率与地形订正。

待处理：

- 补充至正式仓库时，需将导入路径调整为 `NIMM` 下实际包路径。
- 正式入库时需评估 `utils/base_plugin.py` 是否替换为仓库统一基类。
- 需要在正式补充阶段运行完整测试，并确认 `meteva_base`、`cf_units`、`xarray`、`numpy`、`pytest` 等依赖。
