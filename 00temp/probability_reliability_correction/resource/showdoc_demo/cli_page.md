**基础信息**
- **所属包**: `probability_reliability_correction`
- **插件页**: [probability_reliability_correction](https://www.showdoc.com.cn/2598854776811541/11559060627552423)
- **调度脚本**: `cli/prb_construct_reliability_tables.py`、`cli/prb_aggregate_reliability_tables.py`、`cli/prb_manipulate_reliability_table.py`、`cli/prb_apply_reliability_calibration.py`

本页是 CLI 使用说明；算法参数见插件页。样例来自 `resource/cli_input`。本包以单次调用为主，无独立批量调度脚本。

**参数优先级**（由高到低）：**显式传入**（命令行 flag / `XxxCli.call(...)`）**>** **配置文件参数**（ini 非空项）**>** 代码预设默认值。空 ini 项不覆盖上层已给出的值。

**怎么跑**

（发版环境：本包已可导入。）

```bash
python -m probability_reliability_correction.cli
python -m probability_reliability_correction.cli construct --help
python -m probability_reliability_correction.cli aggregate --help
python -m probability_reliability_correction.cli manipulate --help
python -m probability_reliability_correction.cli apply --help

# 建表
python -m probability_reliability_correction.cli construct \
  --forecast-path PATH --truth-path PATH \
  [--n-probability-bins INT] [--aggregate-coords lat,lon] \
  [--output-path PATH] [--config PATH]

# 聚合
python -m probability_reliability_correction.cli aggregate \
  --reliability-table-paths PATH [PATH ...] \
  [--coordinates lat,lon] [--output-path PATH] [--config PATH]

# 整理
python -m probability_reliability_correction.cli manipulate \
  --reliability-table-path PATH \
  [--minimum-forecast-count INT] [--point-by-point | --no-point-by-point] \
  [--output-path PATH] [--config PATH]

# 施加订正
python -m probability_reliability_correction.cli apply \
  --forecast-path PATH [--reliability-table-paths PATH ...] \
  [--point-by-point | --no-point-by-point] \
  [--output-path PATH] [--config PATH]

# 等价：直接跑脚本
python cli/prb_construct_reliability_tables.py --forecast-path PATH --truth-path PATH
python cli/prb_aggregate_reliability_tables.py --reliability-table-paths PATH
python cli/prb_manipulate_reliability_table.py --reliability-table-path PATH
python cli/prb_apply_reliability_calibration.py --forecast-path PATH
```

无子命令时只打印用法。Python 对外入口为各 `XxxCli.call`（返回退出码）。

| 子命令 | 脚本 | 说明 |
| --- | --- | --- |
| `construct` | `cli/prb_construct_reliability_tables.py` | 历史概率 + 实况 → 可靠性表 |
| `aggregate` | `cli/prb_aggregate_reliability_tables.py` | 多表 / 空间坐标求和 |
| `manipulate` | `cli/prb_manipulate_reliability_table.py` | 合并欠采样箱、强制单调 |
| `apply` | `cli/prb_apply_reliability_calibration.py` | 用表订正概率预报 |

# prb_construct_reliability_tables.py

**调用插件**: `ConstructReliabilityCalibrationTables`

对外 Python 入口为 `PrbConstructReliabilityTablesCli.call`（关键字与 flag 同名）。未传入的可选项为 `None`，按参数优先级回落。

<div style="margin:8px 0;padding:10px 14px;background:#e8f3ff;border-left:4px solid #1677ff;border-radius:4px;overflow-x:auto;"><div style="margin:0;padding:0;background:transparent;border:none;color:#1677ff;font-weight:600;font-size:16px;line-height:1.55;font-family:Consolas,Menlo,Monaco,monospace;white-space:pre;">PrbConstructReliabilityTablesCli.call(<br>&nbsp;&nbsp;&nbsp;&nbsp;forecast_path=...,<br>&nbsp;&nbsp;&nbsp;&nbsp;truth_path=...,<br>&nbsp;&nbsp;&nbsp;&nbsp;n_probability_bins=None,<br>&nbsp;&nbsp;&nbsp;&nbsp;single_value_lower_limit=None,<br>&nbsp;&nbsp;&nbsp;&nbsp;single_value_upper_limit=None,<br>&nbsp;&nbsp;&nbsp;&nbsp;aggregate_coords=None,<br>&nbsp;&nbsp;&nbsp;&nbsp;output_path=None,<br>&nbsp;&nbsp;&nbsp;&nbsp;config=None,<br>)</div></div>

| 参数 | 说明 |
| --- | --- |
| <span style="color:#1677ff;font-weight:600;font-size:16px">forecast_path</span> | 历史概率预报 nc/csv。对应 `--forecast-path` |
| <span style="color:#1677ff;font-weight:600;font-size:16px">truth_path</span> | 阈值化实况 nc/csv。对应 `--truth-path` |
| <span style="color:#1677ff;font-weight:600;font-size:16px">n_probability_bins</span> | 概率箱数；省略回落插件默认 5 |
| <span style="color:#1677ff;font-weight:600;font-size:16px">aggregate_coords</span> | 建表后求和坐标列表，如 `["lat","lon"]` |
| <span style="color:#1677ff;font-weight:600;font-size:16px">output_path</span> | 输出 nc/csv；`None` 不写文件 |
| <span style="color:#1677ff;font-weight:400;font-size:16px">return</span> | `int` 退出码（`0` 成功）。需要表对象时再读 `output_path` |

**使用示例**

数据与插件页 Construct 示例相同（`resource/cli_input/construct_*.nc`；须为概率/事件场）。本节逻辑：`call` 写表 → 读回 → `print`。

```python
import xarray as xr
from probability_reliability_correction.cli.prb_construct_reliability_tables import (
    PrbConstructReliabilityTablesCli,
)

out_nc = "resource/cli_output/demo_construct_table.nc"
rc = PrbConstructReliabilityTablesCli.call(
    forecast_path="resource/cli_input/construct_forecast.nc",
    truth_path="resource/cli_input/construct_truth.nc",
    n_probability_bins=5,
    aggregate_coords=["lat", "lon"],
    output_path=out_nc,
)
print(rc)
table = xr.open_dataset(out_nc)
print(table)
```

```
0
<xarray.Dataset> Size: 252B
Dimensions:                        (lon: 1, lat: 1, member: 5, level: 2,
                                    time: 1, dtime: 1)
Coordinates:
  * member                         (member) int32 20B 0 1 2 3 4
    probability_bin                (member) float32 20B 0.1 0.3 0.5 0.7 0.9
  * level                          (level) float32 8B 0.0 5.0
Data variables:
    observation_count              (member, level, time, dtime, lat, lon) float32 ...
    sum_of_forecast_probabilities  (member, level, time, dtime, lat, lon) float32 ...
    forecast_count                 (member, level, time, dtime, lat, lon) float32 ...
Attributes:
    title:                  Reliability calibration data table
    relative_to_threshold:  above
```

# prb_aggregate_reliability_tables.py

**调用插件**: `AggregateReliabilityCalibrationTables`

<div style="margin:8px 0;padding:10px 14px;background:#e8f3ff;border-left:4px solid #1677ff;border-radius:4px;overflow-x:auto;"><div style="margin:0;padding:0;background:transparent;border:none;color:#1677ff;font-weight:600;font-size:16px;line-height:1.55;font-family:Consolas,Menlo,Monaco,monospace;white-space:pre;">PrbAggregateReliabilityTablesCli.call(<br>&nbsp;&nbsp;&nbsp;&nbsp;reliability_table_paths=...,<br>&nbsp;&nbsp;&nbsp;&nbsp;coordinates=None,<br>&nbsp;&nbsp;&nbsp;&nbsp;output_path=None,<br>&nbsp;&nbsp;&nbsp;&nbsp;config=None,<br>)</div></div>

| 参数 | 说明 |
| --- | --- |
| <span style="color:#1677ff;font-weight:600;font-size:16px">reliability_table_paths</span> | 一张或多张表路径（网格 nc 或站点 csv，不可混用） |
| <span style="color:#1677ff;font-weight:600;font-size:16px">coordinates</span> | 求和坐标，如 `["lat","lon"]` 或 `["id"]` |
| <span style="color:#1677ff;font-weight:600;font-size:16px">output_path</span> | 输出路径；`None` 不写文件 |
| <span style="color:#1677ff;font-weight:400;font-size:16px">return</span> | `int` 退出码（`0` 成功） |

**使用示例**

数据与插件页 Aggregate 示例相同。多表时段须不重叠。本节逻辑：`call` 写聚合表 → 读回 → `print`。

```python
import xarray as xr
from probability_reliability_correction.cli.prb_aggregate_reliability_tables import (
    PrbAggregateReliabilityTablesCli,
)

out_nc = "resource/cli_output/demo_aggregate_table.nc"
rc = PrbAggregateReliabilityTablesCli.call(
    reliability_table_paths=[
        "resource/cli_input/aggregate_reliability_table.nc",
        "resource/cli_input/aggregate_reliability_table_2.nc",
    ],
    coordinates=["lat", "lon"],
    output_path=out_nc,
)
print(rc)
print(xr.open_dataset(out_nc))
```

```
0
<xarray.Dataset> Size: 252B
Dimensions:                        (lon: 1, lat: 1, member: 5, level: 2,
                                    dtime: 1, time: 1)
Data variables:
    observation_count              (member, level, time, dtime, lat, lon) float32 ...
    sum_of_forecast_probabilities  (member, level, time, dtime, lat, lon) float32 ...
    forecast_count                 (member, level, time, dtime, lat, lon) float32 ...
Attributes:
    title:                  Reliability calibration data table
    relative_to_threshold:  above
```

# prb_manipulate_reliability_table.py

**调用插件**: `ManipulateReliabilityTable`

<div style="margin:8px 0;padding:10px 14px;background:#e8f3ff;border-left:4px solid #1677ff;border-radius:4px;overflow-x:auto;"><div style="margin:0;padding:0;background:transparent;border:none;color:#1677ff;font-weight:600;font-size:16px;line-height:1.55;font-family:Consolas,Menlo,Monaco,monospace;white-space:pre;">PrbManipulateReliabilityTableCli.call(<br>&nbsp;&nbsp;&nbsp;&nbsp;reliability_table_path=...,<br>&nbsp;&nbsp;&nbsp;&nbsp;minimum_forecast_count=None,<br>&nbsp;&nbsp;&nbsp;&nbsp;point_by_point=None,<br>&nbsp;&nbsp;&nbsp;&nbsp;output_path=None,<br>&nbsp;&nbsp;&nbsp;&nbsp;config=None,<br>)</div></div>

| 参数 | 说明 |
| --- | --- |
| <span style="color:#1677ff;font-weight:600;font-size:16px">reliability_table_path</span> | 待整理表路径（网格 nc 或站点 csv） |
| <span style="color:#1677ff;font-weight:600;font-size:16px">minimum_forecast_count</span> | 箱内最少预报次数；省略回落 200 |
| <span style="color:#1677ff;font-weight:600;font-size:16px">point_by_point</span> | 是否逐点整理；省略回落插件默认 |
| <span style="color:#1677ff;font-weight:600;font-size:16px">output_path</span> | 网格为**输出目录**（按阈值写多文件）；站点为 csv；`None` 不写 |
| <span style="color:#1677ff;font-weight:400;font-size:16px">return</span> | `int` 退出码（`0` 成功） |

**使用示例**

数据与插件页 Manipulate 示例相同（已空间折叠表）。网格写出时 `output_path` 为目录。本节逻辑：`call` 写目录 → 读回首张表 → `print`。

```python
from pathlib import Path
import xarray as xr
from probability_reliability_correction.cli.prb_manipulate_reliability_table import (
    PrbManipulateReliabilityTableCli,
)

out_dir = "resource/cli_output/demo_manipulate"
Path(out_dir).mkdir(parents=True, exist_ok=True)
rc = PrbManipulateReliabilityTableCli.call(
    reliability_table_path="resource/cli_input/manipulate_reliability_table.nc",
    minimum_forecast_count=200,
    output_path=out_dir,
)
print(rc)
files = sorted(Path(out_dir).glob("*.nc"))
print(len(files), xr.open_dataset(files[0]))
```

```
0
17
<xarray.Dataset> Size: 68B
Dimensions:                        (member: 1, level: 1, time: 1, dtime: 1,
                                    lat: 1, lon: 1)
Coordinates:
  * level                          (level) float32 4B 0.0
Data variables:
    observation_count              (member, level, time, dtime, lat, lon) float32 ...
    sum_of_forecast_probabilities  (member, level, time, dtime, lat, lon) float32 ...
    forecast_count                 (member, level, time, dtime, lat, lon) float32 ...
Attributes:
    title:                  Reliability calibration data table
    relative_to_threshold:  above
```

# prb_apply_reliability_calibration.py

**调用插件**: `ApplyReliabilityCalibration`

<div style="margin:8px 0;padding:10px 14px;background:#e8f3ff;border-left:4px solid #1677ff;border-radius:4px;overflow-x:auto;"><div style="margin:0;padding:0;background:transparent;border:none;color:#1677ff;font-weight:600;font-size:16px;line-height:1.55;font-family:Consolas,Menlo,Monaco,monospace;white-space:pre;">PrbApplyReliabilityCalibrationCli.call(<br>&nbsp;&nbsp;&nbsp;&nbsp;forecast_path=...,<br>&nbsp;&nbsp;&nbsp;&nbsp;reliability_table_paths=None,<br>&nbsp;&nbsp;&nbsp;&nbsp;point_by_point=None,<br>&nbsp;&nbsp;&nbsp;&nbsp;output_path=None,<br>&nbsp;&nbsp;&nbsp;&nbsp;config=None,<br>)</div></div>

| 参数 | 说明 |
| --- | --- |
| <span style="color:#1677ff;font-weight:600;font-size:16px">forecast_path</span> | 待订正概率场 nc/csv |
| <span style="color:#1677ff;font-weight:600;font-size:16px">reliability_table_paths</span> | 可靠性表路径列表；省略则为 `None`（不订正） |
| <span style="color:#1677ff;font-weight:600;font-size:16px">point_by_point</span> | 是否逐点套表 |
| <span style="color:#1677ff;font-weight:600;font-size:16px">output_path</span> | 订正结果路径；`None` 不写文件 |
| <span style="color:#1677ff;font-weight:400;font-size:16px">return</span> | `int` 退出码（`0` 成功） |

**使用示例**

数据与插件页 Apply 示例相同。本节逻辑：`call` 写订正场 → 读订正前/后 → `print`；作图另块（同一概率色标）。

```python
import meteva_base as meb
from probability_reliability_correction.cli.prb_apply_reliability_calibration import (
    PrbApplyReliabilityCalibrationCli,
)

fc = "resource/cli_input/apply_forecast.nc"
tbl = "resource/cli_input/apply_collapsed_table.nc"
out = "resource/cli_output/demo_calibrated.nc"
rc = PrbApplyReliabilityCalibrationCli.call(
    forecast_path=fc,
    reliability_table_paths=[tbl],
    output_path=out,
)
print(rc)
before = meb.read_griddata_from_nc(fc)
after = meb.read_griddata_from_nc(out)
print(after)
```

```
0
<xarray.DataArray 'probability_of_air_temperature_above_threshold' (member: 1,
                                                                    level: 2,
                                                                    time: 1,
                                                                    dtime: 1,
                                                                    lat: 49,
                                                                    lon: 53)> Size: 21kB
array([[[[[[0.99543023, 0.99543023, 0.99543023, ..., 0.99543023,
            0.99543023, 0.99543023],
           ...,
           [0.99543023, 0.99543023, 0.99543023, ..., 0.00992512,
            0.00992512, 0.00992512]]]],
        [[[[0.99320304, 0.99320304, 0.99320304, ..., 0.99320304,
            0.99320304, 0.99320304],
           ...,
           [0.99320304, 0.99320304, 0.93693244, ..., 0.00724841,
            0.00724841, 0.00724841]]]]]],
      shape=(1, 2, 1, 1, 49, 53), dtype=float32)
Coordinates:
  * level    (level) float32 8B 270.0 275.0
  * time     (time) datetime64[ns] 8B 2019-02-02T22:00:00
  * dtime    (dtime) int32 4B 19
Attributes:
    units:                  1
    relative_to_threshold:  above
```

```python
import matplotlib.pyplot as plt
from meteva_base.tool.plot_tools import pcolormesh_2d_grid

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

PROB_CLEVS = [0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
pcolormesh_2d_grid(
    before.isel(level=0),
    save_path="cli_rel_before.png",
    title="订正前 - 阈值概率",
    clevs=PROB_CLEVS,
    cmap="YlOrRd",
    show=False,
)
pcolormesh_2d_grid(
    after.isel(level=0),
    save_path="cli_rel_after.png",
    title="订正后 - 阈值概率",
    clevs=PROB_CLEVS,
    cmap="YlOrRd",
    show=False,
)
```

订正前：

![CLI可靠性前](https://www.showdoc.com.cn/server/api/attachment/visitFile?sign=f3c9aaffecd3196035fa605f1e5329cd&file=file.png)

订正后：

![CLI可靠性后](https://www.showdoc.com.cn/server/api/attachment/visitFile?sign=a1c9b48c1441c543ea4b4f2ee001fd43&file=file.png)

---

插件说明请见 [probability_reliability_correction](https://www.showdoc.com.cn/2598854776811541/11559060627552423)。
