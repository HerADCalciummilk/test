# 地形辅助场生成

## 基本信息

- 算法名称：`generate_ancillary`
- 原始路径：`D:\workspace\improver\generate_ancillary`
- 算法类型：`ancillaries`
- 贡献人：郭云谦、王亭波

## 算法功能

生成地形相关辅助场：对插值后的海陆掩码做 0/1 二值化纠正；按阈值配置将地形高度场分带输出各带二值掩码；并按带内位置计算折叠权重。面向 `xarray.DataArray` / `numpy.ndarray`，兼容 meteva_base 六维网格。

## 主要方法

| 方法 | 功能 |
| --- | --- |
| `CorrectLandSeaMask` | 海陆掩码二值化纠正 |
| `GenerateOrographyBandAncils` | 地形带掩码生成 |
| `GenerateTopographicZoneWeights` | 地形带折叠权重生成 |
| `cli/anc_generate_landmask_ancillary.py` | 海陆掩码 CLI |
| `cli/dsc_generate_topography_bands_mask.py` | 地形带掩码 CLI |
| `cli/dsc_generate_topographic_zone_weights.py` | 地形带权重 CLI |

## 目录说明

| 类型 | 路径 | 说明 |
| --- | --- | --- |
| 核心源码 | `src/generate_ancillary.py` | 海陆掩码与地形带掩码插件 |
| 核心源码 | `src/generate_topographic_zone_weights.py` | 地形带折叠权重插件 |
| 内部工具 | `src/utils/_make_mask_griddata.py` | 地形带掩码/权重六维网格构造 |
| CLI | `cli/anc_*.py`、`cli/dsc_*.py` | 示例入口 |
| 预处理 | `cli/preprocess_test_data.py` | 官方投影样例预处理（仅中间目录） |
| 测试 | `test/` | 单元测试与官方样例对照 |
| 文档 | `docs/generate_ancillary.md` | 详细算法说明 |
| notebook | `nbs/generate_ancillary.ipynb` | 示例 |

## 当前整理状态

- 已从原目录增量同步源码、CLI、测试、文档与 notebook；模块名保持 `generate_ancillary`。
- 2026-08-21：同步 `meb.checkout_griddata()`、新增地形带权重插件与 `src/utils/_make_mask_griddata.py`。
- `test_data/` 约 3.88MB、44 文件，中间目录未同步；官方对照缺数据时 skip；CLI 缺样例时提示而不崩溃。
- 原目录 pytest 58 passed；中间目录 50 passed, 8 skipped（2026-08-21）。
- 补充至 `NIMM/ancillaries/` 时需调整为仓库正式包路径。
