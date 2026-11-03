# orographic_precipitation_downscaling

## 算法概述

`orographic_precipitation_downscaling` 用于基于地形抬升效应计算降水地形增强项，并支持将该增强项叠加或扣除到降水场。原始算法迁移自 Met Office IMPROVER 的地形增强相关实现，并适配 `meteva_base` 的 `grid_data` 六维数据结构，同时保留二维场和 `numpy.ndarray` 输入能力。

本次整理的核心能力包括：

- 从温度、相对湿度、气压、风速、风向和目标地形计算地形增强项。
- 将风速风向解析为目标网格坐标系下的 `u/v` 风分量。
- 基于迎风抬升项 `v·gradZ`、湿度阈值、地形阈值和上游贡献计算地形增强。
- 支持将地形增强项以 `add` 或 `subtract` 模式应用到降水场。
- 提供 CLI 示例、notebook 示例和单元测试。

## 算法分类

- 分类：`00space_downscale`
- 分类依据：算法以地形抬升和风场为主要物理约束，对降水场进行空间降尺度和地形影响订正。

## 主要文件


| 类型   | 文件                                    | 说明                               |
| ---- | ------------------------------------- | -------------------------------- |
| 核心源码 | `src/orographic_enhancement.py`       | 地形增强项计算、风分量解析和元插件流程              |
| 应用源码 | `src/apply_orographic_enhancement.py` | 将地形增强项叠加或扣除到降水场                  |
| 内部工具 | `src/utils/`                          | 网格处理、数值计算、饱和水汽压等内部函数             |
| 辅助源码 | `utils/base_plugin.py`                | 插件基类与后处理插件基类                     |
| 辅助源码 | `utils/utils.py`                      | `meteva_base` 网格数据校验、坐标检查与输出封装工具 |
| CLI  | `cli/dsc_orographic_enhancement.py`   | 地形增强项计算示例调度脚本                    |
| 文档   | `docs/orographic_enhancement.md`      | 原始算法说明文档                         |
| 测试   | `test/test_orographic_enhancement.py` | 合成样例与官方样例对照测试                    |
| 测试   | `test/test_grid_spacing.py`           | 投影米制与真经纬格距推断                       |
| CLI 入口 | `cli/__main__.py`                    | `python -m` 列出示例脚本                   |




## 输入输出



### 地形增强项计算

输入：

- `temperature`：温度场，支持 `K` 或 `degC`。
- `humidity`：相对湿度场，支持 `1` 或 `%`。
- `pressure`：气压场，支持 `Pa`、`hPa` 或 `kPa`。
- `wind_speed`：风速场，支持 `m s-1` 或等效单位。
- `wind_direction`：风向场，通常为相对真北角度。
- `orography`：目标地形高度场，通常为 `m`。

输出：

- `orographic_enhancement`：地形增强项，单位 `m s-1`。



### 地形增强项应用

输入：

- `precip_data`：降水场，单场或场序列。
- `orographic_enhancement_data`：地形增强项。
- `operation`：`add` 或 `subtract`。
- `allowed_time_diff`：多时次增强场与降水场的时间匹配容差。

输出：

- 应用地形增强后的降水场。



## 当前整理状态

当前阶段为原始算法整理至中间目录，尚未补充到正式算法仓库目录。

已完成：

- 原始源码、CLI、文档、notebook、测试脚本复制到 `00temp/orographic_precipitation_downscaling/`。
- 2026-07-03 从 `D:\workspace\improver\orographic_enhancement` 增量同步，导入路径已统一为中间目录模块名 `orographic_precipitation_downscaling`。
- **2026-08-18 增量同步**：
  - 核心算法改用 `meb.checkout_griddata()` 直接调用，移除本地封装函数 `check_for_meb_griddata()` / `check_for_xy_coordinates()`。
  - CLI 调度脚本同步改用 `meb.checkout_griddata()` 进行网格数据校验。
  - 补齐测试数据预处理脚本 `cli/preprocess_test_data.py`。
  - 同步最新测试用例、文档说明和验证 notebook。
- **2026-09-15 增量同步**：
  - 从 `D:\workspace\improver\orographic_enhancement` 再次同步源码、CLI、文档与 notebook。
  - 补齐 `cli/__main__.py`、`test/test_grid_spacing.py`（投影米制 / 真经纬格距推断）。
  - `src/utils/_grid.py` 同步经纬与投影格距判断（含 `_is_geographic_spatial`）。
  - 导入仍统一为 `orographic_precipitation_downscaling`；`test_data/` 未拷入中间目录。

待处理：

- 补充至正式仓库时，需将导入路径调整为 `NIMM` 下实际包路径。
- 正式入库时需评估 `utils/base_plugin.py` 是否替换为仓库统一基类。
- 需要在正式补充阶段运行完整测试，并确认 `meteva_base`、`cf_units`、`xarray`、`numpy`、`scipy`、`pyproj`、`pytest`、`netcdf4` 等依赖。

