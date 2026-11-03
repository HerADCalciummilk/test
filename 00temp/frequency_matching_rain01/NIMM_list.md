# NIMM 算法仓库整理清单

以表格形式记录已整理入本仓库的算法，便于检索、维护与后续补充。

> **说明**  
> - 一次「原始算法整理过程」对应 `00log/` 下的一份日志。  
> - 整理过程中间数据放 `00temp/<算法代号>/`。  
> - 「仍存在问题」详见本表待办，并与对应 `00log/*_整理_*.log` 第五节同步。

---

## 已整理算法列表

| 算法种类 | 算法代号 | 算法功能 | 更新时间 | 贡献人 | 源码与配置位置 | CLI 入口 | 仍存在问题 |
|----------|----------|----------|----------|--------|----------------|----------|------------|
| 短临预报 · 降水订正 | **multi_qpf_fm_rain01** | 单模式逐 1 小时（1–48h）降水统计订正：分块相似个例 + 光流平流 + 频率匹配；输出 Micaps3/4；支持 `is_multi` 多起报并行 | 2026-07-23 | 曹勇 | 见下表「目录明细」 | `python -m cli ...`<br>`from runner import process`<br>`python src/runner.py` | 见下表「待办」 |

---

## multi_qpf_fm_rain01 目录明细

| 类别 | 路径 | 作用 |
|------|------|------|
| **主程序** | `src/runner.py` | `process(...)` 调度；`__main__` 直接传参 |
| CLI | `cli/__main__.py` | argparse → `runner.process`（中文 help） |
| 相似评分 | `src/proc/ensemble.py` | TS+BIAS 相似个例 |
| 光流 | `src/proc/optical_flow.py` | 光流风场 |
| 平流 | `src/proc/rain_extrapolation.py` | 半拉格朗日平流 |
| 频率匹配 | `src/proc/frequency_match.py` | CDF 分位数映射 |
| 空间分析 | `src/proc/spatial_analysis.py` | Cressman、站点约束 |
| 数据 I/O | `src/utils/types.py` | GridData / ScatterData 等（`from utils.types`） |
| 检验脚本 | `src/utils/verify.py` | 检验准备（调用共享 `data_prepare_plugin`） |
| 本包工具 | `src/utils/util_env.py`、`util_paths.py`、`log.py`、`string_process.py` | ini / 路径 / 日志 / 日期占位符 |
| 共享插件 | `00temp/utils/multipro_plugin.py`、`data_prepare_plugin.py` | 经根 `utils/__init__` 合并；包内无副本 |
| 配置资源 | `resource/qpf_fm.ini`、`path.json`、`config.json`、`sta.info`、`mask010.dat` | 路径、模式、站网、掩膜 |
| 文档 | `docs/multi_qpf_fm_rain01_算法说明.md`、`README.md` | 算法与入口说明 |
| notebook | `nbs/qpf_fm_rain01_说明.ipynb` | 说明 notebook（文件名待随代号同步） |
| 测试 | `test/test_multi_qpf_fm_rain01.py`、`test_runner_config.py`、`test_util_env.py` | 配置、频率匹配、路径 |
| **整理日志** | `00log/multi_qpf_fm_rain01_整理_20260723.log` | 一次整理过程一份日志 |
| **中间数据** | `00temp/multi_qpf_fm_rain01/` | 整理过程临时样本（当前占位） |
| 仓库索引 | 仓库根 `00log/multi_qpf_fm_rain01.md` | 全库摘要日志 |

> **入口约定**：命令行用 `python -m cli`；模块用 `from runner import process`；直跑改 `src/runner.py` 的 `__main__` 传参。

---

## multi_qpf_fm_rain01 待办（需人工补充）

| 序号 | 仍存在问题（目录/事项） | 建议处理 |
|------|-------------------------|----------|
| 1 | 贡献人 / 原始路径登记不完整 | 补全 `NIMM_list` 与 `00log/*_整理_*.log` 页眉 |
| 2 | `docs/`、`nbs/` 旧入口或旧代号 | 统一为 `process` / `python -m cli` / `multi_qpf_fm_rain01` |
| 3 | `requirements.txt` 缺失 | 按 numpy、meteva 等补全并入库（建议 `env/`） |
| 4 | `resource/data/` 样例过大 | 正式入库前筛选最小集；大文件勿进 `00temp/` |
| 5 | 未迁入正式 NIMM 目录 | 按仓库规范再调整路径与包名 |
| 6 | 业务端到端未复跑 | 配置真实路径后跑 `python -m cli` / `src/runner.py` |
| 7 | `00temp/multi_qpf_fm_rain01/` 仅占位 | 有对照/备份中间文件时放入并记入 `00log/` |
| 8 | `nbs/` notebook 文件名未更名 | 按需改为 `multi_qpf_fm_rain01_说明.ipynb` 并核对内容 |

---

## 新增算法登记模板

| 算法种类 | 算法代号 | 算法功能 | 更新时间 | 贡献人 | 源码与配置位置 | CLI 入口 | 仍存在问题 |
|----------|----------|----------|----------|--------|----------------|----------|------------|
| （填写） | （填写） | （填写） | YYYY-MM-DD | （填写） | （填写） | （填写） | （填写） |

同时新增：

- `00log/<算法代号>_整理_<YYYYMMDD>.log`
- `00temp/<算法代号>/`
