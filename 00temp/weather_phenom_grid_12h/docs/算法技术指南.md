# 算法技术指南

**系统名称**：网格天气现象综合电码生成算法  
**标准依据**：QX/T 740-2024《基于网格预报的城镇预报生成规范 天气现象》  
**架构规范**：国省统筹算法技术规范（三级架构）  
**版本**：v1.0.0

---

## 一、三级架构总览

```
┌─────────────────────────────────────────────────────────┐
│  Level 3  算法应用 (CLI)                                  │
│           cli/main.py — 命令行入口，POSIX 退出码           │
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

---

## 二、算法流程

依据 QX/T 740-2024 附录C 流程图（见 `附录图C.1 的流程图.png`）：

```
输入变量 (NC格式)
    │
    ▼
[Step 1] 数据加载 — data_loader.load_segment()
         读取 R03/PTYPE03/TCC/FOG/HAZE/SAND/THUNDER/HAIL
         返回 {变量名: ndarray[4, lat, lon]}
    │
    ▼
[Step 2] 天气现象判识 — DIA_WeatherPhenomIdentifier.process()
         依附录A 表A.1/A.2/A.3 判识31种天气现象是否出现
         输出 {电码: {"12h": bool[lat,lon], "fine": bool[4,lat,lon]}}
    │
    ▼
[Step 3] 现象选取 — DIA_WeatherPhenomSelector.process()
         选取影响级最高的A现象 + 独立出现的B现象
         输出 idx_A[lat,lon] int8, idx_B[lat,lon] int8
    │
    ▼
[Step 4] 逻辑关系判断 — DIA_WeatherPhenomLogicJudger.process()
         判断 A与B 的关系：单一(0) / 转(1) / 间(2) / 伴有(3)
         确定表述顺序 idx_final_A, idx_final_B
    │
    ▼
[Step 5] 综合电码编码 — DIA_WeatherPhenomEncoder.process()
         生成 5位整型电码：K*10000 + AA*100 + BB
         输出 ndarray[lat,lon] int32
    │
    ▼
输出文件 (NetCDF4, meteva 6D格式)
```

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

## 四、天气现象电码体系

### 4.1 31 种天气现象（SORTED_CODES 顺序，影响级升序）

| 电码 | 天气现象 | 影响级 | 类别 |
|------|----------|--------|------|
| 00 | 晴 | 10 | 天空状况 |
| 01 | 多云 | 9 | 天空状况 |
| 02 | 阴 | 8 | 天空状况 |
| 07 | 小雨 | 7 | 降水 |
| 08 | 中雨 | 6 | 降水 |
| 09 | 大雨 | 5 | 降水 |
| 10 | 暴雨 | 4 | 降水 |
| 11 | 大暴雨 | 3 | 降水 |
| 12 | 特大暴雨 | 2 | 降水 |
| ... | ... | ... | ... |

### 4.2 综合电码格式（5位整型）

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

## 五、数据规格

### 5.1 输入变量

| 变量名 | 说明 | 单位 | 有效时效 |
|--------|------|------|----------|
| R03 | 3h累计降水量 | mm | 003~240h |
| PTYPE03 | 降水类型 (1=雨/2=雪/3=雨夹雪/4=冻雨) | — | 003~240h |
| TCC | 总云量 | % 或 0~1 | 003~240h |
| FOG | 雾等级 (1~4) | — | 003~072h |
| HAZE | 霾等级 (1~3) | — | 003~072h |
| SAND | 沙尘等级 (1~3) | — | 003~072h |
| THUNDER | 雷暴标志 (≥1=有雷暴) | — | 003~072h |
| HAIL | 冰雹标志 (≥1=有冰雹) | — | 003~072h |

> 系统对 72h 后缺失的 FOG/HAZE/SAND/THUNDER/HAIL 自动填零处理，不影响降水类和天空类判识。

### 5.2 输出文件格式

```
{output_dir}/{YYYYMMDDHH}/{YYYYMMDDHH}.{TTT}.nc
```

采用 **meteva 标准 6D DataArray** 格式，可直接用 `meteva.base.read_griddata_from_nc` 读取：

```python
import meteva.base as meb
da = meb.read_griddata_from_nc("2026030100.012.nc")
# da.dims: ['member', 'level', 'time', 'dtime', 'lat', 'lon']
```

---

## 六、关键设计决策

### 6.1 全 int8 索引运算

为避免 `dtype=object` 字符串数组的性能开销，selector 和 logic_judger 中的天气现象均以 `int8` 索引表示，仅在输出阶段通过查找表（LUT）转换为字符串电码或整型电码。

### 6.2 预计算矩阵

在模块加载时一次性预计算：
- `_EXCL[N_CODES, N_CODES]` — 互斥关系矩阵（selector）
- `_ACCOMPANY[N_CODES, N_CODES]` — 伴有关系矩阵（logic_judger）
- `_JIAN_CAND[N_CODES, N_CODES]` — 间候选矩阵（logic_judger）
- `_CODE_INT_LUT[N_CODES]` — 索引→整型电码查找表（encoder）

### 6.3 Plugin 单例模式

`processor.py` 中以模块级单例形式持有四个 Plugin 实例，避免每次处理时段时重复初始化和预计算：

```python
_identifier = DIA_WeatherPhenomIdentifier()
_selector   = DIA_WeatherPhenomSelector()
_judger     = DIA_WeatherPhenomLogicJudger()
_encoder    = DIA_WeatherPhenomEncoder()
```

### 6.4 TCC 单位自适应

输入 TCC 可能为分数（0~1）或百分比（0~100）。判识时自动检测：若 `max(TCC) ≤ 1.1` 则自动 ×100 转换，无需手动设置。

---

## 七、并行策略

```
run(init_time)
  └─ ThreadPoolExecutor(max_seg_workers=3)   # 时段间并行
       ├─ run_segment(seg=1)
       │    └─ load_segment(max_workers=4)   # 文件级并行
       ├─ run_segment(seg=2)
       └─ run_segment(seg=3)
```

| 参数 | 推荐值 | 说明 |
|------|--------|------|
| `--max-seg-workers` | 3~5 | 时段间并行；受网络/NFS带宽限制 |
| `--max-workers` | 4~8 | 单时段内文件并发读取线程数 |
| `--numexpr-threads` | CPU核数 | 限制 NumExpr 占用核数，避免超线程争用 |

---

## 八、单元测试

```powershell
# 运行全部测试（使用 pyproject.toml 配置）
pytest

# 运行并输出覆盖率报告
pytest --cov=src --cov-report=term-missing

# 运行特定测试文件
pytest test/test_identifier.py -v
```

---

## 九、快速集成示例

```python
from src.identifier import DIA_WeatherPhenomIdentifier
from src.selector   import DIA_WeatherPhenomSelector
from src.logic_judger import DIA_WeatherPhenomLogicJudger
from src.encoder    import DIA_WeatherPhenomEncoder

# 初始化 Plugin（单例使用，构造一次即可）
identifier = DIA_WeatherPhenomIdentifier()
selector   = DIA_WeatherPhenomSelector()
judger     = DIA_WeatherPhenomLogicJudger()
encoder    = DIA_WeatherPhenomEncoder()

# 执行流程
occur                        = identifier.process(data_dict)
idx_A, idx_B                 = selector.process(occur)
logic, idx_fa, idx_fb        = judger.process(idx_A, idx_B, occur)
result                       = encoder.process(idx_fa, idx_fb, logic)
# result: ndarray[lat, lon] int32，5位综合电码
```
