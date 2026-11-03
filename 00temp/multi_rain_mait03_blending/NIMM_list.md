# NIMM 算法仓库整理清单

> 一次整理过程对应 `00log/` 一份日志；中间数据放 `00temp/<算法代号>/`。

---

## 已整理算法列表

| 算法种类 | 算法代号 | 算法功能 | 更新时间 | 贡献人 | CLI 入口 | 仍存在问题 |
|----------|----------|----------|----------|--------|----------|------------|
| 短临预报 · 降水集成 | **mait_3h** / multi_rain_mait03_blending | 3h 多模式 Micaps3 TS 加权集成；频率匹配；Cressman；输出 Micaps3/4；`is_multi` 按起报多进程 | 2026-09-02 | 曹勇等 | `python -m cli ...`<br>`from mait_3h import process`<br>`python src/mait_3h.py` | 见待办 |

---

## mait_3h 目录明细

| 类别 | 路径 | 作用 |
|------|------|------|
| 主程序 | `src/mait_3h.py` | `process` / `RunProcess` |
| CLI | `cli/__main__.py` | argparse → `process` |
| 算法 | `src/mait_3_plugin.py` | TS 权重、DataFlg、Cressman |
| 读数 | `src/mait_3_plugin_util.py` | Micaps 读数、beta、写出 |
| 配置 | `src/utils/util_env.py` | `resource/mait_3.ini` |
| I/O | `src/utils/util_new.py` | 掩码、频率匹配 |
| 多进程 | `utils/multipro_plugin.py` | `SimpleParallelTool`（与 mait01/24 相同） |
| 资源 | `resource/mait_3.ini`、`para_3*.ini`、`para_3_background*.ini`、`station_info.txt`、`mask010.dat` | |
| 文档 | `docs/MAIT_3H_程序说明.md`、`nbs/mait_3h_说明.ipynb` | 与 docs 同结构：说明 / 原理 / 实现 / 参数 / 使用 / CLI |
| 测试 | `test/` | 布局 / util_env / 多进程；`mait_3_nimm_test.py` 业务时段入口 |
| 整理日志 | `00log/mait_3h_整理_20260827.log` | |
| 原始目录 | 同级 `mait_3h/` | 对照保留 |

---

## 待办

| 序号 | 事项 |
|------|------|
| 1 | 业务路径端到端复跑与原 `mait_3h` 对照 |
| 2 | 是否进一步对齐 mait01 的 `RunContext` / background_ini |
| 3 | `00temp/mait_3h/` 仅占位 |
| 4 | 原目录 `mait_3h` 验证后可归档 |
