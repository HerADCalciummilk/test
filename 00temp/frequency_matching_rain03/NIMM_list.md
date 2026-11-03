# NIMM 算法仓库整理清单

> 一次「原始算法整理过程」对应 `00log/` 下的一份日志；中间数据放 `00temp/<算法代号>/`。

---

## 已整理算法列表

| 算法种类 | 算法代号 | 算法功能 | 更新时间 | 贡献人 | 源码与配置位置 | CLI 入口 | 仍存在问题 |
|----------|----------|----------|----------|--------|----------------|----------|------------|
| 短临预报 · 降水订正 | **frequency_matching_rain03** | 单模式逐 3 小时（3–252h）降水统计订正：相似个例 +（短时效）光流平流 + 频率匹配；输出 Micaps3/4/NC | 2026-08-26 | 曹勇 | 见下表 | `python -m cli ...`<br>`from runner import process`<br>`python src/runner.py` | 见待办 |

---

## frequency_matching_rain03 目录明细

| 类别 | 路径 | 作用 |
|------|------|------|
| **主程序** | `src/runner.py` | `process` / `main`；时效并行子进程 |
| CLI | `cli/__main__.py` | argparse → `process` |
| 算法 | `src/proc/` | ensemble / frequency_match / optical_flow / rain_extrapolation / spatial_analysis / alglib |
| 本包工具 | `src/utils/` | types / log / string_process / io_meb / util_env / util_paths / grid_data 等 |
| 配置 | `resource/qpf_fm.ini`、`path.json`、`config.json`、`sta.info`、`mask*.dat` | |
| 文档 | `docs/frequency_matching_rain03_算法说明.md`、`nbs/frequency_matching_rain03_说明.ipynb` | 与 docs 同结构：说明 / 原理 / 实现 / 参数 / 使用 / CLI / 示例 |
| 测试 | `test/test_parallel_dispatch.py`、`test_util_env.py`、`test_layout.py`、`test_datetime_args.py`、`test_io_meb.py` | |
| **整理日志** | `00log/frequency_matching_rain03_整理_20260826.log` | |
| **中间数据** | `00temp/frequency_matching_rain03/` | 占位 |
| **原始目录** | 同级 `QPFFrequencyMatch_Rain03/` | 未删，便于对照 |

---

## 待办（需人工补充）

| 序号 | 事项 | 建议 |
|------|------|------|
| 1 | 业务路径端到端未复跑 | 配置 `path.json` 后 `python -m cli ecmwf YYYYMMDDHHMM` |
| 2 | 与 Rain01 并行模型未完全统一 | 仍保留时效子进程；可后续对齐 `is_multi` |
| 3 | docs/nbs 已与源码注释对齐 | 业务路径端到端仍待复跑 |
| 4 | `00temp` 仅占位 | 有对照样本再放入 |
| 5 | 原目录是否归档 | 验证通过后决定是否只保留本包 |
| 6 | 旧名 `multi_qpf_fm_rain03` 目录 | 若仍存在可删除，以本包为准 |
