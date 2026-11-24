**基础信息**
- **所属包**: `probability_reliability_correction`
- **预报类型**: 概率构造
- **算法类别**: `07probability`
- **正式目录规划**: `NIMM/07probability/probability_reliability_correction/`
- **对外入口**: `ConstructReliabilityCalibrationTables`、`AggregateReliabilityCalibrationTables`、`ManipulateReliabilityTable`、`ApplyReliabilityCalibration`
- **CLI 页**: [probability_reliability_correction](https://www.showdoc.com.cn/2598854776811541/11559060627556706)
- **应用场景**: [概率与集合产品](https://www.showdoc.com.cn/2598854776811541/11559060627556901)

用历史概率预报与阈值化实况构建可靠性计数表，经可选聚合与整理后，对当前概率预报做分段线性订正。网格为 meb 六维场；站点为 meb 六列表。读文件与调度见 [CLI 页](https://www.showdoc.com.cn/2598854776811541/11559060627556706)。

**算法功能与流程**

```mermaid
flowchart LR
    A[历史概率预报 / 阈值化实况] --> B[ConstructReliabilityCalibrationTables]
    B --> C[可靠性表]
    C --> D[AggregateReliabilityCalibrationTables]
    D --> E[ManipulateReliabilityTable]
    E --> F[ApplyReliabilityCalibration]
    G[当前概率预报] --> F
    F --> H[订正后概率]
```

1. 历史概率预报 + 阈值化实况 → `ConstructReliabilityCalibrationTables` → 可靠性表。
2. 可选：多表 / 空间坐标 → `AggregateReliabilityCalibrationTables`。
3. `ManipulateReliabilityTable` 合并欠采样箱并强制观测频率单调。
4. 当前概率预报 + 整理后表 → `ApplyReliabilityCalibration` → 订正概率（裁剪到 `[0,1]`，并按 `relative_to_threshold` 跨阈值单调）。

# ConstructReliabilityCalibrationTables

<div style="margin:8px 0;padding:10px 14px;background:#e8f3ff;border-left:4px solid #1677ff;border-radius:4px;overflow-x:auto;"><div style="margin:0;padding:0;background:transparent;border:none;color:#1677ff;font-weight:600;font-size:16px;line-height:1.55;font-family:Consolas,Menlo,Monaco,monospace;white-space:pre;">ConstructReliabilityCalibrationTables(<br>&nbsp;&nbsp;&nbsp;&nbsp;n_probability_bins=5,<br>&nbsp;&nbsp;&nbsp;&nbsp;single_value_lower_limit=False,<br>&nbsp;&nbsp;&nbsp;&nbsp;single_value_upper_limit=False,<br>).process(historic_forecasts, truths, aggregate_coords=None)</div></div>

将预报概率落入互不重叠的概率箱，累计各箱观测次数、预报概率和与预报次数。一次调用要求起报钟点唯一、`dtime` 唯一；多有效时间在同钟点下累加。

**构造参数**

| 参数 | 说明 |
| --- | --- |
| <span style="color:#1677ff;font-weight:600;font-size:16px">n_probability_bins</span> | int。概率箱个数（含可选 0/1 端点箱） |
| <span style="color:#1677ff;font-weight:600;font-size:16px">single_value_lower_limit</span> | bool。是否在 0 附近增加单值箱 |
| <span style="color:#1677ff;font-weight:600;font-size:16px">single_value_upper_limit</span> | bool。是否在 1 附近增加单值箱 |

**process 参数**

| 参数 | 说明 |
| --- | --- |
| <span style="color:#1677ff;font-weight:600;font-size:16px">historic_forecasts</span> | `xr.DataArray` / `pd.DataFrame`。历史**概率**预报（网格 meb 六维，`member` 长度须为 1；或站点六列表） |
| <span style="color:#1677ff;font-weight:600;font-size:16px">truths</span> | 同类型。**阈值化**实况/事件场（事件为 1，否则为 0；缺测用 NaN） |
| <span style="color:#1677ff;font-weight:600;font-size:16px">aggregate_coords</span> | `list[str]` / None。建表后空间求和；网格常用 `["lat","lon"]`，站点仅 `["id"]` |
| <span style="color:#1677ff;font-weight:600;font-size:16px">forecast_data_name</span> / <span style="color:#1677ff;font-weight:600;font-size:16px">truth_data_name</span> | 仅站点：要素列名；可省略自动检测 |
| <span style="color:#1677ff;font-weight:400;font-size:16px">return</span> | 网格：含 `observation_count` / `sum_of_forecast_probabilities` / `forecast_count` 的 `xr.Dataset`；站点：可靠性长表 `DataFrame` |

**使用示例**

样例为包内 `resource/cli_input/construct_*.nc`（小网格阈值概率与事件场）。相对业务原始场，传入前须已是**概率/事件**（非连续气温等），`level` 为阈值且预报与实况精确一致，起报钟点与 `dtime` 唯一；算法按有效时间 `time+dtime` 数值对齐，不做重网格。本节逻辑：读预报/实况 → 建表并空间聚合 → `print` 表。

```python
import meteva_base as meb
from probability_reliability_correction.src.reliability_calibration import (
    ConstructReliabilityCalibrationTables,
)

# 历史概率预报 + 阈值化实况（同网格、同阈值）
hist = meb.read_griddata_from_nc("resource/cli_input/construct_forecast.nc")
truth = meb.read_griddata_from_nc("resource/cli_input/construct_truth.nc")

# 5 箱；建表后对 lat/lon 求和，得到空间折叠表
table = ConstructReliabilityCalibrationTables(n_probability_bins=5).process(
    hist, truth, aggregate_coords=["lat", "lon"]
)
print(table)
```

```
<xarray.Dataset> Size: 252B
Dimensions:                        (lon: 1, lat: 1, member: 5, level: 2,
                                    time: 1, dtime: 1)
Coordinates:
  * lon                            (lon) float64 8B 0.0
  * lat                            (lat) float64 8B 60.0
  * member                         (member) int32 20B 0 1 2 3 4
    probability_bin                (member) float32 20B 0.1 0.3 0.5 0.7 0.9
    probability_bin_bound_lower    (member) float32 20B 0.0 0.2 0.4 0.6 0.8
    probability_bin_bound_upper    (member) float32 20B 0.2 0.4 0.6 0.8 1.0
  * level                          (level) float32 8B 0.0 5.0
  * time                           (time) datetime64[ns] 8B 2017-11-11
  * dtime                          (dtime) float32 4B 4.0
Data variables:
    observation_count              (member, level, time, dtime, lat, lon) float32 40B ...
    sum_of_forecast_probabilities  (member, level, time, dtime, lat, lon) float32 40B ...
    forecast_count                 (member, level, time, dtime, lat, lon) float32 40B ...
Attributes:
    title:                  Reliability calibration data table
    relative_to_threshold:  above
```

# AggregateReliabilityCalibrationTables

<div style="margin:8px 0;padding:10px 14px;background:#e8f3ff;border-left:4px solid #1677ff;border-radius:4px;overflow-x:auto;"><div style="margin:0;padding:0;background:transparent;border:none;color:#1677ff;font-weight:600;font-size:16px;line-height:1.55;font-family:Consolas,Menlo,Monaco,monospace;white-space:pre;">AggregateReliabilityCalibrationTables().process(<br>&nbsp;&nbsp;&nbsp;&nbsp;reliability_tables,<br>&nbsp;&nbsp;&nbsp;&nbsp;coordinates=None,<br>)</div></div>

多表沿时间段拼接求和，和/或对指定空间坐标求和。多表要求各表 `time_bound` 区间不重叠，避免同一预报样本重复计数；不可混用网格 `Dataset` 与站点 `DataFrame`。

**构造参数**

| 参数 | 说明 |
| --- | --- |
| 无 | 无额外构造参数 |

**process 参数**

| 参数 | 说明 |
| --- | --- |
| <span style="color:#1677ff;font-weight:600;font-size:16px">reliability_tables</span> | `xr.Dataset` / `pd.DataFrame` / 其序列。一张或多张可靠性表 |
| <span style="color:#1677ff;font-weight:600;font-size:16px">coordinates</span> | `list[str]` / None。要求和的坐标；网格 `lat`/`lon`，站点仅 `["id"]` |
| <span style="color:#1677ff;font-weight:400;font-size:16px">return</span> | 与输入同类型的聚合表（网格 `Dataset` 或站点长表） |

**使用示例**

样例为 `resource/cli_input/aggregate_reliability_table*.nc`（两段不重叠时段的可靠性表）。相对业务表，传入前须已是 Construct 产出的计数表，且多表时段不重叠。本节逻辑：读多表 → 对 `lat`/`lon` 求和聚合 → `print`。

```python
import xarray as xr
from probability_reliability_correction.src.reliability_calibration import (
    AggregateReliabilityCalibrationTables,
)

# 两段不重叠时段的可靠性表 → 计数相加并空间折叠
t1 = xr.open_dataset("resource/cli_input/aggregate_reliability_table.nc")
t2 = xr.open_dataset("resource/cli_input/aggregate_reliability_table_2.nc")
agg = AggregateReliabilityCalibrationTables().process(
    [t1, t2], coordinates=["lat", "lon"]
)
print(agg)
```

```
<xarray.Dataset> Size: 252B
Dimensions:                        (lon: 1, lat: 1, member: 5, level: 2,
                                    dtime: 1, time: 1)
Coordinates:
  * lon                            (lon) float64 8B 0.0
  * lat                            (lat) float64 8B 60.0
  * member                         (member) int32 20B 0 1 2 3 4
    probability_bin                (member) float32 20B 5e-07 0.1667 ... 1.0
  * level                          (level) float32 8B 0.0 5.0
  * dtime                          (dtime) float32 4B 4.0
  * time                           (time) datetime64[ns] 8B 2017-11-13
Data variables:
    observation_count              (member, level, time, dtime, lat, lon) float32 40B ...
    sum_of_forecast_probabilities  (member, level, time, dtime, lat, lon) float32 40B ...
    forecast_count                 (member, level, time, dtime, lat, lon) float32 40B ...
Attributes:
    title:                  Reliability calibration data table
    relative_to_threshold:  above
```

# ManipulateReliabilityTable

<div style="margin:8px 0;padding:10px 14px;background:#e8f3ff;border-left:4px solid #1677ff;border-radius:4px;overflow-x:auto;"><div style="margin:0;padding:0;background:transparent;border:none;color:#1677ff;font-weight:600;font-size:16px;line-height:1.55;font-family:Consolas,Menlo,Monaco,monospace;white-space:pre;">ManipulateReliabilityTable(<br>&nbsp;&nbsp;&nbsp;&nbsp;minimum_forecast_count=200,<br>&nbsp;&nbsp;&nbsp;&nbsp;point_by_point=False,<br>).process(reliability_table)</div></div>

合并预报次数低于下限的欠采样箱，并强制观测频率随预报概率单调。默认要求空间已聚合（网格 `lat`/`lon` 长度为 1，或站点 `spatial_kind=aggregated`）；`point_by_point=True` 时对每个格点/站点分别整理。

**构造参数**

| 参数 | 说明 |
| --- | --- |
| <span style="color:#1677ff;font-weight:600;font-size:16px">minimum_forecast_count</span> | int。箱内预报次数下限，须 ≥ 1；默认 200 |
| <span style="color:#1677ff;font-weight:600;font-size:16px">point_by_point</span> | bool。是否按格点/站点分别整理 |

**process 参数**

| 参数 | 说明 |
| --- | --- |
| <span style="color:#1677ff;font-weight:600;font-size:16px">reliability_table</span> | `xr.Dataset` / `pd.DataFrame`。待整理的可靠性表 |
| <span style="color:#1677ff;font-weight:400;font-size:16px">return</span> | 网格：`list[xr.Dataset]`（按阈值拆开，各表箱数可不同）；站点：一张可靠性长表 |

**使用示例**

样例为 `resource/cli_input/manipulate_reliability_table.nc`（已空间折叠、多阈值云量阈值表）。相对 Construct/Aggregate 产出，默认路径下须先空间聚合，否则应设 `point_by_point=True`。本节逻辑：读表 → 整理 → `print` 表个数与首张表。

```python
import xarray as xr
from probability_reliability_correction.src.reliability_calibration import (
    ManipulateReliabilityTable,
)

# 已空间折叠的可靠性表 → 按阈值拆开并合并欠采样箱
raw = xr.open_dataset("resource/cli_input/manipulate_reliability_table.nc")
tables = ManipulateReliabilityTable(minimum_forecast_count=200).process(raw)
print(len(tables), tables[0])
```

```
17
<xarray.Dataset> Size: 68B
Dimensions:                        (member: 1, level: 1, time: 1, dtime: 1,
                                    lat: 1, lon: 1)
Coordinates:
  * member                         (member) int32 4B 0
    probability_bin                (member) float32 4B 0.5
    probability_bin_bound_lower    (member) float32 4B 0.0
    probability_bin_bound_upper    (member) float32 4B 1.0
  * level                          (level) float32 4B 0.0
  * time                           (time) datetime64[ns] 8B 2020-01-27
  * dtime                          (dtime) float32 4B 120.0
  * lat                            (lat) float32 4B -6.7e+04
  * lon                            (lon) float32 4B -1.17e+05
Data variables:
    observation_count              (member, level, time, dtime, lat, lon) float32 4B ...
    sum_of_forecast_probabilities  (member, level, time, dtime, lat, lon) float32 4B ...
    forecast_count                 (member, level, time, dtime, lat, lon) float32 4B ...
Attributes:
    title:                  Reliability calibration data table
    relative_to_threshold:  above
```

# ApplyReliabilityCalibration

<div style="margin:8px 0;padding:10px 14px;background:#e8f3ff;border-left:4px solid #1677ff;border-radius:4px;overflow-x:auto;"><div style="margin:0;padding:0;background:transparent;border:none;color:#1677ff;font-weight:600;font-size:16px;line-height:1.55;font-family:Consolas,Menlo,Monaco,monospace;white-space:pre;">ApplyReliabilityCalibration(<br>&nbsp;&nbsp;&nbsp;&nbsp;point_by_point=False,<br>).process(forecast, reliability_table=None)</div></div>

由计数表得到箱中心预报概率与观测频率，对原始概率分段线性插值并裁剪到 `[0,1]`；再按 `relative_to_threshold` 强制跨阈值单调。`reliability_table=None` 时原样返回预报（流水线占位）。默认要求表已空间聚合；`point_by_point=True` 时逐格点/站点套各自曲线。

**构造参数**

| 参数 | 说明 |
| --- | --- |
| <span style="color:#1677ff;font-weight:600;font-size:16px">point_by_point</span> | bool。是否逐空间点/站点套表 |

**process 参数**

| 参数 | 说明 |
| --- | --- |
| <span style="color:#1677ff;font-weight:600;font-size:16px">forecast</span> | `xr.DataArray` / `pd.DataFrame`。待订正概率预报 |
| <span style="color:#1677ff;font-weight:600;font-size:16px">reliability_table</span> | `xr.Dataset` / `pd.DataFrame` / `Sequence[xr.Dataset]` / None。整理后的可靠性表；`None` 则不订正 |
| <span style="color:#1677ff;font-weight:600;font-size:16px">data_name</span> | 仅站点：概率列名；可省略自动检测 |
| <span style="color:#1677ff;font-weight:400;font-size:16px">return</span> | 与 `forecast` 同类型；网格为 meb 六维 `DataArray`（`units="1"`）；表为 `None` 时返回原预报 |

**使用示例**

样例为 `resource/cli_input/apply_forecast.nc` 与已折叠的 `apply_collapsed_table.nc`（气温超阈概率）。相对业务场，预报须带 `relative_to_threshold`，阈值 `level` 须能在表中精确匹配；表宜先经 Manipulate（网格常为按阈值拆开的列表，本样例用已折叠单表）。本节逻辑：读预报与表 → 订正 → `print`；作图另块（订正前/后，同一概率色标）。

```python
import meteva_base as meb
import xarray as xr
from probability_reliability_correction.src.reliability_calibration import (
    ApplyReliabilityCalibration,
)

# 待订正概率场 + 折叠可靠性表
fc = meb.read_griddata_from_nc("resource/cli_input/apply_forecast.nc")
table = xr.open_dataset("resource/cli_input/apply_collapsed_table.nc")
calibrated = ApplyReliabilityCalibration(point_by_point=False).process(fc, table)
print(calibrated)
```

```
<xarray.DataArray 'probability_of_air_temperature_above_threshold' (member: 1,
                                                                    level: 2,
                                                                    time: 1,
                                                                    dtime: 1,
                                                                    lat: 49,
                                                                    lon: 53)> Size: 21kB
array([[[[[[0.99543023, 0.99543023, 0.99543023, ..., 0.99543023,
            0.99543023, 0.99543023],
           [0.99543023, 0.99543023, 0.99543023, ..., 0.99543023,
            0.99543023, 0.99543023],
           [0.99543023, 0.99543023, 0.99543023, ..., 0.99543023,
            0.99543023, 0.99543023],
           ...,
           [0.99543023, 0.99543023, 0.99543023, ..., 0.00992512,
            0.00992512, 0.00992512],
           [0.99543023, 0.99543023, 0.99543023, ..., 0.00992512,
            0.00992512, 0.00992512],
           [0.99543023, 0.99543023, 0.99543023, ..., 0.00992512,
            0.00992512, 0.00992512]]]],



        [[[[0.99320304, 0.99320304, 0.99320304, ..., 0.99320304,
            0.99320304, 0.99320304],
           [0.99320304, 0.99320304, 0.99320304, ..., 0.99320304,
            0.99320304, 0.99320304],
           [0.99320304, 0.99320304, 0.99320304, ..., 0.99320304,
            0.99320304, 0.99320304],
           ...,
           [0.99320304, 0.99320304, 0.99320304, ..., 0.00724841,
            0.00724841, 0.00724841],
           [0.99320304, 0.99320304, 0.99320304, ..., 0.00724841,
            0.00724841, 0.00724841],
           [0.99320304, 0.99320304, 0.93693244, ..., 0.00724841,
            0.00724841, 0.00724841]]]]]],
      shape=(1, 2, 1, 1, 49, 53), dtype=float32)
Coordinates:
  * member   (member) <U5 20B 'data0'
  * level    (level) float32 8B 270.0 275.0
  * time     (time) datetime64[ns] 8B 2019-02-02T22:00:00
  * dtime    (dtime) int32 4B 19
  * lat      (lat) float64 392B -1.036e+06 -9.956e+05 ... 8.616e+05 9.02e+05
  * lon      (lon) float64 424B -1.158e+06 -1.118e+06 ... 8.84e+05 9.24e+05
Attributes:
    units:                  1
    relative_to_threshold:  above
    model_var:              
    dtime_units:            hour
    level_type:             isobaric
    time_type:              UT
    time_bounds:            [0, 0]
```

```python
import matplotlib.pyplot as plt
import meteva_base as meb
from meteva_base.tool.plot_tools import pcolormesh_2d_grid

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

# 订正前 / 订正后共用概率分级色标（取第一个阈值）
PROB_CLEVS = [0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
pcolormesh_2d_grid(
    fc.isel(level=0),
    save_path="rel_before.png",
    title="订正前 - 阈值概率",
    clevs=PROB_CLEVS,
    cmap="YlOrRd",
    show=False,
)
pcolormesh_2d_grid(
    calibrated.isel(level=0),
    save_path="rel_after.png",
    title="订正后 - 阈值概率",
    clevs=PROB_CLEVS,
    cmap="YlOrRd",
    show=False,
)
```

订正前 - 阈值概率：

![可靠性订正前](https://www.showdoc.com.cn/server/api/attachment/visitFile?sign=9f808869f2e0462d4947986618407244&file=file.png)

订正后 - 阈值概率：

![可靠性订正后](https://www.showdoc.com.cn/server/api/attachment/visitFile?sign=216c97fa7a760c23e852772d108afcc2&file=file.png)

---

算法 CLI 使用说明请见 [probability_reliability_correction](https://www.showdoc.com.cn/2598854776811541/11559060627556706)。
