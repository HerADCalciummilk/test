# orographic_wind_downscaling

## 算法概述

`orographic_wind_downscaling` 用于基于地形粗糙度和地形高度差进行风速空间降尺度。原始算法迁移自 Met Office IMPROVER 风速降尺度相关实现，并适配 `meteva_base` 的 `grid_data` 六维数据结构，同时支持 `numpy.ndarray` 输入。

核心能力包括：

- **粗糙度计算**：由高分辨率 DEM 与模式网格地形统计 `sigma`（格点内高度标准差）与 `a_over_s`（轮廓粗糙度），输出落在细网格上。
- **风速订正**：根据 `a_over_s`、`sigma`、目标/模式地形与可选植被粗糙度，对风速做粗糙度订正（RC）与高度订正（HC）；固定返回 `(订正风速, hc_add)`。
- 支持一维公共高度层或三维空间变化高度层。
- 支持投影米制与真经纬分辨率推断。
- 提供 CLI、notebook 示例和单元测试。

典型衔接：

```text
细网格 DEM + 模式网格地形 → RoughnessCalculation → sigma / a_over_s
细网格风速 + 辅料 → RoughnessCorrection → (订正风速, hc_add)
```

## 算法分类

- 分类：`00space_downscale`
- 分类依据：算法以地形和粗糙度辅助场为约束，对风速场进行空间降尺度和地形影响订正。

## 主要文件

| 类型 | 文件 | 说明 |
| --- | --- | --- |
| 核心源码 | `src/roughness.py` | `RoughnessCalculation`：由 DEM + 模式网格地形计算 `sigma` / `a_over_s` |
| 核心源码 | `src/wind_downscaling.py` | 风速粗糙度订正与高度订正（`RoughnessCorrection` 等） |
| 辅助源码 | `utils/base_plugin.py` | 插件基类与后处理插件基类 |
| 辅助源码 | `utils/utils.py` | `meteva_base` 网格数据校验与输出封装工具 |
| CLI | `cli/roughness_cli.py` | `AncRoughnessCli`：粗糙度辅料计算调度 |
| CLI | `cli/dsc_wind_downscaling.py` | `DscWindDownscalingCli`：风速降尺度调度 |
| CLI | `cli/preprocess_test_data.py` | 官方样例预处理（投影维重命名 / 经纬重网格） |
| 文档 | `docs/wind_downscaling.md` | 粗糙度计算（`RoughnessCalculation` / `AncRoughnessCli`）与风速订正说明 |
| notebook | `nbs/wind_calculations.ipynb` | 投影与经纬路径验证 |
| notebook | `nbs/batch_cli.ipynb` | 批量调度与检验示例 |
| 测试 | `test/test_RoughnessCorrection.py` | 粗糙度订正主流程测试 |
| 测试 | `test/test_official_wind_downscaling.py` | 官方样例数据对照测试 |
| 测试 | `test/test_infer_grid_resolution.py` | 网格分辨率推断测试 |
| 测试 | `test/test_synthetic_latlon_roughness.py` | 合成经纬端到端测试 |

## 输入输出

### RoughnessCalculation

输入：

- `orography`：高分辨率地形（`DataArray`，米）。
- `model_orography`：模式网格地形（`DataArray`）；只用 `lat`/`lon` 网格，须保持模式分辨率。

输出：

- `(sigma, a_over_s)`：与细网格同形；`sigma` 单位米，`a_over_s` 无量纲。

### RoughnessCorrection

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

- `(订正风速, hc_add)`：订正风速结构与输入风速一致；`hc_add` 为高度订正附加项（截断前），与订正风速同型。`DataArray` 输入时二者均为 meteva_base 六维，`hc_add.name='height_correction'`。

## 当前整理状态

当前阶段为原始算法整理至中间目录，尚未补充到正式算法仓库目录。

已完成：

- 原始源码、CLI、文档、notebook、测试脚本整理到 `00temp/orographic_wind_downscaling/`。
- 2026-07-06 完成 NIMM 标准化；2026-08-14 从 `D:\workspace\improver\wind_calculations` 增量同步。
- 导入路径已统一为中间目录模块名 `orographic_wind_downscaling`。
- 2026-08-21：说明文档与 CLI 提示对齐原目录，验证 notebook 统一为 `nbs/wind_calculations.ipynb`；删除包内 `00log/`、`00temp/`、`NIMM_list.md`。
- 新增 `RoughnessCalculation` / `AncRoughnessCli`；`RoughnessCorrection.process` 固定返回 `(订正风速, hc_add)`；说明见 `docs/wind_downscaling.md`。

待处理：

- 补充至正式仓库时，需将导入路径调整为 `NIMM` 下实际包路径。
- 正式入库时需评估 `utils/base_plugin.py` 是否替换为仓库统一基类。
- 需要在正式补充阶段运行完整测试，并确认 `meteva_base`、`cf_units`、`xarray`、`numpy`、`pytest`、`netcdf4` 等依赖。
