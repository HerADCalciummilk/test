**基础信息**
- **所属包**: `frequency_matching_rain24`
- **预报类型**: 单来源校准
- **算法类别**: `04single_calibration`
- **正式目录规划**: `NIMM/04single_calibration/frequency_matching_rain24/`
- **对外入口**: `correct_tp_24h.process`、`correct_tp_24h_nowcast.process`
- **CLI 页**: [frequency_matching_rain24](https://www.showdoc.com.cn/2598854776811541/11559060627556649)
- **应用场景**: [预报偏差订正](https://www.showdoc.com.cn/2598854776811541/11559060627556900)

对 24 小时累积降水做相似个例检索、切片光流/平流与 CDF 频率匹配订正，写出 Micaps3/4（或 NC）产品。两条入口参数相同，内部光流与插值实现不同：`correct_tp_24h` 为本包原光流 + 原 Cressman/双线性；`correct_tp_24h_nowcast` 为项目光流 + 项目 Cressman/双线性。调度与读盘细节见 CLI。

**算法功能与流程**

```mermaid
flowchart LR
    IN[模式降水+实况] --> A[correct_tp_24h.process]
    IN --> B[correct_tp_24h_nowcast.process]
    A --> OUT[订正降水产品]
    B --> OUT
```

1. 按起报 × 时效展开任务；非 `None` 的 `process` 参数覆盖 ini，ini 为空再用代码预设。
2. 单任务：加载历史/当前模式与实况 → 相似检索 → 切片光流与频率匹配 → 按 JSON 路径模板写盘。
3. `FrequencyMatch` 等为内部算子，**不是**对外入口；业务请调上述两个 `process`（或 CLI）。

# correct_tp_24h.process

<div style="margin:8px 0;padding:10px 14px;background:#e8f3ff;border-left:4px solid #1677ff;border-radius:4px;overflow-x:auto;"><div style="margin:0;padding:0;background:transparent;border:none;color:#1677ff;font-weight:600;font-size:16px;line-height:1.55;font-family:Consolas,Menlo,Monaco,monospace;white-space:pre;">correct_tp_24h.process(<br>&nbsp;&nbsp;&nbsp;&nbsp;plugin=None,<br>&nbsp;&nbsp;&nbsp;&nbsp;is_multi=None,<br>&nbsp;&nbsp;&nbsp;&nbsp;pro_count=None,<br>&nbsp;&nbsp;&nbsp;&nbsp;rpt_times=None,<br>&nbsp;&nbsp;&nbsp;&nbsp;config=None,<br>&nbsp;&nbsp;&nbsp;&nbsp;default_plugin=None,<br>&nbsp;&nbsp;&nbsp;&nbsp;rpt_list=None,<br>&nbsp;&nbsp;&nbsp;&nbsp;log_file=None,<br>&nbsp;&nbsp;&nbsp;&nbsp;station_info=None,<br>&nbsp;&nbsp;&nbsp;&nbsp;mask_nc=None,<br>&nbsp;&nbsp;&nbsp;&nbsp;ipt_model=None,<br>&nbsp;&nbsp;&nbsp;&nbsp;ipt_obs=None,<br>&nbsp;&nbsp;&nbsp;&nbsp;ipt_type=None,<br>&nbsp;&nbsp;&nbsp;&nbsp;opt_type=None,<br>&nbsp;&nbsp;&nbsp;&nbsp;over_w=None,<br>&nbsp;&nbsp;&nbsp;&nbsp;start_dtime=None,<br>&nbsp;&nbsp;&nbsp;&nbsp;end_dtime=None,<br>&nbsp;&nbsp;&nbsp;&nbsp;inter_dtime1=None,<br>&nbsp;&nbsp;&nbsp;&nbsp;inter_dtime2=None,<br>&nbsp;&nbsp;&nbsp;&nbsp;report_inter=None,<br>&nbsp;&nbsp;&nbsp;&nbsp;res=None,<br>&nbsp;&nbsp;&nbsp;&nbsp;clip_coords=None,<br>)</div></div>

本包原算法入口：`cal_optical_flow` + `interpolation.py` 的 Cressman 与双线性。CLI 默认转调本入口。`plugin` 优先于 `default_plugin`；`rpt_times` 优先于 `rpt_list`。

**构造参数**

| 参数 | 说明 |
| --- | --- |
| 无 | 无额外构造参数（模块级函数） |

**process 参数**

| 参数 | 说明 |
| --- | --- |
| <span style="color:#1677ff;font-weight:600;font-size:16px">plugin</span> | 模式路径 JSON（含 `tp_model` / `tp_obs` / `correct_tp_outpath`）。示例 `resource/ecmwf.json`。`None` 时用 `default_plugin`，再否则 ini |
| <span style="color:#1677ff;font-weight:600;font-size:16px">config</span> | 运行配置 ini；`None` 用 `resource/conf.ini` |
| <span style="color:#1677ff;font-weight:600;font-size:16px">is_multi</span> | 是否多进程并行「起报×时效」。`None` 读 ini（默认 `true`） |
| <span style="color:#1677ff;font-weight:600;font-size:16px">pro_count</span> | 进程数；`None` 读 ini `pro_count`（或旧键 `pool_num`） |
| <span style="color:#1677ff;font-weight:600;font-size:16px">rpt_times</span> | 起报字符串列表；优先于 `rpt_list` |
| <span style="color:#1677ff;font-weight:600;font-size:16px">rpt_list</span> | 起报列表（与 ini 同名）；仅当 `rpt_times` 为 `None` 时采用。1 个值=单时次，2 个值=起止闭区间（按 `report_inter` 展开） |
| <span style="color:#1677ff;font-weight:600;font-size:16px">default_plugin</span> | 覆盖 ini `default_plugin`；仅当 `plugin` 为 `None` 时生效 |
| <span style="color:#1677ff;font-weight:600;font-size:16px">log_file</span> / <span style="color:#1677ff;font-weight:600;font-size:16px">station_info</span> / <span style="color:#1677ff;font-weight:600;font-size:16px">mask_nc</span> | 日志模板、站点表、掩膜 nc；覆盖 ini |
| <span style="color:#1677ff;font-weight:600;font-size:16px">ipt_model</span> / <span style="color:#1677ff;font-weight:600;font-size:16px">ipt_obs</span> | 模式/实况时间类型；覆盖 ini |
| <span style="color:#1677ff;font-weight:600;font-size:16px">ipt_type</span> / <span style="color:#1677ff;font-weight:600;font-size:16px">opt_type</span> | 输入/输出格式（如 `m4`）；覆盖 ini |
| <span style="color:#1677ff;font-weight:600;font-size:16px">over_w</span> | 已有产品是否覆盖；覆盖 ini |
| <span style="color:#1677ff;font-weight:600;font-size:16px">start_dtime</span> / <span style="color:#1677ff;font-weight:600;font-size:16px">end_dtime</span> | 预报时效起止（小时）；覆盖 ini |
| <span style="color:#1677ff;font-weight:600;font-size:16px">inter_dtime1</span> / <span style="color:#1677ff;font-weight:600;font-size:16px">inter_dtime2</span> | 短/长时效步长；覆盖 ini |
| <span style="color:#1677ff;font-weight:600;font-size:16px">report_inter</span> | 起报间隔（小时）；覆盖 ini |
| <span style="color:#1677ff;font-weight:600;font-size:16px">res</span> | 格距（度）；覆盖 ini |
| <span style="color:#1677ff;font-weight:600;font-size:16px">clip_coords</span> | `[slon, elon, slat, elat]`，同时改写外扩边界 |
| <span style="color:#1677ff;font-weight:400;font-size:16px">return</span> | `None`。订正场按 JSON 的 `correct_tp_outpath` 写出（`.m3` / `.m4` 等）；需场对象时再读盘 |

**使用示例**

样例对照场来自包内 `resource/showdoc_demo`（约 0.1°、40×40 强降水子域），展示频率匹配订正前/后量级变化。全量业务需配置 JSON 中的模式/实况路径后调用 `process` 写盘；文档示例用已备好的订正前后场作图，避免并行拉全量历史样本。

```python
import meteva_base as meb
from correct_tp_24h import process

# 业务调度：按起报×时效写盘（路径见 plugin JSON）；全量检索耗内存，正式跑请配好数据
# process(
#     plugin="resource/ecmwf.json",
#     config="resource/conf.ini",
#     rpt_list=["2025100100"],
#     start_dtime=36,
#     end_dtime=36,
#     is_multi=False,
# )

# 读包内示意场，展示订正效果
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
plt.savefig("fm24_compare.png", dpi=120, bbox_inches="tight")
```

订正前 - 24h降水：

![订正前 - 24h降水](https://www.showdoc.com.cn/server/api/attachment/visitFile?sign=298ec97662e4fe402cb6b2befdc0d2d8&file=file.png)

订正后 - 24h降水：

![订正后 - 24h降水](https://www.showdoc.com.cn/server/api/attachment/visitFile?sign=6445fe27b0402e84a6b999426eefbe78&file=file.png)

# correct_tp_24h_nowcast.process

<div style="margin:8px 0;padding:10px 14px;background:#e8f3ff;border-left:4px solid #1677ff;border-radius:4px;overflow-x:auto;"><div style="margin:0;padding:0;background:transparent;border:none;color:#1677ff;font-weight:600;font-size:16px;line-height:1.55;font-family:Consolas,Menlo,Monaco,monospace;white-space:pre;">correct_tp_24h_nowcast.process(<br>&nbsp;&nbsp;&nbsp;&nbsp;plugin=None,<br>&nbsp;&nbsp;&nbsp;&nbsp;is_multi=None,<br>&nbsp;&nbsp;&nbsp;&nbsp;pro_count=None,<br>&nbsp;&nbsp;&nbsp;&nbsp;rpt_times=None,<br>&nbsp;&nbsp;&nbsp;&nbsp;config=None,<br>&nbsp;&nbsp;&nbsp;&nbsp;default_plugin=None,<br>&nbsp;&nbsp;&nbsp;&nbsp;rpt_list=None,<br>&nbsp;&nbsp;&nbsp;&nbsp;log_file=None,<br>&nbsp;&nbsp;&nbsp;&nbsp;station_info=None,<br>&nbsp;&nbsp;&nbsp;&nbsp;mask_nc=None,<br>&nbsp;&nbsp;&nbsp;&nbsp;ipt_model=None,<br>&nbsp;&nbsp;&nbsp;&nbsp;ipt_obs=None,<br>&nbsp;&nbsp;&nbsp;&nbsp;ipt_type=None,<br>&nbsp;&nbsp;&nbsp;&nbsp;opt_type=None,<br>&nbsp;&nbsp;&nbsp;&nbsp;over_w=None,<br>&nbsp;&nbsp;&nbsp;&nbsp;start_dtime=None,<br>&nbsp;&nbsp;&nbsp;&nbsp;end_dtime=None,<br>&nbsp;&nbsp;&nbsp;&nbsp;inter_dtime1=None,<br>&nbsp;&nbsp;&nbsp;&nbsp;inter_dtime2=None,<br>&nbsp;&nbsp;&nbsp;&nbsp;report_inter=None,<br>&nbsp;&nbsp;&nbsp;&nbsp;res=None,<br>&nbsp;&nbsp;&nbsp;&nbsp;clip_coords=None,<br>)</div></div>

项目算法入口：参数表与 `correct_tp_24h.process` **相同**。内部固定使用 `cal_optical_flow_nowcast`、`interpolation_sg_cressman`、`interpolation_gg_linear`。不经默认 CLI；Python 直接 `from correct_tp_24h_nowcast import process`。

**构造参数**

| 参数 | 说明 |
| --- | --- |
| 无 | 无额外构造参数（模块级函数） |

**process 参数**

与上一节 `correct_tp_24h.process` 相同（含 `return`：`None`，产品写盘）。

**使用示例**

调用方式与原入口一致，仅换模块；订正前后对照图同上一节（示意场相同）。

```python
from correct_tp_24h_nowcast import process

# process(plugin="resource/ecmwf.json", is_multi=False, rpt_list=["2025100100"], start_dtime=36, end_dtime=36)
```

---

算法 CLI 使用说明请见 [frequency_matching_rain24](https://www.showdoc.com.cn/2598854776811541/11559060627556649)。
