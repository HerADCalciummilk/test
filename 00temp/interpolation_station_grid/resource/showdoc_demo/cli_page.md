**基础信息**
- **所属包**: `interpolation_station_grid`
- **插件页**: [interpolation_station_grid](https://www.showdoc.com.cn/2598854776811541/11559060627552458)
- **调度脚本**: `cli/interpolation_station_grid_cli.py`

本页是 CLI 使用说明；算法参数见插件页。样例为包内阵风站点 + `bg_fcst_idw` 背景（约 0.1°）。本包以单次 `--module` 调用为主，无批量调度节。

**参数优先级**（由高到低）：**显式传入**（命令行 flag / `InterpolationStationGridCli.call(...)`）**>** **配置文件参数**（ini 非空项）**>** 代码预设默认值。空 ini 项不覆盖上层已给出的值。

**怎么跑**

（发版环境：本包已可导入。）

```bash
python -m cli --help

# 无 [] = 必填；[] 内 = 可选
# --grid 与 --background 至少其一；--reprocess true / idw_delta 时须 --background
python -m cli \
  --module {idw|idw_delta|gaussian|kriging|cressman} \
  --sta PATH [--grid PATH] [--background PATH] \
  [--reprocess true|false] [--output PATH] \
  [--effect-r N] [--near-num N] [--decrease N] \
  [--half-r N] [--r-list R1,R2,...] \
  [--kriging-model spherical|exponential|gaussian] \
  [--kriging-sill N] [--kriging-range N] [--kriging-nugget N] \
  [--sta-type csv|m3] [--grid-type nc|m4] [--config PATH]

# 等价：直接跑脚本
python cli/interpolation_station_grid_cli.py --module idw --sta PATH --background PATH --reprocess true --output out.nc
```

`--module` 省略则读 ini，预设 `idw`（`total` 为 `idw` 旧别名）。`--sta` 必填；`--grid` / `--background` 至少其一。有 `--output`（或 ini `path`）则写格点 nc/m4；否则只 `print` 结果。Python 对外为 `InterpolationStationGridCli.call`（返回退出码）。

| 子命令 | 脚本 | 说明 |
| --- | --- | --- |
| 无（flag `--module`） | `cli/interpolation_station_grid_cli.py` | `idw` / `idw_delta` / `gaussian` / `kriging` / `cressman`；`python -m cli` |

# interpolation_station_grid_cli

**调用插件**: `InterpSgIdw` / `InterpSgGaussian` / `InterpSgKriging` / `InterpSgCressman`（由 `--module` 选择）

对外 Python 入口为 `InterpolationStationGridCli.call`（关键字与 flag 同名）。未传入的可选项为 `None`，按参数优先级回落。

<div style="margin:8px 0;padding:10px 14px;background:#e8f3ff;border-left:4px solid #1677ff;border-radius:4px;overflow-x:auto;"><div style="margin:0;padding:0;background:transparent;border:none;color:#1677ff;font-weight:600;font-size:16px;line-height:1.55;font-family:Consolas,Menlo,Monaco,monospace;white-space:pre;">InterpolationStationGridCli.call(<br>&nbsp;&nbsp;&nbsp;&nbsp;module=None,<br>&nbsp;&nbsp;&nbsp;&nbsp;sta=None,<br>&nbsp;&nbsp;&nbsp;&nbsp;grid=None,<br>&nbsp;&nbsp;&nbsp;&nbsp;background=None,<br>&nbsp;&nbsp;&nbsp;&nbsp;reprocess=None,<br>&nbsp;&nbsp;&nbsp;&nbsp;sta_type=None,<br>&nbsp;&nbsp;&nbsp;&nbsp;grid_type=None,<br>&nbsp;&nbsp;&nbsp;&nbsp;background_type=None,<br>&nbsp;&nbsp;&nbsp;&nbsp;output=None,<br>&nbsp;&nbsp;&nbsp;&nbsp;output_type=None,<br>&nbsp;&nbsp;&nbsp;&nbsp;effect_r=None,<br>&nbsp;&nbsp;&nbsp;&nbsp;near_num=None,<br>&nbsp;&nbsp;&nbsp;&nbsp;decrease=None,<br>&nbsp;&nbsp;&nbsp;&nbsp;half_r=None,<br>&nbsp;&nbsp;&nbsp;&nbsp;r_list=None,<br>&nbsp;&nbsp;&nbsp;&nbsp;kriging_model=None,<br>&nbsp;&nbsp;&nbsp;&nbsp;kriging_sill=None,<br>&nbsp;&nbsp;&nbsp;&nbsp;kriging_range=None,<br>&nbsp;&nbsp;&nbsp;&nbsp;kriging_nugget=None,<br>&nbsp;&nbsp;&nbsp;&nbsp;config=None,<br>)</div></div>

| 参数 | 说明 |
| --- | --- |
| <span style="color:#1677ff;font-weight:600;font-size:16px">module</span> | 选择插值算法：`idw` / `idw_delta` / `gaussian` / `kriging` / `cressman`；`total` 为 `idw` 旧别名。省略读 ini，预设 `idw` |
| <span style="color:#1677ff;font-weight:600;font-size:16px">sta</span> | 输入**站点场**路径（csv/m3，`--sta`）。读入后交给插件作观测源；必填（或由 ini 提供） |
| <span style="color:#1677ff;font-weight:600;font-size:16px">grid</span> | 输入格点文件路径（nc/m4，`--grid`）。CLI **只取网格信息**传给插件，场值不参与插值。可与 `background` 二选一以提供网格；两者都缺则报错 |
| <span style="color:#1677ff;font-weight:600;font-size:16px">background</span> | 输入**背景格点场**路径（nc/m4）。`reprocess=true` / `idw_delta` 时必需。`false` 时：IDW/Gaussian/Cressman 作远点填充或初场，Kriging 仅在缺 `grid` 时取网格。无 `grid` 时也可单独提供网格 |
| <span style="color:#1677ff;font-weight:600;font-size:16px">reprocess</span> | `false`：直接用站点值插值；`true`：先算站点与背景场的偏差再对偏差插值（透传插件；`idw_delta` 强制 `true`） |
| <span style="color:#1677ff;font-weight:600;font-size:16px">output</span> | 可选输出格点路径；给出则写 nc/m4。`call` 只返回退出码，需要场对象时再读该文件；省略则仅 `print` |
| <span style="color:#1677ff;font-weight:600;font-size:16px">effect_r</span> / <span style="color:#1677ff;font-weight:600;font-size:16px">near_num</span> / <span style="color:#1677ff;font-weight:600;font-size:16px">decrease</span> | IDW / 克里金近邻等 |
| <span style="color:#1677ff;font-weight:600;font-size:16px">half_r</span> | 仅 `gaussian` |
| <span style="color:#1677ff;font-weight:600;font-size:16px">r_list</span> | 仅 `cressman`，逗号分隔（米；`reprocess=true` 时为度） |
| <span style="color:#1677ff;font-weight:600;font-size:16px">kriging_&#42;</span> | 仅 `kriging`：变异函数 / 基台 / 变程 / 块金 |
| <span style="color:#1677ff;font-weight:600;font-size:16px">sta_type</span> / <span style="color:#1677ff;font-weight:600;font-size:16px">grid_type</span> / <span style="color:#1677ff;font-weight:600;font-size:16px">background_type</span> / <span style="color:#1677ff;font-weight:600;font-size:16px">output_type</span> | 格式；省略按扩展名 |
| <span style="color:#1677ff;font-weight:600;font-size:16px">config</span> | 运行配置 ini |
| <span style="color:#1677ff;font-weight:400;font-size:16px">return</span> | `int` 退出码（`0` 成功）。场写入 `output`（若给定）；需要 `DataArray` 时再读该 nc |

说明：`idw_delta` = `InterpSgIdw(gaussian=True, reprocess=True)`，须 `--background`（不再把 `--grid` 当背景场）。普通 `idw` 是否偏差订正仅由 `--reprocess` 控制，**不会**因有背景自动改成高斯×偏差。

**使用示例**

包内真实样例：站点 `resource/obs_gust_d24.csv`、目标网格 `resource/target_grid.nc`、背景 `resource/bg_fcst_idw.nc`。`call` 写盘后再读场；展示输入站点与 **订正前/订正后** 对照（共用 `wind_speed` 色标）。

```python
from pathlib import Path
import matplotlib.pyplot as plt
import meteva_base as meb
import numpy as np
from meteva_base.tool.color_tools import get_cmap_and_clevs_by_element_name
from cli.interpolation_station_grid_cli import InterpolationStationGridCli

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

PKG = Path("interpolation_station_grid/resource")
DEMO = PKG / "showdoc_demo"
sta_path = str(PKG / "obs_gust_d24.csv")
grid_path = str(PKG / "target_grid.nc")
bg_path = str(PKG / "bg_fcst_idw.nc")
out_path = str(DEMO / "cli_idw_bg_out.nc")

# 调度写盘：IDW 偏差订正
rc = InterpolationStationGridCli.call(
    module="idw",
    sta=sta_path,
    grid=grid_path,
    background=bg_path,
    reprocess="true",
    output=out_path,
    effect_r=150000,
    near_num=8,
    decrease=2,
    sta_type="csv",
    grid_type="nc",
    background_type="nc",
    output_type="nc",
)

# 读出场结果
grd = meb.read_griddata_from_nc(out_path)
print(f"exit {rc}")
print(grd)
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
    units:               
    model_var:           
    dtime_units:         hour
    level_type:          isobaric
    time_type:           UT
    time_bounds:         [np.int64(0), np.int64(0)]
    data_start_columns:  6
```

```python
bg = meb.read_griddata_from_nc(bg_path)
obs = meb.read_stadata_from_csv(sta_path)
cmap, clevs = get_cmap_and_clevs_by_element_name("wind_speed")
clevs = np.asarray(clevs, dtype=float)
map_extend = [float(bg.lon.min()), float(bg.lon.max()), float(bg.lat.min()), float(bg.lat.max())]

# 输入站点
axs = meb.creat_axs(1, map_extend, ncol=1, height=6.5, width=12, dpi=120,
                    title_list=["输入-站点阵风 obs_gust"])
meb.add_scatter(axs[0], obs, cmap=cmap, clevs=clevs, point_size=28, add_colorbar=True,
                title="输入-站点阵风 obs_gust", title_fontsize=12)
plt.savefig("cli_obs_sta.png", dpi=120, bbox_inches="tight"); plt.close("all")

# 订正前 / 订正后对照（同一色标）
axs = meb.creat_axs(
    2, map_extend, ncol=2, add_index=True, add_worldmap=False,
    title_list=["订正前-背景场", "订正后-CLI InterpSgIdw"],
)
meb.add_contourf(axs[0], bg, cmap=cmap, clevs=clevs, cut_colorbar=False, add_colorbar=True)
meb.add_contourf(axs[1], grd, cmap=cmap, clevs=clevs, cut_colorbar=False, add_colorbar=True)
axs[0].set_title("订正前-背景场")
axs[1].set_title("订正后-CLI InterpSgIdw")
plt.savefig("cli_compare.png", dpi=120, bbox_inches="tight"); plt.close("all")
```

![输入-站点阵风](https://www.showdoc.com.cn/server/api/attachment/visitFile?sign=3954ae98c0bf50869a8984a7c4f959bf&file=file.png)

![订正前-背景场 / 订正后-CLI](https://www.showdoc.com.cn/server/api/attachment/visitFile?sign=4f54fdcf926fc824bc596f12565411cf&file=file.png)

---

插件说明请见 [interpolation_station_grid](https://www.showdoc.com.cn/2598854776811541/11559060627552458)。
