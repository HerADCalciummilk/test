# NIMM 算法仓库整理清单

以表格形式记录已整理入本仓库的算法，便于检索、维护与后续补充。

> **说明**：一次「原始算法整理过程」对应 `00log/` 下的一份日志；中间数据放 `00temp/<算法代号>/`。

---

## 已整理算法列表

| 算法种类 | 算法代号 | 算法功能 | 更新时间 | 贡献人 | 源码与配置位置 | CLI 入口 | 仍存在问题 |
|----------|----------|----------|----------|--------|----------------|----------|------------|
| 短临预报 · 降水集成 | **mait_1h** / multi_rain_mait01_blending | 1 小时多模式 Micaps3 站点降水 TS 动态加权集成；频率匹配订正；Cressman 插值至格点；输出 Micaps3 站点 + Micaps4/NC 格点产品；`is_multi` 控制多进程 | 2026-07-23 | 郭云谦、曹勇、陈荣 | 见下表「mait_1h 目录明细」 | `python -m cli --time-inputs=...`<br>`from mait_1h import process`<br>`python src/mait_1h.py`（`__main__` 内直接传参）<br>`python -m cli verify ...` | 见下表「mait_1h 待办」 |

---

## mait_1h 目录明细

| 类别 | 路径 | 作用 |
|------|------|------|
| 执行入口 | `src/mait_1h.py` | `process(...)` / `RunProcess` 供模块引用；`__main__` 中直接传参运行 |
| CLI 路由 | `cli/__main__.py` | `python -m cli` 解析参数（Clize，含中文说明）→ `mait_1h.process` |
| 检验 CLI | `cli/verify.py` | prepare / result / ts / plot-dt；`python -m cli verify ...` |
| 算法核心 | `src/mait_1_plugin.py` | TS 权重、DataFlg、Cressman 插值 |
| 读数 | `src/mait_1_plugin_util.py` | Micaps3/M4/NC 读数、background、时间回溯 |
| 运行上下文 | `src/utils/util_context.py` | `RunContext`、`build_run_context`、`dt_search_base` |
| 配置 | `src/utils/util_env.py` | `resource/mait_1.ini` 解析 |
| I/O | `src/utils/util_new.py` | 掩码、Micaps 写出、频率匹配、全 0 背景 |
| 插件 | `utils/base_plugin.py`、`utils/multipro_plugin.py` | 插件基类、多进程（与 `00temp/utils` 合并） |
| 检验辅助 | `utils/data_prepare_plugin.py` | meteva 检验数据集准备 |
| 配置资源 | `resource/mait_1.ini`、`resource/para*.ini`、`resource/para_1_background.ini`、`resource/sta.info` | 路径、模式、站点、背景格点 |
| 文档 | `docs/MAIT_1H_程序说明.md`、`nbs/mait_1h_说明.ipynb` | 程序说明与原理 notebook |
| 测试 | `test/test_run_context.py`、`test/mait_1_nimm_test.py`、`test/test_mait_1h.py` | 单元测试与批量业务脚本 |
| 整理日志 | `00log/mait_1h_整理_20260723.log`（本次）；`00log/mait_1h_整理_20260703.log`（前次） | 一次整理过程一份日志 |
| 中间数据 | `00temp/mait_1h/` | 整理过程临时样本（当前为空占位） |
| 仓库索引 | 仓库根 `00log/multi_rain_mait01_blending.md` | 全库摘要日志 |

> **入口约定**：命令行用 `python -m cli`；模块用 `from mait_1h import process`；直跑改 `src/mait_1h.py` 的 `__main__` 传参。Clize 已不在 `src/mait_1h.py` 内。

---

## mait_1h 待办（需人工补充）

| 序号 | 问题 | 建议处理 |
|------|------|----------|
| 1 | docs / nbs / README 旧入口文案 | 统一为 `python -m cli` / `mait_1h.process` / `__main__` 传参 |
| 2 | 依赖清单可能不完整 | 按 meteva / clize 等补全 `requirements` 并入库 |
| 3 | 生产数据路径不在仓库内 | 部署配置 `para_1.ini` 与 background；本地以单元测试为主 |
| 4 | 默认 `para_ini=resource/local.ini` | 生产改为 `para_1.ini` 或 CLI `--para-path` |
| 5 | 改造前后对比未在新结构复验 | 目标环境重跑 notebook 对比段 |
| 6 | 尚未迁入正式 `NIMM/05blending/` | 路径与包名按仓库规范再调整 |
| 7 | 完整业务试跑未做 | 用真实 Micaps 数据验证集成效果与多进程 |
| 8 | `00temp/mait_1h/` 仅占位 | 有对照/备份中间文件时放入并记入日志，无则保持空 |

---

## 新增算法登记模板

| 算法种类 | 算法代号 | 算法功能 | 更新时间 | 贡献人 | 源码与配置位置 | CLI 入口 | 仍存在问题 |
|----------|----------|----------|----------|--------|----------------|----------|------------|
| （填写） | （填写） | （填写） | YYYY-MM-DD | （填写） | （填写） | （填写） | （填写） |

同时新增：

- `00log/<算法代号>_整理_<YYYYMMDD>.log`
- `00temp/<算法代号>/`
