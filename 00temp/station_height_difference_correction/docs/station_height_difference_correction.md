# 站点高差订正

## 基本信息

- 算法名称：`station_height_difference_correction`
- 原始路径：`D:\workspace\improver\dz_rescaling`（原包名 `dz_rescaling`）
- 算法类型：`04single_calibration`
- 贡献人：郭云谦、王亭波

## 算法能力

当模式格点高度与站点高度不一致时，用历史站点预报、实况与邻点高差估计订正因子，再乘到新站点预报上，减弱高度差引起的系统性偏差。I/O 为 meteva_base 站点表（`pandas.DataFrame`）。对应 IMPROVER `improver.calibration.dz_rescaling`。

## 主要插件

| 插件 | 说明 |
| --- | --- |
| `EstimateDzRescaling` | 由历史预报、实况与邻点高差拟合斜率，估计 `scaled_vertical_displacement` |
| `ApplyDzRescaling` | 将订正因子乘到待订正站点预报 |
| `cli/dsc_estimate_dz_rescaling.py` | 估计因子 CLI 示例 |
| `cli/dsc_apply_dz_rescaling.py` | 应用订正 CLI 示例 |

## 目录说明

| 内容 | 路径 | 说明 |
| --- | --- | --- |
| 核心源码 | `src/dz_rescaling.py` | 主插件 |
| 模块工具 | `src/utils/_sta.py` | 站点表列校验与对齐 |
| CLI | `cli/dsc_*.py` | 示例入口 |
| 测试 | `test/` | 单元与 CLI 冒烟 |
| 文档 | `docs/dz_rescaling.md`、`docs/station_height_difference_correction.md` | 详细说明与简要说明 |
| notebook | `nbs/dz_rescaling_validation.ipynb` | 示例与对照 |

## 当前整理状态

- 已从原目录同步源码、CLI、测试、文档与 notebook；模块导入名现为 `station_height_difference_correction`（原包名 `dz_rescaling`）；类名仍为 EstimateDzRescaling / ApplyDzRescaling。
- 未同步 `test_data/`（约 3.07MB、21 文件）；缺官方样例时相关用例会跳过。
- 原目录 pytest：27 passed（improver venv，2026-07-31）。
- 中间目录 pytest：26 passed, 1 skipped（2026-07-31）。
- 迁入正式 `NIMM/04single_calibration/` 时再改为仓库正式包路径。
