# NIMM 算法仓库整理清单

以表格形式记录已整理入本仓库的算法，便于检索、维护与后续补充。

> **说明**：一次「原始算法整理过程」对应 `00log/` 下的一份日志；中间数据放 `00temp/<算法代号>/`。

---

## 已整理算法列表

| 算法种类 | 算法代号 | 算法功能 | 更新时间 | 贡献人 | 源码与配置位置 | CLI 入口 | 仍存在问题 |
|----------|----------|----------|----------|--------|----------------|----------|------------|
| 短临预报 · 降水集成 | **mait_24h** / multi_rain_mait24_blending | 多模式 24 小时累积降水自适应集成（分区 TS 权重 + 历史 beta + 站点融合 + 格点插值输出 Micaps3/4）；`is_multi` 控制多进程 | 2026-07-23 | 郝书剑、赵如奇、杨宸源 | 见下表「mait_24h 目录明细」 | `python -m cli --time-inputs=...`<br>`from mait_24h import process`<br>`python src/mait_24h.py`（`__main__` 内直接传参）<br>`python -m cli verify ...` | 见下表「mait_24h 待办」 |

---

## mait_24h 目录明细

| 类别 | 路径 | 作用 |
|------|------|------|
| 执行入口 | `src/mait_24h.py` | `process(...)` / `RunProcess` 供模块引用；`__main__` 中直接传参运行 |
| CLI 路由 | `cli/__main__.py` | `python -m cli` 解析参数（Clize，含中文说明）→ `mait_24h.process` |
| 检验 CLI | `cli/verify.py` | TS/HFMC 检验与出图；`python -m cli verify ...` |
| 算法核心 | `src/mait_24_plugin.py` | TS 权重、站点→格点插值 |
| 读数 | `src/mait_24_plugin_util.py` | 模式/实况/背景场读取 |
| 运行上下文 | `src/utils/util_context.py` | `RunContext`、`build_run_context` |
| 配置 | `src/utils/util_env.py` | `resource/mait_24.ini` 解析 |
| I/O | `src/utils/util_new.py` | INI、掩码、Micaps、beta 读写 |
| 掩码辅助 | `src/utils/util_mask_file.py` | GeoJSON/矢量 → 掩码栅格 |
| 插件 | `utils/base_plugin.py`、`utils/multipro_plugin.py` | 插件基类、多进程（与 `00temp/utils` 合并） |
| 检验辅助 | `utils/data_prepare_plugin.py` | 检验数据准备 |
| 配置资源 | `resource/mait_24.ini`、`resource/para_24.ini`、`resource/para_24_background.ini` | 路径、模式、背景格点 |
| 文档 | `docs/MAIT_24H_程序说明.md`、`nbs/mait_24h_说明.ipynb` | 程序说明与原理 notebook |
| 测试 | `test/test_run_context.py`、`test/test_mait_24h_cli_flow.py`、`test/test_mait_24h.py` | 单元测试与业务脚本 |
| 整理日志 | `00log/mait_24h_整理_20260723.log`（本次）；`00log/mait_24h_整理_20260706.log`（前次） | 一次整理过程一份日志 |
| 中间数据 | `00temp/mait_24h/` | 整理过程临时样本（当前为空占位） |
| 仓库索引 | 仓库根 `00log/multi_rain_mait24_blending.md` | 全库摘要日志 |

> **入口约定**：命令行用 `python -m cli`；模块用 `from mait_24h import process`；直跑改 `src/mait_24h.py` 的 `__main__` 传参。Clize 已不在 `src/mait_24h.py` 内。  
> **导入约定**：`src/utils/` 与根目录 `utils/` 合并为同一 `utils` 包（见 `utils/__init__.py`）。

---

## mait_24h 待办（需人工补充）

| 序号 | 问题 | 建议处理 |
|------|------|----------|
| 1 | docs / nbs / README 旧入口文案 | 统一为 `python -m cli` / `mait_24h.process` / `__main__` 传参 |
| 2 | 生产数据路径不在仓库内 | 部署时修改 `para_24.ini` 等实际挂载路径 |
| 3 | `resource/` 资源偏多 | 正式入库前筛选最小配置/掩码/样例集 |
| 4 | 扩展插件未纳入主流程 CI | `data_distribute` 等按需保留或移出 |
| 5 | 尚未迁入正式 `NIMM/05blending/` | 路径与包名按仓库规范再调整 |
| 6 | 完整业务试跑未做 | 用真实 Micaps 数据验证集成效果与多进程 |
| 7 | `00temp/mait_24h/` 仅占位 | 有对照/备份中间文件时放入并记入日志，无则保持空 |

---

## 新增算法登记模板

| 算法种类 | 算法代号 | 算法功能 | 更新时间 | 贡献人 | 源码与配置位置 | CLI 入口 | 仍存在问题 |
|----------|----------|----------|----------|--------|----------------|----------|------------|
| （填写） | （填写） | （填写） | YYYY-MM-DD | （填写） | （填写） | （填写） | （填写） |

同时新增：

- `00log/<算法代号>_整理_<YYYYMMDD>.log`
- `00temp/<算法代号>/`
