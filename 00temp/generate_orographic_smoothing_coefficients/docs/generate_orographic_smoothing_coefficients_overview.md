# 地形平滑系数生成

## 基本信息

- 算法名称：`generate_orographic_smoothing_coefficients`
- 原始路径：`D:\workspace\improver\generate_orographic_smoothing_coefficients`
- 算法类型：`ancillaries`
- 贡献人：郭云谦、王亭波

## 算法功能

基于地形邻接梯度生成递归滤波所用的 x/y 方向平滑系数；可选掩码将系数置零。面向 `xarray.DataArray` / meteva_base 六维单场网格；支持投影米制坐标与经纬球面路径。

## 主要方法

| 方法 | 功能 |
| --- | --- |
| `OrographicSmoothingCoefficients` | 由地形梯度生成 x/y 平滑系数 |
| `cli/dsc_generate_orographic_smoothing_coefficients.py` | 文件式 CLI 示例 |
| `cli/preprocess_test_data.py` | 官方投影样例预处理（仅中间目录） |

## 目录说明

| 类型 | 路径 | 说明 |
| --- | --- | --- |
| 核心源码 | `src/generate_orographic_smoothing_coefficients.py` | 插件类 |
| 模块工具 | `src/utils/` | 邻接梯度（投影 / 经纬） |
| CLI | `cli/dsc_*.py` | 示例入口 |
| 预处理 | `cli/preprocess_test_data.py` | 官方投影样例预处理（仅中间目录） |
| 测试 | `test/` | 单元测试与官方样例对照 |
| 文档 | `docs/generate_orographic_smoothing_coefficients.md` | 详细算法说明（对照原目录） |
| notebook | `nbs/generate_orographic_smoothing_coefficients.ipynb` | 示例 |

## 当前整理状态

- 已从原目录增量同步源码、CLI、测试、文档与 notebook；模块名保持 `generate_orographic_smoothing_coefficients`。
- 2026-08-22：改用 `meb.checkout_griddata()`；补齐 `cli/preprocess_test_data.py`；删除包内 `00log/`、`00temp/`、`NIMM_list.md` 和原目录没有的 `utils/utils.py`。
- `test_data/` 约 2.66MB、19 文件，中间目录未同步；官方对照 / 原方法对照缺数据或缺 `improver-1.18.7` 时 skip；CLI / 预处理缺样例时提示而不崩溃。
- 原目录 pytest 19 passed；中间目录 12 passed, 7 skipped（2026-08-22）。
- 补充至 `NIMM/ancillaries/` 时需调整为仓库正式包路径。
