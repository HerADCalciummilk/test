# NIMM 算法仓库整理清单

以表格形式记录已整理入本仓库的算法，便于检索、维护与后续补充。

> **说明**：一次「原始算法整理过程」对应 `00log/` 下的一份日志；中间数据放 `00temp/lapse_rate/`。

---

## 已整理算法列表

| 算法种类 | 算法代号 | 算法功能 | 更新时间 | 贡献人 | 源码与配置位置 | CLI 入口 | 仍存在问题 |
|----------|----------|----------|----------|--------|----------------|----------|------------|
| 空间降尺度 | **lapse_rate** | 基于层结递减率和地形高度差进行气温空间降尺度与地形订正 | 2026-08-17 | 郭云谦、王亭波 | 见下表「lapse_rate 目录明细」 | `python -m orographic_temperature_downscaling.cli.dsc_temp_lapse_rate`<br>`python -m orographic_temperature_downscaling.cli.anc_lapse_rate` | 见下表「lapse_rate 待办」 |

---

## lapse_rate 目录明细

| 类别 | 路径 | 作用 |
|------|------|------|
| 核心算法 | `src/lapse_rate.py` | LapseRate、ApplyGriddedLapseRate、compute_lapse_rate_adjustment |
| 模块工具 | `utils/utils.py` | meteva_base 网格数据单位换算与输出封装 |
| 插件基类 | `utils/base_plugin.py` | BasePlugin 本地提供 |
| CLI | `cli/dsc_temp_lapse_rate.py` | 层结递减率计算 |
| CLI | `cli/anc_lapse_rate.py` | 温度地形订正 |
| CLI | `cli/preprocess_test_data.py` | 官方投影样例预处理 |
| 文档 | `docs/lapse_rate.md、docs/orographic_temperature_downscaling.md` | 算法说明 |
| notebook | `nbs/lapse_rate.ipynb` | 示例与验证 |
| 测试 | `test/test_lapse_rate.py、test/test_official_lapse_rate_actual_orog.py` | 单元测试与官方样例 |
| 整理日志 | `00log/lapse_rate_整理_20260706.log` | 整理过程记录 |
| 中间数据 | `00temp/lapse_rate/` | 整理过程临时样本（当前为空） |

---

## lapse_rate 待办（需人工补充）

| 序号 | 问题 | 建议处理 |
|------|------|----------|
| 1 | 入库路径 | 补充至 NIMM/00space_downscale/ 时需调整为仓库正式包路径 |
| 2 | BasePlugin | 正式入库时评估是否改为仓库统一基类 |
| 3 | resource/ | 当前为空，正式补充时确认是否保留 |
| 4 | test_data | 由独立仓库存放，中间目录不同步；正式入库前确认必要样例范围 |
| 5 | pytest | 2026-08-17 同步后尚未重跑完整测试，正式入库前需确认全部通过 |
