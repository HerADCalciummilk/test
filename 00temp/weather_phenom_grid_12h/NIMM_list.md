# NIMM 算法仓库整理清单

以表格形式记录已整理入本仓库的算法，便于检索、维护与后续补充。

> **说明**：一次「原始算法整理过程」对应 `00log/` 下的一份日志；中间数据放 `00temp/<算法代号>/`。

---

## 已整理算法列表

| 算法种类 | 算法代号 | 算法功能 | 更新时间 | 贡献人 | 源码与配置位置 | CLI 入口 | 仍存在问题 |
|----------|----------|----------|----------|--------|----------------|----------|------------|
| 诊断相关 · 天气现象 | **weather_phenom_grid_12h** | 读取网格预报 NC，按 QX/T 740-2024 判识 31 种天气现象，选取 A/B、判断逻辑关系（单一/转/间/伴有），输出 12h 时段 5 位综合电码网格（meteva 6D NetCDF）；多起报支持 `is_multi` 多进程 | 2026-07-23 | 待补充 | 见下表「weather_phenom_grid_12h 目录明细」 | `python -m cli <YYYYMMDDHH> [...] [--is-multi --pro-count N]`<br>`from src.main import process`<br>`python src/main.py`（`__main__` 内直接传参） | 见下表「weather_phenom_grid_12h 待办」 |

---

## weather_phenom_grid_12h 目录明细

| 类别 | 路径 | 作用 |
|------|------|------|
| 执行入口 | `src/main.py` | `process(...)` 供外部模块引用；`__main__` 中直接给 `process` 传参运行 |
| CLI 路由 | `cli/__main__.py` | `python -m cli` 解析参数 → `src.main.process` |
| 数据加载 | `src/utils/data_loader.py` | SCMOC 网格 NC 读取（meteva），供主程序调用 |
| 输出工具 | `src/utils/output.py` | 电码场写 NetCDF、统计打印 |
| 计算调度 | `src/processor.py` | 纯内存：判识→选取→逻辑→编码→保存 |
| 判识插件 | `src/identifier.py` | `DIA_WeatherPhenomIdentifier` |
| 选取插件 | `src/selector.py` | `DIA_WeatherPhenomSelector` |
| 逻辑插件 | `src/logic_judger.py` | `DIA_WeatherPhenomLogicJudger` |
| 编码插件 | `src/encoder.py` | `DIA_WeatherPhenomEncoder` / `decode` |
| 业务规则 | `resource/weather_config.py` | 电码、影响级、阈值、互斥、逻辑关系 |
| 结构常量 | `resource/data_schema.py` | 变量分组、时效、12h 时段映射 |
| 运行配置 | `resource/config.py` | `SCMOC_DATA_ROOT` / 路径模板（输入在外部 SCMOC，非仓库内） |
| 共享多进程 | `00temp/utils/multipro_plugin.py` | `SimpleParallelTool`（`main.py` 将上级 `00temp` 加入 `sys.path`） |
| 算法说明 | `docs/算法说明.md` | 场景 / 原理 / 实现 / 参数 / 调用 |
| 使用说明 | `docs/README.md` | 安装与运行（部分旧入口文案待人工同步） |
| Notebook | `nbs/算法说明.ipynb` 等 | 说明与测试/性能脚本 |
| 单元测试 | `test/test_*.py` | data_loader + 四 Plugin |
| 运行输出 | `PHENOM/<起报时次>/` | 业务产出电码 NC（非整理中间数据） |
| 整理日志 | `00log/weather_phenom_grid_12h_整理_20260723.log` | 本次（入口/CLI/多进程）整理记录 |
| 历史日志 | `00log/weather_phenom_grid_12h_整理_20260722.log` | 文档与 NIMM 目录初建记录 |
| 中间数据 | `00temp/weather_phenom_grid_12h/` | 整理过程临时样本（当前为空占位） |

> **已废弃并删除**：`cli/main.py`、`cli/runner.py`、`cli/data_loader.py`。  
> 请使用：`python -m cli` / `from src.main import process` / `src/utils/data_loader.py`。

---

## weather_phenom_grid_12h 待办（需人工补充）

| 序号 | 问题 | 建议处理 |
|------|------|----------|
| 1 | 贡献人、原始代码来源未登记 | 补全本表与整理日志 |
| 2 | docs / nbs 仍有旧 `cli/main.py`、`cli/runner`、`cli/data_loader` 文案 | 改为 `python -m cli` / `src.main.process` / `src.utils.data_loader` |
| 3 | docs 多份算法文档并存 | 明确 `算法说明.md` / `algorithm_guide.md` / `算法技术指南.md` 主从 |
| 4 | 输入依赖外部 SCMOC 网络盘 | 部署设 `SCMOC_DATA_ROOT` 或 `--data-root`；本地以 pytest/mock 为主 |
| 5 | `PHENOM/` 运行输出是否入库 | 建议加入 `.gitignore`，勿与 `00temp/` 混淆 |
| 6 | 根目录空 `utils/`、汇报 PPT 大文件 | 确认删除/移出或补充说明 |
| 7 | `nbs/算法说明.ipynb` 未本机执行验证 | 打开跑通路径与 mock 流程 |
| 8 | 多起报 `--is-multi` 真实数据端到端未复跑 | 有 SCMOC 权限后验证多进程 |
| 9 | 正式入库中央仓库路径/编号 | 补充 NIMM 目标路径与种类编号 |
| 10 | `00temp/weather_phenom_grid_12h/` 仅占位 | 有对照中间文件时放入并记入日志 |

---

## 新增算法登记模板

| 算法种类 | 算法代号 | 算法功能 | 更新时间 | 贡献人 | 源码与配置位置 | CLI 入口 | 仍存在问题 |
|----------|----------|----------|----------|--------|----------------|----------|------------|
| （填写） | （填写） | （填写） | YYYY-MM-DD | （填写） | （填写） | （填写） | （填写） |

同时新增：

- `00log/<算法代号>_整理_<YYYYMMDD>.log`
- `00temp/<算法代号>/`
