# NIMM 算法仓库整理清单

> 一次原始算法整理过程对应 `00log/` 下的一份日志；中间稿存放 `00temp/station_height_difference_correction/`。

## 已整理算法列表

| 算法种类 | 算法名称 | 算法功能 | 整理时间 | 贡献人 | CLI 入口 |
| --- | --- | --- | --- | --- | --- |
| 单模式订正 | **station_height_difference_correction** | 基于站点高差估计并应用订正因子，减弱高度差引起的预报系统性偏差 | 2026-08-05 | 郭云谦、王亭波 | `cli/dsc_estimate_dz_rescaling.py`、`cli/dsc_apply_dz_rescaling.py` |

## station_height_difference_correction 目录明细

| 类别 | 路径 | 内容 |
| --- | --- | --- |
| 核心算法 | `src/dz_rescaling.py` | `EstimateDzRescaling`、`ApplyDzRescaling` |
| 模块工具 | `src/utils/_sta.py` | 站点表列校验与对齐 |
| 插件基类 | `utils/base_plugin.py` | BasePlugin / PostProcessingPlugin 本地提供 |
| CLI | `cli/dsc_estimate_dz_rescaling.py`、`cli/dsc_apply_dz_rescaling.py` | 文件式示例入口 |
| 文档 | `docs/dz_rescaling.md`、`docs/station_height_difference_correction.md` | 算法说明 |
| notebook | `nbs/dz_rescaling_validation.ipynb` | 示例与验证 |
| 测试 | `test/` | 单元与 CLI 冒烟 |
| 整理日志 | `00log/station_height_difference_correction_整理_20260731.log` | 整理过程记录 |

## station_height_difference_correction 待办（供人工填写）

| 序号 | 事项 | 建议处理 |
| --- | --- | --- |
| 1 | 导入路径 | 迁入正式 NIMM/04single_calibration/ 时调整为仓库正式包路径 |
| 2 | BasePlugin | 正式入库时评估是否改为仓库统一基类 |
| 3 | test_data | 约 3.07MB、21 文件；中间目录未同步；可放入 NIMM_pip_testdata 并在正式入库前筛选 |
| 4 | resource/ | 当前为空；正式入库时确认是否需要 |

## station_height_difference_correction 验证记录

| 范围 | 结果 | 日期 |
| --- | --- | --- |
| 中间目录 `00temp/station_height_difference_correction/` | 26 passed, 1 skipped | 2026-07-31 |
| 原始算法目录 `D:\workspace\improver\dz_rescaling` | 27 passed（improver venv） | 2026-07-31 |
