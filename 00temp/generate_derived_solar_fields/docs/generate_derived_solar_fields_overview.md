# 太阳衍生场生成

## 基本信息

- 算法名称：`generate_derived_solar_fields`
- 原始路径：`D:\workspace\improver\generate_derived_solar_fields`
- 算法类型：`ancillaries`
- 贡献人：郭云谦、王亭波

## 算法功能

生成太阳衍生场：按目标网格与指定时刻计算地方太阳时；按累积时段与可选海拔、Linke 浑浊度累计晴空太阳辐射。面向 `xarray.DataArray` / meteva_base 六维单场网格；支持经纬与投影坐标（投影需 `grid_mapping_attrs`）。

## 主要方法

| 方法 | 功能 |
| --- | --- |
| `GenerateSolarTime` | 地方太阳时计算 |
| `GenerateClearskySolarRadiation` | 指定时段晴空太阳辐射累计 |
| `cli/cal_generate_solar_time.py` | 地方太阳时 CLI |
| `cli/cal_generate_clearsky_solar_radiation.py` | 晴空太阳辐射累计 CLI |
| `cli/preprocess_test_data.py` | 官方投影样例预处理（仅中间目录） |

## 目录说明

| 类型 | 路径 | 说明 |
| --- | --- | --- |
| 核心源码 | `src/generate_derived_solar_fields.py` | 插件类 |
| 模块工具 | `src/utils/` | 网格映射与太阳天文计算 |
| CLI | `cli/cal_*.py` | 示例入口 |
| 预处理 | `cli/preprocess_test_data.py` | 官方投影样例预处理（仅中间目录） |
| 测试 | `test/` | 单元测试 |
| 文档 | `docs/generate_derived_solar_fields.md` | 详细算法说明（对照原目录） |
| notebook | `nbs/generate_derived_solar_fields.ipynb` | 示例 |

## 当前整理状态

- 已从原目录增量同步源码、CLI、测试、文档与 notebook；模块名保持 `generate_derived_solar_fields`。
- 2026-08-22：改用 `meb.checkout_griddata()`；补齐 `cli/preprocess_test_data.py`；删除包内 `00log/`、`00temp/`、`NIMM_list.md` 和原目录没有的 `utils/utils.py`。
- `test_data/` 约 1.25MB、23 文件，中间目录未同步；CLI / 预处理缺样例时提示而不崩溃。
- 原目录与中间目录 pytest 均为 10 passed（2026-08-22）。
- 补充至 `NIMM/ancillaries/` 时需调整为仓库正式包路径。
