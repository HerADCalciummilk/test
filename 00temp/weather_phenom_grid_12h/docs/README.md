# 网格天气现象电码生成

> **版本 v1.0.0** | 依据 **QX/T 740-2024** 行业标准

读取网格预报 NC 数据，自动判识31种天气现象并输出标准5位综合电码网格。

---

## 目录

1. [概述](#概述)
2. [环境要求](#环境要求)
3. [数据准备](#数据准备)
4. [运行方式](#运行方式)
5. [输出说明](#输出说明)
6. [项目结构](#项目结构)

---

## 概述

系统采用 **cli / src 两层架构**，职责严格分离：

- **cli 层**：负责数据加载（NC文件I/O，唯一入口）与调度编排，包含命令行入口
- **src 层**：纯内存计算（判识 → 选取 → 逻辑关系 → 编码），只接收 cli 层传入的内存数据，不涉及任何文件读取

算法与架构细节详见 [algorithm_guide.md](algorithm_guide.md)。

---

## 环境要求

- Python **3.10+**
- 必要依赖：`numpy >= 1.24`、`xarray >= 2023.1`、`netcdf4 >= 1.6`、`meteva >= 1.3`、`numexpr >= 2.8`

```powershell
# 安装依赖（推荐）
pip install -r env/requirements.txt

# 或以可编辑模式安装本项目（使 cli 脚本全局可用）
pip install -e ".[dev]"
```

---

## 数据准备

### 目录结构

```
{DATA_ROOT}/{变量名}/{INIT_TIME}/YYYYMMDDHH.TTT.nc
```

### 数据变量

| 变量 | 说明 | 有效时效 |
|------|------|----------|
| R03 | 3h 累计降水量 (mm) | 003~240h |
| PTYPE03 | 降水类型 (1=雨/2=雪/3=雨夹雪/4=冻雨) | 003~240h |
| TCC | 总云量 (% 或 0~1，自动识别) | 003~240h |
| FOG / HAZE / SAND | 雾/霾/沙尘等级 | 003~072h |
| THUNDER / HAIL | 雷暴/冰雹标志 | 003~072h |

### 配置数据路径

优先级从高到低：

```powershell
# 方式一：CLI 参数（最高优先级，临时覆盖）
python cli/main.py 2026030100 --data-root \\your_server\share\SCMOC

# 方式二：环境变量（推荐生产部署）
$env:SCMOC_DATA_ROOT = "\\your_server\share\SCMOC"
python cli/main.py 2026030100

# 方式三：修改 resource/config.py 中的默认值（仅开发参考）
```

---

## 运行方式

### 命令行

```powershell
# 处理单个起报时次（全部20段，FH 003~240h）
python cli/main.py 2026030100

# 处理多个起报时次
python cli/main.py 2026030100 2026030112

# 只处理前6个时段（0~72h）
python cli/main.py 2026030100 --seg-range 1 6

# 指定输出目录 / 数据根目录
python cli/main.py 2026030100 --output-dir D:/output --data-root \\server\share\SCMOC

# 仅统计，不保存文件
python cli/main.py 2026030100 --stats-only
```

**退出码**（POSIX 标准）：

| 退出码 | 含义 |
|--------|------|
| 0 | 全部成功 |
| 1 | 数据缺失（部分时段跳过，非致命） |
| 2 | 计算错误（致命异常） |

> 并行参数（`--max-seg-workers`/`--max-workers`/`--numexpr-threads`）调优说明详见 [algorithm_guide.md](algorithm_guide.md)。

### Python API

```python
from cli.runner import run

# 处理单个起报时次（cli 层加载数据 + src 层纯内存计算）
run("2026030100", output_dir="./PHENOM")
```

---

## 输出说明

```
{output_dir}/{INIT_TIME}/YYYYMMDDHH.TTT.nc
```

例如 `2026030100.012.nc` 对应第 1 时段（FH 003~012h）。

NC 文件采用 **meteva 标准 6D DataArray** 格式，维度为 `[member, level, time, dtime, lat, lon]`，变量名 `phenom_code`：

```python
import meteva.base as meb
da = meb.read_griddata_from_nc("2026030100.012.nc")
# 5位综合电码: 00000=晴, 00101=多云, 10207=阴转小雨, ...
```

---

## 项目结构

```
weather_phenom_grid_12h/
├── cli/
│   ├── main.py             # 命令行入口（POSIX 退出码）
│   ├── runner.py           # 编排调度（加载cli.data_loader + 计算src.processor，并行）
│   └── data_loader.py      # 数据加载（唯一的文件I/O入口，meteva 6D 接口）
├── src/
│   ├── __init__.py        # 包入口（__version__ + Plugin 导出）
│   ├── processor.py       # 核心计算（纯内存，Plugin 单例，不涉及任何文件I/O读取）
│   ├── identifier.py      # 天气现象判识 → DIA_WeatherPhenomIdentifier
│   ├── selector.py         # A/B 现象选取 → DIA_WeatherPhenomSelector
│   ├── logic_judger.py    # 逻辑关系判断 → DIA_WeatherPhenomLogicJudger
│   └── encoder.py         # 电码编码 → DIA_WeatherPhenomEncoder
├── resource/
│   ├── config.py          # 数据路径与时效配置
│   ├── data_schema.py     # 数据结构常量
│   └── weather_config.py  # 天气现象标准配置（阈值/互斥/影响级）
├── test/                  # pytest 单元测试
├── docs/
│   ├── README.md          # 本文件
│   └── algorithm_guide.md # 算法技术指南（架构、流程、并行策略、测试）
├── nbs/
│   └── run_test.ipynb     # 一键集成测试 Notebook
├── env/
│   └── requirements.txt   # 依赖清单
├── pyproject.toml         # 包管理 + pytest 配置
└── conftest.py            # pytest 路径配置
```
