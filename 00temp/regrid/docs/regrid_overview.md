# 海陆感知重网格

## 基本信息

- 算法名称：`regrid`
- 原始路径：`D:\workspace\improver\regrid`
- 算法类型：`ancillaries`
- 贡献人：郭云谦、王亭波

## 算法能力

将源场插值到目标空间网格，可选按海陆掩膜避免“陆取海值 / 海取陆值”。面向 `meteva_base` 六维 `xarray.DataArray`（`member, level, time, dtime, lat, lon`），对应 IMPROVER `improver.regrid.landsea` / `landsea2`。

支持模式包括双线性、最近邻、海陆感知最近邻，以及新版 `*-2` 经纬度源网格路径（含掩膜变体）。

## 主要插件

| 插件 | 说明 |
| --- | --- |
| `RegridLandSea` | 统一入口，按 `regrid_mode` 分派 scipy 路径或新版 `*-2` 路径 |
| `AdjustLandSeaPoints` | scipy 最近邻后的海陆点匹配订正（`nearest-with-mask`） |
| `RegridWithLandSeaMask` | 新版经纬度源网格上的最近邻 / 双线性（可选掩膜） |
| `cli/preprocess_test_data.py` | 官方样例预处理为六维 meb |
| `cli/tran_regrid.py` | 文件式 CLI 示例 |

## 目录说明

| 内容 | 路径 | 说明 |
| --- | --- | --- |
| 核心源码 | `src/landsea.py`、`src/landsea2.py` | 主插件 |
| 模块工具 | `src/utils/` | 插值与网格辅助 |
| CLI | `cli/tran_regrid.py` | 示例入口 |
| 测试 | `test/` | 单元与回归 |
| 文档 | `docs/regrid_landsea.md` | 详细算法说明 |
| notebook | `nbs/regrid_landsea_validation.ipynb` | 示例 |

## 当前整理状态

- 已从原目录同步源码、CLI、测试、文档与 notebook；模块导入名保持 `regrid`。
- 未同步 `test_data/`（约 1.7MB、27 文件）；缺数据时相关用例会跳过。
- 原目录 pytest：38 passed（improver venv，2026-08-17）。
- 中间目录 pytest：25 passed, 13 skipped（2026-08-17）；缺 test_data 或缺相对 `parents[2]/improver-1.18.7` 时会跳过。
- 迁入正式 `NIMM/ancillaries/` 时再改为仓库正式包路径。

- 2026-08-17：自原目录增量同步；网格校验改用 `meb.checkout_griddata`；CLI 缺样例时提示而不崩溃。
- 2026-08-05：自原目录增量同步；新增 `cli/preprocess_test_data.py`；CLI 缺样例时提示而不崩溃。
