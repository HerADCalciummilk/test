**基础信息**
- **所属包**: `frequency_matching_rain24`
- **插件页**: [frequency_matching_rain24](https://www.showdoc.com.cn/2598854776811541/11559060627552472)
- **调度脚本**: `cli/frequency_matching_rain24_cli.py`

本页是 CLI 使用说明。算法参数与两条 `process` 入口见插件页。命令行固定转调 `correct_tp_24h.process`（原光流 + 原 Cressman）；项目光流/Cressman 请用 `correct_tp_24h_nowcast.process`。支持多起报批量（`--is-multi`）。示例对照图与插件页同套 `resource/showdoc_demo`。

**参数优先级**（由高到低）：**显式传入**（命令行 flag / `FrequencyMatchingRain24Cli.call(...)`）**>** **配置文件参数**（ini 非空项）**>** 代码预设默认值。空 ini 项不覆盖上层已给出的值。

**怎么跑**

（发版环境：本包已可导入。在包根目录执行。）

```bash
python -m cli --help

# 必填无方括号；可选写在 [] 内
python -m cli \
  [--plugin PATH] [--config PATH] [--rpt-list YYYYMMDDHH[,...]] \
  [--is-multi true|false] [--pro-count N] \
  [--start-dtime N] [--end-dtime N] [--clip-coords SLON,ELON,SLAT,ELAT]

# 等价：直接跑脚本
python cli/frequency_matching_rain24_cli.py --plugin=resource/CMA_MESO.json
```

省略 `--plugin` 时用配置 ini 的 `default_plugin`。起报未指定则用 ini 的 `rpt_list`（空表示实时）。Python 对外为 `FrequencyMatchingRain24Cli.call`（返回退出码）。

| 子命令 | 脚本 | 说明 |
| --- | --- | --- |
| 无 | `cli/frequency_matching_rain24_cli.py` | 24h 降水频率匹配调度；`python -m cli` |

# frequency_matching_rain24_cli.py

**调用插件**: `correct_tp_24h.process`

对外 Python 入口为 `FrequencyMatchingRain24Cli.call`（关键字与 flag 同名）。未传入的可选项为 `None`，按参数优先级回落。

<div style="margin:8px 0;padding:10px 14px;background:#e8f3ff;border-left:4px solid #1677ff;border-radius:4px;overflow-x:auto;"><div style="margin:0;padding:0;background:transparent;border:none;color:#1677ff;font-weight:600;font-size:16px;line-height:1.55;font-family:Consolas,Menlo,Monaco,monospace;white-space:pre;">FrequencyMatchingRain24Cli.call(<br>&nbsp;&nbsp;&nbsp;&nbsp;plugin=None,<br>&nbsp;&nbsp;&nbsp;&nbsp;config=None,<br>&nbsp;&nbsp;&nbsp;&nbsp;rpt_list=None,<br>&nbsp;&nbsp;&nbsp;&nbsp;is_multi=None,<br>&nbsp;&nbsp;&nbsp;&nbsp;pro_count=None,<br>&nbsp;&nbsp;&nbsp;&nbsp;default_plugin=None,<br>&nbsp;&nbsp;&nbsp;&nbsp;log_file=None,<br>&nbsp;&nbsp;&nbsp;&nbsp;station_info=None,<br>&nbsp;&nbsp;&nbsp;&nbsp;mask_nc=None,<br>&nbsp;&nbsp;&nbsp;&nbsp;ipt_model=None,<br>&nbsp;&nbsp;&nbsp;&nbsp;ipt_obs=None,<br>&nbsp;&nbsp;&nbsp;&nbsp;ipt_type=None,<br>&nbsp;&nbsp;&nbsp;&nbsp;opt_type=None,<br>&nbsp;&nbsp;&nbsp;&nbsp;over_w=None,<br>&nbsp;&nbsp;&nbsp;&nbsp;start_dtime=None,<br>&nbsp;&nbsp;&nbsp;&nbsp;end_dtime=None,<br>&nbsp;&nbsp;&nbsp;&nbsp;inter_dtime1=None,<br>&nbsp;&nbsp;&nbsp;&nbsp;inter_dtime2=None,<br>&nbsp;&nbsp;&nbsp;&nbsp;report_inter=None,<br>&nbsp;&nbsp;&nbsp;&nbsp;res=None,<br>&nbsp;&nbsp;&nbsp;&nbsp;clip_coords=None,<br>)</div></div>

| 参数 | 说明 |
| --- | --- |
| <span style="color:#1677ff;font-weight:600;font-size:16px">plugin</span> | 模式路径 JSON（`--plugin`）。省略则用 ini `default_plugin` |
| <span style="color:#1677ff;font-weight:600;font-size:16px">config</span> | 运行配置 ini（`--config`）；省略则 `resource/conf.ini` |
| <span style="color:#1677ff;font-weight:600;font-size:16px">rpt_list</span> | 起报列表，逗号分隔（`--rpt-list`）；传给 `process` 的 `rpt_list` |
| <span style="color:#1677ff;font-weight:600;font-size:16px">is_multi</span> | 是否多进程（`--is-multi`）；省略读 ini |
| <span style="color:#1677ff;font-weight:600;font-size:16px">pro_count</span> | 进程数（`--pro-count`）；仅 `is_multi=true` 时生效 |
| <span style="color:#1677ff;font-weight:600;font-size:16px">default_plugin</span> / <span style="color:#1677ff;font-weight:600;font-size:16px">log_file</span> / <span style="color:#1677ff;font-weight:600;font-size:16px">station_info</span> / <span style="color:#1677ff;font-weight:600;font-size:16px">mask_nc</span> | 覆盖 ini 同名项 |
| <span style="color:#1677ff;font-weight:600;font-size:16px">ipt_model</span> / <span style="color:#1677ff;font-weight:600;font-size:16px">ipt_obs</span> / <span style="color:#1677ff;font-weight:600;font-size:16px">ipt_type</span> / <span style="color:#1677ff;font-weight:600;font-size:16px">opt_type</span> / <span style="color:#1677ff;font-weight:600;font-size:16px">over_w</span> | 时间类型、格式、覆盖开关；覆盖 ini |
| <span style="color:#1677ff;font-weight:600;font-size:16px">start_dtime</span> / <span style="color:#1677ff;font-weight:600;font-size:16px">end_dtime</span> / <span style="color:#1677ff;font-weight:600;font-size:16px">inter_dtime1</span> / <span style="color:#1677ff;font-weight:600;font-size:16px">inter_dtime2</span> / <span style="color:#1677ff;font-weight:600;font-size:16px">report_inter</span> | 时效与起报间隔；覆盖 ini |
| <span style="color:#1677ff;font-weight:600;font-size:16px">res</span> | 格距（度）；覆盖 ini |
| <span style="color:#1677ff;font-weight:600;font-size:16px">clip_coords</span> | `slon,elon,slat,elat`；覆盖 ini |
| <span style="color:#1677ff;font-weight:400;font-size:16px">return</span> | `int` 退出码（`0` 成功）。产品按 plugin JSON 的 `correct_tp_outpath` 写出；需要场时再读盘 |

**使用示例**

调度写出业务产品后可读输出场作图。下列对照复用 `resource/showdoc_demo` 订正前/后场（与插件页同套），色标 `rain_24h`。全量历史检索耗内存，正式跑请先配好模式/实况路径。

```python
import meteva_base as meb
from cli.frequency_matching_rain24_cli import FrequencyMatchingRain24Cli

# 调度写盘（转调 correct_tp_24h.process）
# code = FrequencyMatchingRain24Cli.call(
#     plugin="resource/ecmwf.json",
#     config="resource/conf.ini",
#     rpt_list=["2025100100"],
#     start_dtime=36,
#     end_dtime=36,
#     is_multi=False,
# )
# print(code)

before = meb.read_griddata_from_nc("resource/showdoc_demo/before.nc")
after = meb.read_griddata_from_nc("resource/showdoc_demo/after.nc")
print(after)
```

```
<xarray.DataArray 'data0' (member: 1, level: 1, time: 1, dtime: 1, lat: 40,
                           lon: 40)> Size: 6kB
array([[[[[[ 2.834,  2.935,  2.935, ..., 13.819, 14.128, 14.334],
           [ 2.52 ,  2.625,  2.625, ..., 14.025, 14.334, 14.541],
           [ 2.31 ,  2.31 ,  2.31 , ..., 14.334, 14.747, 15.056],
           ...,
           [35.333, 40.077, 46.406, ..., 97.559, 96.187, 94.922],
           [36.303, 41.155, 48.199, ..., 92.18 , 91.336, 90.809],
           [37.166, 42.233, 49.781, ..., 87.645, 87.434, 87.434]]]]]],
      shape=(1, 1, 1, 1, 40, 40), dtype=float32)
Coordinates:
  * member   (member) <U5 20B 'data0'
  * level    (level) float32 4B 0.0
  * time     (time) datetime64[ns] 8B 2020-01-01
  * dtime    (dtime) int32 4B 0
  * lat      (lat) float64 320B 14.0 14.1 14.2 14.3 14.4 ... 17.6 17.7 17.8 17.9
  * lon      (lon) float64 320B 115.0 115.1 115.2 115.3 ... 118.7 118.8 118.9
Attributes:
    units:        
    model_var:    
    dtime_units:  hour
    level_type:   isobaric
    time_type:    UT
    time_bounds:  [np.int64(0), np.int64(0)]
before max=205.6500 mean=68.7465
after  max=144.5980 mean=48.1933
delta mean=-20.5532
```

```python
import matplotlib.pyplot as plt
import meteva_base as meb
from meteva_base.tool.color_tools import get_cmap_and_clevs_by_element_name

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

cmap, clevs = get_cmap_and_clevs_by_element_name("rain_24h")
grid = meb.get_grid_of_data(before)
map_extend = [float(grid.slon), float(grid.elon), float(grid.slat), float(grid.elat)]
axs = meb.creat_axs(
    2, map_extend, ncol=2,
    title_list=["订正前 - 24h降水", "订正后 - 24h降水"],
    add_worldmap=False, add_index=True, wspace=0.25, width=12,
)
meb.add_contourf(axs[0], before, cmap=cmap, clevs=clevs, cut_colorbar=False, add_colorbar=True)
meb.add_contourf(axs[1], after, cmap=cmap, clevs=clevs, cut_colorbar=False, add_colorbar=True)
plt.savefig("fm24_cli_compare.png", dpi=120, bbox_inches="tight")
```

订正前：

![订正前 - 24h降水](https://www.showdoc.com.cn/server/api/attachment/visitFile?sign=3d06c872e25b40776929d7ca7a1dcb78&file=file.png)

订正后：

![订正后 - 24h降水](https://www.showdoc.com.cn/server/api/attachment/visitFile?sign=55cb4afd49f6f62e28ffea6d2a124277&file=file.png)

# 批量调度示例

```python
from cli.frequency_matching_rain24_cli import FrequencyMatchingRain24Cli

# 多起报闭区间；注意内存，正式环境可按需开 is_multi
code = FrequencyMatchingRain24Cli.call(
    plugin="resource/ecmwf.json",
    config="resource/conf.ini",
    rpt_list=["2025100100", "2025100112"],
    is_multi=False,
)
print(code)
```

项目光流入口不经本 CLI，请：

```python
from correct_tp_24h_nowcast import process
process(plugin="resource/ecmwf.json", is_multi=False, rpt_list=["2025100100"])
```

---

插件说明请见 [frequency_matching_rain24](https://www.showdoc.com.cn/2598854776811541/11559060627552472)。
