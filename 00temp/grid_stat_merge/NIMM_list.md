# NIMM 算法仓库整理清单

以表格形式记录已整理入本仓库的算法，便于检索、维护与后续补充。

> **说明**  
> - 一次「原始算法整理过程」对应 `00log/` 下的一份日志。  
> - 整理过程中间数据放 `00temp/<算法代号>/`。  
> - 「仍存在问题」详见本表待办，并与对应 `00log/*_整理_*.log` 同步。

---

## 已整理算法列表

| 算法种类 | 算法代号 | 算法功能 | 更新时间 | 贡献人 | 源码与配置位置 | CLI 入口 | 仍存在问题 |
|----------|----------|----------|----------|--------|----------------|----------|------------|
| 通用算法 · 格站融合 | **grid_stat_merge** | 站点偏差高斯订正网格：`融合 = 原格点 + 偏差场`；可选地形掩膜 / 热传导 | 2026-08-26 | （待补） | 见下表「目录明细」 | `python -m cli ...`<br>`from runner import process`<br>`python src/runner.py` | 见下表「待办」 |

---

## grid_stat_merge 目录明细

| 类别 | 路径 | 作用 |
|------|------|------|
| **主程序** | `src/runner.py` | `process(...)` 读格点/站点 → `do_gs_merge` → 写 Micaps4 |
| **算法核心** | `src/grid_stat_merge.py` | `do_gs_merge` / `diffuse_values` / `GridStatMergePlugin` |
| CLI | `cli/__main__.py` | argparse → `runner.process`；中文 `--help` |
| 本包工具 | `src/utils/util_env.py` | 读 `resource/grid_stat_merge.ini`（`from utils.util_env`） |
| 共享插件 | 仓库根 `utils/base_plugin.py`（及可选 `grid_stat_merge_plugin.py`） | 经本包根 `utils/__init__.py` 合并 `../../utils` + `src/utils` |
| 配置资源 | `resource/grid_stat_merge.ini` | 路径与融合参数（`R` / `domain` / 热传导等） |
| 文档 | `docs/grid_stat_merge_程序说明.md`、`README.md` | 算法与入口 |
| notebook | `nbs/grid_stat_merge_说明.ipynb` | 说明 notebook |
| 测试 | `test/test_layout.py`、`test_util_env.py`、`test_merge_smoke.py` | 布局 / ini / 小场烟测 |
| **整理日志** | `00log/grid_stat_merge_整理_20260826.log` | 一次整理过程一份日志 |
| **中间数据** | `00temp/grid_stat_merge/` | 整理过程临时样本（当前占位） |

> **入口约定**：命令行用 `python -m cli`；模块用 `from runner import process`；直跑改 `src/runner.py` 的 `__main__` 或传 `process(...)`。

---

## grid_stat_merge 待办（需人工补充）

| 序号 | 仍存在问题（目录/事项） | 建议处理 |
|------|-------------------------|----------|
| 1 | 贡献人 / 原始绝对路径登记不完整 | 补全本表与 `00log/*_整理_*.log` 页眉 |
| 2 | `resource/` 未附带演示格点/站点样例 | 放入最小 Micaps4/3 样例并改 ini |
| 3 | 业务端到端未复跑 | 配置真实路径后跑 `python -m cli` / `src/runner.py` |
| 4 | `00temp/grid_stat_merge/` 仅占位 | 有对照中间文件时放入并记入 `00log/` |
| 5 | 与共享 `utils/grid_stat_merge_plugin.py` 双份算法 | 确认以本包 `src/grid_stat_merge.py` 为业务入口；共享插件保持同步或改为 re-export |
| 6 | `requirements*.txt` 未锁定版本 | 按环境补全 numpy / scipy / pandas / meteva |

---

## 新增算法登记模板

| 算法种类 | 算法代号 | 算法功能 | 更新时间 | 贡献人 | 源码与配置位置 | CLI 入口 | 仍存在问题 |
|----------|----------|----------|----------|--------|----------------|----------|------------|
| （填写） | （填写） | （填写） | YYYY-MM-DD | （填写） | （填写） | （填写） | （填写） |

同时新增：

- `00log/<算法代号>_整理_<YYYYMMDD>.log`
- `00temp/<算法代号>/`
