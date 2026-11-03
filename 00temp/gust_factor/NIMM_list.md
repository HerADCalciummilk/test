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
| 通用算法 · 阵风订正 | **gust_factor** | 历史站点统计阵风系数；U/V 订正阵风格点 | 2026-09-04 | （待补） | 见下表「目录明细」 | `python -m cli ...`<br>`from gust_factor import process`<br>`python src/gust_factor.py` | 见下表「待办」 |

---

## gust_factor 目录明细

| 类别 | 路径 | 作用 |
|------|------|------|
| **主程序 / 算法核** | `src/gust_factor.py` | `GustFactorCalculatorPlugin` / `GustCorrectWithFactorPlugin` / `process` |
| CLI | `cli/__main__.py` | argparse → `process`；中文 `--help` |
| 本包工具 | `src/utils/util_env.py` | 读 `resource/gust_factor.ini` |
| 共享插件路径 | 本包根 `utils/__init__.py` | 合并 `../../utils` + `src/utils` |
| 配置资源 | `resource/gust_factor.ini`、`test_data/`、`sample/*.nc` | 运行配置与演示样例 |
| 文档 | `docs/gust_factor_程序说明.md`、`README.md` | 说明 / 原理 / 实现 / 应用 / 调用 |
| notebook | `nbs/gust_factor_说明.ipynb` | 与 docs 同结构 |
| 测试 | `test/test_layout.py`、`test_util_env.py`、`test_smoke.py` | 布局 / ini / 烟测 |
| **整理日志** | `00log/gust_factor_整理_20260904.log` | 一次整理过程一份日志 |
| **中间数据** | `00temp/gust_factor/` | 整理过程临时样本（当前占位） |
| 原始目录 | 同级 `GustFactorForNimm/` | 对照保留 |

> **入口约定**：命令行用 `python -m cli`；模块用 `from gust_factor import process`；直跑 `python src/gust_factor.py`。无独立 `runner`。

---

## gust_factor 待办（需人工补充）

| 序号 | 仍存在问题（目录/事项） | 建议处理 |
|------|-------------------------|----------|
| 1 | 贡献人 / 原始绝对路径登记不完整 | 补全本表与 `00log/*_整理_*.log` 页眉 |
| 2 | 业务业务路径端到端未与原目录逐字节对照 | 配置真实路径后对照 `GustFactorForNimm` 输出 |
| 3 | `00temp/gust_factor/` 仅占位 | 有对照中间文件时放入并记入 `00log/` |
| 4 | `requirements*.txt` 未锁定版本 | 按环境补全 numpy / pandas / meteva_base |

---

## 新增算法登记模板

| 算法种类 | 算法代号 | 算法功能 | 更新时间 | 贡献人 | 源码与配置位置 | CLI 入口 | 仍存在问题 |
|----------|----------|----------|----------|--------|----------------|----------|------------|
| （填写） | （填写） | （填写） | YYYY-MM-DD | （填写） | （填写） | （填写） | （填写） |

同时新增：

- `00log/<算法代号>_整理_<YYYYMMDD>.log`
- `00temp/<算法代号>/`
