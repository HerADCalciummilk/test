# NIMM 算法仓库整理清单

以表格形式记录已整理入本仓库的算法，便于检索、维护与后续补充。

> **说明**：一次「原始算法整理过程」对应 `00log/` 下的一份日志；中间数据放 `00temp/<算法代号>/`。

---

## 已整理算法列表

| 算法种类 | 算法代号 | 算法功能 | 更新时间 | 贡献人 | 源码与配置位置 | CLI 入口 | 仍存在问题 |
|----------|----------|----------|----------|--------|----------------|----------|------------|
| 短临预报 · 风场融合 | **fft_merge** / multi_wind_fft_blending | 基于 FFT 谱方法与迭代优化，估计主风场与辅助风场位移场并平流融合；支持 UV 矢量、多辅助场；`is_multi` 控制多进程 | 2026-10-27 | 胡海川、李振、郭云谦 | 见下表「fft_merge 目录明细」 | `python -m cli --main-uv <主风场.m11> --ass-uv <辅助风场.m11> --output-dir resource/output --output-prefix sample_a` | 见下表「fft_merge 待办」 |

---

## fft_merge 目录明细

| 类别 | 路径 | 作用 |
|------|------|------|
| 算法核心 | `src/fft_merge.py` | `FFTMergePlugin` 频域特征匹配与平流融合 |
| 执行入口 | `src/main.py` | `process(...)` 供模块引用；`__main__` 中直接传参运行 |
| CLI 路由 | `cli/__main__.py` | `python -m cli --main-uv <主风场.m11> --ass-uv <辅助风场.m11> --output-dir resource/output --output-prefix sample_a` |
| 运行配置 | `resource/fft_merge.ini` | 未显式传入的参数先读此文件，再没有则用代码预设；算法常量只在此配置 |
| 共享多进程 | `00temp/utils/multipro_plugin.py` | `SimpleParallelTool`（`main.py` 将 `00temp` 加入 `sys.path`） |
| 测试 | `test/test_fft_merge.py`、`test/test_main.py` | 算法单元测试与 `process` 集成测试 |
| 文档 | `docs/FFT_MERGE_程序说明.md`、`docs/multi_wind_fft_blending.md` | 程序说明与整理说明 |
| notebook | `nbs/fft_merge_说明.ipynb` | 原理与示例 |
| 样例资源 | `NIMM_pip_testdata/multi_wind_fft_blending/test_data/` | 与 `NIMM_pip_repos` 同级；Micaps11 样例（当前缺失） |
| 整理日志 | `00log/fft_merge_整理_20260723.log`（本次）；`00log/fft_merge_整理_20260722.log`（前次） | 一次整理过程一份日志 |
| 中间数据 | `00temp/fft_merge/` | 整理过程临时样本 |
| 仓库索引 | 仓库根 `NIMM_list.md`、`00log/multi_wind_fft_blending.md` | 全库算法表与摘要日志 |

> **已废弃**：`cli/fft_merge_cli.py`（原示例 CLI）。请使用 `python -m cli` 或 `python src/main.py`（改 `__main__` 传参）。

---

## fft_merge 待办（需人工补充）

| 序号 | 问题 | 建议处理 |
|------|------|----------|
| 1 | `NIMM_pip_testdata/.../test_data` 样例缺失 | 补齐 `sample_a1/a2_uv.m11`、`sample_b1/b2_uv.m11` 后跑通 `python src/main.py` / pytest |
| 2 | notebook 与 docs 的 CLI 示例 | 已改为 `python -m cli --main-uv ...`；参数优先级见 `resource/fft_merge.ini` |
| 3 | 未继承统一 `BasePlugin` | 正式入库前评估是否接入 `NIMM.utilities.base_plugin` |
| 4 | 尚未迁入正式 `NIMM/05blending/` | 路径与包名按仓库规范再调整 |
| 5 | 完整业务试跑未做 | 用真实 Micaps11 风场验证融合效果 |
| 6 | `00temp/fft_merge/` 仅占位 | 有对照/备份中间文件时放入并记入日志，无则保持空 |

---

## 新增算法登记模板

| 算法种类 | 算法代号 | 算法功能 | 更新时间 | 贡献人 | 源码与配置位置 | CLI 入口 | 仍存在问题 |
|----------|----------|----------|----------|--------|----------------|----------|------------|
| （填写） | （填写） | （填写） | YYYY-MM-DD | （填写） | （填写） | （填写） | （填写） |

同时新增：

- `00log/<算法代号>_整理_<YYYYMMDD>.log`
- `00temp/<算法代号>/`
