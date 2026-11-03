# orographic_wind_downscaling

## 算法概述

`orographic_wind_downscaling` 用于基于地形粗糙度和地形高度差进行风速空间降尺度。原始算法迁移自 Met Office IMPROVER 风速降尺度相关实现，并适配 `meteva_base` 的 `grid_data` 六维数据结构，同时支持 `numpy.ndarray` 输入。

本次整理的核心能力包括：

- 根据地形轮廓粗糙度、网格内地形高度标准差、目标地形、模式地形和植被粗糙度长度构建订正参数。
- 对输入风速执行粗糙度订正和高度订正。
- 支持一维公共高度层或三维空间变化高度层。
- 支持投影米制与真经纬分辨率推断。
- 提供 CLI 示例、notebook 示例和单元测试。

## 算法分类

- 分类：`00space_downscale`
- 分类依据：算法以地形和粗糙度辅助场为约束，对风速场进行空间降尺度和地形影响订正。

## 主要文件

| 类型 | 文件 | 说明 |
| --- | --- | --- |
| 核心源码 | `src/wind_downscaling.py` | 风速粗糙度订正和高度订正核心算法 |
| 辅助源码 | `utils/base_plugin.py` | 插件基类与后处理插件基类 |
| 辅助源码 | `utils/utils.py` | `meteva_base` 网格数据校验与输出封装工具 |
| CLI | `cli/dsc_wind_downscaling.py` | 风速降尺度示例调度脚本 |
| CLI | `cli/preprocess_test_data.py` | 官方样例预处理（投影维重命名 / 经纬重网格） |
| 文档 | `docs/wind_downscaling.md` | 算法分析与 CLI 参数说明（对照原目录 `wind_calculations/docs/wind_downscaling.md`） |
| notebook | `nbs/wind_calculations.ipynb` | 投影与经纬路径验证 |
| 测试 | `test/test_RoughnessCorrection.py` | 粗糙度订正主流程测试 |
| 测试 | `test/test_official_wind_downscaling.py` | 官方样例数据对照测试 |
| 测试 | `test/test_infer_grid_resolution.py` | 网格分辨率推断测试 |
| 测试 | `test/test_synthetic_latlon_roughness.py` | 合成经纬端到端测试 |

## 输入输出

输入：

- `wind_speed`：待订正风速场，支持 `xarray.DataArray` 或 `numpy.ndarray`。
- `a_over_s`：地形轮廓粗糙度，无量纲。
- `sigma`：网格内地形高度标准差，单位通常为 `m`。
- `pporo`：目标网格地形高度，单位通常为 `m`。
- `modoro`：插值至目标网格的模式地形高度，单位通常为 `m`。
- `z0`：植被粗糙度长度，可选，单位通常为 `m`。
- `modres`：模式原始分辨率。
- `ppres`：后处理目标网格分辨率（米）；`pporo` 为 `DataArray` 且未显式传入时，可由坐标推断（投影米制直接取间距，真经纬将度间距换算为米）。
- `height_grid`：风速对应高度层，一维或三维。

输出：

- 经地形粗糙度和高度订正后的风速场，输出结构与输入风速保持一致；`DataArray` 输入返回 `meteva_base` 六维结构。

## 当前整理状态

当前阶段为原始算法整理至中间目录，尚未补充到正式算法仓库目录。

已完成：

- 原始源码、CLI、文档、notebook、测试脚本整理到 `00temp/orographic_wind_downscaling/`。
- 2026-07-06 完成 NIMM 标准化；2026-08-14 从 `D:\workspace\improver\wind_calculations` 增量同步。
- 导入路径已统一为中间目录模块名 `orographic_wind_downscaling`。
- 2026-08-21：说明文档与 CLI 提示对齐原目录，验证 notebook 统一为 `nbs/wind_calculations.ipynb`；删除包内 `00log/`、`00temp/`、`NIMM_list.md`。

待处理：

- 补充至正式仓库时，需将导入路径调整为 `NIMM` 下实际包路径。
- 正式入库时需评估 `utils/base_plugin.py` 是否替换为仓库统一基类。
- 需要在正式补充阶段运行完整测试，并确认 `meteva_base`、`cf_units`、`xarray`、`numpy`、`pytest`、`netcdf4` 等依赖。
