# 算法技术指南

**系统名称**：网格天气现象综合电码生成系统  
**标准依据**：QX/T 740-2024《基于网格预报的城镇预报生成规范 天气现象》  
**架构规范**：国省统筹算法技术规范（三级架构）  
**版本**：v1.0.0

---

## 一、三级架构总览

```
┌─────────────────────────────────────────────────────────┐
│  Level 3  算法应用 (CLI)                                  │
│           cli/main.py     — 命令行入口，POSIX 退出码       │
│           cli/runner.py   — 编排调度：加载(cli.data_loader)│
│                              + 计算(src.processor)，并行   │
│           cli/data_loader.py — 唯一的文件I/O入口           │
│                              （meteva 读取NC文件）          │
├─────────────────────────────────────────────────────────┤
│  Level 2  算法插件 (Plugins)                              │
│           DIA_WeatherPhenomIdentifier   判识               │
│           DIA_WeatherPhenomSelector     选取               │
│           DIA_WeatherPhenomLogicJudger  逻辑关系判断        │
│           DIA_WeatherPhenomEncoder      编码               │
├─────────────────────────────────────────────────────────┤
│  Level 1  基础函数 (Functions)                            │
│           identify / select / judge / encode / decode    │
└─────────────────────────────────────────────────────────┘
```

**DIA** = Diagnostic（诊断算法），适用于从预报场推断天气现象的一类算法。

**分层职责边界**（cli 与 src 严格解耦）：

| 层级 | 模块 | 职责 | 是否涉及文件I/O |
|------|------|------|----------------|
| cli | `cli/data_loader.py` | 读取NC文件，产出内存数据（data_dict/lat/lon） | **是**（唯一入口） |
| cli | `cli/runner.py` | 编排：先调用 `cli.data_loader.load_segment()` 加载，再调用 `src.processor.run_segment()` 计算 | 否（仅编排） |
| cli | `cli/main.py` | 命令行参数解析，调用 `cli.runner` | 否 |
| src | `processor.py` 及各算法模块 | 纯内存计算（判识/选取/逻辑/编码），保存输出NC文件 | 否（只接收内存数据，不读取输入文件） |

> src 包不 `import meteva`、不感知任何数据加载细节，`run_segment(data_dict, shape, lat_arr, lon_arr, init_time, seg_idx, output_dir)` 的入参均为内存对象，保证算法层环境无关、可独立单测（mock即可，无需真实NC文件）。

---

## 二、算法流程

依据 QX/T 740-2024 附录C 流程图（见 `附录图C.1 的流程图.png`）：

```
输入变量 (NC格式)
    │
    ▼
[Step 1] 数据加载 — cli 层 唯一文件I/O入口
         cli.data_loader.load_segment()
         读取 R03/PTYPE03/TCC/FOG/HAZE/SAND/THUNDER/HAIL
         返回 {变量名: ndarray[4, lat, lon]}（内存数据，下传至 src 层）
    │
    ▼
[Step 2] 天气现象判识 — DIA_WeatherPhenomIdentifier.process()  [src层，纯内存]
         依附录A 表A.1/A.2/A.3 判识31种天气现象是否出现
         输出 {电码: {"12h": bool[lat,lon], "fine": bool[4,lat,lon]}}
    │
    ▼
[Step 3] 现象选取 — DIA_WeatherPhenomSelector.process()  [src层，纯内存]
         选取影响级最高的A现象 + 独立出现的B现象
         输出 idx_A[lat,lon] int8, idx_B[lat,lon] int8
    │
    ▼
[Step 4] 逻辑关系判断 — DIA_WeatherPhenomLogicJudger.process()  [src层，纯内存]
         判断 A与B 的关系：单一(0) / 转(1) / 间(2) / 伴有(3)
         确定表述顺序 idx_final_A, idx_final_B
    │
    ▼
[Step 5] 综合电码编码 — DIA_WeatherPhenomEncoder.process()  [src层，纯内存]
         生成 5位整型电码：K*10000 + AA*100 + BB
         输出 ndarray[lat,lon] int32
    │
    ▼
输出文件 (NetCDF4, meteva 6D格式) — src.processor._save_nc() 写盘
```

> Step1 属于 cli 层职责，Step2~5 均在 src 层完成，仅接收 Step1 产出的内存数据，不反过来调用任何数据加载接口。实际编排者为 cli/runner.py 中的 run_segment()，它依次调用 cli.data_loader.load_segment()与 src.processor.run_segment()。

---

## 三、Plugin 接口规范

所有 Plugin 必须满足以下接口约束（国省统筹算法技术规范 §3.2）：

```python
class DIA_Xxx:
    def __init__(self, config: dict | None = None) -> None:
        """可选配置注入，默认使用标准参数"""
        ...

    def process(self, *args, **kwargs):
        """主计算接口，严禁文件 I/O"""
        ...
```

**强制约束**：
- 严禁在 `process()` 内部进行文件读写（I/O 解耦）
- 输入输出均为内存对象（`ndarray` / `dict` / `tuple`）
- 环境无关：所有配置通过 `__init__` 注入

---

## 四、配置模块职责划分

`resource/` 目录下的三个模块职责严格分离：

```
resource/
  ├── data_schema.py     ← 算法结构常量（环境无关）
  ├── config.py          ← 运行环境配置（部署环境相关）
  └── weather_config.py  ← 天气现象业务规则（环境无关）
```

### 4.1 `resource/data_schema.py` — 算法结构常量

包含与运行环境完全无关的算法层定义，任何环境下值不变：

| 常量 | 说明 |
|------|------|
| `VARS_240H` | `["R03", "PTYPE03", "TCC"]` — 240h 时效变量 |
| `VARS_72H` | `["FOG", "HAIL", "HAZE", "SAND", "THUNDER", "VIS"]` — 72h 时效变量 |
| `FORECAST_INTERVAL` | `3`（小时，逐3小时预报） |
| `MAX_FORECAST_HOUR_240` | `240` |
| `MAX_FORECAST_HOUR_72` | `72` |
| `get_max_forecast_hour(var)` | 返回该变量的最大预报时效 |
| `get_forecast_hours(var)` | 返回该变量的所有预报时效列表 |

### 4.2 `resource/config.py` — 运行环境配置

包含与部署环境相关的配置，支持三级覆盖：

```
优先级（高→低）：
  1. CLI  --data-root 参数        （写入 SCMOC_DATA_ROOT 环境变量）
  2. 系统环境变量 SCMOC_DATA_ROOT
  3. config.py 中的硬编码默认值   （仅作开发参考）
```

```python
# resource/config.py 核心逻辑
DATA_ROOT = os.environ.get(
    "SCMOC_DATA_ROOT",
    r"\\10.28.16.251\pool_public\SCMOC"   # 默认值，仅开发参考
)
```

**生产部署推荐**：不修改源码，通过环境变量注入：
```powershell
# Windows
$env:SCMOC_DATA_ROOT = "\\prod_server\nfs\SCMOC"
python cli/main.py 2026030100

# 或通过 CLI 参数（一次性覆盖）
python cli/main.py 2026030100 --data-root \\prod_server\nfs\SCMOC
```

### 4.3 `resource/weather_config.py` — 天气现象业务规则

包含 QX/T 740-2024 规定的所有算法参数，完全与运行环境无关：

| 内容 | 说明 |
|------|------|
| `WEATHER_CODE_NAME` | 31种天气现象电码→名称映射 |
| `WEATHER_INFLUENCE_LEVEL` | 影响级（数字越小影响级越高） |
| `RAIN_THRESHOLDS` / `SNOW_THRESHOLDS` | 降水量分级阈值 |
| `MUTUALLY_EXCLUSIVE_GROUPS` | 互斥天气现象分组 |
| `FOG_LEVEL_TO_CODE` / `HAZE_LEVEL_TO_CODE` / `SAND_LEVEL_TO_CODE` | 等级→电码映射 |
| `STANDARD_EXAMPLES` | 标准示例（用于验证） |

### 4.4 部署配置模板

参考 `env/config.example.ini`，复制为 `env/config.ini` 后按实际环境修改：

```ini
[data]
data_root = \\your_server\share\SCMOC

[runtime]
max_seg_workers = 3
max_workers = 4
numexpr_threads = 0

[output]
output_dir = ./PHENOM
```

---

## 五、天气现象电码体系

### 5.1 31 种天气现象（SORTED_CODES 顺序，影响级升序）

| 电码 | 天气现象 | 影响级 | 类别 |
|------|----------|--------|------|
| 12 | 特大暴雨 | 1 | 降水 |
| 37 | 特大暴雪 | 2 | 降水 |
| ... | ... | ... | ... |
| 01 | 多云 | 30 | 天空状况 |
| 00 | 晴 | 31 | 天空状况 |

### 5.2 综合电码格式（5位整型）

```
KAABB
  │││└─ BB: 后一天气现象电码 (00~37)
  ││└── AA: 前一天气现象电码 (00~37)
  │└─── K:  逻辑关系电码
  │       0 = 单一现象 (AA=BB)
  │       1 = 转 (AA转BB)
  │       2 = 间 (AA间BB)
  │       3 = 伴有 (AA伴有BB)
  └──── 示例: 10207 → 阴转小雨, 00101 → 多云
```

---

## 六、数据规格

### 6.1 输入变量

| 变量名 | 说明 | 单位 | 有效时效 |
|--------|------|------|----------|
| R03 | 3h累计降水量 | mm | 003~240h |
| PTYPE03 | 降水类型 (1=雨/2=雪/3=雨夹雪/4=冻雨) | — | 003~240h |
| TCC | 总云量 | % 或 0~1 | 003~240h |
| FOG | 雾等级 (1~5) | — | 003~072h |
| HAZE | 霾等级 (1~4) | — | 003~072h |
| SAND | 沙尘等级 (1~3) | — | 003~072h |
| THUNDER | 雷暴标志 (≥1=有雷暴) | — | 003~072h |
| HAIL | 冰雹标志 (≥1=有冰雹) | — | 003~072h |

> 系统对 72h 后缺失的 FOG/HAZE/SAND/THUNDER/HAIL 自动填零处理，不影响降水类和天空类判识。

### 6.2 输出文件格式

```
{output_dir}/{YYYYMMDDHH}/{YYYYMMDDHH}.{TTT}.nc
```

采用 **meteva 标准 6D DataArray** 格式：

```python
import meteva.base as meb
da = meb.read_griddata_from_nc("2026030100.012.nc")
# da.dims: ['member', 'level', 'time', 'dtime', 'lat', 'lon']
```

---

## 七、关键设计决策

### 7.1 全 int8 索引运算

为避免 `dtype=object` 字符串数组的性能开销，selector 和 logic_judger 中的天气现象均以 `int8` 索引表示，仅在输出阶段通过查找表（LUT）转换为整型电码。

### 7.2 预计算矩阵

在模块加载时一次性预计算：
- `_EXCL[N_CODES, N_CODES]` — 互斥关系矩阵（selector）
- `_ACCOMPANY[N_CODES, N_CODES]` — 伴有关系矩阵（logic_judger）
- `_JIAN_CAND[N_CODES, N_CODES]` — 间候选矩阵（logic_judger）
- `_CODE_INT_LUT[N_CODES]` — 索引→整型电码查找表（encoder）

### 7.3 Plugin 单例模式

`processor.py` 中以模块级单例形式持有四个 Plugin 实例，避免重复初始化：

```python
_identifier = DIA_WeatherPhenomIdentifier()
_selector   = DIA_WeatherPhenomSelector()
_judger     = DIA_WeatherPhenomLogicJudger()
_encoder    = DIA_WeatherPhenomEncoder()
```

### 7.4 TCC 单位自适应

输入 TCC 可能为分数（0~1）或百分比（0~100）。若 `max(TCC) ≤ 1.1` 则自动 ×100 转换。

### 7.5 配置职责分离

遵循国省统筹规范"环境无关性"原则，`resource/` 内部严格分层：

| 模块 | 变更频率 | 部署相关 |
|------|----------|----------|
| `data_schema.py` | 算法规范变更时 | 否 |
| `config.py` | 每个部署环境不同 | **是** |
| `weather_config.py` | 业务规则变更时 | 否 |

`DATA_ROOT` 通过环境变量 `SCMOC_DATA_ROOT` 或 CLI `--data-root` 注入，源码本身不绑定具体服务器地址。

---

## 八、并行策略

并行编排完全属于 cli 层职责（`cli/runner.py`），src 层只接收每个时段已加载完成的内存数据，不感知并行调度细节：

```
cli.runner.run(init_time)
  └─ ThreadPoolExecutor(max_seg_workers=3)         # 时段间并行
       ├─ cli.runner.run_segment(seg=1, max_workers=4)
       │    ├─ cli.data_loader.load_segment(max_workers=4)   # 文件级并行(cli层)
       │    └─ src.processor.run_segment(data_dict, ...)      # 纯内存计算(src层)
       ├─ cli.runner.run_segment(seg=2, max_workers=4)
       └─ cli.runner.run_segment(seg=3, max_workers=4)
```

| 参数 | 推荐值 | 说明 |
|------|--------|------|
| `--max-seg-workers` | 3~5 | 时段间并行；受网络/NFS带宽限制 |
| `--max-workers` | 4~8 | 单时段内文件并发读取线程数 |
| `--numexpr-threads` | CPU核数 | 限制 NumExpr 占用核数 |
| `--data-root` | — | 覆盖数据根目录，无需改代码 |

---

## 九、单元测试

```powershell
# 运行全部测试（使用 pyproject.toml 配置）
pytest

# 运行并输出覆盖率报告
pytest --cov=src --cov-report=term-missing

# 运行特定测试文件
pytest test/test_identifier.py -v
```

---

## 十、快速集成示例

### 10.1 Plugin API（纯内存计算，src 层）

```python
from src.identifier  import DIA_WeatherPhenomIdentifier
from src.selector    import DIA_WeatherPhenomSelector
from src.logic_judger import DIA_WeatherPhenomLogicJudger
from src.encoder     import DIA_WeatherPhenomEncoder

# 初始化 Plugin（单例使用，构造一次即可）
identifier = DIA_WeatherPhenomIdentifier()
selector   = DIA_WeatherPhenomSelector()
judger     = DIA_WeatherPhenomLogicJudger()
encoder    = DIA_WeatherPhenomEncoder()

# data_dict 来自 cli.data_loader.load_segment()，src 层仅接收内存数据
occur                        = identifier.process(data_dict)
idx_A, idx_B                 = selector.process(occur)
logic, idx_fa, idx_fb        = judger.process(idx_A, idx_B, occur)
result                       = encoder.process(idx_fa, idx_fb, logic)
# result: ndarray[lat, lon] int32，5位综合电码
```

### 10.2 完整链路示例（cli 加载 + src 计算）

```python
from cli.data_loader import load_segment
from src.processor import run_segment

# Step 1: cli 层加载单个12h时段数据（唯一文件I/O入口）
data_dict, shape, lat_arr, lon_arr = load_segment("2026030100", seg_idx=1)

# Step 2: src 层纯内存计算 + 保存输出
result = run_segment(data_dict, shape, lat_arr, lon_arr,
                     init_time="2026030100", seg_idx=1,
                     output_dir="./PHENOM")
```

### 10.3 引用完整编排（推荐，cli.runner）

```python
from cli.runner import run

run("2026030100", output_dir="./PHENOM", max_seg_workers=5, max_workers=8)
```

