**基础信息**
- **所属包**: `interpolation_station_grid`
- **插件页**: [interpolation_station_grid](https://www.showdoc.com.cn/2598854776811541/11559060627552458)
- **调度脚本**: `cli/interpolation_station_grid_cli.py`

本页是 CLI 使用说明；算法参数见插件页。样例为包内阵风站点 + `fcst_wind` IDW 背景（约 0.1°）。本包以单次 `--module` 调用为主。

**参数优先级**（由高到低）：**显式传入**（命令行 flag / `InterpolationStationGridCli.call(...)`）**>** **配置文件参数**（ini 非空项）**>** 代码预设默认值。空 ini 项不覆盖上层已给出的值。

**怎么跑**

（发版环境：本包已可导入。）

```bash
python -m cli --help

# 无 [] = 必填；[] 内 = 可选
python -m cli \
  --module {idw|idw_delta|gaussian|kriging|cressman} \
  --sta PATH --grid PATH \
  [--background PATH] [--output PATH] \
  [--effect-r N] [--near-num N] [--decrease N] \
  [--half-r N] [--r-list R1,R2,...] \
  [--kriging-model spherical|exponential|gaussian] \
  [--kriging-sill N] [--kriging-range N] [--kriging-nugget N] \
  [--sta-type csv|m3] [--grid-type nc|m4] [--config PATH]

# 等价：直接跑脚本
python cli/interpolation_station_grid_cli.py --module idw --sta PATH --grid PATH --output out.nc
```

`--module` 省略则读 ini，预设 `idw`（`total` 为 `idw` 旧别名）。`--sta` / `--grid` 省略读 ini，空则报错。有 `--output`（或 ini `path`）则写格点 nc/m4；否则只 `print` 结果。Python 对外为 `InterpolationStationGridCli.call`（返回退出码）。

| 子命令 | 脚本 | 说明 |
| --- | --- | --- |
| 无（flag `--module`） | `cli/interpolation_station_grid_cli.py` | `idw` / `idw_delta` / `gaussian` / `kriging` / `cressman`；`python -m cli` |

# interpolation_station_grid_cli

**调用插件**: `InterpSgIdw` / `InterpSgGaussian` / `InterpSgKriging` / `InterpSgCressman`（由 `--module` 选择）

<div style="margin:8px 0;padding:10px 14px;background:#e8f3ff;border-left:4px solid #1677ff;border-radius:4px;overflow-x:auto;"><div style="margin:0;padding:0;background:transparent;border:none;color:#1677ff;font-weight:600;font-size:16px;line-height:1.55;font-family:Consolas,Menlo,Monaco,monospace;white-space:pre;">InterpolationStationGridCli.call(<br>&nbsp;&nbsp;&nbsp;&nbsp;module=None,<br>&nbsp;&nbsp;&nbsp;&nbsp;sta=None,<br>&nbsp;&nbsp;&nbsp;&nbsp;grid=None,<br>&nbsp;&nbsp;&nbsp;&nbsp;background=None,<br>&nbsp;&nbsp;&nbsp;&nbsp;sta_type=None,<br>&nbsp;&nbsp;&nbsp;&nbsp;grid_type=None,<br>&nbsp;&nbsp;&nbsp;&nbsp;background_type=None,<br>&nbsp;&nbsp;&nbsp;&nbsp;output=None,<br>&nbsp;&nbsp;&nbsp;&nbsp;output_type=None,<br>&nbsp;&nbsp;&nbsp;&nbsp;effect_r=None,<br>&nbsp;&nbsp;&nbsp;&nbsp;near_num=None,<br>&nbsp;&nbsp;&nbsp;&nbsp;decrease=None,<br>&nbsp;&nbsp;&nbsp;&nbsp;half_r=None,<br>&nbsp;&nbsp;&nbsp;&nbsp;r_list=None,<br>&nbsp;&nbsp;&nbsp;&nbsp;kriging_model=None,<br>&nbsp;&nbsp;&nbsp;&nbsp;kriging_sill=None,<br>&nbsp;&nbsp;&nbsp;&nbsp;kriging_range=None,<br>&nbsp;&nbsp;&nbsp;&nbsp;kriging_nugget=None,<br>&nbsp;&nbsp;&nbsp;&nbsp;config=None,<br>)</div></div>

| 参数 | 说明 |
| --- | --- |
| <span style="color:#1677ff;font-weight:600;font-size:16px">module</span> | `idw` / `idw_delta` / `gaussian` / `kriging` / `cressman`；`total`=`idw` 旧别名；省略读 ini，预设 `idw` |
| <span style="color:#1677ff;font-weight:600;font-size:16px">sta</span> | 站点 csv/m3（`--sta`） |
| <span style="color:#1677ff;font-weight:600;font-size:16px">grid</span> | 格点 nc/m4：取目标网格；`idw_delta` 同时作背景场（`--grid`） |
| <span style="color:#1677ff;font-weight:600;font-size:16px">background</span> | 可选背景 nc/m4；`idw`/`gaussian`/`kriging` 偏差订正，`cressman` 初估场 |
| <span style="color:#1677ff;font-weight:600;font-size:16px">output</span> | 可选输出路径；给出则写 nc/m4，需要场对象时再读该文件 |
| <span style="color:#1677ff;font-weight:600;font-size:16px">effect_r</span> / <span style="color:#1677ff;font-weight:600;font-size:16px">near_num</span> / <span style="color:#1677ff;font-weight:600;font-size:16px">decrease</span> | IDW / 克里金近邻等 |
| <span style="color:#1677ff;font-weight:600;font-size:16px">half_r</span> | 仅 `gaussian` |
| <span style="color:#1677ff;font-weight:600;font-size:16px">r_list</span> | 仅 `cressman`，逗号分隔半径（米） |
| <span style="color:#1677ff;font-weight:600;font-size:16px">kriging_&#42;</span> | 仅 `kriging`：变异函数 / 基台 / 变程 / 块金 |
| <span style="color:#1677ff;font-weight:600;font-size:16px">sta_type</span> / <span style="color:#1677ff;font-weight:600;font-size:16px">grid_type</span> / <span style="color:#1677ff;font-weight:600;font-size:16px">background_type</span> / <span style="color:#1677ff;font-weight:600;font-size:16px">output_type</span> | 格式；省略按扩展名 |
| <span style="color:#1677ff;font-weight:600;font-size:16px">config</span> | 运行配置 ini |
| <span style="color:#1677ff;font-weight:400;font-size:16px">return</span> | `int` 退出码（`0` 成功）。场写入 `output`（若给定）；需要 `DataArray` 时再读该 nc |

说明：`module=idw` 且提供 `background` 时，CLI 内部会设 `gaussian=True`（IDW×高斯偏差订正）。`idw_delta` 固定 `gaussian=True`，并以 `--grid` 为背景。

**使用示例**

包内真实样例：站点 `resource/obs_gust_d24.csv`、目标网格 `resource/target_grid.nc`、背景 `resource/showdoc_demo/bg_fcst_idw.nc`（由 `fcst_wind` IDW 得到）。`call` 写盘后再读场，订正前/后共用预置 `wind_speed` 色标。

```python
from pathlib import Path
import matplotlib.pyplot as plt
import meteva_base as meb
from meteva_base.tool.color_tools import get_cmap_and_clevs_by_element_name
from meteva_base.tool.plot_tools import pcolormesh_2d_grid
from cli.interpolation_station_grid_cli import InterpolationStationGridCli

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

PKG = Path("interpolation_station_grid/resource")
DEMO = PKG / "showdoc_demo"
sta_path = str(PKG / "obs_gust_d24.csv")
grid_path = str(PKG / "target_grid.nc")
bg_path = str(DEMO / "bg_fcst_idw.nc")
out_path = str(DEMO / "cli_idw_bg_out.nc")

# 1) CLI 调度写盘（有背景 → InterpSgIdw + 高斯偏差订正）
rc = InterpolationStationGridCli.call(
    module="idw",
    sta=sta_path,
    grid=grid_path,
    background=bg_path,
    output=out_path,
    effect_r=150000,
    near_num=8,
    decrease=2,
    sta_type="csv",
    grid_type="nc",
    background_type="nc",
    output_type="nc",
)
print("exit", rc)

# 2) 读出场作图
bg = meb.read_griddata_from_nc(bg_path)
grd = meb.read_griddata_from_nc(out_path)
print(grd)

cmap, clevs = get_cmap_and_clevs_by_element_name("wind_speed")
pcolormesh_2d_grid(
    bg, save_path="cli_before.png", title="订正前-背景场",
    cmap=cmap, clevs=clevs, show=False,
)
pcolormesh_2d_grid(
    grd, save_path="cli_after.png", title="订正后-CLI InterpSgIdw",
    cmap=cmap, clevs=clevs, show=False,
)
```

```
exit 0
<xarray.DataArray 'data0' (member: 1, level: 1, time: 1, dtime: 1, lat: 71,
                           lon: 210)> Size: 60kB
array([[[[[[14.653, 13.959, 13.871, ..., 12.191, 12.223, 12.262],
           [14.89 , 14.231, 14.153, ..., 12.085, 12.125, 12.173],
           [15.166, 15.117, 14.501, ..., 11.965, 12.015, 12.073],
           ...,
           [14.582, 14.639, 14.711, ..., 15.565, 15.692, 15.815],
           [14.636, 15.338, 15.363, ..., 15.811, 15.893, 15.981],
           [15.458, 15.474, 15.503, ..., 16.033, 16.084, 16.142]]]]]],
      shape=(1, 1, 1, 1, 71, 210), dtype=float32)
Coordinates:
  * member   (member) <U5 20B 'data0'
  * level    (level) float32 4B 0.0
  * time     (time) datetime64[ns] 8B 2026-06-02
  * dtime    (dtime) int32 4B 24
  * lat      (lat) float64 568B 31.54 31.64 31.74 31.84 ... 38.34 38.44 38.54
  * lon      (lon) float64 2kB 99.6 99.7 99.8 99.9 ... 120.2 120.3 120.4 120.5
Attributes:
    dtime_units:         hour
    level_type:          isobaric
    time_type:           UT
    time_bounds:         [np.int64(0), np.int64(0)]
    data_start_columns:  6
```

![订正前-背景场](__URL_cli_before__)

![订正后-CLI InterpSgIdw](__URL_cli_after__)

---

插件说明请见 [interpolation_station_grid](https://www.showdoc.com.cn/2598854776811541/11559060627552458)。
