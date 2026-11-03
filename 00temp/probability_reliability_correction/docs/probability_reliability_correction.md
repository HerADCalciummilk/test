# 概率可靠性订正

## 基本信息

- 算法名称：`probability_reliability_correction`
- 原始路径：`D:\workspace\improver\reliability_calibration`（原包名 `reliability_calibration`）
- 算法类型：`07probability`
- 贡献人：郭云谦、王亭波

## 算法能力

对概率预报做可靠性订正：用历史概率预报与阈值化实况构建可靠性表，经聚合/整理后按表插值订正待发布概率场；同时支持网格（meb 六维 xarray）与站点（meb 站点表）。对应 IMPROVER `improver.calibration.reliability_calibration`（Flowerdew 2014）。

## 主要插件

| 插件 | 说明 |
| --- | --- |
| `ConstructReliabilityCalibrationTables` | 历史概率预报 + 阈值化实况 → 可靠性表 |
| `AggregateReliabilityCalibrationTables` | 多表和/或指定坐标求和 |
| `ManipulateReliabilityTable` | 合并欠采样箱、强制观测频率单调 |
| `ApplyReliabilityCalibration` | 用可靠性表插值订正概率预报 |
| `cli/prb_*.py` | 四阶段 CLI 示例 |
| `cli/preprocess_test_data.py` | 官方 Iris 样例预处理为 meb |

## 目录说明

| 内容 | 路径 | 说明 |
| --- | --- | --- |
| 核心源码 | `src/reliability_calibration.py` | 四插件编排 |
| 数值内核 | `src/utils/` | construct / manipulate / apply 与网格/站点适配 |
| CLI | `cli/prb_*.py`、`cli/io.py` | 示例入口与读写 |
| 测试 | `test/` | 网格/站点单元与 CLI I/O |
| 文档 | `docs/reliability_calibration.md`、`docs/probability_reliability_correction.md` | 详细说明与简要说明 |
| notebook | `nbs/reliability_calibration_validation.ipynb` | 示例与对照 |

## 当前整理状态

- 已从原目录同步源码、CLI、测试、文档与 notebook；中间目录导入名为 `probability_reliability_correction`。
- 未同步 `test_data/`（约 1.32MB、54 文件）；单元测试不依赖样例；CLI 缺样例时提示而不崩溃。
- 原目录与中间目录 pytest：均为 18 passed（2026-08-08）。
- 迁入正式 `NIMM/07probability/` 时再改为仓库正式包路径。
