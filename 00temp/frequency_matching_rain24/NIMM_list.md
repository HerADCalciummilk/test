# NIMM 算法仓库整理清单

以表格形式记录已整理入本仓库的算法，便于检索、维护与后续补充。

> **说明**  
> - 一次「原始算法整理过程」对应 `00log/` 下的一份日志。  
> - 整理过程中间数据放 `00temp/<算法代号>/`。  
> - 「仍存在问题」详见本表待办，并与对应 `00log/*_整理_*.log` 第四节同步。

---

## 已整理算法列表

| 算法种类 | 算法代号 | 算法功能 | 更新时间 | 贡献人 | 源码与配置位置 | CLI 入口 | 仍存在问题 |
|----------|----------|----------|----------|--------|----------------|----------|------------|
| 短临预报 · 降水订正 | **multi_optimize_tp_24h** | 单模式 24h 累积降水频率匹配订正：相似检索 → 切片光流/平流 → 频率匹配；输出 Micaps3/4（或 NC）；外层「起报×时效」可用 `is_multi`/`pro_count` 多进程 | 2026-07-23 | 马劲松 | 见下表「目录明细」 | `python -m cli ...`<br>`from correct_tp_24h import process`<br>`python src/correct_tp_24h.py` | 见下表「待办」 |

---

## multi_optimize_tp_24h 目录明细

| 类别 | 路径 | 作用 |
|------|------|------|
| **主程序** | `src/correct_tp_24h.py` | `process(...)` / `mainProcess`；`__main__` 直接传参 |
| CLI | `cli/__main__.py` | argparse → `process`；中文 help（`--plugin` / `--rpt-list` / `--is-multi` / `--pro-count`） |
| 相似评分 | `src/cal_similarity.py` | 历史—当前模式相似度 |
| 切片订正 | `src/cal_slice_tp.py` | 切片内光流 + 频率匹配 |
| 光流 | `src/cal_optical_flow.py` | 光流 / 拉格朗日平流 |
| 频率匹配 | `src/cal_frequency_match.py` | 分位数频率匹配 |
| 插值 | `src/interpolation.py` | Cressman / 双线性 |
| 本包工具 | `src/utils/config.py`、`data_proc.py`、`data_save.py`、`util_env.py`、`logger.py`、`verify.py` | 参数、预处理、写出、ini、日志、检验（`from utils.xxx`） |
| 共享插件 | `00temp/utils/multipro_plugin.py`、`data_prepare_plugin.py` | 经根 `utils/__init__` 合并；包内无副本 |
| 配置资源 | `resource/optimize_tp_24.ini`、`resource/*.json`、`sta.m3`、`mask010.nc` | 运行参数、模式路径、站网、掩膜 |
| 文档 | `docs/multi_optimize_tp_24h_程序说明.md`、`README.md` | 算法与入口说明 |
| notebook | `nbs/multi_optimize_tp_24h_说明.ipynb` | 说明 notebook |
| 测试 | `test/test_multi_optimize_tp_24h.py` | 布局 / 导入 / CLI / 调度任务集等价 |
| **整理日志** | `00log/multi_optimize_tp_24h_整理_20260723.log` | 一次整理过程一份日志 |
| **中间数据** | `00temp/multi_optimize_tp_24h/` | 整理过程临时样本（当前占位） |
| 仓库索引 | 仓库根 `00log/multi_optimize_tp_24h.md` | 全库摘要日志 |

> **入口约定**：命令行用 `python -m cli`；模块用 `from correct_tp_24h import process`；直跑改 `src/correct_tp_24h.py` 的 `__main__` 传参。预报时效仍由 ini `start_dtime`/`end_dtime`/`inter_dtime*` 决定。

---

## multi_optimize_tp_24h 待办（需人工补充）

| 序号 | 仍存在问题（目录/事项） | 建议处理 |
|------|-------------------------|----------|
| 1 | 贡献人 / 原始绝对路径登记不完整 | 补全本表与 `00log/*_整理_*.log` 页眉 |
| 2 | `resource/` 样例与输出体积大 | 正式入库前筛选；大文件勿进 `00temp/` |
| 3 | `test/test_compare_version.py` 硬编码外盘路径 | 改为可配置或移出 CI |
| 4 | `resource/*.json` 业务绝对路径 | 部署环境按机房修改 |
| 5 | 未迁入正式 NIMM 目录 | 按仓库规范再调整路径与包名 |
| 6 | 业务端到端未复跑 | 配置真实路径后跑 `python -m cli` / `src/correct_tp_24h.py` |
| 7 | `00temp/multi_optimize_tp_24h/` 仅占位 | 有对照/备份中间文件时放入并记入 `00log/` |
| 8 | `nbs/` 内容可能仍含旧代号/入口 | 人工核对并同步为 `multi_optimize_tp_24h` / `process` |

---

## 新增算法登记模板

| 算法种类 | 算法代号 | 算法功能 | 更新时间 | 贡献人 | 源码与配置位置 | CLI 入口 | 仍存在问题 |
|----------|----------|----------|----------|--------|----------------|----------|------------|
| （填写） | （填写） | （填写） | YYYY-MM-DD | （填写） | （填写） | （填写） | （填写） |

同时新增：

- `00log/<算法代号>_整理_<YYYYMMDD>.log`
- `00temp/<算法代号>/`
